"""page.db import, diff and export (Stage 5b) on a fixture page."""

import json
from pathlib import Path

import pytest

from agent_annotate import store


def _page(root: Path) -> dict:
    """A page with every record file, a bus and a cursor of each kind."""
    page = root / "pages" / "proj" / "demo"
    (page / ".review-drafts").mkdir(parents=True)

    def comment(cid, number, **extra):
        return {"id": cid, "anchor_id": "x", "text": "Ship it? — ünïcode", "number": number,
                "version": "v2", "status": "open", "replies": [], **extra}

    store_data = {"schema_version": 2,
                  "anchors": {"d:q1": [comment("a1", 1), comment("a2", 1, origin_id="a1")],
                              "d:q2": [comment("b1", 2, decision={"choice": "yes", "history": [{"at": 1.5}]})],
                              "empty": [],
                              "d:old": [comment("c1", 2)]},          # a legacy number reused on another anchor
                  "archived": {"d:gone": [comment("z1", 3, archived_at="t")]},
                  "approved_plans": {"p2": {"id": "p2"}, "p1": {"id": "p1"}}}
    (page / "comments.json").write_text(json.dumps(store_data, ensure_ascii=False, separators=(",", ":")))
    meta = {"current": "v2", "history": [{"version": "v1", "ts": "t1", "label": "initial"},
                                         {"version": "v2", "ts": "t2", "label": "Round", "fixes": "v1"}],
            "content_stamps": {"v2": {"whole": "abc", "_mtime": 1.25}},
            "owner": {"owner_session": "s1"}, "name": "Demo"}
    (page / "current.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    (page / ".review-drafts" / "v3.json").write_text(json.dumps({"version": "v3", "label": "next", "preview": "tok",
                                                                 "reserved": [4, 5]}, indent=2))
    (page / "seen.json").write_text('{"a": {"ts": "t"}}')
    (page / "project.json").write_text(json.dumps({"title": "Demo", "modules": []}, indent=2) + "\n")
    (page / "rounds.ndjson").write_text('{"id": "r1", "ts": "t"}\n{"id": "r2", "ts": "u"}\n')
    bus = root / "bus" / "proj" / "demo.ndjson"
    bus.parent.mkdir(parents=True)
    lines = [b'{"event": "comment_created", "comment_id": "a1", "ts": "t"}\n', b"not json\n",
             b'{"event": "session_push", "round": "r1"}\n']
    bus.write_bytes(b"".join(lines) + b'{"event": "partial')
    state = root / "state"
    ends = [len(lines[0]), len(lines[0]) + len(lines[1]), sum(map(len, lines))]
    cursors = {"bus-offsets/proj/demo.offset": ends[0], "bus-offsets/s1/proj/demo.offset": ends[2],
               "bus-offsets/s1/proj/demo.offset.review": ends[1], "hook-offsets/s2/proj/demo.offset": 0,
               "monitor-offsets/proj/demo.offset": ends[2]}
    for name, value in cursors.items():
        (state / name).parent.mkdir(parents=True, exist_ok=True)
        (state / name).write_text(str(value))
    (state / "deliveries" / "proj").mkdir(parents=True)
    (state / "deliveries" / "proj" / "demo.json").write_text(json.dumps(
        {"offset": ends[2], "deliveries": {"d1": {"id": "d1", "state": "acknowledged", "round_id": "r1"}}}))
    return {"page": page, "bus": bus, "state": state, "ends": ends}


def _import(fixture, **kwargs):
    return store.import_page(fixture["page"], project="proj", slug="demo", bus_file=fixture["bus"],
                             state_dir=fixture["state"], **kwargs)


def test_import_diff_zero_and_export_byte_stable(tmp_path):
    fixture = _page(tmp_path)
    before = {p.relative_to(fixture["page"]): p.read_bytes() for p in fixture["page"].rglob("*") if p.is_file()}
    result = _import(fixture)
    assert (result["items"], result["versions"], result["drafts"], result["events"]) == (5, 2, 1, 2)
    assert result["skipped_lines"] == 2 and result["diff"] == 0
    assert result["shared_numbers"] == ["#2: anchor d:q2 (item b1) and anchor d:old (item c1)"]
    assert result["identical"] == result["files"] + 1  # every page file and the journal, byte for byte
    conn = store.connect(fixture["page"] / "page.db")
    texts = store.export_texts(conn)
    assert {Path(k): v.encode() for k, v in texts.items()} == before
    cursors = {(k, r): (s, o) for k, r, s, o in conn.execute("SELECT * FROM cursors")}
    ends = fixture["ends"]
    assert cursors[("inbox", "proj/demo.offset")] == (1, ends[0])
    assert cursors[("inbox", "s1/proj/demo.offset.review")] == (1, ends[1])  # after the invalid line
    assert cursors[("inbox", "s1/proj/demo.offset")] == (2, ends[2])
    assert cursors[("hook", "s2/proj/demo.offset")] == (0, 0)
    assert cursors[("monitor", "monitor")] == cursors[("delivery", "journal")] == (2, ends[2])
    assert [r for r in conn.execute("SELECT number, anchor_id, first_item FROM numbers ORDER BY number, anchor_id")] == [
        (1, "d:q1", "a1"), (2, "d:old", "c1"), (2, "d:q2", "b1"), (3, "d:gone", "z1")]
    conn.close()
    # Files are never modified by import; export rewrites nothing that is current.
    assert {p.relative_to(fixture["page"]): p.read_bytes() for p in fixture["page"].rglob("*")
            if p.is_file() and not p.name.startswith("page.db")} == before
    store.export_page(fixture["page"])
    assert {p.relative_to(fixture["page"]): p.read_bytes() for p in fixture["page"].rglob("*")
            if p.is_file() and not p.name.startswith("page.db") and p.suffix != ".lock"} == before


