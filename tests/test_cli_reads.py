"""`inbox`, `cards` and `ask`: compact output, session-keyed cursors, one
batch call per round.
"""

import http.server
import json
import threading
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.sync_server import make_handler


def _slug(tmp_path):
    slug_dir = tmp_path / "pages" / "demo"
    slug_dir.mkdir(parents=True)
    (slug_dir / "comments.json").write_text(json.dumps({
        "schema_version": 2,
        "anchors": {
            "s:a": [{"id": "aaaaaaaaaaaa", "anchor_id": "s:a", "text": "Rename status?", "status": "open",
                     "version": "v1", "decision_request": {"prompt": "Rename status?"},
                     "decision": {"verdict": "accept", "text": None, "ts": "2026-09-17T10:00:00Z", "by": "r@x"}}],
            "s:b": [{"id": "bbbbbbbbbbbb", "anchor_id": "s:b", "text": "Drop column?", "status": "open",
                     "version": "v1", "decision_request": {"prompt": "Drop column?"}}],
        },
        "archived": {},
    }))
    (slug_dir / "current.meta.json").write_text(json.dumps({"current": "v1", "history": []}))
    return slug_dir


@pytest.fixture
def registry(tmp_path, monkeypatch):
    slug_dir = _slug(tmp_path)
    bus_dir = tmp_path / "bus" / "proj"
    bus_dir.mkdir(parents=True)
    bus = bus_dir / "demo.ndjson"
    events = [
        {"ts": "2026-09-17T09:00:00Z", "event": "comment_created", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "agent:test", "version": "v1"},
        {"ts": "2026-09-17T09:00:01Z", "event": "seen_updated", "slug": "demo", "author": "r@x"},
        {"ts": "2026-09-17T10:00:00Z", "event": "comment_updated", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "r@x", "decision": "accept",
         "old_status": "open", "new_status": "user_confirmed"},
    ]
    bus.write_text("".join(json.dumps(e) + "\n" for e in events))
    record = {"slug": "demo", "slug_dir": str(slug_dir), "project": "proj", "pid": 0, "port": 8899,
              "local_url": "http://localhost:8899/", "bus_file": str(bus), "owner_session": "sess-owner"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("proj", "demo", record)])
    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", tmp_path / "state" / "bus-offsets")
    return SimpleNamespace(slug_dir=slug_dir, bus=bus, record=record)


def _inbox(**over):
    base = dict(slug="demo", project=None, unread=False, json=False, all_events=False)
    base.update(over)
    return SimpleNamespace(**base)


def test_inbox_is_compact_and_hides_bookkeeping(registry, capsys):
    assert cli.cmd_inbox(_inbox()) == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 3  # two events + summary; seen_updated hidden
    assert "seen_updated" not in out
    assert "comment_created" in lines[0] and "aaaaaaaaaa" in lines[0] and "Rename status?" in lines[0]
    assert "comment_updated" in lines[1] and "accept" in lines[1]
    assert lines[2].strip() == (
        "decisions: 1 accept, 0 reject, 0 changes, 0 select, 0 comment; undecided: s:b")


def test_inbox_all_events_shows_bookkeeping(registry, capsys):
    cli.cmd_inbox(_inbox(all_events=True))
    assert "seen_updated" in capsys.readouterr().out


