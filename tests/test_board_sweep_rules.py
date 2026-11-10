#!/usr/bin/env python3
"""FLD safety fixtures, unchanged apart from the board prefix and sweep import."""
import copy
import datetime
import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bsc", HERE.parent / "scripts/sweep.py")
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)
FIXTURE = json.loads((HERE / "fixtures/board_sweep_checks.json").read_text())
NOW = bsc.parse_ts("2026-11-10T06:05Z")
NOBODY = {"names": set(), "ctxs": set(), "terms": set()}


def run(beads, live=NOBODY, cards=None, now=NOW):
    return bsc.check_board(beads, 0, live, cards or {}, "", now, "FLD")


def test_rule1_live_false_positives_stay_blocked():
    f = run(FIXTURE["beads"])
    assert f["blocked_with_closed_blocker"] == [], f["blocked_with_closed_blocker"]
    # every one of the 19 is still sorted somewhere, none as beads-only
    sorted_ids = {i for ids in f["blocked_sort"].values() for i in ids}
    assert set(FIXTURE["false_positive_ids"]) <= sorted_ids
    assert not set(FIXTURE["false_positive_ids"]) & set(f["blocked_sort"].get("beads_only", []))


def test_rule1_bead_only_shapes():
    beads = [
        {"id": "FLD-ok", "status": "blocked", "notes": "BLOCKED BY: FLD-x1, FLD-x2 | UNBLOCKS WHEN: both close",
         "dependencies": [{"type": "blocks", "depends_on_id": "FLD-x3"}]},
        {"id": "FLD-ok2", "status": "blocked", "notes": "BLOCKED BY (NOT M1MAX16): FLD-x1 and FLD-x2 | x\nolder line"},
        {"id": "FLD-depopen", "status": "blocked", "notes": "BLOCKED BY: FLD-x1",
         "dependencies": [{"type": "blocks", "depends_on_id": "FLD-open"}]},
        {"id": "FLD-noteopen", "status": "blocked", "notes": "BLOCKED BY: FLD-open | UNBLOCKS WHEN: it closes"},
        {"id": "FLD-text", "status": "blocked", "notes": "BLOCKED BY: FLD-x1 (card 2887 plan order) | x"},
        {"id": "FLD-plus", "status": "blocked", "notes": "BLOCKED BY: FLD-x1 and FLD-x2 plus exact production candidate"},
        {"id": "FLD-unknown", "status": "blocked", "notes": "BLOCKED BY: FLD-gone"},
        {"id": "FLD-depsonly", "status": "blocked", "notes": "BLOCKED BY: Chang card 35510",
         "dependencies": [{"type": "blocks", "depends_on_id": "FLD-x1"}]},
        {"id": "FLD-x1", "status": "closed"}, {"id": "FLD-x2", "status": "closed"}, {"id": "FLD-x3", "status": "closed"},
        {"id": "FLD-open", "status": "open"},
    ]
    f = run(beads)
    got = {x["id"]: x["blockers"] for x in f["blocked_with_closed_blocker"]}
    assert got == {"FLD-ok": ["FLD-x1", "FLD-x2", "FLD-x3"], "FLD-ok2": ["FLD-x1", "FLD-x2"]}, got
    assert "FLD-depsonly" in f["blocked_sort"]["owner"]
    assert {"id": "FLD-depsonly", "cards": {"35510": "not_on_page"}} in f["owner_cards"]
    p, _ = bsc.plan(f, None, [], 0, NOW)
    assert sorted(a["bead"] for a in p["actions"]) == ["FLD-ok", "FLD-ok2"]
    assert all(a["before"] == "blocked" and a["after"] == "open" for a in p["actions"])


