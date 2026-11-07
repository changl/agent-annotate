"""page.db as the backend under store.py (Stage 5c)."""

import json
import os
import subprocess
import sys
from pathlib import Path

from test_store_db import _page

from agent_annotate import paths, store

ROOT = Path(__file__).resolve().parents[1]


def _imported(tmp_path):
    fixture = _page(tmp_path)
    store.import_page(fixture["page"], project="proj", slug="demo", bus_file=fixture["bus"], state_dir=fixture["state"])
    return fixture


def _diff(fixture):
    with store.transaction(fixture["page"]) as tx:
        sources = store.Sources(fixture["page"], project="proj", slug="demo", bus_file=fixture["bus"],
                                state_dir=fixture["state"])
        return store.diff(tx.conn, sources)[0]


def _rows(fixture, sql, *args):
    conn = store.connect(fixture["page"] / "page.db")
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def test_every_writer_lands_in_the_db_and_the_files(tmp_path):
    fixture = _imported(tmp_path)
    page = fixture["page"]
    data = store.read_comments(page)
    data["anchors"]["d:q1"][0]["status"] = "resolved_in_version"
    data["anchors"]["d:new"] = [{"id": "n1", "number": 9, "text": "New"}]
    with store.transaction(page):
        store.write_bytes(page / "comments.json", json.dumps(data, separators=(",", ":")).encode(), value=data)
        store.update_meta(page, lambda meta: meta.update(current="v3"))
    store.write_json(page / ".review-drafts" / "v4.json", {"version": "v4", "label": "four"})
    store.remove(page / ".review-drafts" / "v3.json")
    store.write_text(page / "cards.json", "[]\n")
    store.append_round(page, {"id": "r3", "ts": "w"})
    from agent_annotate.project_state import save_project
    save_project(page, {"title": "Renamed", "modules": []})
    assert _rows(fixture, "SELECT status FROM items WHERE id = 'a1'") == [("resolved_in_version",)]
    assert _rows(fixture, "SELECT number, anchor_id FROM numbers WHERE first_item = 'n1'") == [(9, "d:new")]
    assert _rows(fixture, "SELECT current_version FROM page") == [("v3",)]
    assert _rows(fixture, "SELECT n FROM versions WHERE state = 'draft'") == [(4,)]
    assert _rows(fixture, "SELECT round FROM rounds ORDER BY seq") == [("r1",), ("r2",), ("r3",)]
    assert _rows(fixture, "SELECT body_json FROM sidecars WHERE name = 'cards'") == [("[]\n",)]
    assert _diff(fixture) == []
    assert not (page / "page.db.writing").exists()
    assert _rows(fixture, "SELECT value FROM meta WHERE key = 'store_foreign_write'") == []


def test_only_changed_rows_are_written(tmp_path):
    fixture = _imported(tmp_path)
    conn = store.connect(fixture["page"] / "page.db")
    rows = conn.execute(f"SELECT {', '.join(store._ITEM_COLUMNS)} FROM items").fetchall()
    edited = [row[:13] + (row[13].replace("open", "done"),) if row[0] == "b1" else row for row in rows]
    conn.execute("BEGIN IMMEDIATE")
    assert store._sync_rows(conn, "items", store._ITEM_COLUMNS, 1, edited) == 1
    assert store._sync_rows(conn, "items", store._ITEM_COLUMNS, 1, edited) == 0
    conn.execute("ROLLBACK")


def test_a_foreign_json_write_is_taken_in_and_logged(tmp_path):
    fixture = _imported(tmp_path)
    page = fixture["page"]
    meta = json.loads((page / "current.meta.json").read_text())
    meta["current"] = "v1"
    (page / "current.meta.json").write_text(json.dumps(meta, indent=2))   # an older process, no store
    (page / "categories.json").write_text('{"schema_version": 1, "findings_sets": []}')
    (page / "seen.json").unlink()
    with store.transaction(page):
        pass
    assert _rows(fixture, "SELECT current_version FROM page") == [("v1",)]
    assert _rows(fixture, "SELECT name FROM sidecars ORDER BY name") == [("categories",), ("project",)]
    assert _rows(fixture, "SELECT value FROM meta WHERE key = 'store_foreign_write'") == [("3",)]
    log = (paths.LOG_DIR / "store.log").read_text().splitlines()[-1]
    assert f"store_foreign_write {page} categories.json current.meta.json seen.json" in log
    assert _diff(fixture) == []


def test_a_crash_between_file_write_and_commit_is_recovered(tmp_path):
    fixture = _imported(tmp_path)
    page = fixture["page"]
    (page / "page.db.writing").touch()    # the dead transaction's marker
    (page / "seen.json").write_text('{"b": {}}')
    with store.transaction(page):
        pass
    assert _rows(fixture, "SELECT value FROM meta WHERE key LIKE 'store_%'") == [("1",)]
    assert _rows(fixture, "SELECT key FROM meta WHERE key LIKE 'store_%'") == [("store_recovered",)]
    assert not (page / "page.db.writing").exists()
    assert _diff(fixture) == []


