"""Long pages: previews, Earlier updates and archive pages, all decided by publish."""

import datetime
import json
from pathlib import Path

import pytest
from test_pagegen_images import png, write

from agent_annotate import long_pages
from agent_annotate.categories import is_archive_plan, list_plans
from agent_annotate.pagegen import generate


def source(tmp_path: Path, sections: dict[str, str], cards: list | None = None, version="v1") -> Path:
    body = "".join(f"## {title}\n\n{text}\n\n" for title, text in sections.items())
    if cards:
        body += "## Questions for reviewer\n\n```cards\n" + json.dumps(cards) + "\n```\n"
    path = tmp_path / f"{version}.md"
    path.write_text(f"---\ntitle: Long\nversion: {version}\nother_files_required: none\n---\n\n{body}", encoding="utf-8")
    return path


def card(number: int, evidence: str) -> dict:
    return {"number": number, "anchor_id": f"d:q{number}", "decision_request": {
        "prompt": f"Ship part {number}?", "context": "Checks passed.", "recommendation": "yes",
        "options": [{"id": "yes", "label": "Yes", "consequence": "Ships."},
                    {"id": "no", "label": "No", "consequence": "Waits."}],
        "evidence": [{"label": "The part", "anchor": evidence}]}}


def canvas(slug: Path, version: str) -> str:
    return (slug / "versions" / f"{version}.html").read_text(encoding="utf-8")


