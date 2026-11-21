"""The frame's data: this page's waiting count and every project's read-only Home counts."""

import json
import os
import time
from pathlib import Path

from agent_annotate.proto_data import frame


def _page(d, waiting=0, versions=0):
    d.mkdir(parents=True)
    items = [{"id": f"q{i}", "author": "agent:x", "text": "Pick one?", "status": "open", "version": "v1",
              "decision_request": {"prompt": "Pick one?", "options": [{"id": "a", "label": "A"}]}} for i in range(waiting)]
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"a": items}, "archived": {}}))
    (d / "current.meta.json").write_text(json.dumps({"name": d.name, "current": "v1"}))
    (d / "versions").mkdir()
    for i in range(versions):
        (d / "versions" / f"v{i}.html").write_text("x")
    return d


def test_home_counts_group_pages_by_project_and_this_page_comes_first(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _page(root / "rebex" / "reviews" / "one", waiting=2, versions=3)
    _page(root / "rebex" / "reviews" / "two", waiting=1, versions=1)
    _page(root / "leadory" / "reviews" / "plan")
    (root / "leadory" / "reviews" / "not-a-page").mkdir()
    old = root / "leadory" / "reviews" / "plan" / "versions" / "v0.html"
    old.write_text("x")
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    this = _page(tmp_path / "copy", waiting=3, versions=2)
    monkeypatch.setenv("ANNOTATE_PROTO_PROJECTS_ROOT", str(root))

    data = frame.build(this)

    assert data["waiting"] == 3
    keys = [p["key"] for p in data["projects"]]
    assert keys[0] == "this" and data["projects"][0]["this"] is True
    rebex = next(p for p in data["projects"] if p["key"] == "rebex")
    assert (rebex["name"], rebex["pages"], rebex["waiting"], sum(rebex["vday"])) == ("Rebex", 2, 3, 4)
    leadory = next(p for p in data["projects"] if p["key"] == "leadory")
    assert leadory["pages"] == 1 and sum(leadory["vday"]) == 0 and leadory["lastAgoH"] > 24 * 30
    json.dumps(data)  # the page gets it as JSON


def test_project_code_owner_and_last_send(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    rebex = _page(root / "rebex" / "reviews" / "one")
    meta = json.loads((rebex / "current.meta.json").read_text())
    meta["owner"] = {"owner_agent": "claude", "claimed_at": "2026-11-20T08:00:00Z", "target": {"pid": os.getpid()}}
    (rebex / "current.meta.json").write_text(json.dumps(meta))
    fld = _page(root / "fastlane-drive" / "reviews" / "page")
    meta = json.loads((fld / "current.meta.json").read_text())
    meta["owner"] = {"owner_agent": "codex", "claimed_at": "2026-11-19T08:00:00Z", "target": {"pid": 999999999}}
    (fld / "current.meta.json").write_text(json.dumps(meta))
    this = _page(tmp_path / "copy")
    (this / "project.json").write_text(json.dumps({"board": {"project": "fastlane-drive"}}))
    (this / "rounds.ndjson").write_text('{"ts": "2026-11-20T09:00:00Z", "delivery": "acknowledged", "answers": [1, 2]}\nnot json\n')
    monkeypatch.setenv("ANNOTATE_PROTO_PROJECTS_ROOT", str(root))
    frame._cache.clear()

    data = frame.build(this)

    by = {p["key"]: p for p in data["projects"]}
    assert by["rebex"]["code"] == "rebex" and by["fastlane-drive"]["code"] == "fld"
    assert by["rebex"]["owner"] == {"agent": "claude", "at": "2026-11-20T08:00:00Z", "alive": True}
    assert by["fastlane-drive"]["owner"]["alive"] is False
    # a copy has no owner of its own: its project's session stands in, so Settings can name where a Send goes
    assert by["this"]["code"] == "fld" and by["this"]["owner"]["agent"] == "codex"
    assert data["lastSend"] == {"ts": "2026-11-20T09:00:00Z", "delivery": "acknowledged", "n": 2}


# The broken frame items are browser behaviour; these pin the code that fixes each, so a later edit cannot drop it quietly.
WEB = Path(frame.__file__).resolve().parents[1] / "web" / "proto"


def _src(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_broken_items_keep_their_fixes():
    js, css, tokens, shell = _src("frame.js"), _src("frame.css"), _src("tokens.css"), _src("shell.html")
    # 1 another project opens with its six tabs, from Home and the project menu
    assert "data-proj=" in js and "`project/${d.proj}/questions`" in js and "function drawOther" in js
    # 2 a Home read that finishes after he left never draws over the tab
    home = js[js.index("async function drawHome"):js.index("function drawOther")]
    assert home.count("if (!S.home) return;") == 2
    # 3 the review document follows Text size
    assert ".p-main{--aa-text:var(--fs,1)}" in tokens
    # 4 unsent answers stay in memory with the switch off, and old ones are dropped
    assert "DRAFT.test(k) && !remember('drafts')" in js and "if (!remember('drafts')) dropStoredDrafts();" in js
    # 5 folded sections are saved and restored with the switch on
    assert "addEventListener('toggle', saveFold, true)" in js and "restoreFolds(main)" in js
    # 6 a reload with Open tab off starts on Questions
    assert "nav.type === 'reload' && !remember('tab')" in js
    # 7 F and A from any tab open Questions and hand the key over; Esc closes an area's dialog
    assert "if ((k !== 'f' && k !== 'a') || onQuestions()) return;" in js and "new KeyboardEvent('keydown'" in js
    assert "[data-sendclose]" in js
    # 8 sign out shows the sign-in screen
    assert "function signOut" in js and "body.p-gated" in css
    # the Running fixer's stale render: each render draws into its own box
    assert "view.isConnected" in js and ".p-view{display:contents}" in css
    # 17 three skip links
    assert shell.count('class="skip"') == 3
