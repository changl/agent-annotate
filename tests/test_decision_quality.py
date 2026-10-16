"""Card refusals are narrow, atomic, and shared by new and ask."""

import json
from types import SimpleNamespace

import pytest

from agent_annotate import cli, pagegen
from agent_annotate.decision_quality import card_refusal


def _card(prompt="Approve the timeout?", **request):
    return {"anchor_id": "d:question", "decision_request": {"prompt": prompt, **request}}


@pytest.mark.parametrize("fields", [
    {"prompt": "Accept all 41"},
    {"prompt": "Approve all?"},
    {"prompt": "Confirm both changes?"},
    {"prompt": "Approve these 41 recommendations?"},
    {"prompt": "Confirm the 2 rows?"},
    {"prompt": "Accept 10 items?"},
    {"options": ["Accept all", "Keep reviewing"]},
    {"options": [{"id": "accept_all", "label": "Continue"}]},
    {"prompt": "Approve these?", "options": [{"id": "yes", "label": "All 41 recommendations"}]},
])
def test_explicit_bulk_approval_is_refused(fields):
    assert "one decision" in card_refusal(_card(**fields), {"d:question"})


@pytest.mark.parametrize("fields", [
    {"prompt": "Approve 1 item?"},
    {"prompt": "Use a timeout of 41 seconds?"},
    {"prompt": "Choose between 3 recommendations?"},
    {"prompt": "Approve the timeout?", "context": "There are 41 rows in the report."},
    {"prompt": "Confirm the fallback?", "options": ["Accept", "Reject"]},
    {"prompt": "Keep all rows visible?"},
    {"prompt": "Approve the limit of 2 rows per page?"},
    {"prompt": "Confirm changing the minimum to 3 items?"},
])
def test_single_decisions_and_comparisons_are_not_bulk_approval(fields):
    assert card_refusal(_card(evidence=[{"anchor": "s:scope"}], **fields), {"s:scope", "d:question"}) is None


def test_every_evidence_target_must_exist_and_card_cannot_be_its_own_evidence():
    card = _card(evidence=[{"anchor": "s:gone"}, {"anchor": "s:scope"}])
    assert "s:gone" in card_refusal(card, {"s:scope", "d:question"})
    assert card_refusal(card, {"s:gone", "s:scope"}) is None
    assert "at least one" in card_refusal(_card(), {"d:question"})
    assert "visible content" in card_refusal(_card(evidence=[{"anchor": "d:question"}]), {"d:question"})


def _snapshot(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("bad", [
    _card("Accept all 41"),
    _card(evidence=[{"anchor": "s:missing"}]),
])
def test_ask_refuses_whole_batch_in_one_line_without_writing(tmp_path, monkeypatch, capsys, bad):
    directory = tmp_path / "page"
    (directory / "versions").mkdir(parents=True)
    (directory / "versions" / "v2.html").write_text('<p data-anchor-id="s:scope">Evidence</p>')
    (directory / "comments.json").write_text('{"schema_version":2,"anchors":{},"archived":{}}')
    source = tmp_path / "cards.json"
    valid = _card("Choose an option letter: A/B?", evidence=[{"anchor": "s:scope"}])
    source.write_text(json.dumps([valid, bad]))
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("reviews", "demo", {"slug_dir": str(directory)})])
    monkeypatch.setattr(cli, "_api", lambda *a: pytest.fail("refused batch reached the API"))
    before = _snapshot(directory)
    assert cli.cmd_ask(SimpleNamespace(slug="reviews/demo", from_file=str(source), version="v2",
                                      project=None, author=None, json=False)) == 2
    captured = capsys.readouterr()
    assert len(captured.err.splitlines()) == 1
    assert not captured.out
    assert _snapshot(directory) == before


def test_new_refuses_bulk_approval_before_writing_existing_page(tmp_path, monkeypatch, capsys):
    directory = tmp_path / "page"
    directory.mkdir()
    (directory / "keep.txt").write_text("Existing reviewer content")
    source = tmp_path / "source.md"
    source.write_text('## Proposal\n\nA change.\n\n```cards\n' + json.dumps([_card("Accept all 41")]) + '\n```\n')
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    before = _snapshot(directory)
    assert pagegen.cmd_new(SimpleNamespace(slug_dir=str(directory), from_file=str(source),
        project="reviews", version="v2", label=None, publish=True, ask=True, exception=None)) == 1
    captured = capsys.readouterr()
    assert len(captured.err.splitlines()) == 1
    assert "one decision" in captured.err
    assert not captured.out
    assert _snapshot(directory) == before


def test_new_checks_rendered_anchors_instead_of_trusting_registry(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.md"
    source.write_text('## Proposal\n\nA change.\n\n```cards\n' + json.dumps([_card()]) + '\n```\n')
    render = pagegen.render

    def missing_location(*args):
        canvas, registry, cards = render(*args)
        return canvas.replace('data-anchor-id="d:question"', ''), registry, cards

    monkeypatch.setattr(pagegen, "render", missing_location)
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    directory = tmp_path / "page"
    assert pagegen.cmd_new(SimpleNamespace(slug_dir=str(directory), from_file=str(source),
        project="reviews", version="v1", label=None, publish=True, ask=True, exception=None)) == 1
    assert len(capsys.readouterr().err.splitlines()) == 1
    assert not directory.exists()
