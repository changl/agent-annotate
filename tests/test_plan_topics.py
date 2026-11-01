"""Plans topics (cards #8 and #9): fixed keyword rules file each item, Move to…
pins it and teaches a rule, Unsorted takes what no rule matches, and hidden
items and archive pages stay out."""

import json

import pytest

from agent_annotate import plan_topics as pt

TOPICS = {"topics": [
    {"name": "Rally & navigation", "words": ["rally", "route", "navigation"]},
    {"name": "Release & testing", "words": ["test", "uat", "app store"]},
    {"name": "Sign-in & accounts", "words": ["sign in", "account", "owner"]},
    {"name": "Shop", "words": ["shop"]},
], "learned": [], "placed": {}}


def _page(tmp_path, topics=TOPICS):
    if topics is not None:
        (tmp_path / pt.FILE).write_text(json.dumps(topics))
    return tmp_path


def _plan(identifier, title, section="reference", **extra):
    return {"id": identifier, "title": title, "section": section, **extra}


def test_rules_file_by_the_earliest_keyword_in_the_title():
    config = json.loads(json.dumps(TOPICS))
    # "owner" alone would file this in Sign-in; "UAT" comes first.
    assert pt.topic_for(_plan("a", "UAT results — Monday tester owner review"), config) == "Release & testing"
    assert pt.topic_for(_plan("b", "Shop account and orders"), config) == "Shop"
    # Every word of a phrase rule must start a title word; plurals and longer forms count.
    assert pt.topic_for(_plan("c", "Name in the App Store"), config) == "Release & testing"
    assert pt.topic_for(_plan("d", "Shopping screens"), config) == "Shop"
    assert pt.topic_for(_plan("e", "Rallying point"), config) == "Rally & navigation"
    # A short rule word takes only its plural: "app" never files "apple".
    assert pt.topic_for(_plan("f", "Use Apple's blue"), {"topics": [{"name": "X", "words": ["app"]}], "learned": [], "placed": {}}) == pt.UNSORTED
    # Same position: the topic listed first wins.
    assert pt.topic_for(_plan("g", "Route test"), config) == "Rally & navigation"


def test_unmatched_items_go_to_unsorted_first(tmp_path):
    plans = [_plan("route-central", "Route central plan"), _plan("dns-records", "DNS records")]
    names = pt.file_plans(_page(tmp_path), plans)
    assert [p["topic"] for p in plans] == ["Rally & navigation", pt.UNSORTED]
    assert names == [pt.UNSORTED, "Rally & navigation", "Release & testing", "Sign-in & accounts", "Shop"]
    plans = [_plan("route-central", "Route central plan")]
    assert pt.UNSORTED not in pt.file_plans(tmp_path, plans)


def test_hidden_items_and_archive_pages_stay_out(tmp_path):
    plans = [_plan("route-central", "Route central plan"), _plan("old-route", "Route email", section="hidden"),
             _plan("archive-2026-10", "Route archive", section="archive")]
    pt.file_plans(_page(tmp_path), plans)
    assert [p.get("topic") for p in plans] == ["Rally & navigation", None, None]
    with pytest.raises(KeyError):
        pt.change(tmp_path, plans, {"move": "archive-2026-10", "topic": "Shop"})
    with pytest.raises(KeyError):
        pt.change(tmp_path, plans, {"move": "old-route", "topic": "Shop"})


def test_move_pins_the_item_and_teaches_a_rule(tmp_path):
    plans = [_plan("dns-records", "DNS records for fastlanedrive.com"), _plan("owner-actions", "Owner actions")]
    page = _page(tmp_path)
    assert pt.learned_words("DNS records for fastlanedrive.com") == "dns records"
    config = pt.change(page, plans, {"move": "dns-records", "topic": "Operations", "new": True})
    assert config["placed"] == {"dns-records": "Operations"}
    assert config["learned"] == [{"words": "dns records", "topic": "Operations"}]
    assert config["topics"][-1] == {"name": "Operations", "words": []}
    pt.change(page, plans, {"move": "owner-actions", "topic": "Operations"})
    # The next item of the same kind lands there, as do the moved ones.
    plans.append(_plan("dns-records-2", "DNS records: mail"))
    pt.file_plans(page, plans)
    assert [p["topic"] for p in plans] == ["Operations"] * 3
    stored = json.loads((tmp_path / pt.FILE).read_text())
    assert [r["words"] for r in stored["learned"]] == ["owner actions", "dns records"]


