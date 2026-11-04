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