def test_rule2_reset_guards_and_two_runs():
    live = {"names": {"LIVE-W"}, "ctxs": {"ctx_aaaaaaaaaaaa"}, "terms": {"term_11111111-2222-3333-4444-555555555555"}}
    beads = [
        {"id": "FLD-gone", "status": "in_progress", "assignee": "GONE-1", "notes": "NOW: ctx_bbbbbbbbbbbb was here"},
        {"id": "FLD-line2", "status": "in_progress", "assignee": "X", "notes": "old first line\nNOW: ctx_aaaaaaaaaaaa live"},
        {"id": "FLD-term", "status": "in_progress", "assignee": "Y",
         "notes": "a\nb\nterm_11111111-2222-3333-4444-555555555555 holds it"},
        {"id": "FLD-name", "status": "in_progress", "assignee": "LIVE-W", "notes": ""},
        {"id": "FLD-tldn", "status": "in_progress", "assignee": "m1e", "notes": "NOW: TEST-TIERS-BUILD-LEAD-2 ctx_325c1142083d"},
        {"id": "FLD-lead", "status": "in_progress", "assignee": "TEST-TIERS-BUILD-LEAD-2", "notes": ""},
        {"id": "FLD-human", "status": "in_progress", "assignee": "changlee", "notes": ""},
    ]
    f = run(beads, live)
    assert [x["id"] for x in f["in_progress_without_live_worker"]] == ["FLD-gone"], f
    assert sorted(x["id"] for x in f["in_progress_guarded"]) == ["FLD-human", "FLD-lead", "FLD-tldn"]
    p1, s1 = bsc.plan(f, None, [], 0, NOW)
    assert p1["actions"] == []  # first flag: no reset
    p2, s2 = bsc.plan(f, s1, [], 0, NOW + datetime.timedelta(minutes=10))
    assert p2["actions"] == []  # manual re-run inside the hour does not count as a second hourly run
    p3, _ = bsc.plan(f, s2, [], 0, NOW + datetime.timedelta(hours=1))
    assert [(a["bead"], a["rule"], a["after"]) for a in p3["actions"]] == [("FLD-gone", "reset-no-live-worker", "open")]
    # cleared in between: the clock restarts
    f_live = run(beads, dict(live, ctxs=live["ctxs"] | {"ctx_bbbbbbbbbbbb"}))
    _, s_clear = bsc.plan(f_live, s1, [], 0, NOW + datetime.timedelta(minutes=30))
    p4, _ = bsc.plan(f, s_clear, [], 0, NOW + datetime.timedelta(hours=1))
    assert p4["actions"] == []


def test_rule6_settled_delta():
    beads = copy.deepcopy(FIXTURE["beads"])
    for b in beads:  # on the live board all 19 carry the AUDIT-1220Z keep-blocked line
        if b["id"] in FIXTURE["false_positive_ids"]:
            b["notes"] += "\nAUDIT-1220Z 2026-11-09T17:46:19Z: Keep blocked: fixture"
    beads += [
        {"id": "FLD-c", "status": "blocked", "notes": "BLOCKED BY: owner card 2959 | x"},
        {"id": "FLD-odd", "status": "blocked", "notes": "BLOCKED BY: waiting for the moon | x"},
        {"id": "FLD-oddjudged", "status": "blocked", "notes": "BLOCKED BY: a comet | x\nAUDIT-1220Z 2026-11-09T17:46Z: Keep blocked"},
    ]
    f1 = run(beads, cards={"2959": False})
    p1, s1 = bsc.plan(f1, None, ["FLD-r1"], 2, NOW)
    assert p1["baseline"] and p1["new_flags"]
    assert p1["needs_model"]["unsettled"] == ["sort-other:FLD-odd"], p1["needs_model"]  # judged item not re-flagged
    assert p1["needs_model"]["new_ready"] == []
    later = NOW + datetime.timedelta(hours=1)
    p2, s2 = bsc.plan(run(beads, cards={"2959": False}), s1, ["FLD-r1"], 2, later)
    assert p2["new_flags"] == [] and p2["cleared_flags"] == [] and p2["needs_model"]["unsettled"] == []
    # card answered -> one new unsettled item; new ready bead with free slot -> listed; at cap -> not listed
    p3, s3 = bsc.plan(run(beads, cards={"2959": True}), s2, ["FLD-r1", "FLD-r2"], 2, later)
    assert p3["new_flags"] == ["card-answered:FLD-c"] and p3["cleared_flags"] == ["card-waiting:FLD-c"]
    assert p3["needs_model"]["unsettled"] == ["card-answered:FLD-c"]
    assert p3["needs_model"]["new_ready"] == ["FLD-r2"]
    p4, _ = bsc.plan(run(beads, cards={"2959": True}), s2, ["FLD-r1", "FLD-r2"], 8, later)
    assert p4["needs_model"]["new_ready"] == []


def test_card_numbers():
    assert bsc.card_numbers("owner B3 HOLD cards2748-2751") == ["2748", "2749", "2750", "2751"]
    assert bsc.card_numbers("Chang card #37518, d:q2876, card 2962") == ["2876", "2962", "37518"]

