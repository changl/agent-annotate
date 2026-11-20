"""Pages & links data: this project's pages only, archived snapshots, folders, and People with masked emails."""

import json

from agent_annotate.proto_data import links


def test_links(tmp_path, monkeypatch):
    project, other, registry = tmp_path / "proj", tmp_path / "other", tmp_path / "state"
    for p in (project / "reviews" / "a", other / "b", registry):
        p.mkdir(parents=True)
    (project / "reviews" / "a" / "current.meta.json").write_text(json.dumps({"name": "Page A", "history": [{"version": "v1", "ts": "2026-11-01T00:00:00Z"}]}))
    (registry / "a.json").write_text(json.dumps({"slugs": {"a": {"slug_dir": str(project / "reviews" / "a"), "url": "https://x/a/"}}}))
    (registry / "b.json").write_text(json.dumps({"slugs": {"b": {"slug_dir": str(other / "b"), "url": "https://x/b/"}}}))
    monkeypatch.setattr(links, "PROJECT", project)
    monkeypatch.setattr(links, "REGISTRY", registry)

    page = tmp_path / "copy"
    (page / "plans" / "archive-2026-11-02" / "versions").mkdir(parents=True)
    (page / "plans" / "archive-2026-11-02" / "meta.json").write_text(json.dumps({"title": "Snap", "history": [{"version": "v1", "ts": "2026-11-02T00:00:00Z"}]}))
    (page / "plans" / "archive-2026-11-02" / "versions" / "v1.html").write_text("<p>snap</p>")
    (page / "current.meta.json").write_text(json.dumps({"name": "Copy", "current": "v9", "history": [{"version": "v9"}]}))
    (page / "project.json").write_text(json.dumps({"board": {"url": "https://board/p/x", "label": "Beads"}}))
    (page / "comments.json").write_text(json.dumps({"anchors": {"x": [
        {"id": "1", "author": "me@gmail.com", "author_name": "Pat", "author_email": "me@gmail.com", "created_at": "2026-11-03T00:00:00Z"},
        {"id": "2", "author": "agent:claude", "author_name": "", "created_at": "2026-11-04T00:00:00Z"}]}}))

    d = links.build(page)
    assert [p["name"] for p in d["pages"]] == ["Page A"]  # another project's page never shows
    assert d["archived"] == [{"id": "archive-2026-11-02", "v": "v1", "t": "Snap", "when": "2026-11-02"}]
    assert d["people"] == [{"name": "Pat", "email": "member@example.com", "role": "owner", "seen": "2026-11-03"}]
    assert d["links"][0]["url"] == "https://board/p/x" and len(d["folders"]) == 3
    assert "gmail" not in json.dumps(d)
