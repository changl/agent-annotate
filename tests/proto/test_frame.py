"""The frame's data: this page's waiting count and every project's read-only Home counts."""

import json
import os
import time

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