def test_diff_names_a_changed_file(tmp_path):
    fixture = _page(tmp_path)
    _import(fixture)
    meta = json.loads((fixture["page"] / "current.meta.json").read_text())
    meta["current"] = "v1"
    (fixture["page"] / "current.meta.json").write_text(json.dumps(meta, indent=2))
    conn = store.connect(fixture["page"] / "page.db")
    differences, _ = store.diff(conn, store.Sources(fixture["page"], project="proj", slug="demo",
                                                    bus_file=fixture["bus"], state_dir=fixture["state"]))
    assert differences == ["current.meta.json: content differs"]


def test_import_refuses_and_lists(tmp_path):
    fixture = _page(tmp_path)
    (fixture["state"] / "hook-offsets/s2/proj/demo.offset").write_text("5")
    meta = json.loads((fixture["page"] / "current.meta.json").read_text())
    meta["history"].append({"version": "v2", "ts": "t3"})
    (fixture["page"] / "current.meta.json").write_text(json.dumps(meta))
    with pytest.raises(store.Refused) as refused:
        _import(fixture)
    assert refused.value.rows == ["history[2]: v2 listed twice",
                                  "cursor hook s2/proj/demo.offset: byte 5 is inside a bus line"]
    assert not list(fixture["page"].glob("page.db*"))


def test_dry_run_leaves_no_db_and_import_twice_refuses(tmp_path):
    fixture = _page(tmp_path)
    assert _import(fixture, dry_run=True)["diff"] == 0
    assert not list(fixture["page"].glob("page.db*"))
    _import(fixture)
    with pytest.raises(ValueError, match="page.db exists"):
        _import(fixture)


def test_catch_up_bus_copies_new_lines_and_follows_a_pruned_bus(tmp_path):
    fixture = _page(tmp_path)
    fixture["bus"].write_bytes(fixture["bus"].read_bytes()[:fixture["ends"][2]])
    _import(fixture)
    store.append_line(fixture["bus"], '{"event": "hooked", "ts": "v"}\n')
    assert store.catch_up_bus(fixture["page"]) == 1
    assert store.catch_up_bus(fixture["page"]) == 0
    fixture["bus"].write_text('{"event": "fresh"}\n')  # pruned and started again
    assert store.catch_up_bus(fixture["page"]) == 1
    assert store.catch_up_bus(fixture["page"]) == 0
    conn = store.connect(fixture["page"] / "page.db")
    assert [t for (t,) in conn.execute("SELECT type FROM events ORDER BY seq")] == [
        "comment_created", "session_push", "hooked", "fresh"]


def test_db_off_sets_the_db_aside(tmp_path):
    fixture = _page(tmp_path)
    _import(fixture)
    assert store.backend(fixture["page"]) == "sqlite"
    kept = store.db_off(fixture["page"])
    assert kept.name.startswith("page.db.off-") and kept.is_file()
    assert store.backend(fixture["page"]) == "json"


def test_db_refuses_volumes_before_any_filesystem_probe(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("must refuse before df"))
    with pytest.raises(ValueError, match="refused under /Volumes"):
        store._refuse_network_volume(Path("/Volumes/share/review"))


def test_doctor_storage_reports_each_backend_and_reason(tmp_path, monkeypatch):
    from agent_annotate import cli
    from agent_annotate.db_command import storage_lines
    fixture = _page(tmp_path)
    _import(fixture)
    monkeypatch.setattr(cli, "_registry_entries", lambda: [
        ("proj", "db", {"slug_dir": str(fixture["page"])}),
        ("proj", "hold", {"slug_dir": str(tmp_path / "hold"), "db_hold": "held for this rollout"}),
        ("proj", "refused", {"slug_dir": "/Volumes/share/page"}),
        ("proj", "failed", {"slug_dir": str(tmp_path / "failed"), "db_reason": "cursor is mid-line"})])
    assert storage_lines() == ["storage proj/db: page.db", "storage proj/hold: JSON (held for this rollout)",
                               "storage proj/refused: JSON (page.db refused under /Volumes)",
                               "storage proj/failed: JSON (cursor is mid-line)"]


def test_db_commands_print_one_line_each(monkeypatch, capsys):
    from agent_annotate import cli, paths
    fixture = _page(paths.STATE_DIR.parent)  # cursors and the journal under the sandbox state
    record = {"slug_dir": str(fixture["page"]), "bus_file": str(fixture["bus"])}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("proj", "demo", record)])
    monkeypatch.setattr(cli, "_running_servers", lambda *a, **k: {})

    def run(argv):
        return cli.run_command(cli.build_parser().parse_args(argv))

    assert run(["db", "import", "proj/demo", "--dry-run"]) == 0
    assert run(["db", "import", "demo"]) == 0
    assert run(["db", "diff", "demo"]) == 0
    assert run(["db", "export", "demo"]) == 0
    assert run(["db", "off", "demo"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("demo would import · 5 items · 2 versions · 2 events · diff 0 · ")
    assert lines[1].startswith("demo imported · 5 items") and lines[1].endswith(" · 1 legacy numbers on two anchors")
    assert lines[2:4] == ["demo db = json · 0 differences", "demo exported 6 files · bus caught up (0 events)"]
    assert lines[4].startswith("demo back on json · page.db kept as page.db.off-")
    assert len(lines) == 5
