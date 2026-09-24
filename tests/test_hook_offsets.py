"""The UserPromptSubmit hook keeps one cursor per session and never touches
the inbox cursor.

v2.18 shared a single cursor per slug between the hook and `inbox --unread`,
so whichever session was prompted first consumed everybody's delta and 22 of
22 observed `inbox --unread` calls answered "(no new events)". These tests run
the packaged hook the way Claude Code does — a subprocess with the payload on
stdin — against a fixture estate.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "agent_annotate" / "hooks" / "check_comment_bus.py"


def _estate(tmp_path, owner=None, legacy_offset=None):
    bus_root = tmp_path / "bus"
    state = tmp_path / "state"
    slug_dir = tmp_path / "pages" / "demo"
    slug_dir.mkdir(parents=True)
    (bus_root / "proj").mkdir(parents=True)
    state.mkdir()
    record = {"slug": "demo", "slug_dir": str(slug_dir), "project": "proj",
              "bus_file": str(bus_root / "proj" / "demo.ndjson")}
    if owner:
        record["owner_session"] = owner
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {"demo": record}}))
    (slug_dir / "comments.json").write_text(json.dumps({
        "schema_version": 2,
        "anchors": {
            "s:a": [{"id": "aaaaaaaaaaaa", "anchor_id": "s:a", "text": "A?", "status": "open",
                     "decision_request": {"prompt": "A?"},
                     "decision": {"verdict": "accept", "ts": "2026-09-17T10:00:00Z", "by": "r@x"}}],
            "s:b": [{"id": "bbbbbbbbbbbb", "anchor_id": "s:b", "text": "B?", "status": "open",
                     "decision_request": {"prompt": "B?"}}],
        },
        "archived": {},
    }))
    bus = bus_root / "proj" / "demo.ndjson"
    lines = [
        {"ts": "2026-09-17T09:00:00Z", "event": "comment_created", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "agent:test"},
        {"ts": "2026-09-17T09:00:01Z", "event": "seen_updated", "slug": "demo", "author": "r@x"},
        {"ts": "2026-09-17T10:00:00Z", "event": "comment_updated", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "r@x", "decision": "accept"},
        {"ts": "2026-09-17T10:00:00Z", "event": "session_push", "slug": "demo",
         "comment_ids": ["aaaaaaaaaaaa"], "author": "r@x", "delivery": "queued"},
        {"ts": "2026-09-17T10:00:05Z", "event": "comment_reply", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "r@x"},
    ]
    bus.write_text("".join(json.dumps(x) + "\n" for x in lines))
    if legacy_offset is not None:
        legacy = state / "bus-offsets" / "proj" / "demo.offset"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(str(legacy_offset))
    return bus_root, state, bus


def _run(bus_root, state, session, extra_env=None, as_script=False):
    env = os.environ.copy()
    env["ANNOTATE_BUS_ROOT"] = str(bus_root)
    env["ANNOTATE_STATE_DIR"] = str(state)
    env.pop("ANNOTATE_STATE_ROOT", None)
    env.update(extra_env or {})
    argv = [sys.executable, str(HOOK)] if as_script else [sys.executable, "-m", "agent_annotate.hooks.check_comment_bus"]
    proc = subprocess.run(argv, input=json.dumps({"session_id": session, "cwd": "/tmp"}),
                          capture_output=True, text=True, env=env, timeout=20)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _hook_cursor(state, session):
    return state / "hook-offsets" / session / "proj" / "demo.offset"


def test_two_sessions_do_not_consume_each_other(tmp_path):
    bus_root, state, bus = _estate(tmp_path)

    out_a = _run(bus_root, state, "sess-A")
    assert "[annotate] proj/demo: 2 reviewer event(s)" in out_a, out_a
    assert "aaaaaaaaaaaa accept" in out_a
    assert "undecided: 1 of 2 cards" in out_a
    assert "inbox demo --unread" in out_a

    # A's notice advanced only A's cursor. B still sees the same delta.
    out_b = _run(bus_root, state, "sess-B")
    assert "2 reviewer event(s)" in out_b, out_b

    assert _hook_cursor(state, "sess-A").exists()
    assert _hook_cursor(state, "sess-B").exists()
    assert not (state / "bus-offsets").exists(), "the hook must never write the inbox cursor"

    # Second prompt in A: nothing new.
    assert _run(bus_root, state, "sess-A").strip() == ""

    notices = [json.loads(line) for line in bus.read_text().splitlines() if '"notice_emitted"' in line]
    assert [n["session_id"] for n in notices] == ["sess-A", "sess-B"]


def test_a_new_session_is_seeded_from_the_legacy_cursor(tmp_path):
    """A cursor a session has never held starts where the v2.18 shared cursor
    was, never at zero — otherwise every live session replays every page's
    history on the turn this ships."""
    bus_root, state, bus = _estate(tmp_path, legacy_offset=None)
    size = bus.stat().st_size
    bus_root, state, bus = _estate(tmp_path / "again", legacy_offset=size)
    # Nothing after the legacy cursor: silence, and no history replayed.
    assert _run(bus_root, state, "sess-new").strip() == ""
    with bus.open("a") as fh:
        fh.write(json.dumps({"ts": "2026-09-17T11:00:00Z", "event": "comment_reply", "slug": "demo",
                             "comment_id": "bbbbbbbbbbbb", "anchor_id": "s:b", "author": "r@x"}) + "\n")
    out = _run(bus_root, state, "sess-new")
    assert "1 reviewer event(s)" in out, out
    assert int(_hook_cursor(state, "sess-new").read_text()) >= bus.stat().st_size - 1


def test_owner_targeting_silences_bystanders(tmp_path):
    bus_root, state, _ = _estate(tmp_path, owner="sess-owner")
    assert "reviewer event" in _run(bus_root, state, "sess-owner")
    assert _run(bus_root, state, "sess-other").strip() == ""
    assert "reviewer event" in _run(bus_root, state, "sess-other", {"ANNOTATE_HOOK_ALL": "1"})


def test_a_retired_page_notifies_nobody(tmp_path):
    """Retiring moves the row out of state/<project>.json; its bus stays.
    With no row there is no owner, and the backlog used to go to everyone."""
    bus_root, state, _ = _estate(tmp_path, owner="sess-owner")
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {}}))
    assert _run(bus_root, state, "sess-owner").strip() == ""
    assert _run(bus_root, state, "sess-other").strip() == ""


def test_inbox_cursor_is_read_but_never_written(tmp_path):
    """`inbox --unread` consuming the backlog also silences the notice."""
    bus_root, state, bus = _estate(tmp_path)
    inbox_cursor = state / "bus-offsets" / "sess-A" / "proj" / "demo.offset"
    inbox_cursor.parent.mkdir(parents=True)
    inbox_cursor.write_text(str(bus.stat().st_size))
    assert _run(bus_root, state, "sess-A").strip() == ""
    assert inbox_cursor.read_text() == str(bus.stat().st_size)


def test_dry_run_writes_nothing(tmp_path):
    bus_root, state, bus = _estate(tmp_path)
    before = bus.read_text()
    out = _run(bus_root, state, "sess-A", {"ANNOTATE_HOOK_DRY_RUN": "1"})
    assert "reviewer event" in out
    assert bus.read_text() == before
    assert not (state / "hook-offsets").exists() or not _hook_cursor(state, "sess-A").exists()


def test_round_submitted_is_announced(tmp_path):
    bus_root, state, bus = _estate(tmp_path)
    with bus.open("a") as fh:
        fh.write(json.dumps({"ts": "2026-09-17T10:01:00Z", "event": "round_submitted", "slug": "demo",
                             "comment_ids": ["aaaaaaaaaaaa"], "by": "r@x",
                             "verdict_counts": {"accept": 1, "reject": 0, "comment": 0},
                             "undecided_ids": ["bbbbbbbbbbbb"]}) + "\n")
    out = _run(bus_root, state, "sess-A")
    assert out.startswith("ROUND SUBMITTED: [annotate] proj/demo:")


def test_the_shell_wrapper_runs_the_same_hook(tmp_path):
    """check-comment-bus.sh locates the Python next to itself; no `annotate`
    on PATH is consulted, so libgd's binary can never be exec'd by mistake."""
    bus_root, state, _ = _estate(tmp_path)
    env = os.environ.copy()
    env["ANNOTATE_BUS_ROOT"] = str(bus_root)
    env["ANNOTATE_STATE_DIR"] = str(state)
    sh = HOOK.parent / "check-comment-bus.sh"
    proc = subprocess.run(["bash", str(sh)], input=json.dumps({"session_id": "sess-sh"}),
                          capture_output=True, text=True, env=env, timeout=20)
    assert proc.returncode == 0
    assert "2 reviewer event(s)" in proc.stdout


def test_the_bare_script_form_matches_the_module_form(tmp_path):
    bus_root, state, _ = _estate(tmp_path)
    assert "2 reviewer event(s)" in _run(bus_root, state, "sess-A", as_script=True)


def test_a_changes_verdict_shows_its_note_in_the_notice(tmp_path):
    """D2: "Request changes" carries the instruction in its note, so the
    one-line notice must print the note, not just the word. The pre-D2
    spelling `comment` reads the same way — an already-loaded page keeps
    posting it."""
    bus_root, state, bus = _estate(tmp_path)
    store = json.loads((Path(state) / "proj.json").read_text())
    slug_dir = Path(store["slugs"]["demo"]["slug_dir"])
    comments = json.loads((slug_dir / "comments.json").read_text())
    comments["anchors"]["s:b"][0]["decision"] = {
        "verdict": "changes", "text": "cite the source for row 3",
        "ts": "2026-09-17T11:00:00Z", "by": "r@x"}
    (slug_dir / "comments.json").write_text(json.dumps(comments))
    with bus.open("a") as fh:
        fh.write(json.dumps({"ts": "2026-09-17T11:00:00Z", "event": "comment_updated",
                             "slug": "demo", "comment_id": "bbbbbbbbbbbb", "anchor_id": "s:b",
                             "author": "r@x", "decision": "changes"}) + "\n")

    out = _run(bus_root, state, "sess-changes")
    assert 'bbbbbbbbbbbb changes("cite the source for row 3")' in out, out
    assert "undecided: 0 of 2 cards" in out


def test_notice_excludes_resolved_prior_round_cards_from_undecided(tmp_path):
    bus_root, state, _ = _estate(tmp_path)
    registry = json.loads((Path(state) / "proj.json").read_text())
    slug_dir = Path(registry["slugs"]["demo"]["slug_dir"])
    comments = json.loads((slug_dir / "comments.json").read_text())
    old = comments["anchors"]["s:b"][0]
    old["status"] = "resolved_in_version"
    old["resolved_in_version"] = "v2"
    old["resolution_anchor_id"] = "s:a"
    old["decision"] = {
        "verdict": "comment",
        "text": "apply this in v2",
        "ts": "2026-09-17T10:30:00Z",
        "by": "r@x",
    }
    (slug_dir / "comments.json").write_text(json.dumps(comments))

    out = _run(bus_root, state, "sess-resolved")

    assert "undecided: 0 of 1 cards" in out


def test_page_closed_is_bookkeeping_for_the_notice(tmp_path):
    """D7: `annotate close` archiving stale cards is not reviewer activity."""
    bus_root, state, bus = _estate(tmp_path)
    _run(bus_root, state, "sess-quiet")  # drain the existing delta
    with bus.open("a") as fh:
        fh.write(json.dumps({"ts": "2026-09-17T12:00:00Z", "event": "page_closed",
                             "slug": "demo", "archived_ids": ["bbbbbbbbbbbb"],
                             "archived_count": 1, "by": "agent:test"}) + "\n")
    assert _run(bus_root, state, "sess-quiet").strip() == ""
