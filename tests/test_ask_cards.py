"""Plain-text ```ask cards, the automatic next version and `publish SLUG --from` (stage 3a, 3c)."""
import argparse
import json

import pytest

from agent_annotate import cli, pagegen
from agent_annotate.review_versions import next_version, stage

CARD = """Use one-step payment?
The receipt remains visible in the comparison.
+ One step: Payment and receipt share a screen.
- Keep current: Payment stays on a separate screen."""


@pytest.mark.parametrize("raw, expected", [
    (CARD, {"source_kind": "ask", "decision_request": {
        "prompt": "Use one-step payment?", "context": "The receipt remains visible in the comparison.",
        "recommendation": "one-step", "options": [
            {"id": "one-step", "label": "One step", "consequence": "Payment and receipt share a screen."},
            {"id": "keep-current", "label": "Keep current", "consequence": "Payment stays on a separate screen."}]}}),
    ("#19012 Ship it?\n- Ship: Goes out.\n- Hold\nsee: cmp:checkout, s:plan\nimpact: HIGH\nblocking: yes\ncatalog: no",
     {"source_kind": "ask", "number": 19012, "decision_request": {
         "prompt": "Ship it?", "options": [{"id": "ship", "label": "Ship", "consequence": "Goes out."},
                                           {"id": "hold", "label": "Hold", "consequence": ""}],
         "evidence": [{"label": "cmp:checkout", "anchor": "cmp:checkout"}, {"label": "s:plan", "anchor": "s:plan"}],
         "impact": "high", "blocking": True, "catalog": False}}),
    ("Start at 10:30?\nTwo lines\nof context.\n+ 10:30 start: Everyone can attend.\n- Later:",
     {"source_kind": "ask", "decision_request": {
         "prompt": "Start at 10:30?", "context": "Two lines of context.", "recommendation": "10-30-start",
         "options": [{"id": "10-30-start", "label": "10:30 start", "consequence": "Everyone can attend."},
                     {"id": "later", "label": "Later", "consequence": ""}]}}),
    ("Keep going?\nsee: s:plan is context before any option", {"source_kind": "ask", "decision_request": {
        "prompt": "Keep going?", "context": "see: s:plan is context before any option"}}),
])
def test_every_line_kind_becomes_todays_card_dict(raw, expected):
    assert pagegen.parse_ask(raw) == expected


@pytest.mark.parametrize("raw, refusal", [
    ("", "is empty"),
    ("+ Yes: first line is an option", "put the question on the fence's first line"),
    ("#0 Zero?\n- A: a", "#0 is not a question number"),
    ("Two picks?\n+ A: a\n+ B: b", "recommends 2 options"),
    ("Twice?\n- Same: a\n- same: b", "two options are named"),
    ("Late context?\n- A: a\nThis line came late.", "comes after the options"),
    ("Option after keys?\n- A: a\nimpact: low\n- B: b", "comes after the options"),
    ("Bad impact?\n- A: a\nimpact: huge", "impact: low, medium or high"),
    ("Bad flag?\n- A: a\nblocking: maybe", "blocking: yes or no"),
    ("No anchor?\n- A: a\nsee:", "see: names no anchor"),
    ("No label?\n- : a", "an option has no label"),
])
def test_each_refusal_names_one_fix(raw, refusal):
    with pytest.raises(pagegen.PageGenError, match=refusal) as caught:
        pagegen.parse_ask(raw)
    assert str(caught.value).count(" · fix: ") == 1


def _source(tmp_path, body):
    source = tmp_path / "page.md"
    source.write_text("---\ntitle: Checkout\n---\n\n" + body)
    return source


def test_a_card_cites_its_section_by_default_and_renders_like_a_json_card(tmp_path):
    ask = _source(tmp_path, "## Plan\n\nPay in one step.\n\n```ask\n" + CARD + "\n```\n")
    result = pagegen.generate(ask, tmp_path / "ask")
    [card] = json.loads(result["cards_json"].read_text())
    assert card["source_kind"] == "ask"
    assert card["decision_request"]["evidence"] == [{"label": "Plan", "anchor": "s:plan"}]
    assert (card["number"], card["anchor_id"]) == (1, "d:q1")
    as_json = dict(card)
    as_json.pop("source_kind")
    js = _source(tmp_path, "## Plan\n\nPay in one step.\n\n```cards\n" + json.dumps([as_json]) + "\n```\n")
    expected = pagegen.generate(js, tmp_path / "json")
    assert (result["html"].read_text().split("<!-- CANVAS")[1]
            == expected["html"].read_text().split("<!-- CANVAS")[1])


def test_stored_source_distinguishes_implicit_asks_from_explicit_section_citations():
    text = ("## Plan\n\n```ask\n#1 First?\n+ Yes: Go.\n- No: Wait.\n```\n\n"
            "```ask\n#2 Explicit section?\n+ Yes: Go.\n- No: Wait.\nsee: s:plan\n```\n\n"
            "```ask\nUnnumbered?\n+ Yes: Go.\n- No: Wait.\n```\n\n"
            "```ask\n#3 Another?\nsee: this is context, before options\n+ Yes: Go.\n- No: Wait.\n```\n")
    assert pagegen.implicit_ask_anchors(text) == ["d:q1", "d:q3"]


