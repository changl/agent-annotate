"""Consolidating pages: every record kept, sources frozen, old addresses redirect."""

import argparse
import copy
import hashlib
import http.server
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from agent_annotate import cli, consolidate, pagegen, sync_server, workspace


def _page(tmp_path, name, versions=1):
    directory = tmp_path / "pages" / name
    for number in range(1, versions + 1):
        source = tmp_path / f"{name}-v{number}.md"
        source.write_text(f"---\ntitle: {name} page\n---\n\n## Scope\n\nVersion {number} of {name}.\n")
        pagegen.generate(source, directory, version=f"v{number}")
    # publish-version registers later versions; record them as it would.
    meta = json.loads((directory / "current.meta.json").read_text())
    meta.update(current=f"v{versions}", history=[{"version": f"v{n}", "ts": f"2026-09-0{n}T00:00:00Z", "label": f"v{n}"}
                                                 for n in range(1, versions + 1)])
    (directory / "current.meta.json").write_text(json.dumps(meta))
    return directory


def _card(cid, number, anchor="s:scope", **extra):
    return {"id": cid, "anchor_id": anchor, "text": f"Question {number}?", "author": "agent:claude",
            "created_at": f"2026-10-01T00:00:{number:02d}Z", "version": "v1", "status": "open",
            "response_text": None, "replies": [], "number": number,
            "decision_request": {"prompt": f"Question {number}?", "options": [
                {"id": "fix", "label": "Fix it"}, {"id": "keep", "label": "Keep it"}]}, **extra}


def _store(directory, live, archived=()):
    store = {"schema_version": 2, "anchors": {}, "archived": {}}
    for comment in live:
        store["anchors"].setdefault(comment["anchor_id"], []).append(comment)
    for comment in archived:
        store["archived"].setdefault(comment["anchor_id"], []).append(comment)
    (directory / "comments.json").write_text(json.dumps(store))


@pytest.fixture
def estate(tmp_path, monkeypatch):
    """Four registered pages of one project, with answers, replies, history,
    read state and submitted rounds."""
    state = tmp_path / "state"
    state.mkdir()
    bus = tmp_path / "bus" / "reviews"
    bus.mkdir(parents=True)
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(sync_server, "STATE_DIR", state)
    decisions = _page(tmp_path, "shop-decisions", versions=2)
    plan = _page(tmp_path, "shop-plan", versions=2)
    gaps = _page(tmp_path, "shop-gaps")
    copy_page = _page(tmp_path, "shop-copy")
    answered = {"verdict": "select", "text": "Fix it", "option_id": "fix", "ts": "2026-10-02T00:00:00Z",
                "by": "chang@example.test"}
    reply = {"author": "chang@example.test", "text": "Yes", "ts": "2026-10-02T00:00:00Z"}
    _store(decisions, [
        _card("dec1", 1, decision=answered, replies=[reply], status="resolved_in_version",
              resolved_in_version="v2", resolution_anchor_id="s:scope"),
        {**_card("dec2", 2, version="v2"), "decision_history": [answered]},
        # No stored number: the page shows the next free one, 3.
        {k: v for k, v in _card("dec3", 3, version="v2").items() if k != "number"},
    ], archived=[_card("dec0", 9, status="archived")])
    _store(plan, [_card("plan1", 1, decision=answered, replies=[reply]), _card("plan2", 2, version="v2")])
    _store(gaps, [_card("gap1", 1, anchor="d:q1", decision=answered),
                  {"id": "gapnote", "anchor_id": "d:q1", "text": "Also the footer", "author": "chang@example.test",
                   "created_at": "2026-10-02T00:00:00Z", "version": "v1", "status": "open", "replies": []}])
    _store(copy_page, [_card("copy1", 1, anchor="tbl:copy:row:hero", decision=answered, status="user_confirmed")])
    (decisions / "read-state.json").write_text(json.dumps({"chang@example.test": {"dec1": {"ts": "x", "sig": "a"}}}))
    (plan / "read-state.json").write_text(json.dumps({"chang@example.test": {"plan1": {"ts": "y", "sig": "b"}}}))
    (decisions / "project.json").write_text(json.dumps({"schema_version": 1, "title": "Shop", "modules": []}))
    (bus / "shop-plan.ndjson").write_text(json.dumps({
        "event": "round_submitted", "round_id": "round-a", "ts": "2026-10-02T00:00:01Z", "by": "chang@example.test",
        "version": "v1", "comment_ids": ["plan1"]}) + "\n")
    (bus / "shop-decisions.ndjson").write_text(json.dumps({
        "event": "round_submitted", "round_id": "round-b", "ts": "2026-10-02T00:00:02Z", "by": "chang@example.test",
        "version": "v1", "comment_ids": ["dec1"]}) + "\n")
    slugs = {}
    for index, directory in enumerate((decisions, plan, gaps, copy_page)):
        port = 8976 + index
        slugs[directory.name] = {"slug": directory.name, "slug_dir": str(directory), "project": "reviews",
                                 "port": port, "transport": "local", "public_base_path": f"/annotate/reviews/{directory.name}",
                                 "url": f"http://localhost:{port}/annotate/reviews/{directory.name}/",
                                 "local_url": f"http://localhost:{port}/", "bus_file": str(bus / f"{directory.name}.ndjson")}
    (state / "reviews.json").write_text(json.dumps({"project": "reviews", "slugs": slugs}))
    return {"tmp": tmp_path, "state": state, "pages": {d.name: d for d in (decisions, plan, gaps, copy_page)},
            "target": tmp_path / "pages" / "shop"}


