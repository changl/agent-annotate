"""D7: closing stale questions and retiring dead registry rows.

Both commands exist because the estate accumulated two kinds of rot that
nothing could clear: decision cards nobody ever answered (which kept
inflating every unanswered count) and registry rows for servers that died
months ago (which made `status` unreadable). Neither command deletes
anything, and the tests below pin exactly what each one is allowed to touch.
"""

import datetime as dt
import json
from types import SimpleNamespace

import pytest

from agent_annotate import cli


def _iso(days_ago):
    return (dt.datetime.now(dt.UTC) - dt.timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _card(cid, anchor, days_ago, **extra):
    c = {"id": cid, "anchor_id": anchor, "text": "Q?", "status": "open",
         "version": "v1", "created_at": _iso(days_ago),
         "decision_request": {"prompt": f"Question on {anchor}?"}}
    c.update(extra)
    return c


@pytest.fixture
def page(tmp_path, monkeypatch):
    """One page with every kind of comment `close` has to tell apart."""
    slug_dir = tmp_path / "pages" / "demo"
    slug_dir.mkdir(parents=True)
    store = {
        "schema_version": 2,
        "anchors": {
            # Stale and unanswered — the only two in scope.
            "s:a": [_card("aaaaaaaaaaaa", "s:a", 90)],
            "s:b": [_card("bbbbbbbbbbbb", "s:b", 45)],
            # Stale but ANSWERED: a verdict is not stale work.
            "s:c": [_card("cccccccccccc", "s:c", 120, status="user_confirmed",
                          decision={"verdict": "accept", "text": None,
                                    "ts": _iso(119), "by": "r@x"})],
            # Unanswered but young.
            "s:d": [_card("dddddddddddd", "s:d", 3)],
            # A plain reviewer comment, stale, with no decision_request.
            "s:e": [{"id": "eeeeeeeeeeee", "anchor_id": "s:e", "text": "typo here",
                     "status": "open", "version": "v1", "created_at": _iso(200)}],
        },
        "archived": {},
    }
    (slug_dir / "comments.json").write_text(json.dumps(store), encoding="utf-8")
    bus = tmp_path / "bus" / "proj" / "demo.ndjson"
    bus.parent.mkdir(parents=True)
    record = {"slug": "demo", "slug_dir": str(slug_dir), "project": "proj",
              "pid": 0, "port": 8899, "bus_file": str(bus), "url": "http://x/"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("proj", "demo", record)])
    monkeypatch.setattr(cli, "_running_servers", lambda: {})
    monkeypatch.setattr(cli, "LOCK_DIR", tmp_path / "locks")
    return SimpleNamespace(slug_dir=slug_dir, bus=bus, record=record)


def _close(**over):
    base = dict(slug="demo", project=None, older_than="30d", dry_run=False, author="agent:test")
    base.update(over)
    return SimpleNamespace(**base)


def _store(page):
    return json.loads((page.slug_dir / "comments.json").read_text(encoding="utf-8"))


def _events(page):
    if not page.bus.exists():
        return []
    return [json.loads(x) for x in page.bus.read_text(encoding="utf-8").splitlines() if x.strip()]


# ── close ─────────────────────────────────────────────────────────────────

def test_close_dry_run_names_the_cards_and_writes_nothing(page, capsys):
    before = _store(page)
    assert cli.cmd_close(_close(dry_run=True)) == 0
    out = capsys.readouterr().out

    assert "2 unanswered card(s) older than 30d" in out
    assert "aaaaaaaaaaaa" in out and "bbbbbbbbbbbb" in out
    assert "cccccccccccc" not in out and "dddddddddddd" not in out
    assert "dry run" in out
    assert _store(page) == before
    assert _events(page) == []


