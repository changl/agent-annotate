"""Stored canonical labels and historical reservations agree with the UI."""

import json
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.cli import _decision_cards


def _card(cid, number=None, **changes):
    card = {"id": cid, "anchor_id": "d:q13", "version": "v2", "status": "open",
            "created_at": "2026-09-30T09:00:00Z", "decision_request": {"prompt": "Choose a response?"}}
    if number is not None:
        card["number"] = number
    card.update(changes)
    return card


def test_reposed_explicit_question_keeps_its_label_when_prior_round_remains_in_history():
    store = {"anchors": {"d:q13": [
        _card("prior", 13, version="v1", status="resolved_in_version"), _card("current", 13),
    ], "d:q14": [_card("carried", 14, anchor_id="d:q14", carry_history=[{"version": "v1"}])],
        "d:q15": [_card("new", 15, anchor_id="d:q15")]}, "archived": {}}
    assert {card["id"]: card["number"] for card in _decision_cards(store)} == {
        "current": 13, "carried": 14, "new": 15,
    }


@pytest.mark.parametrize("archived", [
    {"d:old": [_card("old", 21, status="archived")]},
    {"old": _card("old", 21, status="archived")},
    [_card("old", 21, status="archived")],
])
def test_archived_questions_reserve_labels_without_becoming_live_cards(archived):
    store = {"anchors": {"s:coverage": [_card("legacy", anchor_id="s:coverage")]}, "archived": archived}
    assert [(card["id"], card["number"]) for card in _decision_cards(store)] == [("legacy", 22)]


def test_legacy_q_prefix_stays_canonical_when_same_question_exists_in_prior_version():
    store = {"anchors": {"d:q13": [_card("prior", 13, status="resolved_in_version"),
                                   _card("legacy", decision_request={"prompt": "Q13: Choose a response?"})]}, "archived": {}}
    assert [(card["id"], card["number"]) for card in _decision_cards(store)] == [("legacy", 13)]


@pytest.mark.parametrize("archived, expected", [
    ({"d:old": [_card("old", 21, status="archived")]}, 22),
    ([_card("old", 21, status="archived")], 22),
    ("malformed history", 1),
])
def test_real_cmd_cards_loads_archive_reservations_without_mutating_store(tmp_path, monkeypatch, capsys, archived, expected):
    state, directory = tmp_path / "state", tmp_path / "demo"
    state.mkdir()
    directory.mkdir()
    record = {"slug_dir": str(directory), "slug": "demo", "project": "proj"}
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {"demo": record}}))
    store = directory / "comments.json"
    store.write_text(json.dumps({"schema_version": 2, "anchors": {"s:coverage": [_card("legacy")]}, "archived": archived}))
    original = store.read_bytes()
    monkeypatch.setattr(cli, "STATE_DIR", state)
    loaded = cli._load_store(record)
    assert loaded["archived"] == (archived if isinstance(archived, (dict, list)) else [])
    assert cli.cmd_cards(SimpleNamespace(slug="demo", project="proj", json=True)) == 0
    cards = json.loads(capsys.readouterr().out)
    assert [(card["id"], card["number"]) for card in cards] == [("legacy", expected)]
    assert store.read_bytes() == original
    assert not (state / "bus-offsets").exists()