def store(slug: Path, anchors: dict) -> None:
    (slug / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": {}}))


@pytest.fixture
def no_sips(monkeypatch):
    monkeypatch.setattr(long_pages.shutil, "which", lambda name: None)


@pytest.fixture
def fake_sips(monkeypatch):
    calls, real = [], long_pages.subprocess.run

    def run(command, **kwargs):
        if command[0] != "/usr/bin/sips":
            return real(command, **kwargs)
        calls.append(command)
        Path(command[-1]).write_bytes(b"small preview")
        return type("Done", (), {"returncode": 0})()
    monkeypatch.setattr(long_pages.shutil, "which", lambda name: "/usr/bin/sips")
    monkeypatch.setattr(long_pages.subprocess, "run", run)
    return calls


def test_a_large_screenshot_gets_one_cached_preview_and_a_full_size_link(tmp_path, fake_sips):
    write(tmp_path / "shots" / "wide.png", png(2400, 1600))
    write(tmp_path / "shots" / "small.png", png(300, 200))
    sections = {"Board": "The board.\n\n![Board](shots/wide.png)\n\n![Icon](shots/small.png)"}
    slug = tmp_path / "slug"
    generate(source(tmp_path, sections), slug)
    html = canvas(slug, "v1")
    preview = next((slug / "assets" / "preview").iterdir())
    assert preview.suffix == ".jpg" and len(fake_sips) == 1 and "-Z" in fake_sips[0]
    assert f'src="assets/preview/{preview.name}" data-full="assets/' in html
    assert 'class="aa-full"' in html and "⤢ Full size" in html
    assert html.count('loading="lazy" decoding="async"') == 2 and html.count("aa-full") == 1
    generate(source(tmp_path, sections, version="v2"), slug)
    assert len(fake_sips) == 1                      # cached by content hash
    assert "data-unchanged-since" in canvas(slug, "v2")   # preview markup does not count as a change


def test_without_sips_the_original_is_used(tmp_path, no_sips):
    write(tmp_path / "shots" / "wide.png", png(2400, 1600))
    slug = tmp_path / "slug"
    generate(source(tmp_path, {"Board": "![Board](shots/wide.png)"}), slug)
    html = canvas(slug, "v1")
    assert 'loading="lazy"' in html and "data-full" not in html and "aa-full" not in html
    assert not (slug / "assets" / "preview").exists()


def test_finished_topics_fold_in_page_order_and_open_ones_stay(tmp_path, no_sips):
    slug = tmp_path / "slug"
    parts = {"Alpha": "Done.", "Beta": "Done too.", "Gamma": "Evidence for an open card.", "Delta": "Has a comment."}
    generate(source(tmp_path, parts, [card(1, "s:gamma")]), slug)
    assert "aa-earlier" not in canvas(slug, "v1")    # nothing is unchanged on v1
    store(slug, {"s:delta:p1": [{"id": "c1", "author": "chang", "status": "open", "body": "Why?", "version": "v1"}]})
    changed = {**parts, "Beta": "Changed this round."}
    result = generate(source(tmp_path, changed, [card(1, "s:gamma")], "v2"), slug)
    html = canvas(slug, "v2")
    fold = html[html.index('<details class="aa-earlier"'):]
    assert result["layout"]["folded"] == ["s:alpha"]
    assert 'data-anchor-id="s:alpha"' in fold and "<template" in fold
    for kept in ("s:beta", "s:gamma", "s:delta", "s:questions-for-reviewer"):
        assert f'data-anchor-id="{kept}"' not in fold and f'data-anchor-id="{kept}"' in html
    assert "Earlier updates</strong> · 1 section" in fold
    history = json.loads((slug / "current.meta.json").read_text())["history"]
    assert {"sections", "screenshots"} <= set(history[-1]) and "hash" not in json.dumps(history)


def test_an_answered_card_no_longer_holds_its_topic_open(tmp_path, no_sips):
    slug = tmp_path / "slug"
    parts = {"Alpha": "Done.", "Gamma": "Evidence."}
    generate(source(tmp_path, parts, [card(1, "s:gamma")]), slug)
    store(slug, {"d:q1": [{"id": "q1", "number": 1, "author": "agent:claude", "status": "open", "version": "v1",
                           "decision_request": card(1, "s:gamma")["decision_request"],
                           "decision": {"verdict": "yes"}}]})
    result = generate(source(tmp_path, {**parts, "Epsilon": "New."}, version="v2"), slug)
    assert result["layout"]["folded"] == ["s:alpha", "s:gamma"]


def big_page(n=45, changed=None):
    return {f"Topic {i}": (changed or {}).get(i, f"Finished work number {i}.") for i in range(1, n + 1)}


def test_over_the_limit_every_finished_topic_moves_to_one_archive_and_republishing_is_idempotent(tmp_path, no_sips):
    slug = tmp_path / "slug"
    first = generate(source(tmp_path, big_page(), [card(1, "s:topic-3")]), slug)
    assert first["layout"]["archived"] == [] and any("size limit" in w for w in first["warnings"])
    second = generate(source(tmp_path, big_page(), [card(1, "s:topic-3")], "v2"), slug)
    today = datetime.date.today().isoformat()
    assert second["layout"]["archived"][0]["id"] == f"archive-{today}"
    html = canvas(slug, "v2")
    assert 'data-anchor-id="s:topic-3"' in html and 'data-anchor-id="s:topic-1"' not in html
    assert "aa-earlier" not in html and second["cards"] == 1
    archives = [p for p in list_plans(slug) if is_archive_plan(p)]
    assert len(archives) == 1 and archives[0]["archive"]["sections"] == 44
    assert archives[0]["title"].startswith("Archive ") and "Topic 1, Topic 2 +42" in archives[0]["title"]
    archive_html = (slug / "plans" / archives[0]["id"] / "versions" / "v1.html").read_text()
    assert 'data-anchor-id="s:topic-1"' in archive_html and 'data-anchor-id="s:topic-3"' not in archive_html
    cards_before = (slug / "cards.json").read_text()

    third = generate(source(tmp_path, big_page(), [card(1, "s:topic-3")], "v3"), slug)
    assert third["layout"]["archived"] == [] and len(third["layout"]["already_archived"]) == 44
    assert canvas(slug, "v3").count('data-anchor-id="s:topic-1"') == 0
    assert (slug / "cards.json").read_text() == cards_before
    assert len([p for p in list_plans(slug) if is_archive_plan(p)]) == 1

    fourth = generate(source(tmp_path, big_page(changed={1: "Reopened with new work."}), [card(1, "s:topic-3")], "v4"), slug)
    assert fourth["layout"]["returned"] == ["s:topic-1"]
    assert 'data-anchor-id="s:topic-1"' in canvas(slug, "v4")
    index = json.loads((slug / "archive" / "index.json").read_text())
    assert "s:topic-1" not in {t["anchor"] for a in index["archives"] for t in a["topics"]}
    meta = json.loads((slug / "plans" / archives[0]["id"] / "meta.json").read_text())
    latest = (slug / "plans" / archives[0]["id"] / "versions" / f"{meta['current']}.html").read_text()
    assert meta["current"] == "v2" and 'data-anchor-id="s:topic-1"' not in latest
    assert meta["archive"]["sections"] == 43


def test_a_reopened_comment_brings_an_archived_topic_back(tmp_path, no_sips):
    slug = tmp_path / "slug"
    generate(source(tmp_path, big_page()), slug)
    generate(source(tmp_path, big_page(), version="v2"), slug)
    store(slug, {"s:topic-7:p1": [{"id": "c7", "author": "chang", "status": "open", "body": "Again?", "version": "v1"}]})
    result = generate(source(tmp_path, big_page(), version="v3"), slug)
    assert result["layout"]["returned"] == ["s:topic-7"]
    assert 'data-anchor-id="s:topic-7"' in canvas(slug, "v3")
