"""`publish SLUG --from FILE --section NAME` replaces one ## block of the newest source (stage 3d)."""
import argparse
import json

import pytest
from test_ask_numbers import _publish_flow
from test_version_ready import _page, round_server  # noqa: F401 - the fixture

from agent_annotate import cli, pagegen
from agent_annotate.review_versions import stage

BASE = """---
title: Checkout
version: v1
label: First draft
---

Intro before any section.

## Results

Old results.

```text
## not a heading inside a fence
```

## Plan

Pay in one step.

```ask
#1 Use one-step payment?
+ One step: Payment and receipt share a screen.
- Keep current: Payment stays separate.
```

## Questions for reviewer

```ask
#2 Ship on Friday?
+ Friday: It ships.
- Monday: It waits.
```
"""


def _base(directory, text=BASE, version="v1", shown=True):
    (directory / "source").mkdir(parents=True, exist_ok=True)
    (directory / "source" / f"{version}.md").write_text(text)
    if shown:
        (directory / "current.meta.json").write_text(json.dumps({"current": version, "history": [{"version": version}]}))
    else:
        stage(directory, version, "staged", None, {})


def _blocks(text):
    lines = text.split("\n")
    return {heading: "\n".join(lines[start:end]) for start, end, heading in pagegen._h2_blocks(lines)}


def test_replacing_a_section_keeps_every_other_section_byte_identical(tmp_path):
    _base(tmp_path)
    merged = pagegen.section_source(tmp_path, "New results.\n\n- One\n- Two\n", "results")
    old, new = _blocks(BASE.split("---\n", 2)[2]), _blocks(merged["text"])
    assert list(new) == ["Results", "Plan", "Questions for reviewer"]
    assert new["Plan"] == old["Plan"] and new["Questions for reviewer"] == old["Questions for reviewer"]
    assert new["Results"].startswith("## Results\n\nNew results.") and "Old results" not in merged["text"]
    assert "Intro before any section." in merged["text"]
    meta, _ = pagegen.parse_front_matter(merged["text"])
    assert meta == {"title": "Checkout"}  # the base's version and label never carry over
    assert (merged["base"], merged["section"], merged["kept"]) == ("v1", "Results", [1, 2])


def test_a_file_with_its_own_heading_replaces_the_heading_and_anchors_match(tmp_path):
    _base(tmp_path)
    merged = pagegen.section_source(tmp_path, "---\nlabel: Results in\n---\n## Results, measured\n\nDone.\n", "s:results")
    assert "## Results, measured\n\nDone." in merged["text"] and "## Results\n" not in merged["text"]
    assert pagegen.parse_front_matter(merged["text"])[0]["label"] == "Results in"


def test_an_unknown_or_repeated_section_names_the_choices(tmp_path):
    _base(tmp_path)
    with pytest.raises(pagegen.PageGenError) as caught:
        pagegen.section_source(tmp_path, "x", "Resuls")
    assert str(caught.value) == 'no section "Resuls" on v1 · fix: --section one of Results, Plan, Questions for reviewer'
    _base(tmp_path, "## Plan\n\nA\n\n## Plan\n\nB\n", version="v2")
    with pytest.raises(pagegen.PageGenError, match="fix: --section one of s:plan, s:plan-2"):
        pagegen.section_source(tmp_path, "x", "plan")
    assert "B" in pagegen.section_source(tmp_path, "C", "s:plan")["text"].split("## Plan")[2]


def test_the_newest_staged_draft_is_the_base(tmp_path):
    _base(tmp_path)
    _base(tmp_path, BASE.replace("Old results.", "Staged results."), version="v2", shown=False)
    merged = pagegen.section_source(tmp_path, "Plan text.", "Plan")
    assert merged["base"] == "v2" and "Staged results." in merged["text"]


def test_answered_questions_leave_kept_sections_and_open_ones_stay(tmp_path):
    _base(tmp_path)
    answered = {"id": "a", "anchor_id": "d:q1", "number": 1, "author": "agent:x", "status": "open",
                "decision_request": {"prompt": "Use one-step payment?"}, "decision": {"verdict": "select"}}
    asked = {"id": "b", "anchor_id": "d:q2", "number": 2, "author": "agent:x", "status": "open",
             "decision_request": {"prompt": "Ship on Friday?"}}
    (tmp_path / "comments.json").write_text(json.dumps({"anchors": {"d:q1": [answered], "d:q2": [asked]}, "archived": {}}))
    merged = pagegen.section_source(tmp_path, "New.", "Results")
    assert "#1 Use one-step" not in merged["text"] and "#2 Ship on Friday?" in merged["text"]
    assert merged["kept"] == [2]


