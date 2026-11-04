"""Annotate numbers ask cards itself: reservation, 409 regenerate, relaxed rules (stage 3b)."""
import argparse
import json

import pytest
from test_version_ready import _http, _page, round_server  # noqa: F401 - the fixture

from agent_annotate import cli, pagegen, sync_server
from agent_annotate.review_versions import fingerprint, read_draft

ASK = "```ask\n{q}\n+ Yes: It ships.\n- No: It waits.\n```\n"


def _source(tmp_path, *questions, name="page.md", head="---\ntitle: Round\n---\n\n## Evidence\n\nReady.\n\n"):
    source = tmp_path / name
    source.write_text(head + "\n".join(ASK.format(q=q) for q in questions))
    return source


def _store(directory, *comments):
    anchors = {}
    for c in comments:
        anchors.setdefault(c["anchor_id"], []).append(c)
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": {}}))


def test_new_cards_continue_after_archived_and_legacy_numbers(tmp_path):
    directory = _page(tmp_path)
    archived = {"id": "a", "anchor_id": "s:old", "version": "v1", "number": 40, "status": "archived"}
    legacy = {"id": "b", "anchor_id": "s:old", "version": "v1", "status": "open",
              "decision_request": {"prompt": "Q45 Old question?"}}
    _store(directory, archived, legacy)
    result = pagegen.generate(_source(tmp_path, "Ship it?", "Ship later?", "#45 Old question?"), directory)
    cards = json.loads(result["cards_json"].read_text())
    assert [(c["number"], c["anchor_id"]) for c in cards] == [(46, "d:q46"), (47, "d:q47"), (45, "d:q45")]
    assert read_draft(directory, "v2")["reserved"] == [46, 47]
    stored = result["source_copy"].read_text()
    assert "#46 Ship it?" in stored and "#47 Ship later?" in stored and stored.count("#45 ") == 1


def test_two_drafts_reserve_different_numbers_and_a_regeneration_reuses_its_own(tmp_path):
    directory = _page(tmp_path)
    first = pagegen.generate(_source(tmp_path, "One?", "Two?"), directory)
    second = pagegen.generate(_source(tmp_path, "Three?"), directory)
    assert (first["version"], first["reserved"]) == ("v2", [1, 2])
    assert (second["version"], second["reserved"]) == ("v3", [3])
    assert pagegen.generate(_source(tmp_path, "Three?"), directory, "v3")["reserved"] == [3]
    assert pagegen.generate(_source(tmp_path, "One?", "Two?"), directory, "v2")["reserved"] == [4, 5]


def test_a_draft_written_during_generation_moves_the_numbers(tmp_path, monkeypatch):
    directory = _page(tmp_path)
    real = pagegen._reserve_numbers
    calls = []

    def racing(slug_dir, version, blocks):
        numbers = real(slug_dir, version, blocks)
        if not calls:  # a concurrent publish stages its draft between our read and our locked write
            (directory / ".review-drafts").mkdir(exist_ok=True)
            sync_server._atomic_write_json(directory / ".review-drafts/v9.json", {"version": "v9", "reserved": numbers})
        calls.append(numbers)
        return numbers

    monkeypatch.setattr(pagegen, "_reserve_numbers", racing)
    result = pagegen.generate(_source(tmp_path, "One?"), directory)
    assert calls == [[1], [2]] and result["reserved"] == [2]


def _publish_flow(directory, httpd, monkeypatch, before_ask=None):
    record = {"slug_dir": str(directory), "port": httpd.server_port, "local_url": f"http://127.0.0.1:{httpd.server_port}"}
    monkeypatch.setattr(cli, "_slug_project", lambda *a: ("test", "review"))
    monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *a: ("test", "review", record))
    monkeypatch.setattr("agent_annotate.workspace.duplicate_page", lambda *a: None)
    attempts = []

    def checked(slug_dir, args):  # what `publish` records once the page passes its checks
        draft = read_draft(directory, args.candidate_version)
        draft.update(verified=True, fingerprint=fingerprint(directory, args.candidate_version))
        sync_server._atomic_write_json(directory / f".review-drafts/{args.candidate_version}.json", draft)
        attempts.append(draft["reserved"])
        if before_ask:
            before_ask(draft)
        return 0

    monkeypatch.setattr(pagegen, "_call_publish", checked)
    return attempts


