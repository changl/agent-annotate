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
    monkeypatch.setattr(links, "documents", lambda: {"files": [], "groups": {}})
    monkeypatch.setattr(links, "USAGE_AUDIT", tmp_path / "missing.html")
    monkeypatch.setattr(links, "LOAD_TEST", tmp_path / "missing")
    monkeypatch.setattr(links, "MEETING", tmp_path / "missing-meeting")
    monkeypatch.setattr(links, "ROADMAP", tmp_path / "05-roadmap.md")
    (tmp_path / "05-roadmap.md").write_text("# Roadmap\n")

    page = tmp_path / "copy"
    (page / "plans" / "archive-2026-11-02" / "versions").mkdir(parents=True)
    (page / "plans" / "archive-2026-11-02" / "meta.json").write_text(json.dumps({"title": "Snap", "history": [{"version": "v1", "ts": "2026-11-02T00:00:00Z"}]}))
    (page / "plans" / "archive-2026-11-02" / "versions" / "v1.html").write_text("<p>snap</p>")
    (page / "current.meta.json").write_text(json.dumps({"name": "Copy", "current": "v9", "history": [{"version": "v9"}]}))
    (page / "project.json").write_text(json.dumps({"board": {"url": "https://board/p/x", "label": "Beads"}, "modules": [{"id": "resources", "kind": "links", "items": [
        {"label": "Linear: tasks", "url": "https://linear.app/t", "description": "Ask me@gmail.com"},
        {"label": "Admin (port 1): the shared server", "url": "https://host:1/admin", "description": "Tailnet only."},
        {"label": "The rest of the admin: review", "url": "https://host/r"}, {"label": "Batch review pull request 2", "url": "https://github.com/x/pull/2"}]}]}))
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "archived": {}, "anchors": {"x": [
        {"id": "1", "author": "me@gmail.com", "author_name": "Pat", "author_email": "me@gmail.com", "created_at": "2026-11-03T00:00:00Z"},
        {"id": "2", "author": "agent:claude", "author_name": "", "created_at": "2026-11-04T00:00:00Z"}],
        "doc:planning/04-delivery-scope.md~3": [{"id": "3", "author_name": "Pat", "text": "why", "created_at": "2026-11-02T00:00:00Z", "target": {"quote": "car"}}]}}))

    d = links.build(page)
    assert [p["name"] for p in d["pages"]] == ["Page A", "Delivery roadmap"]  # another project's page never shows
    assert d["pages"][1]["ref"] == "delivery-roadmap" and "long" in d["pages"][1]["why"]  # opens Reference's roadmap item
    # the live page's Admin and Linear links come along with their descriptions; its other links do not
    assert [(l["name"], l.get("ic")) for l in d["links"][1:3]] == [("Linear: tasks", "ext"), ("Admin (port 1): the shared server", "ext")]
    assert d["links"][2]["what"] == "Tailnet only." and len(d["links"]) == 4
    # a note on a Markdown file's line reloads with its selected words
    assert [(n["a"], n["target"]) for n in d["notes"]] == [("doc:planning/04-delivery-scope.md~3", {"quote": "car"})]
    assert d["archived"] == [{"id": "archive-2026-11-02", "v": "v1", "t": "Snap", "when": "2026-11-02"}]
    assert d["people"] == [{"name": "Pat", "email": "member@example.com", "role": "owner", "seen": "2026-11-03"}]
    assert d["links"][0]["url"] == "https://board/p/x" and len(d["folders"]) == 3
    assert d["links"][-1]["name"] == "Tester server" and not d["links"][-1]["url"]  # no address recorded: a row, no link
    assert d["pages"][0]["why"] and d["kept"] == [] and d["docs"]["files"] == []
    assert "gmail" not in json.dumps(d)


def test_kept_documents_mask_and_chart(tmp_path, monkeypatch):
    ua, lt = tmp_path / "ua.html", tmp_path / "lt"
    lt.mkdir()
    ua.write_text("<h1>Usage audit</h1><script>x()</script><p>Ask pat@gmail.com about it</p><li>one</li>")
    m = {f"http_req_duration{{kind:{k}}}": {"med": 900.4, "p(90)": 1500, "p(95)": 2000} for k in ("api", "web")}
    (lt / "tiny-summary.json").write_text(json.dumps({"metrics": m}))
    (lt / "report.md").write_text("intro\n- **API p95** 2000 ms, over the gate\n")
    monkeypatch.setattr(links, "USAGE_AUDIT", ua)
    monkeypatch.setattr(links, "LOAD_TEST", lt)
    monkeypatch.setattr(links, "MEETING", tmp_path / "missing-meeting")
    ua_doc, lt_doc = links.kept()
    assert ua_doc["blocks"][0] == ["h", "Usage audit"] and ["li", "one"] in ua_doc["blocks"]
    assert "gmail" not in json.dumps(ua_doc) and "x()" not in json.dumps(ua_doc)
    assert lt_doc["chart"]["pts"][0] == ["API median", 900] and lt_doc["chart"]["gate"] == 1000
    assert lt_doc["blocks"] == [["p", "API p95 2000 ms, over the gate"]]