def test_json_cards_in_kept_sections_drop_answered_entries(tmp_path):
    cards = [{"number": 1, "anchor_id": "d:q1", "decision_request": {"prompt": "A?"}},
             {"number": 2, "anchor_id": "d:q2", "decision_request": {"prompt": "B?"}}]
    _base(tmp_path, "## Results\n\nOld.\n\n## Questions for reviewer\n\n```cards\n" + json.dumps(cards) + "\n```\n")
    (tmp_path / "comments.json").write_text(json.dumps({"anchors": {"d:q1": [
        {"id": "a", "number": 1, "status": "resolved_in_version", "decision_request": {"prompt": "A?"}}]}, "archived": {}}))
    merged = pagegen.section_source(tmp_path, "New.", "Results")
    fence = merged["text"].split("```cards\n")[1].split("\n```")[0]
    assert [c["number"] for c in json.loads(fence)] == [2] and merged["kept"] == [2]


def test_a_page_without_markdown_cannot_replace_a_section(tmp_path):
    with pytest.raises(pagegen.PageGenError, match="fix: publish the whole page with --from first"):
        pagegen.section_source(tmp_path, "x", "Results")


def test_section_publish_carries_open_questions_with_their_numbers(round_server, tmp_path, monkeypatch):  # noqa: F811
    directory, httpd = round_server
    _publish_flow(directory, httpd, monkeypatch)
    page = tmp_path / "page.md"
    page.write_text("---\ntitle: Checkout\n---\n\n## Results\n\nOld.\n\n## Plan\n\nPay.\n\n"
                    "```ask\nUse one-step payment?\n+ One step: Shared screen.\n- Keep current: Separate.\n```\n")
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(page), version=None,
                              label=None, project="test", publish=True, ask=False)
    assert pagegen.cmd_new(args) == 0
    first = json.loads((directory / "comments.json").read_text())["anchors"]["d:q1"][0]
    part = tmp_path / "results.md"
    part.write_text("Measured.\n\n```ask\nShip it?\n+ Ship: Goes out.\n- Hold: Waits.\n```\n")
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(part), version=None, section="Results",
                              label=None, project="test", publish=True, ask=False, cmd="publish")
    assert pagegen.cmd_new(args) == 0
    assert cli._read_meta(directory)["current"] == "v3"
    store = json.loads((directory / "comments.json").read_text())
    carried = [c for c in store["anchors"]["d:q1"] if c["version"] == "v3"]
    assert len(carried) == 1 and carried[0]["number"] == 1 and carried[0]["origin_id"] == first["id"]
    assert [c["number"] for c in store["anchors"]["d:q2"]] == [2]
    assert "Old." not in (directory / "source/v3.md").read_text()
    record = {"slug_dir": str(directory)}
    assert cli._short_receipt(args, record) == "v3 live · Results replaced · 1 card #2 · 1 kept"


def test_a_question_set_aside_stays_set_aside_when_asked_again(round_server, tmp_path, monkeypatch):  # noqa: F811
    """Chang #234: "answer later" questions came back on every new version."""
    directory, httpd = round_server
    _publish_flow(directory, httpd, monkeypatch)
    page = tmp_path / "page.md"
    page.write_text("---\ntitle: Checkout\n---\n\n## Results\n\nOld.\n\n## Plan\n\nPay.\n\n"
                    "```ask\nUse one-step payment?\n+ One step: Shared screen.\n- Keep current: Separate.\n```\n")
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(page), version=None,
                              label=None, project="test", publish=True, ask=False)
    assert pagegen.cmd_new(args) == 0
    store = json.loads((directory / "comments.json").read_text())
    first = store["anchors"]["d:q1"][0]
    first["answer_later"] = {"ts": "2026-11-07T07:00:00Z", "by": "chang@example.com"}  # as the server's answer-later route stores it
    (directory / "comments.json").write_text(json.dumps(store))
    part = tmp_path / "results.md"
    part.write_text("Measured.\n")
    args = argparse.Namespace(slug_dir=str(directory), from_file=str(part), version=None, section="Results",
                              label=None, project="test", publish=True, ask=False, cmd="publish")
    assert pagegen.cmd_new(args) == 0
    carried = [c for c in json.loads((directory / "comments.json").read_text())["anchors"]["d:q1"] if c["version"] == "v3"]
    assert len(carried) == 1 and carried[0]["origin_id"] == first["id"] and carried[0].get("answer_later")

    def republish(change):
        store = json.loads((directory / "comments.json").read_text())
        change(store["anchors"]["d:q1"][-1])
        (directory / "comments.json").write_text(json.dumps(store))
        assert pagegen.cmd_new(args) == 0
        return json.loads((directory / "comments.json").read_text())["anchors"]["d:q1"][-1]

    # A copy made before the fix lost the mark; the next re-ask finds it on an older copy.
    assert republish(lambda c: c.pop("answer_later"))["answer_later"] == first["answer_later"]
    # Brought back on purpose (the route stores False): a re-ask leaves it in front of the reviewer.
    assert not republish(lambda c: c.__setitem__("answer_later", False)).get("answer_later")