def test_unreadable_json_is_kept_whole(tmp_path):
    fixture = _imported(tmp_path)
    (fixture["page"] / "current.meta.json").write_text("{broken json")
    with store.transaction(fixture["page"]):
        pass
    conn = store.connect(fixture["page"] / "page.db")
    assert store.export_texts(conn)["current.meta.json"] == "{broken json"
    conn.close()


def test_bus_lines_from_other_processes_are_events_after_a_transaction(tmp_path):
    fixture = _imported(tmp_path)
    fixture["bus"].write_bytes(fixture["bus"].read_bytes()[:fixture["ends"][2]])
    store.append_line(fixture["bus"], '{"event": "hooked", "ts": "v"}\n')
    with store.transaction(fixture["page"]):
        pass
    assert _rows(fixture, "SELECT seq, type FROM events ORDER BY seq DESC LIMIT 1") == [(3, "hooked")]


def test_the_suite_runs_on_sqlite():
    """The write-heavy tests again, every page they touch on page.db, with the write guard on."""
    modules = ["test_fast_writes.py", "test_decision_api.py", "test_categories_api.py", "test_plan_topics.py",
               "test_project_state.py", "test_publish_version.py", "test_pagegen.py", "test_explicit_send.py",
               "test_meta_stamp_safety.py", "test_close_retire.py", "test_ask_numbers.py", "test_delete_comment.py",
               "test_answer_later.py", "test_comment_carryover.py", "test_version_ready.py",
               "test_cli_reads.py", "test_review_history.py", "test_history_cache.py"]
    log = paths.STATE_DIR.parent / "sqlite-guard.log"
    log.write_text("")
    env = {**os.environ, "ANNOTATE_TEST_SQLITE": "1", "ANNOTATE_WRITE_GUARD": str(log),
           "PYTHONPATH": os.pathsep.join([str(ROOT / "tests" / "write_guard"), str(ROOT / "src")])}
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
                           *(str(ROOT / "tests" / name) for name in modules)],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    assert log.read_text() == ""


def test_snapshot_reads_the_db_and_is_cached_until_a_commit(tmp_path):
    fixture = _imported(tmp_path)
    first = store.snapshot(fixture["page"])
    assert isinstance(first, store.DbSnapshot) and first.meta["current"] == "v2"
    assert store.snapshot(fixture["page"]) is first
    store.update_meta(fixture["page"], lambda meta: meta.update(current="v3"))
    second = store.snapshot(fixture["page"])
    assert second is not first and second.meta["current"] == "v3"
    assert [r["id"] for r in second.rounds()] == ["r1", "r2"]
    assert second.comments["anchors"]["d:q1"][0]["id"] == "a1"


def test_events_after_from_page_db_matches_the_bus_file(tmp_path):
    fixture = _imported(tmp_path)
    page, bus = fixture["page"], fixture["bus"]
    bus.write_bytes(bus.read_bytes()[:fixture["ends"][2]])
    store.append_line(bus, '{"event": "round_submitted", "round_id": "r9"}\n')   # not copied in yet
    for after in (0, fixture["ends"][0], fixture["ends"][1], fixture["ends"][2]):
        for kwargs in ({}, {"types": ("round_submitted", "session_push")}, {"exclude": ("comment_created",)}):
            assert store.events_after(page, bus, after, **kwargs) == store.events_after(None, bus, after, **kwargs)
    assert [row["event"]["event"] for row in store.events_after(page, bus)] == [
        "comment_created", "session_push", "round_submitted"]
    bus.write_text('{"event": "rewritten"}\n')   # rewritten in place: page.db no longer follows it
    assert [row["event"]["event"] for row in store.events_after(page, bus)] == ["rewritten"]
    with store.transaction(page):
        pass
    assert [(r["bus_offset"], r["event"]) for r in store.events_after(page, bus)] == [
        (r["bus_offset"], r["event"]) for r in store.events_after(None, bus)]


def test_a_round_holding_a_line_separator_round_trips(tmp_path):
    fixture = _imported(tmp_path)
    store.append_round(fixture["page"], {"id": "r3", "text": "one two\u0085three"})
    conn = store.connect(fixture["page"] / "page.db")
    assert store.export_texts(conn)["rounds.ndjson"] == (fixture["page"] / "rounds.ndjson").read_text()
    assert _rows(fixture, "SELECT count(*) FROM rounds") == [(3,)]
    conn.close()
    assert _diff(fixture) == []


def test_the_row_cache_never_trusts_the_callers_dict(tmp_path):
    fixture = _imported(tmp_path)
    page = fixture["page"]
    data = store.read_comments(page)
    for text in ("first", "second", "third"):     # the server keeps and mutates one store dict
        data["anchors"]["d:q1"][0]["text"] = text
        store.write_bytes(page / "comments.json", json.dumps(data).encode(), value=data)
        assert json.loads(_rows(fixture, "SELECT body_json FROM items WHERE id = 'a1'")[0][0])["text"] == text
    (page / "comments.json").write_text(json.dumps({**data, "anchors": {}}))   # a foreign write empties it
    store.write_bytes(page / "comments.json", json.dumps(data).encode(), value=data)
    assert _rows(fixture, "SELECT count(*) FROM items") == [(5,)]
    assert _diff(fixture) == []