def test_each_page_says_why_it_is_its_own():
    from pathlib import Path
    assert "meeting" in links._why("FLD admin team meeting, Nov 11", Path("/x/admin-meeting"))
    assert "taken from" in links._why("FLD-B02", links.FLD_SOURCE)
    assert "taken from" in links._why("Rebex", Path("/x/rebex"), Path("/x/rebex"))
    assert "long" in links._why("Delivery roadmap", Path("/x/roadmap"))


def test_a_copy_shows_only_its_own_project(tmp_path, monkeypatch):
    """Audit 3 finding 1: Rebex's and Agent Annotate's copies listed FastLane Drive's pages, folders and documents."""
    fld, rbx, registry = tmp_path / "fld", tmp_path / "rebex", tmp_path / "state"
    for p in (fld / "reviews" / "live", rbx / "reviews" / "rebex", rbx / "reviews" / "old", rbx / "repo" / ".git", rbx / "assets", registry):
        p.mkdir(parents=True)
    (rbx / "reviews" / "rebex" / "current.meta.json").write_text(json.dumps({"name": "Rebex decisions", "history": [{"version": "v1"}]}))
    (registry / "r.json").write_text(json.dumps({"slugs": {
        "live": {"slug_dir": str(fld / "reviews" / "live"), "url": "https://x/live/"},
        "rebex": {"slug_dir": str(rbx / "reviews" / "rebex"), "url": "https://x/rebex/"}}}))
    monkeypatch.setattr(links, "PROJECT", fld)
    monkeypatch.setattr(links, "REGISTRY", registry)
    boom = lambda *a: (_ for _ in ()).throw(AssertionError("FastLane Drive's files read for a copy"))
    monkeypatch.setattr(links, "kept", boom)
    monkeypatch.setattr(links, "documents", boom)
    page = tmp_path / "proto-rebex"
    page.mkdir()
    (page / "current.meta.json").write_text(json.dumps({"name": "Rebex", "proto_copy_of": "rebex", "proto_source": str(rbx / "reviews" / "rebex")}))
    (page / "project.json").write_text(json.dumps({"modules": [
        {"kind": "links", "title": "Links", "items": [{"label": "Staging storefront", "url": "https://shop/"}, {"label": "Same shop", "url": "https://shop/"}]},
        {"kind": "links", "title": "Earlier pages (read-only)", "items": [{"label": "reviews/old → Library", "url": "https://x/reviews/old/?archived=1"}]}]}))

    d = links.build(page)
    assert [(p["name"], p["why"].split(";")[0]) for p in d["pages"]] == [("Rebex decisions", "the live review page this copy was taken from")]
    # the pages it replaced are archived links, read-only
    assert [(a["t"], a["url"], a["why"]) for a in d["archived"]] == [("Old", "https://x/reviews/old/?archived=1", "read-only: its work moved into this page's Library")]
    assert [f["name"] for f in d["folders"]] == ["rebex/repo", "reviews/rebex", "annotate-proto/reviews/proto-rebex"]
    assert [l["name"] for l in d["links"]] == ["Staging storefront"]  # its own links, once each; no Tester server
    assert d["kept"] == [] and d["docs"]["files"] == [] and "fld" not in json.dumps(d)

    # a copy whose source is unknown shows nothing rather than FastLane Drive's
    (page / "current.meta.json").write_text(json.dumps({"name": "Leadory", "proto_copy_of": "leadory"}))
    (page / "project.json").write_text("{}")
    d = links.build(page)
    assert d["pages"] == [] and d["folders"] == [] and d["links"] == []


def test_a_copy_lists_its_copy_library(tmp_path, monkeypatch):
    """Audit4 finding 6: Rebex's Copy library is one of its pages, with a link; the row opens App text in Reference."""
    rbx, registry, page = tmp_path / "rebex", tmp_path / "state", tmp_path / "proto-rebex"
    for p in (rbx / "reviews" / "rebex", registry, page):
        p.mkdir(parents=True)
    monkeypatch.setattr(links, "REGISTRY", registry)
    (page / "current.meta.json").write_text(json.dumps({"name": "Rebex", "proto_copy_of": "rebex", "proto_source": str(rbx / "reviews" / "rebex")}))
    (page / "copy.json").write_text(json.dumps({"blocks": [{"id": "a", "title": "Hero", "status": "needs_you", "current": "r1",
                                                            "revisions": [{"id": "r1", "delta": {"ops": [{"insert": "Hi"}]}}]}]}))
    [p] = links.build(page)["pages"]
    assert p["name"] == "Copy library" and p["ref"] == "copy-library" and p["why"] == "the app's text, in Reference · 1 pieces of text"
    assert "versions" not in p
    s = (links.Path(links.__file__).resolve().parents[1] / "web/proto/links.js").read_text()
    assert "p.versions != null ?" in s  # no "undefined versions" on the library row


def test_kept_document_lines_take_notes():
    """Audit 3 finding 4: a paragraph of a kept document (the Usage audit) opens the note composer, like a Markdown file's."""
    s = (links.Path(links.__file__).resolve().parents[1] / "web/proto/links.js").read_text()
    assert 'data-doc="doc:kept-${esc(d.id)}~p"' in s  # the click handler keys a line note as data-doc + '~' + line
    assert "const line = i => noteBox(ctx, D, `doc:kept-${d.id}~p~${i}`)" in s and "blocksHtml(d.blocks || [], ctx.esc, line)" in s
    assert "/^\\d+$/.test(i || '')" in s  # only ~<n> names a chart bar; a line note never indexes the chart