def test_kept_sections_render_from_the_page_copies_of_their_images(tmp_path):
    from test_pagegen_images import png
    page, work = tmp_path / "page", tmp_path / "agent-worktree"
    for name, shade in (("a/today.png", (10, 20, 30)), ("b/today.png", (200, 100, 50))):
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_bytes(png(390, 844, shade))
    source = work / "page.md"
    source.write_text("## Results\n\nOld.\n\n## Screens\n\n![Today](a/today.png)\n\n## More\n\n![Today again](b/today.png)\n")
    first = pagegen.generate(source, page)
    stored = first["source_copy"].read_text()
    assert "a/today.png" not in stored and stored.count("](assets/") == 2  # the stored source names the page copies
    legacy = page / "source" / "v1.md"  # a page written before stage 3 names the author's files
    legacy.write_text(source.read_text())
    for name in ("a/today.png", "b/today.png"):
        (work / name).unlink()  # the files stayed in another worktree
    merged = pagegen.section_source(page, "New results.", "Results")
    assert "a/today.png" not in merged["text"] and "b/today.png" not in merged["text"]
    part = tmp_path / "elsewhere" / "results.md"
    part.parent.mkdir()
    part.write_text("New results.")
    second = pagegen.generate(part, page, text=merged["text"])
    copies = sorted(p.name for p in (page / "assets").glob("*-today.png"))
    assert len(copies) == 2 and all(f"assets/{c}" in second["html"].read_text() for c in copies)


def test_image_paths_in_alt_text_and_compare_lines_are_rewritten_once():
    text = "![a.png](a.png)\n\n```compare\ncurrent: a.png | Today\nproposed: b.png\n```\n\n```text\n![x](a.png)\n```\n"
    out = pagegen._image_refs(text, {"a.png": "assets/1-a.png", "b.png": "assets/2-b.png"})
    assert out.split("\n")[0] == "![a.png](assets/1-a.png)"
    assert "current: assets/1-a.png | Today" in out and "proposed: assets/2-b.png" in out
    assert "```text\n![x](a.png)\n```" in out  # code stays as written


def test_a_version_picked_twice_is_picked_again_under_the_lock(tmp_path, monkeypatch):
    from agent_annotate import review_versions
    page = tmp_path / "page"
    source = tmp_path / "page.md"
    source.write_text("## Plan\n\nText.\n\n```ask\nShip?\n+ Yes: y\n- No: n\n```\n")
    first = pagegen.generate(source, page)
    real, calls = review_versions.next_version, []
    monkeypatch.setattr(review_versions, "next_version", lambda d: calls.append(1) or ("v1" if len(calls) == 1 else real(d)))
    second = pagegen.generate(source, page)  # picked v1 before the first publish staged it
    assert (first["version"], second["version"]) == ("v1", "v2") and second["reserved"] == [2]


def test_a_section_publish_overtaken_by_another_lands_on_top_of_it(round_server, tmp_path, monkeypatch):  # noqa: F811
    directory, httpd = round_server
    attempts = _publish_flow(directory, httpd, monkeypatch)
    page = tmp_path / "page.md"
    page.write_text("---\ntitle: Checkout\n---\n\n## Results\n\nOld results.\n\n## Plan\n\nOld plan.\n")
    base = argparse.Namespace(slug_dir=str(directory), version=None, label=None, project="test", publish=True, ask=False)
    assert pagegen.cmd_new(argparse.Namespace(**vars(base), from_file=str(page))) == 0
    results, plan = tmp_path / "results.md", tmp_path / "plan.md"
    results.write_text("New results.\n")
    plan.write_text("New plan.\n")
    checked = pagegen._call_publish

    def other_session_lands_first(slug_dir, args):
        rc = checked(slug_dir, args)
        if len(attempts) == 2:  # between this draft's checks and its commit
            assert pagegen.cmd_new(argparse.Namespace(**vars(base), from_file=str(plan), section="Plan")) == 0
        return rc

    monkeypatch.setattr(pagegen, "_call_publish", other_session_lands_first)
    assert pagegen.cmd_new(argparse.Namespace(**vars(base), from_file=str(results), section="Results")) == 0
    meta = cli._read_meta(directory)
    shown = (directory / "source" / f"{meta['current']}.md").read_text()
    assert [h["version"] for h in meta["history"]] == ["v1", "v2", "v4", "v5"]
    assert "New results." in shown and "New plan." in shown