def test_a_number_taken_before_commit_regenerates_silently(round_server, tmp_path, monkeypatch, capsys):  # noqa: F811
    directory, httpd = round_server

    def reviewer_takes(draft):
        if len(attempts) == 1:
            assert _http(httpd, "POST", "/api/comments", {"anchor_id": "s:old", "text": "Mine", "number": draft["reserved"][0]})[0] == 201

    attempts = _publish_flow(directory, httpd, monkeypatch, reviewer_takes)
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(_source(tmp_path, "Ship it?")), version=None,
                              label=None, project="test", publish=True, ask=False)
    assert pagegen.cmd_new(args) == 0
    assert attempts == [[1], [2]]
    assert "ERROR" not in capsys.readouterr().err
    assert cli._read_meta(directory)["current"] == "v2"
    store = json.loads((directory / "comments.json").read_text())
    assert [c["number"] for c in store["anchors"]["d:q2"]] == [2] and "d:q1" not in store["anchors"]


def test_a_third_conflict_names_the_fix(tmp_path, monkeypatch, capsys):
    directory = _page(tmp_path)
    monkeypatch.setattr(cli, "_slug_project", lambda *a: ("test", "review"))
    monkeypatch.setattr("agent_annotate.workspace.duplicate_page", lambda *a: None)
    monkeypatch.setattr(pagegen, "_call_publish", lambda *a: 0)
    calls = []
    monkeypatch.setattr(pagegen, "_call_ask", lambda *a: calls.append(a[2]) or cli.NUMBERS_TAKEN)
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(_source(tmp_path, "Ship it?")), version=None,
                              label=None, project="test", publish=True, ask=False)
    assert pagegen.cmd_new(args) == 2
    assert calls == ["v2", "v2", "v2"]
    assert capsys.readouterr().err.strip() == ("not live: numbers kept colliding with another publish"
                                               " · fix: rerun the same command")


FULL = "---\ntitle: Round\nfull_plan: true\nother_files_required: none\n---\n\n## Evidence\n\nReady.\n\n"


def test_ask_cards_skip_the_numbered_round_rules_and_json_cards_keep_them(tmp_path):
    directory = _page(tmp_path)
    assert pagegen.generate(_source(tmp_path, "Ship it?", head=FULL), directory)["cards"] == 1
    bad = tmp_path / "json.md"
    bad.write_text(FULL + "```cards\n" + json.dumps([{"anchor_id": "d:x", "decision_request": {
        "prompt": "Ship?", "options": ["yes", "no"], "evidence": [{"label": "E", "anchor": "s:evidence"}]}}]) + "\n```\n")
    with pytest.raises(pagegen.PageGenError, match="positive integer `number`"):
        pagegen.generate(bad, directory, "v3")


def test_ask_command_relaxes_only_ask_cards(tmp_path, monkeypatch, capsys):
    directory = _page(tmp_path)
    record = {"slug_dir": str(directory)}
    monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *a: ("test", "review", record))
    evidence = [{"label": "E", "anchor": "s:old"}]
    json_card = {"anchor_id": "d:q9", "number": 9, "decision_request": {"prompt": "A?", "evidence": evidence}}
    ask_card = {"anchor_id": "d:q5", "number": 5, "source_kind": "ask", "decision_request": {"prompt": "B?", "evidence": evidence}}
    cards = tmp_path / "cards.json"

    def ask(*items):
        cards.write_text(json.dumps(list(items)))
        cli.cmd_ask(argparse.Namespace(slug="review", project="test", from_file=str(cards), version="v3", author="agent:t", json=False))
        return capsys.readouterr().err

    assert "strictly increasing" not in ask(json_card, ask_card)
    assert "strictly increasing" in ask(json_card, {**ask_card, "source_kind": None})