def test_a_newer_move_of_the_same_kind_wins_but_pins_hold(tmp_path):
    plans = [_plan("a", "Event page: approve"), _plan("b", "Event page after booking"), _plan("c", "Event page v3")]
    page = _page(tmp_path)
    pt.change(page, plans, {"move": "a", "topic": "Shop"})
    pt.change(page, plans, {"move": "b", "topic": "Rally & navigation"})
    pt.file_plans(page, plans)
    assert [p["topic"] for p in plans] == ["Shop", "Rally & navigation", "Rally & navigation"]
    assert len(json.loads((tmp_path / pt.FILE).read_text())["learned"]) == 1


def test_move_validation(tmp_path):
    plans = [_plan("a", "Route central")]
    page = _page(tmp_path)
    with pytest.raises(KeyError):
        pt.change(page, plans, {"move": "a", "topic": "Nowhere"})
    with pytest.raises(KeyError):
        pt.change(page, plans, {"move": "missing", "topic": "Shop"})
    with pytest.raises(ValueError):
        pt.change(page, plans, {"move": "a", "topic": "shop", "new": True})
    with pytest.raises(ValueError):
        pt.change(page, plans, {"move": "a", "topic": "Unsorted", "new": True})
    with pytest.raises(ValueError):
        pt.change(page, plans, {"move": "a", "rename": "Shop", "to": "Store"})
    with pytest.raises(ValueError):
        pt.change(page, plans, {"move": "../x", "topic": "Shop"})
    assert json.loads((tmp_path / pt.FILE).read_text()) == TOPICS


def test_rename_and_merge_carry_rules_and_pins(tmp_path):
    plans = [_plan("a", "Shop account"), _plan("b", "Owner actions")]
    page = _page(tmp_path)
    pt.change(page, plans, {"move": "b", "topic": "Shop"})
    config = pt.change(page, plans, {"rename": "Shop", "to": "Store"})
    assert "Store" in [t["name"] for t in config["topics"]] and config["placed"] == {"b": "Store"}
    assert config["learned"][0]["topic"] == "Store"
    with pytest.raises(ValueError):
        pt.change(page, plans, {"rename": "Store", "to": "Release & testing"})
    config = pt.change(page, plans, {"merge": "Store", "into": "Sign-in & accounts"})
    merged = next(t for t in config["topics"] if t["name"] == "Sign-in & accounts")
    assert "shop" in merged["words"] and "Store" not in [t["name"] for t in config["topics"]]
    pt.file_plans(page, plans)
    assert [p["topic"] for p in plans] == ["Sign-in & accounts"] * 2


def test_without_a_topic_list_the_first_one_comes_from_the_titles(tmp_path):
    titles = ["Ask Nicole AI: which version?", "Ask Nicole screens: approve?", "Ask Nicole search: which approach?",
              "After the rally: stops", "Rally rerouting", "Android rally reference", "Chat list: approve the screen?",
              "DNS records", "Feed: approve the proposed screen?"]
    plans = [_plan(str(i), t) for i, t in enumerate(titles)]
    names = pt.file_plans(_page(tmp_path, None), plans)
    assert names == [pt.UNSORTED, "Ask Nicole", "Rally"]
    assert [p["topic"] for p in plans][:6] == ["Ask Nicole"] * 3 + ["Rally"] * 3
    assert not (tmp_path / pt.FILE).exists()  # reading never writes; the first change stores the seed
    pt.change(tmp_path, plans, {"move": "7", "topic": "Ops", "new": True})
    assert [t["name"] for t in json.loads((tmp_path / pt.FILE).read_text())["topics"]] == ["Ask Nicole", "Rally", "Ops"]