def test_close_archives_only_the_stale_unanswered_cards(page, capsys):
    assert cli.cmd_close(_close()) == 0
    store = _store(page)

    # The two stale cards moved, keeping every field plus the archive stamps.
    assert "s:a" not in store["anchors"] and "s:b" not in store["anchors"]
    archived = {c["id"]: c for items in store["archived"].values() for c in items}
    assert set(archived) == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}
    for c in archived.values():
        assert c["status"] == "archived"
        assert c["archived_by"] == "agent:test"
        assert c["archived_at"]
        assert c["decision_request"]["prompt"]

    # A decided card and a plain reviewer comment are never in scope.
    assert store["anchors"]["s:c"][0]["decision"]["verdict"] == "accept"
    assert store["anchors"]["s:d"][0]["id"] == "dddddddddddd"
    assert store["anchors"]["s:e"][0]["text"] == "typo here"

    events = _events(page)
    assert len(events) == 1, events
    ev = events[0]
    assert ev["event"] == "page_closed"
    assert ev["slug"] == "demo"
    assert sorted(ev["archived_ids"]) == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    assert ev["archived_count"] == 2
    assert ev["remaining_open"] == 1        # only the 3-day-old card is left
    assert ev["older_than"] == "30d"
    assert ev["by"] == "agent:test"
    assert "session_id" in ev


def test_close_is_bounded_by_older_than(page, capsys):
    """The threshold is the whole contract. The unanswered cards are 90, 45
    and 3 days old, so each boundary picks a different set."""
    assert cli.cmd_close(_close(older_than="100d", dry_run=True)) == 0
    assert "0 unanswered card(s) older than 100d" in capsys.readouterr().out

    assert cli.cmd_close(_close(older_than="60d", dry_run=True)) == 0
    out = capsys.readouterr().out
    assert "1 unanswered card(s) older than 60d" in out
    assert "aaaaaaaaaaaa" in out and "bbbbbbbbbbbb" not in out

    assert cli.cmd_close(_close(older_than="40d", dry_run=True)) == 0
    assert "2 unanswered card(s) older than 40d" in capsys.readouterr().out

    assert cli.cmd_close(_close(older_than="1d")) == 0
    store = _store(page)
    archived = {c["id"] for items in store["archived"].values() for c in items}
    assert archived == {"aaaaaaaaaaaa", "bbbbbbbbbbbb", "dddddddddddd"}
    assert _events(page)[0]["remaining_open"] == 0


def test_close_with_nothing_stale_writes_no_event(page, capsys):
    assert cli.cmd_close(_close(older_than="2w")) == 0  # 14d: a and b are stale
    page.bus.write_text("", encoding="utf-8")
    assert cli.cmd_close(_close(older_than="1000d")) == 0
    assert "nothing to close" in capsys.readouterr().out
    assert _events(page) == []


def test_close_rejects_an_unreadable_age(page, capsys):
    assert cli.cmd_close(_close(older_than="soon")) == 2
    assert "cannot read" in capsys.readouterr().err


# ── retire ────────────────────────────────────────────────────────────────