def test_inbox_json_keeps_raw_events(registry, capsys):
    cli.cmd_inbox(_inbox(json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["event_count"] == 2
    assert payload["decisions"] == {
        "accept": 1, "reject": 0, "changes": 0, "comment": 0, "select": 0}
    assert payload["undecided"] == ["s:b"]
    assert payload["events"][0]["event"] == "comment_created"


def test_unread_cursor_is_per_session(registry, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-one")
    cli.cmd_inbox(_inbox(unread=True))
    first = capsys.readouterr().out
    assert "comment_updated" in first
    cursor = cli.BUS_OFFSET_ROOT / "sess-one" / "proj" / "demo.offset"
    assert cursor.exists()

    cli.cmd_inbox(_inbox(unread=True))
    assert "(no new events)" in capsys.readouterr().out
    assert any('"inbox_read"' in line for line in registry.bus.read_text().splitlines())

    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-two")
    cli.cmd_inbox(_inbox(unread=True))
    assert "comment_updated" in capsys.readouterr().out


def test_owner_replays_the_backlog_and_a_bystander_starts_at_the_legacy_cursor(registry, monkeypatch, capsys):
    legacy = cli.BUS_OFFSET_ROOT / "proj" / "demo.offset"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(str(registry.bus.stat().st_size))

    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-owner")
    cli.cmd_inbox(_inbox(unread=True))
    assert "comment_updated" in capsys.readouterr().out

    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-bystander")
    cli.cmd_inbox(_inbox(unread=True))
    assert "(no new events)" in capsys.readouterr().out


def test_cards_lists_verdicts_without_touching_a_cursor(registry, capsys):
    assert cli.cmd_cards(SimpleNamespace(slug="demo", project=None, json=False)) == 0
    out = capsys.readouterr().out
    assert "2 decision card(s)" in out
    assert "aaaaaaaaaaaa" in out and "accept" in out
    assert "bbbbbbbbbbbb" in out and "—" in out
    assert "undecided: s:b" in out
    assert not (cli.BUS_OFFSET_ROOT).exists()


def test_unknown_slug_lists_the_registered_ones(registry, capsys):
    assert cli.cmd_cards(SimpleNamespace(slug="nope", project=None, json=False)) == 2
    err = capsys.readouterr().err
    assert "no page registered as 'nope'" in err
    assert "proj/demo" in err


def test_project_slash_slug_and_swapped_forms_resolve(registry):
    assert cli._resolve_slug("proj/demo")[1] == "demo"
    assert cli._resolve_slug("demo/proj")[1] == "demo"
    assert cli._resolve_slug("demo", "proj")[0] == "proj"


# ── ask against a live server ────────────────────────────────────────────

def _last_line(capsys) -> str:
    """The in-process server logs each request to stdout; the command's own
    JSON is the final line."""
    return capsys.readouterr().out.strip().splitlines()[-1]


@pytest.fixture
def served(tmp_path, monkeypatch):
    slug_dir = tmp_path / "pages" / "live"
    slug_dir.mkdir(parents=True)
    (slug_dir / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}))
    (slug_dir / "current.meta.json").write_text(json.dumps({"current": "v2", "history": []}))
    bus_dir = tmp_path / "bus" / "proj"
    handler = make_handler(artifact_dir=slug_dir, public_base_path="", slug="live",
                           bus_dir=bus_dir, v2_mode=True)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    record = {"slug": "live", "slug_dir": str(slug_dir), "project": "proj",
              "local_url": f"http://127.0.0.1:{httpd.server_address[1]}/",
              "bus_file": str(bus_dir / "live.ndjson")}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("proj", "live", record)])
    try:
        yield SimpleNamespace(slug_dir=slug_dir, record=record, bus=bus_dir / "live.ndjson")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_ask_posts_one_batch_and_is_idempotent(served, tmp_path, capsys):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([
        {"anchor_id": "s:a", "decision_request": {"prompt": "A?", "recommendation": "accept"}},
        {"anchor_id": "s:b", "text": "B please", "decision_request": {"prompt": "B?"}},
    ]))
    args = SimpleNamespace(slug="live", project=None, from_file=str(cards), version=None,
                           author="agent:test", json=True)
    assert cli.cmd_ask(args) == 0
    first = json.loads(_last_line(capsys))
    assert first["route"] == "batch" and first["created"] == 2 and first["updated"] == 0
    assert first["version"] == "v2"

    assert cli.cmd_ask(args) == 0
    second = json.loads(_last_line(capsys))
    assert second["updated"] == 2 and second["ids"] == first["ids"]

    store = json.loads((served.slug_dir / "comments.json").read_text())
    assert len(store["anchors"]["s:a"]) == 1
    assert store["anchors"]["s:a"][0]["text"] == "A?"          # text defaults to the prompt
    assert store["anchors"]["s:a"][0]["version"] == "v2"
    seeded = [json.loads(line) for line in served.bus.read_text().splitlines() if '"comments_seeded"' in line]
    assert len(seeded) == 2


def test_ask_rejects_a_card_without_anchor(served, tmp_path, capsys):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"text": "no anchor"}]))
    args = SimpleNamespace(slug="live", project=None, from_file=str(cards), version=None,
                           author=None, json=False)
    assert cli.cmd_ask(args) == 2
    assert "has no anchor_id" in capsys.readouterr().err


def test_addressed_goes_through_the_api_with_session_header(served, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-agent")
    code, comment = cli._api(served.record, "POST", "/api/comments",
                             {"anchor_id": "s:z", "text": "hi"}, "reviewer@example.com")
    assert code == 201
    args = SimpleNamespace(slug="proj/live", project=None, comment_id=comment["id"],
                           response="done", author="agent:test")
    assert cli.cmd_addressed(args) == 0
    updated = json.loads(_last_line(capsys))
    assert updated["status"] == "addressed_by_agent" and updated["response_text"] == "done"
    events = [json.loads(line) for line in served.bus.read_text().splitlines()]
    assert events[-1]["event"] == "comment_updated" and events[-1]["session_id"] == "sess-agent"
