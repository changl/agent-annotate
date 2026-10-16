"""Category commands operate on the canonical page and preserve other content."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent_annotate import categories, cli, mcp_server


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "page"
    directory.mkdir()
    comments = {"schema_version": 2, "anchors": {}, "archived": {}}
    for number, category in enumerate(("review", "findings", "library", "plans"), 1):
        anchor = f"d:q{number}" if category != "library" else "copy:hero"
        row = {"id": str(number) * 12, "number": number, "anchor_id": anchor, "text": f"Question {number}",
               "author": "agent:test", "status": "open", "version": "v1",
               "decision_request": {"prompt": f"Question {number}", "options": ["fix", "keep"]}}
        if category not in ("review", "library"):
            row["category"] = category
        if category == "findings":
            row["finding"] = {"set": "design", "title": "Contrast"}
        comments["anchors"][anchor] = [row]
    (directory / "comments.json").write_text(json.dumps(comments))
    (directory / "current.meta.json").write_text(json.dumps({"current": "v5", "history": [{"version": "v5"}]}))
    (directory / "current.html").write_text("<h1>Review remains intact</h1>")
    (directory / "versions").mkdir()
    for version in ("v1", "v5"):
        (directory / "versions" / f"{version}.html").write_text('<p data-anchor-id="s:scope">Scope</p><p data-anchor-id="d:q1">Question</p>')
    bus = tmp_path / "events.ndjson"
    bus.write_text("".join(json.dumps({"event": "comment_created", "comment_id": row[0]["id"],
                                     "anchor_id": anchor}) + "\n" for anchor, row in comments["anchors"].items()))
    record = {"project": "project", "slug": "main", "slug_dir": str(directory), "bus_file": str(bus),
              "url": "http://localhost:8984/", "local_url": "http://localhost:8984/",
              "owner_session": "test-owner", "workspace_primary": True}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "main", record)])
    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", tmp_path / "offsets")
    monkeypatch.setattr(cli, "_session_id", lambda: "test-owner")
    return SimpleNamespace(directory=directory, record=record, bus=bus, root=tmp_path)


def args(**kwargs):
    return SimpleNamespace(slug="project/main", project=None, json=True, **kwargs)


@pytest.mark.parametrize("category", ("review", "library", "findings", "plans"))
@pytest.mark.parametrize("verdict", ("accept", "reject", "changes", "comment", "select"))
def test_round_state_agrees_across_cards_inbox_and_hook(page, capsys, category, verdict):
    from agent_annotate.hooks import check_comment_bus as hook

    rows = []
    for number, (status, decision) in enumerate([
        ("open", {}),
        ("open", {"verdict": verdict, "round_pending": True}),
        ("user_confirmed", {"verdict": verdict}),
        ("addressed_by_agent", {}),
        ("resolved_in_version", {}),
        ("archived", {}),
    ], 9):
        rows.append({"id": str(number), "number": number, "anchor_id": f"d:q{number}",
                     "status": status, "category": category, "decision": decision,
                     "decision_request": {"prompt": f"Question {number}"}})
    store = {"schema_version": 2, "anchors": {row["anchor_id"]: [row] for row in rows}, "archived": {}}
    (page.directory / "comments.json").write_text(json.dumps(store))
    options = dict(slug="project/main", project=None, category=category, json=False)
    assert cli.cmd_cards(SimpleNamespace(**options)) == 0
    cards_output = capsys.readouterr().out
    assert "3 decision card(s)" in cards_output
    assert f"{verdict} (unsent)" in cards_output
    assert "undecided: d:q9; unsent: d:q10" in cards_output
    assert f"1 {verdict}" in cards_output
    assert cli.cmd_inbox(SimpleNamespace(**options, unread=False, all_events=False)) == 0
    inbox_output = capsys.readouterr().out
    assert cards_output.splitlines()[-1] == inbox_output.splitlines()[-1]
    options["json"] = True
    assert cli.cmd_inbox(SimpleNamespace(**options, unread=False, all_events=False)) == 0
    inbox = json.loads(capsys.readouterr().out)
    assert inbox["decisions"][verdict] == 1
    assert sum(inbox["decisions"].values()) == 1
    assert inbox["card_count"] == 3
    assert inbox["undecided"] == ["d:q9"] and inbox["unsent"] == ["d:q10"]
    cards = hook._load_cards(str(page.directory))
    assert set(cards) == {"9", "10", "11"}
    notice = hook._slug_line("project", "main", 1,
                             [{"event": "comment_reply", "comment_id": "10"}], cards, True)
    assert "undecided: 1 of 3 cards; unsent: 1" in notice
    assert f"10 {verdict}" not in notice


def test_inbox_labels_a_deferred_verdict_unsent_only_until_its_round_is_submitted(page, capsys):
    store_path = page.directory / "comments.json"
    store = json.loads(store_path.read_text())
    card = store["anchors"]["d:q1"][0]
    card["decision"] = {"verdict": "accept", "by": "reviewer@example.com", "round_pending": True}
    store_path.write_text(json.dumps(store))
    with page.bus.open("a") as bus:
        bus.write(json.dumps({"event": "comment_updated", "comment_id": card["id"], "anchor_id": "d:q1",
                              "author": "reviewer@example.com", "decision": "accept", "deferred": True}) + "\n")
    options = dict(slug="project/main", project=None, category=None, json=False, unread=False, all_events=False)

    def updated_line():
        assert cli.cmd_inbox(SimpleNamespace(**options)) == 0
        return next(line for line in capsys.readouterr().out.splitlines() if "comment_updated" in line)

    assert "accept (unsent)" in updated_line()
    card["decision"].pop("round_pending")
    store_path.write_text(json.dumps(store))
    with page.bus.open("a") as bus:
        bus.write(json.dumps({"event": "round_submitted", "by": "reviewer@example.com", "answers": []}) + "\n")
    line = updated_line()
    assert "accept" in line and "(unsent)" not in line


def tool(name):
    return mcp_server.build_server()._tool_manager._tools[name].fn


def test_finding_fixed_with_urls_and_local_file_matches_persisted_store(page, capsys):
    proof = page.root / "proof.txt"
    proof.write_text("Observed contrast result")
    assert cli.cmd_finding(args(fixed="2", proof=[str(proof), "https://example.test/proof"],
                                note="Checked on actual page", author="test")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "addressed_by_agent" and result["resolved_in_version"] == "v5"
    assert result["fixed"]["by"] == "agent:test"
    assert result["fixed"]["note"] == "Checked on actual page"
    attachment = result["fixed"]["proof"][0]["attachment"]
    assert (page.directory / "attachments" / attachment).read_text() == proof.read_text()
    assert result["fixed"]["proof"][1]["url"] == "https://example.test/proof"
    persisted = json.loads((page.directory / "comments.json").read_text())
    assert persisted["anchors"]["d:q2"][0]["fixed"] == result["fixed"]
    assert not persisted["anchors"]["d:q1"][0].get("fixed")
    assert json.loads(page.bus.read_text().splitlines()[-1])["category"] == "findings"


@pytest.mark.parametrize("kind", ["missing", "outside", "symlink", "oversize", "url", "directory"])
def test_finding_bad_proof_leaves_comment_unmodified(page, tmp_path, capsys, kind):
    before = (page.directory / "comments.json").read_bytes()
    proof = page.root / "proof"
    if kind == "missing":
        proofs = []
    elif kind == "outside":
        proof = tmp_path.parent / (tmp_path.name + "-outside")
        proof.write_text("outside")
        proofs = [str(proof)]
    elif kind == "symlink":
        target = page.root / "target"
        target.write_text("evidence")
        proof.symlink_to(target)
        proofs = [str(proof)]
    elif kind == "oversize":
        with proof.open("wb") as stream:
            stream.truncate(categories.MAX_PROOF_BYTES + 1)
        proofs = [str(proof)]
    elif kind == "url":
        proofs = ["https://user:password@example.test/proof"]
    else:
        proof.mkdir()
        proofs = [str(proof)]
    assert cli.cmd_finding(args(fixed="2", proof=proofs, note="", author=None)) == 2
    assert (page.directory / "comments.json").read_bytes() == before
    assert "ERROR: finding:" in capsys.readouterr().err
    assert not (page.directory / "attachments").exists()


def test_missing_finding_does_not_copy_proof(page, capsys):
    proof = page.root / "proof.txt"
    proof.write_text("evidence")
    assert cli.cmd_finding(args(fixed="999", proof=[str(proof)], note="", author=None)) == 2
    assert not (page.directory / "attachments").exists()


def test_plan_markdown_and_html_have_independent_history_and_review_is_preserved(page, capsys):
    before = {name: (page.directory / name).read_bytes() for name in ("current.meta.json", "current.html", "comments.json")}
    source = page.root / "plan.md"
    source.write_text("---\ntitle: Launch plan\n---\n\n## Scope\n\n**Observe** the launch.\n\n| Step | State |\n| --- | --- |\n| Check | Ready |\n")
    assert cli.cmd_plan(args(plan_id="launch", from_file=str(source), title=None, label="Initial")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["version"] == "v1" and result["title"] == "Launch plan"
    html = (page.directory / "plans/launch/versions/v1.html").read_text()
    assert "<strong>Observe</strong>" in html and 'data-anchor-id="s:scope"' in html
    source = page.root / "plan.html"
    source.write_text('<h1 data-anchor-id="launch">Revised launch</h1>')
    assert cli.cmd_plan(args(plan_id="launch", from_file=str(source), title="New title", label="Rehearsed")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["version"] == "v2" and result["title"] == "New title"
    assert [entry["label"] for entry in result["history"]] == ["Initial", "Rehearsed"]
    assert (page.directory / "plans/launch/versions/v2.html").read_text() == source.read_text()
    assert before == {name: (page.directory / name).read_bytes() for name in before}


@pytest.mark.parametrize("plan_id,body", [("../escape", "## Scope\n\nText"), ("Bad_ID", "# Text"),
                                         ("good", "```cards\n{bad JSON}\n```"), ("good", "---\nunknown: bad\n---\n# Text")])
def test_plan_invalid_source_or_id_is_refused_without_writes(page, capsys, plan_id, body):
    source = page.root / "bad.md"
    source.write_text(body)
    assert cli.cmd_plan(args(plan_id=plan_id, from_file=str(source), title=None, label=None)) == 2
    assert not (page.directory / "plans").exists()


def test_cards_filter_uses_legacy_defaults_and_preserves_finding_details(page, capsys):
    for category in categories.CATEGORIES:
        assert cli.cmd_cards(args(category=category)) == 0
        cards = json.loads(capsys.readouterr().out)
        assert len(cards) == 1 and cards[0]["category"] == category
    assert cli.cmd_cards(args(category="findings")) == 0
    assert json.loads(capsys.readouterr().out)[0]["finding"]["set"] == "design"


def test_filtered_unread_does_not_consume_other_categories_or_acknowledge_whole_round(page, monkeypatch, capsys):
    from agent_annotate import delivery
    monkeypatch.setattr(delivery, "acknowledge", lambda *a: [] if not a[-1] else pytest.fail("filtered inbox cannot acknowledge whole round"))
    for category in ("findings", "review", "findings"):
        assert cli.cmd_inbox(args(category=category, unread=True, all_events=False)) == 0
        result = json.loads(capsys.readouterr().out)
        expected = 0 if category == "findings" and result["offset_from"] else 1
        assert result["event_count"] == expected
        assert result["card_count"] == 1
    assert cli.cmd_inbox(args(category=None, unread=True, all_events=False)) == 0
    assert json.loads(capsys.readouterr().out)["event_count"] == 4


def test_inbox_filters_mixed_round_and_legacy_events_without_mutating_bus(page, capsys):
    round_event = {"event": "round_submitted", "answers": [{"comment_id": "2" * 12},
                                                            {"comment_id": "1" * 12, "category": "review"}],
                   "edits": [{"block_id": "hero"}]}
    with page.bus.open("a") as stream:
        stream.write(json.dumps(round_event) + "\n")
    before = page.bus.read_bytes()
    assert cli.cmd_inbox(args(category="findings", unread=False, all_events=False)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["event_count"] == 2
    assert result["events"][-1]["answers"] == [{"comment_id": "2" * 12}]
    assert result["events"][-1]["edits"] == []
    assert page.bus.read_bytes() == before


def test_filtered_inbox_retains_session_push_with_comment_ids_and_legacy_copy_events(page, capsys):
    events = [{"event": "session_push", "comment_ids": ["1" * 12, "2" * 12], "edits": [], "comment_count": 2},
              {"event": "copy_updated", "block_count": 1}]
    page.bus.write_text("".join(json.dumps(event) + "\n" for event in events))
    assert cli.cmd_inbox(args(category="findings", unread=False, all_events=False)) == 0
    found = json.loads(capsys.readouterr().out)["events"]
    assert len(found) == 1 and found[0]["comment_ids"] == ["2" * 12] and found[0]["comment_count"] == 1
    assert cli.cmd_inbox(args(category="library", unread=False, all_events=False)) == 0
    found = json.loads(capsys.readouterr().out)["events"]
    assert len(found) == 1 and found[0]["event"] == "copy_updated"


def test_ask_category_flags_and_card_fields_are_passed_to_batch(page, monkeypatch, capsys):
    source = page.root / "cards.json"
    source.write_text(json.dumps([{"number": 5, "anchor_id": "d:q5", "text": "Fix contrast?",
                                   "decision_request": {"prompt": "Fix contrast?", "options": ["fix", "keep"],
                                                        "evidence": [{"label": "Scope", "anchor": "s:scope"}]}},
                                  {"number": 6, "anchor_id": "d:q6", "text": "Fix animation?", "set": "motion",
                                   "decision_request": {"prompt": "Fix animation?", "options": ["fix", "keep"],
                                                        "evidence": [{"label": "Scope", "anchor": "s:scope"}]}}]))
    sent = []
    def api(record, method, path, body, author):
        sent.append(body)
        return 200, {"ids": ["a", "b"], "created": 2, "updated": 0}
    monkeypatch.setattr(cli, "_api", api)
    assert cli.cmd_ask(args(from_file=str(source), category="findings", set="design", version=None, author=None)) == 0
    assert sent[0]["items"][0]["finding"] == {"set": "design", "title": "Fix contrast?"}
    assert sent[0]["items"][1]["finding"]["set"] == "motion"
    assert all(item["category"] == "findings" for item in sent[0]["items"])
    assert json.loads(capsys.readouterr().out)["created"] == 2
    assert categories.load_categories(page.directory)["findings_sets"] == [
        {"id": "design", "label": "design"}, {"id": "motion", "label": "motion"}]


def test_library_json_import_keeps_optional_block_fields_and_groups(page, capsys):
    source = page.root / "library.json"
    block = {"id": "hero", "title": "Hero", "current": "r1", "group": "home", "where": "Home hero", "number": 1,
             "status": "held", "held_note": "Waiting for copy", "question_comment_id": "2" * 12,
             "alternatives": [{"label": "Short", "delta": {"ops": [{"insert": "Short headline\n"}]}}],
             "revisions": [{"id": "r1", "created_at": "2026-10-04T00:00:00Z", "author": {"id": "agent:test", "name": "Test"},
                            "status": "draft", "delta": {"ops": [{"insert": "Headline\n"}]}}]}
    source.write_text(json.dumps({"schema_version": 1, "groups": [{"id": "home", "label": "Home"}], "blocks": [block]}))
    assert cli.cmd_copy(args(from_file=str(source), block=None)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["groups"] == [{"id": "home", "label": "Home"}]
    for key in ("group", "where", "number", "status", "alternatives", "question_comment_id", "held_note"):
        assert result["blocks"][0][key] == block[key]


def test_mcp_category_tools_use_same_storage_and_filters(page):
    pytest.importorskip("mcp")
    tools = {item.name: item for item in asyncio.run(mcp_server.build_server().list_tools())}
    for name in ("list_comments", "list_cards", "read_inbox"):
        schema = getattr(tools[name], "inputSchema", None) or getattr(tools[name], "input_schema")
        assert "category" in schema["properties"]
    assert len(tool("list_comments")("project/main", category="library")) == 1
    assert tool("list_cards")("project/main", "findings")[0]["number"] == 2
    before = page.bus.read_bytes()
    assert tool("read_inbox")("project/main", "plans")["event_count"] == 1
    assert page.bus.read_bytes() == before
    fixed = tool("mark_finding_fixed")("project/main", "2", ["https://example.test/proof"], "Checked")
    assert fixed["fixed"]["note"] == "Checked"
    with pytest.raises(ValueError, match="requires"):
        tool("mark_finding_fixed")("project/main", "2", [])


@pytest.mark.parametrize("command", ["copy", "library"])
def test_copy_and_library_parsers_share_json_output(page, monkeypatch, capsys, command):
    monkeypatch.setattr("sys.argv", ["annotate", command, "project/main", "--json"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["blocks"] == []


@pytest.mark.parametrize("category,set_id", [("review", "design"), ("findings", "../unsafe"), ("invalid", None)])
def test_ask_invalid_category_set_refuses_before_http(page, monkeypatch, capsys, category, set_id):
    source = page.root / "bad-cards.json"
    source.write_text(json.dumps([{"anchor_id": "d:q5", "text": "Fix?"}]))
    monkeypatch.setattr(cli, "_api", lambda *a, **k: pytest.fail("invalid authoring must not write HTTP"))
    assert cli.cmd_ask(args(from_file=str(source), category=category, set=set_id, version="v1", author=None)) == 2
    assert "ERROR" in capsys.readouterr().err


def test_ask_json_category_fields_can_supply_defaults_without_flags(page, monkeypatch, capsys):
    source = page.root / "finding-cards.json"
    source.write_text(json.dumps([{"number": 5, "anchor_id": "d:q5", "text": "Fix?", "category": "findings", "set": "design"}]))
    sent = []
    monkeypatch.setattr(cli, "_api", lambda record, method, path, body, author:
                        (sent.append(body) or 200, {"ids": ["id"], "created": 1, "updated": 0}))
    assert cli.cmd_ask(args(from_file=str(source), version="v1", author=None)) == 0
    assert sent[0]["items"][0]["finding"]["set"] == "design"
    assert sent[0]["items"][0]["category"] == "findings"


def test_plan_oversized_input_leaves_plan_store_absent(page, capsys):
    source = page.root / "large.html"
    with source.open("wb") as stream:
        stream.truncate(categories.MAX_PLAN_BYTES + 1)
    assert cli.cmd_plan(args(plan_id="large", from_file=str(source), title=None, label=None)) == 2
    assert not (page.directory / "plans").exists()


def test_multiple_file_proof_failure_removes_copied_attachments(page, capsys):
    one = page.root / "one.txt"
    one.write_text("one")
    two = page.root / "two.txt"
    two.symlink_to(one)
    assert cli.cmd_finding(args(fixed="2", proof=[str(one), str(two)], note="", author=None)) == 2
    assert not list((page.directory / "attachments").glob("*"))


def test_real_cli_processes_publish_plan_fix_finding_and_read_categories(page):
    import os
    import subprocess
    import sys

    state = page.root / "registry"
    state.mkdir()
    (state / "project.json").write_text(json.dumps({"project": "project", "slugs": {"main": page.record}}))
    env = {**os.environ, "ANNOTATE_STATE_DIR": str(state)}
    def run(*arguments):
        process = subprocess.run([sys.executable, "-m", "agent_annotate.cli", *arguments],
                                 cwd=page.root, env=env, capture_output=True, text=True, timeout=10)
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout)
    source = page.root / "plan.md"
    source.write_text("## Scope\n\nObserve the actual rollout.\n")
    assert run("plan", "project/main", "rollout", "--from", str(source), "--label", "Checked", "--json")["current"] == "v1"
    proof = page.root / "proof.txt"
    proof.write_text("Observed proof")
    assert run("finding", "project/main", "--fixed", "2", "--proof", str(proof), "--json")["fixed"]["proof"]
    assert run("cards", "project/main", "--category", "findings", "--json")[0]["status"] == "addressed_by_agent"
    assert run("inbox", "project/main", "--category", "findings", "--json")["event_count"] == 2
    assert run("library", "project/main", "--json")["blocks"] == []
    assert run("copy", "project/main", "--json")["blocks"] == []


def test_finding_current_and_proposed_proof_store_role_caption_and_size(page, capsys):
    from test_pagegen_images import png
    (page.root / "a.png").write_bytes(png(390, 844))
    (page.root / "b.png").write_bytes(png(390, 844))
    assert cli.cmd_finding(args(fixed="2", proof=["current: a.png | Border today", "proposed: b.png",
                                                  "https://example.test/proof"], note="", author=None)) == 0
    proof = json.loads(capsys.readouterr().out)["fixed"]["proof"]
    assert {k: proof[0][k] for k in ("label", "role", "w", "h")} == {
        "label": "Border today", "role": "current", "w": 390, "h": 844}
    assert proof[1]["role"] == "proposed" and proof[1]["label"] == "b.png" and proof[1]["attachment"].endswith("-b.png")
    assert "role" not in proof[2]


@pytest.mark.parametrize("value, message", [("current: notes.txt", "must be a .png"),
                                            ("proposed: fake.png", "not a readable PNG")])
def test_finding_role_proof_must_be_an_image(page, capsys, value, message):
    (page.root / "notes.txt").write_text("text")
    (page.root / "fake.png").write_text("<html>")
    before = (page.directory / "comments.json").read_bytes()
    assert cli.cmd_finding(args(fixed="2", proof=[value], note="", author=None)) == 2
    assert message in capsys.readouterr().err
    assert (page.directory / "comments.json").read_bytes() == before
    assert not list((page.directory / "attachments").glob("*")) if (page.directory / "attachments").exists() else True


def test_validate_proof_refuses_a_bad_role_or_size(page):
    with pytest.raises(ValueError, match="role"):
        categories.validate_proof(page.directory, [{"label": "x", "url": "https://e.test/a.png", "role": "after"}])
    with pytest.raises(ValueError, match="width and height"):
        categories.validate_proof(page.directory, [{"label": "x", "url": "https://e.test/a.png", "w": True}])


def test_plan_markdown_images_are_copied_into_the_page_assets(page, capsys):
    from test_pagegen_images import png
    (page.root / "shots").mkdir()
    (page.root / "shots" / "board.png").write_bytes(png(1440, 900))
    source = page.root / "plan.md"
    source.write_text("## Look\n\n![Board](shots/board.png)\n")
    assert cli.cmd_plan(args(plan_id="look", from_file=str(source), title=None, label="Shots")) == 0
    name = next((page.directory / "assets").iterdir()).name
    assert f'src="assets/{name}"' in (page.directory / "plans/look/versions/v1.html").read_text()
    source.write_text("## Look\n\n![Board](shots/missing.png)\n")
    assert cli.cmd_plan(args(plan_id="look", from_file=str(source), title=None, label="Shots")) == 2
    assert "image not found: shots/missing.png" in capsys.readouterr().err