SOURCES = ["reviews/shop-decisions:review", "reviews/shop-plan:plans", "reviews/shop-gaps:findings",
           "reviews/shop-copy:library"]


def _run(estate, *extra, sources=SOURCES, capsys=None):
    args = argparse.Namespace(target="shop/shop", sources=list(sources), dir=str(estate["target"]),
                              dry_run="--dry-run" in extra, json=True)
    code = cli.cmd_consolidate(args)
    return code


def _tree(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def test_dry_run_counts_every_page_and_tab_and_writes_nothing(estate, capsys):
    before = {name: _tree(path) for name, path in estate["pages"].items()}
    assert _run(estate, "--dry-run") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["sources"]["reviews/shop-decisions"]["comments"] == 4
    assert report["sources"]["reviews/shop-decisions"]["earlier_verdicts"] == 1
    assert report["sources"]["reviews/shop-plan"]["versions"] == 2
    assert report["tabs"]["review"]["comments"] == 4
    assert report["tabs"]["plans"] == {"comments": 2, "cards": 2, "verdicts": 1, "earlier_verdicts": 0,
                                       "replies": 1, "open": 2}
    assert report["tabs"]["findings"]["comments"] == 2 and report["tabs"]["library"]["comments"] == 1
    assert report["rounds"] == 2 and report["read_state"] == 2
    assert not estate["target"].exists()
    assert {name: _tree(path) for name, path in estate["pages"].items()} == before
    assert "consolidated_into" not in (estate["state"] / "reviews.json").read_text()


def test_consolidate_keeps_every_record_and_freezes_the_sources(estate, capsys):
    originals = {name: json.loads((path / "comments.json").read_text()) for name, path in estate["pages"].items()}
    before = {name: _tree(path) for name, path in estate["pages"].items()}
    assert _run(estate) == 0
    capsys.readouterr()
    target = estate["target"]
    store = json.loads((target / "comments.json").read_text())
    moved = {c["id"]: c for bucket in ("anchors", "archived") for items in store[bucket].values() for c in items}
    for name, source in originals.items():
        for bucket in ("anchors", "archived"):
            for items in source[bucket].values():
                for comment in items:
                    kept = moved[comment["id"]]
                    for key, value in comment.items():
                        if key not in ("anchor_id", "category", "doc", "finding", "number", "moved_from"):
                            assert kept[key] == value, (name, comment["id"], key)
    assert len(moved) == 9
    # Tabs, plan document and finding metadata.
    assert moved["dec1"].get("category") is None and "moved_from" not in moved["dec1"]
    assert moved["dec3"]["number"] == 10  # the number its page showed (9 is the archived card's)
    assert moved["plan1"]["category"] == "plans" and moved["plan1"]["doc"] == "plan:plan"
    assert moved["plan1"]["moved_from"] == "reviews/shop-plan"
    assert moved["gap1"]["finding"] == {"set": "gaps", "title": "Question 1?"}
    assert moved["gap1"]["anchor_id"] == moved["gapnote"]["anchor_id"] == "gaps:d:q1"
    assert moved["copy1"]["category"] == "library" and moved["copy1"]["anchor_id"] == "copy:copy"
    assert "dec0" in store["archived"]["s:scope"][0]["id"]
    # Documents: the Review versions byte for byte, every plan version.
    for version in ("v1", "v2"):
        assert (target / "versions" / f"{version}.html").read_bytes() == \
            (estate["pages"]["shop-decisions"] / "versions" / f"{version}.html").read_bytes()
        assert (target / "plans" / "plan" / "versions" / f"{version}.html").is_file()
    plan_meta = json.loads((target / "plans" / "plan" / "meta.json").read_text())
    assert plan_meta["current"] == "v2" and [h["version"] for h in plan_meta["history"]] == ["v1", "v2"]
    assert json.loads((target / "categories.json").read_text())["findings_sets"][0]["id"] == "gaps"
    library = json.loads((target / "copy.json").read_text())
    assert [b["id"] for b in library["blocks"]] == ["copy"]
    assert "?archived=1" in json.dumps(library)
    # Viewer state and rounds.
    read = json.loads((target / "read-state.json").read_text())
    assert read == {"chang@example.test": {"dec1": {"ts": "x", "sig": "a"}, "plan1": {"ts": "y", "sig": "b"}}}
    rounds = [json.loads(line) for line in (target / "rounds.ndjson").read_text().splitlines()]
    assert {r["id"] for r in rounds} == {"reviews/shop-plan:round-a", "reviews/shop-decisions:round-b"}
    assert next(r for r in rounds if r["page"] == "reviews/shop-plan")["answers"][0]["category"] == "plans"
    project = json.loads((target / "project.json").read_text())
    assert project["title"] == "Shop" and project["modules"][-1]["id"] == "earlier-pages"
    assert json.loads((target / consolidate.MANIFEST).read_text())["tabs"]["plans"]["comments"] == 2
    # Sources: unchanged but for the marker; registry says where they went.
    for name, path in estate["pages"].items():
        after = _tree(path)
        assert after.pop(consolidate.MARKER)
        assert after == before[name]
    registry = json.loads((estate["state"] / "reviews.json").read_text())["slugs"]
    assert registry["shop-gaps"]["consolidated_into"]["tab"] == "findings"
    assert registry["shop-gaps"]["consolidated_into"]["id"] == "gaps"
    # A second run is refused: the target exists and the sources are marked.
    assert _run(estate) == 2


def test_refusals_leave_everything_untouched(estate, capsys):
    before = {name: _tree(path) for name, path in estate["pages"].items()}
    assert _run(estate, sources=["reviews/shop-decisions:review", "reviews/shop-plan:review"]) == 2
    assert "exactly one source" in capsys.readouterr().err
    clash = json.loads((estate["pages"]["shop-plan"] / "comments.json").read_text())
    clash["anchors"]["s:scope"][0]["id"] = "dec1"
    (estate["pages"]["shop-plan"] / "comments.json").write_text(json.dumps(clash))
    before["shop-plan"] = _tree(estate["pages"]["shop-plan"])
    assert _run(estate) == 2
    assert "comment id dec1" in capsys.readouterr().err
    estate["target"].mkdir()
    assert _run(estate) == 2
    assert "already exists" in capsys.readouterr().err
    assert {name: _tree(path) for name, path in estate["pages"].items()} == before


def _serve(directory, base, slug):
    handler = sync_server.make_handler(artifact_dir=directory, public_base_path=base, slug=slug,
                                       bus_dir=directory.parent, v2_mode=True, skill_dir=sync_server.WEB_DIR,
                                       local_author="chang@example.test", local_author_name="Chang")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _request(url, method="GET", body=None):
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def test_old_address_redirects_to_its_tab_and_takes_no_writes(estate, capsys):
    assert _run(estate) == 0
    capsys.readouterr()
    state = estate["state"]
    (state / "shop.json").write_text(json.dumps({"project": "shop", "slugs": {"shop": {
        "slug": "shop", "slug_dir": str(estate["target"]), "transport": "local", "public_base_path": None,
        "url": "http://localhost:8984/", "local_url": "http://localhost:8984/"}}}))
    servers = {}
    try:
        for name in ("shop-gaps", "shop-decisions", "shop-plan"):
            servers[name] = _serve(estate["pages"][name], f"/annotate/reviews/{name}", name)
        gaps = f"http://localhost:{servers['shop-gaps'].server_port}/annotate/reviews/shop-gaps/"
        status, headers, _ = _request(gaps)
        assert status == 302 and headers["Location"] == "http://localhost:8984/#view=findings&set=gaps"
        decisions = f"http://localhost:{servers['shop-decisions'].server_port}/annotate/reviews/shop-decisions/"
        assert _request(decisions + "?v=v1")[1]["Location"] == "http://localhost:8984/#view=review&v=v1"
        plan = f"http://localhost:{servers['shop-plan'].server_port}/annotate/reviews/shop-plan/"
        assert _request(plan + "?v=v2")[1]["Location"] == "http://localhost:8984/#view=plans&plan=plan&v=v2"
        # The old page, read-only.
        status, _, body = _request(gaps + "?archived=1")
        assert status == 200 and b"shell" in body.lower()
        assert _request(gaps + "comments.json")[0] == 200
        for path, payload in (("api/comments", {"anchor_id": "d:q1", "text": "late"}),
                              ("api/read-state", {"comment_id": "gap1", "sig": "z"})):
            status, _, body = _request(gaps + path, "POST", payload)
            assert status == 410 and json.loads(body)["moved_to"] == "http://localhost:8984/"
        assert _request(gaps + "api/comments/gap1", "PUT", {"status": "open"})[0] == 410
        capabilities = json.loads(_request(gaps + "api/capabilities")[2])
        assert capabilities["consolidation"] is True
        # The redirect holds without the target's registration too: it says where the page went.
        (state / "shop.json").unlink()
        status, _, body = _request(gaps)
        assert status == 503 and b"shop/shop" in body
    finally:
        for server in servers.values():
            server.shutdown()
            server.server_close()


def test_frozen_pages_refuse_cli_writes(estate, capsys, monkeypatch):
    assert _run(estate) == 0
    capsys.readouterr()
    directory = estate["pages"]["shop-plan"]
    args = argparse.Namespace(slug_dir=str(directory), version="v2", label=None, project=None)
    assert cli.cmd_publish_version(args) == 2
    assert "moved to shop/shop" in capsys.readouterr().err
    source = estate["tmp"] / "plan.md"
    source.write_text("## Next\n\nMore.\n")
    assert cli.cmd_plan(argparse.Namespace(slug="reviews/shop-plan", plan_id="next", from_file=str(source),
                                           title=None, label=None, project=None, json=True)) == 2
    assert not (directory / "plans").exists()
    with pytest.raises(ValueError, match="consolidated"):
        cli.fix_finding(json.loads((estate["state"] / "reviews.json").read_text())["slugs"]["shop-gaps"],
                        "1", ["https://example.test/proof"], "", "agent:test")
    # A consolidated page is no longer a project page of its own.
    monkeypatch.chdir(estate["tmp"])
    assert workspace.candidates(estate["tmp"], "reviews") == []


def test_review_versions_are_not_blocked_by_other_tabs(tmp_path):
    directory = _page(tmp_path, "main", versions=2)
    plan_card = _card("p1", 1, category="plans", doc="plan:rollout")
    finding = _card("f1", 2, anchor="design:d:q2", category="findings", finding={"set": "design", "title": "x"})
    review = _card("r1", 3)
    _store(directory, [plan_card, finding, review])
    blockers = cli._carryover_blockers(directory, "v2")
    assert [b["id"] for b in blockers] == ["r1"]


def test_reasking_a_review_card_never_rewrites_a_plan_card_on_the_same_anchor(tmp_path, monkeypatch):
    directory = _page(tmp_path, "main")
    plan_card = {**_card("p1", 5, anchor="d:q5", category="plans", doc="plan:rollout")}
    _store(directory, [copy.deepcopy(plan_card)])
    server = _serve(directory, "", "main")
    try:
        item = {"anchor_id": "d:q5", "number": 5, "text": "Review question?",
                "decision_request": {"prompt": "Review question?", "options": [{"id": "yes", "label": "Yes"}]}}
        request = urllib.request.Request(f"http://localhost:{server.server_port}/api/comments/batch", method="POST",
                                         data=json.dumps({"items": [item], "idempotency": "anchor"}).encode(),
                                         headers={"Content-Type": "application/json", "X-Annotate-Agent": "agent:claude"})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.loads(response.read())["created"] == 1
    finally:
        server.shutdown()
        server.server_close()
    store = json.loads((directory / "comments.json").read_text())
    kept = next(c for c in store["anchors"]["d:q5"] if c["id"] == "p1")
    assert kept == plan_card


def test_source_syntax():
    assert consolidate.parse_source("p/s:findings=design") == ("p/s", "findings", "design")
    with pytest.raises(ValueError):
        consolidate.parse_source("p/s:notes")
    with pytest.raises(ValueError):
        consolidate.parse_source("p/s:review=x")
    moved = {"tab": "plans", "id": "rollout"}
    assert consolidate.tab_fragment(moved, "v=v3") == "view=plans&plan=rollout&v=v3"
    assert consolidate.tab_fragment({"tab": "library"}, "v=v3") == "view=library"
    assert consolidate.tab_fragment({"tab": "review"}, "v=../x") == "view=review"
    assert consolidate.marker(Path("/nonexistent")) is None