def test_see_labels_come_from_the_whole_page_and_unknown_anchors_are_refused(tmp_path):
    later = _source(tmp_path, "## Plan\n\n```ask\nShip?\n- Yes: y\n- No: n\nsee: s:results\n```\n\n## Results\n\nDone.\n")
    [card] = json.loads(pagegen.generate(later, tmp_path / "ok")["cards_json"].read_text())
    assert card["decision_request"]["evidence"] == [{"label": "Results", "anchor": "s:results"}]
    typo = _source(tmp_path, "## Plan\n\n```ask\nShip?\n- Yes: y\n- No: n\nsee: s:resuls\n```\n\n## Results\n\nDone.\n")
    with pytest.raises(pagegen.PageGenError, match="s:resuls"):
        pagegen.generate(typo, tmp_path / "typo")


def test_a_numbered_card_keeps_its_question_anchor(tmp_path):
    source = _source(tmp_path, "## Plan\n\nText.\n\n```ask\n#7 Ship?\n- Yes: y\n- No: n\n```\n")
    [card] = json.loads(pagegen.generate(source, tmp_path / "page")["cards_json"].read_text())
    assert (card["number"], card["anchor_id"]) == (7, "d:q7")


def test_json_cards_fence_is_unchanged(tmp_path):
    source = _source(tmp_path, "## Plan\n\nText.\n\n```cards\n" + json.dumps([{
        "anchor_id": "d:q1", "number": 1, "decision_request": {
            "prompt": "Ship?", "options": ["yes", "no"], "evidence": [{"label": "Plan", "anchor": "s:plan"}]}}]) + "\n```\n")
    [card] = json.loads(pagegen.generate(source, tmp_path / "page")["cards_json"].read_text())
    assert "source_kind" not in card and card["anchor_id"] == "d:q1"


def test_next_version_follows_history_drafts_and_files(tmp_path):
    page = tmp_path / "page"
    assert next_version(page) == "v1"
    (page / "versions").mkdir(parents=True)
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]}))
    assert next_version(page) == "v3"
    stage(page, "v4", "staged", None, {})
    assert next_version(page) == "v5"
    (page / "versions" / "v9.html").write_text("<p>hand-made</p>")
    assert next_version(page) == "v10"


def test_generate_without_a_version_writes_the_next_one(tmp_path):
    source = _source(tmp_path, "## Plan\n\nText.\n")
    page = tmp_path / "page"
    assert pagegen.generate(source, page)["version"] == "v1"
    assert pagegen.generate(source, page)["version"] == "v2"


def _new_args(tmp_path, source, **extra):
    return argparse.Namespace(slug_dir=str(tmp_path / "review"), from_file=str(source), version=None,
                              label=None, project="test", publish=True, ask=False, **extra)


def test_cards_imply_ask_on_publish(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_slug_project", lambda *a: ("test", "review"))
    monkeypatch.setattr("agent_annotate.workspace.duplicate_page", lambda *a: None)
    monkeypatch.setattr(pagegen, "_call_publish", lambda *a: 0)
    monkeypatch.setattr(pagegen, "_call_ask", lambda slug, cards, version, args, renumber: calls.append(version) or 0)
    source = _source(tmp_path, "## Plan\n\nText.\n\n```ask\n" + CARD + "\n```\n")
    assert pagegen.cmd_new(_new_args(tmp_path, source)) == 0
    assert calls == ["v1"]


def test_publish_from_routes_through_new_and_finds_registered_pages(tmp_path, monkeypatch):
    page = tmp_path / "pages" / "review"
    seen = []
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("proj", "review", {"slug_dir": str(page)})])
    monkeypatch.setattr(pagegen, "cmd_new", lambda args: seen.append(args) or 0)
    args = cli.build_parser().parse_args(["publish", "proj/review", "--from", "page.md", "--stage"])
    assert cli.cmd_publish(args) == 0
    assert seen[0].slug_dir == str(page.resolve()) and seen[0].publish is False and seen[0].page_arg == "proj/review"
    args = cli.build_parser().parse_args(["publish", str(tmp_path / "fresh"), "--from", "page.md"])
    assert cli.cmd_publish(args) == 0
    assert seen[1].slug_dir == str((tmp_path / "fresh").resolve()) and seen[1].publish is True


def test_publish_version_alone_shows_a_staged_version(tmp_path, monkeypatch):
    page = tmp_path / "review"
    page.mkdir()
    shown = []
    monkeypatch.setattr(cli, "cmd_publish_version", lambda ns: shown.append((ns.slug_dir, ns.version)) or 0)
    assert cli.cmd_publish(cli.build_parser().parse_args(["publish", str(page), "--version", "v4"])) == 0
    assert shown == [(str(page.resolve()), "v4")]


def test_two_pages_with_one_slug_ask_for_the_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [
        ("a", "review", {"slug_dir": str(tmp_path / "a")}), ("b", "review", {"slug_dir": str(tmp_path / "b")})])
    assert cli.cmd_publish(cli.build_parser().parse_args(["publish", "review", "--from", "page.md"])) == 2
    assert "· fix: use PROJECT/SLUG" in capsys.readouterr().err


def test_staged_receipt_names_the_show_command(tmp_path):
    args = argparse.Namespace(cmd="publish", candidate_version="v412", publish=False,
                              page_arg="proj/review", slug_dir=str(tmp_path))
    assert cli._short_receipt(args, None) == f"v412 staged · show it: {cli._inv()} publish proj/review --version v412"