@pytest.fixture
def estate(tmp_path, monkeypatch):
    """Two projects: one dead row, one dead row with a stale pid, one alive."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(cli, "LOCK_DIR", tmp_path / "locks")
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {
        "gone": {"slug": "gone", "slug_dir": str(tmp_path / "gone"), "pid": 999999,
                 "port": 8801, "url": "http://x/gone/", "owner_session": "sess-old"},
        "serving": {"slug": "serving", "slug_dir": str(tmp_path / "serving"), "pid": 4242,
                    "port": 8802, "url": "http://x/serving/"},
    }}))
    (state / "other.json").write_text(json.dumps({"project": "other", "slugs": {
        # pid is stale but a server really is on this slug_dir: NOT dead.
        "restarted": {"slug": "restarted", "slug_dir": str(tmp_path / "restarted"),
                      "pid": 999998, "port": 8803, "url": "http://x/restarted/"},
    }}))
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(cli, "_running_servers",
                        lambda: {str(tmp_path / "restarted"): [{"pid": 7777, "port": 8803}]})
    return SimpleNamespace(state=state, tmp=tmp_path)


def _retire(**over):
    base = dict(slug=None, project=None, dead=False, dry_run=False)
    base.update(over)
    return SimpleNamespace(**base)


def _registry(estate, project):
    return json.loads((estate.state / f"{project}.json").read_text(encoding="utf-8"))["slugs"]


def test_retire_dead_moves_only_the_dead_row(estate, capsys):
    assert cli.cmd_retire(_retire(dead=True)) == 0
    out = capsys.readouterr().out
    assert "gone" in out and "retired 1 entr" in out
    assert "still alive" in out

    assert set(_registry(estate, "proj")) == {"serving"}
    assert set(_registry(estate, "other")) == {"restarted"}

    retired = json.loads((estate.state / "retired" / "proj.json").read_text(encoding="utf-8"))
    entry = retired["slugs"]["gone"]
    assert entry["retired_at"]
    # Every original field survives the move.
    assert entry["port"] == 8801
    assert entry["url"] == "http://x/gone/"
    assert entry["owner_session"] == "sess-old"


def test_retire_dry_run_changes_nothing(estate, capsys):
    assert cli.cmd_retire(_retire(dead=True, dry_run=True)) == 0
    assert "dry run" in capsys.readouterr().out
    assert set(_registry(estate, "proj")) == {"gone", "serving"}
    assert not (estate.state / "retired").exists()


def test_retire_refuses_a_page_that_is_still_serving(estate, capsys):
    assert cli.cmd_retire(_retire(slug="serving")) == 2
    assert "still alive" in capsys.readouterr().err
    assert set(_registry(estate, "proj")) == {"gone", "serving"}


def test_retire_never_touches_the_slug_dir_or_the_bus(estate, tmp_path):
    slug_dir = tmp_path / "gone"
    slug_dir.mkdir()
    (slug_dir / "comments.json").write_text("{}", encoding="utf-8")
    bus = tmp_path / "bus" / "proj" / "gone.ndjson"
    bus.parent.mkdir(parents=True)
    bus.write_text('{"event":"page_published"}\n', encoding="utf-8")

    assert cli.cmd_retire(_retire(dead=True)) == 0
    assert (slug_dir / "comments.json").exists()
    assert bus.read_text(encoding="utf-8") == '{"event":"page_published"}\n'


# ── status ────────────────────────────────────────────────────────────────

def test_status_reports_the_retired_count_and_lists_them(estate, capsys):
    cli.cmd_retire(_retire(dead=True))
    capsys.readouterr()

    assert cli.cmd_status(SimpleNamespace(slug=None, retired=False)) == 0
    assert "1 retired entries" in capsys.readouterr().out

    assert cli.cmd_status(SimpleNamespace(slug=None, retired=True)) == 0
    out = capsys.readouterr().out
    assert "gone" in out and "http://x/gone/" in out


def test_status_names_the_owner_and_flags_a_dead_one(estate, monkeypatch, capsys):
    (estate.state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {
        "serving": {"slug": "serving", "slug_dir": str(estate.tmp / "serving"), "pid": 4242,
                    "port": 8802, "url": "http://x/serving/",
                    "owner_session": "sess-vanished", "owner_label": "parrotfish:sess-van",
                    "owner_claimed_at": _iso(2)},
    }}))
    monkeypatch.setattr(cli, "_ps_command_snapshot", lambda: "some other process\n")

    assert cli.cmd_status(SimpleNamespace(slug=None, retired=False)) == 0
    out = capsys.readouterr().out
    assert "parrotfish:sess-van" in out
    assert "claimed 2d" in out
    assert "(gone)" in out
    assert "claim <slug>" in out


def test_status_does_not_guess_when_ps_is_unavailable(estate, monkeypatch, capsys):
    (estate.state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {
        "serving": {"slug": "serving", "slug_dir": str(estate.tmp / "serving"), "pid": 4242,
                    "port": 8802, "url": "http://x/serving/",
                    "owner_session": "sess-vanished", "owner_claimed_at": _iso(1)},
    }}))
    monkeypatch.setattr(cli, "_ps_command_snapshot", lambda: "")

    assert cli.cmd_status(SimpleNamespace(slug=None, retired=False)) == 0
    assert "(gone)" not in capsys.readouterr().out
