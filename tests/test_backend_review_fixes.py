"""Regression tests for the backend review findings BE-1 … BE-19.

Each test started from the reviewer's repro (which asserted the faulty
behaviour) and asserts the fixed behaviour instead.
"""
import http.client
import json
import os
import subprocess
import threading
import uuid
from types import SimpleNamespace

import pytest
from test_categories_api import finding
from test_copy_api import _seed
from test_decision_api import _call, _card, _events, _store
from test_decision_api import server as server

from agent_annotate import cli, delivery, pagegen, project_state, review_access, transports, workspace
from agent_annotate.categories import add_proof_file, category_counts, mark_finding_fixed

MARKER_HTML = "<!doctype html><title>proof</title><script>document.title='annotate-review-marker'</script>"
MARKER_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" onload="document.title=\'annotate-review-marker\'">'
              '<rect width="10" height="10"/></svg>')
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def _raw(httpd, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}, body


def _plant(directory, folder, name, body):
    """A file already in the page dir (older data, or a copied page)."""
    path = directory / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body if isinstance(body, bytes) else body.encode())
    return name


# ── BE-1: proof attachments never run script in the review origin ──────────

@pytest.mark.parametrize("folder", ["attachments", "assets"])
def test_be1_active_files_are_downloads_with_sandbox_csp(server, folder):
    httpd, directory, _ = server
    for name, body in (("0a-report.html", MARKER_HTML), ("0b-shot.svg", MARKER_SVG),
                       ("0c-notes.txt", "plain"), ("0d-run.js", "alert(1)")):
        _plant(directory, folder, name, body)
        status, headers, _ = _raw(httpd, f"/{folder}/{name}")
        assert status == 200
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["content-security-policy"] == "sandbox"
        assert headers["content-disposition"].startswith("attachment")


@pytest.mark.parametrize("folder", ["attachments", "assets"])
def test_be1_images_and_pdf_stay_inline_but_sandboxed(server, folder):
    httpd, directory, _ = server
    for name, mime in (("1a-shot.png", "image/png"), ("1b-shot.jpg", "image/jpeg"), ("1c-a.gif", "image/gif"),
                       ("1d-a.webp", "image/webp"), ("1e-report.pdf", "application/pdf")):
        _plant(directory, folder, name, PNG)
        status, headers, _ = _raw(httpd, f"/{folder}/{name}")
        assert status == 200 and headers["content-type"] == mime
        assert headers["content-security-policy"] == "sandbox"
        assert headers["x-content-type-options"] == "nosniff"
        assert "content-disposition" not in headers


@pytest.mark.parametrize("name", ["report.html", "shot.svg", "page.htm", "x.js", "noext"])
def test_be1_cli_refuses_proof_types_outside_the_allowlist(name, tmp_path, monkeypatch, capsys):
    page = _finding_page(tmp_path, monkeypatch)
    (page.work / name).write_text("x")
    assert cli.cmd_finding(_args(fixed="1", proof=[name])) == 2
    err = capsys.readouterr().err
    assert "proof files must be one of" in err and "png" in err and "pdf" in err
    assert not (page.directory / "attachments").exists()
    with pytest.raises(ValueError, match="proof files must be one of"):
        add_proof_file(page.directory, page.work / name)


@pytest.mark.parametrize("name", ["shot.PNG", "a.jpg", "a.jpeg", "a.gif", "a.webp", "r.pdf", "r.txt", "r.md",
                                  "r.log", "r.json", "r.csv"])
def test_be1_cli_accepts_allowlisted_proof_types(name, tmp_path, monkeypatch, capsys):
    page = _finding_page(tmp_path, monkeypatch)
    (page.work / name).write_bytes(PNG)
    assert cli.cmd_finding(_args(fixed="1", proof=[name])) == 0, capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("REVIEW_BROWSER"), reason="set REVIEW_BROWSER=1 to run headless Chromium")
def test_be1_marker_script_does_not_run_when_opened(server):
    from playwright.sync_api import sync_playwright
    httpd, directory, _ = server
    names = {"html": _plant(directory, "attachments", "2a-report.html", MARKER_HTML),
             "svg": _plant(directory, "attachments", "2b-shot.svg", MARKER_SVG)}
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(accept_downloads=True)
        for kind, stored in names.items():
            page.goto(base + "/api/capabilities")
            with page.expect_download() as download:
                page.evaluate("url => { location.href = url }", f"{base}/attachments/{stored}")
            seen[kind] = download.value.suggested_filename
            page.wait_for_timeout(200)
            seen[kind + "-title"] = page.title()
        browser.close()
    assert seen["html"] == "2a-report.html" and seen["svg"] == "2b-shot.svg"
    assert "annotate-review-marker" not in (seen["html-title"], seen["svg-title"])


def test_be1_findings_ui_renders_png_attachment_as_image_and_svg_as_link():
    from pathlib import Path
    source = (Path(cli.__file__).parent / "web" / "findings.js").read_text()
    assert "const IMG_ATTACHMENT = /\\.(png|jpe?g|gif|webp)$/i;" in source


# ── BE-2: an agent re-fix keeps the reviewer's unsent reopen or verdict ────

def test_be2_fix_while_reopen_pending_keeps_reopen_in_next_send(server):
    httpd, directory, bus = server
    card = finding(httpd)
    mark_finding_fixed(directory, card["id"], by="agent:builder", note="first", proof=[])
    status, _ = _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "Still broken on mobile"},
                      author="chang@example.com")
    assert status == 200
    fixed = mark_finding_fixed(directory, card["id"], by="agent:builder", note="second", proof=[])
    assert fixed["round_pending"] is True and fixed["fixed"]["note"] == "second"
    assert category_counts(directory)["findings"]["ready"] == 1
    result = _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]
    assert result["delivery"] != "noop" and result["comment_ids"] == [card["id"]]
    [submitted] = _events(bus, "round_submitted")
    assert [(a["verdict"], a["text"]) for a in submitted["answers"]] == [("reopen", "Still broken on mobile")]
    comment = _store(directory)["anchors"]["d:gap"][0]
    assert "round_pending" not in comment and comment["fixed"]["note"] == "second"
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"


def test_be2_fix_while_verdict_pending_keeps_the_verdict_in_next_send(server):
    httpd, directory, bus = server
    card = finding(httpd)
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision",
          {"verdict": "reject", "text": "Keep as is", "defer_push": True}, author="chang@example.com")
    fixed = mark_finding_fixed(directory, card["id"], by="agent:builder", note="fixed anyway", proof=[])
    assert fixed["decision"]["round_pending"] is True
    result = _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]
    assert result["delivery"] != "noop"
    [submitted] = _events(bus, "round_submitted")
    assert [(a["verdict"], a["text"]) for a in submitted["answers"]] == [("reject", "Keep as is")]
    assert "round_pending" not in _store(directory)["anchors"]["d:gap"][0]["decision"]


def test_be2_second_reopen_before_send_carries_both_texts(server):
    httpd, directory, bus = server
    card = finding(httpd)
    mark_finding_fixed(directory, card["id"], by="agent:builder", note="first", proof=[])
    _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "Still broken on mobile"}, author="chang@example.com")
    mark_finding_fixed(directory, card["id"], by="agent:builder", note="second", proof=[])
    _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "And on tablet"}, author="chang@example.com")
    _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    [submitted] = _events(bus, "round_submitted")
    assert [a["text"] for a in submitted["answers"]] == ["Still broken on mobile\n\nAnd on tablet"]
    # A later reopen after that Send carries only its own words.
    mark_finding_fixed(directory, card["id"], by="agent:builder", note="third", proof=[])
    _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "Desktop now"}, author="chang@example.com")
    _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    assert [a["text"] for a in _events(bus, "round_submitted")[-1]["answers"]] == ["Desktop now"]


def test_be2_draft_reopen_event_is_not_in_the_agent_inbox(tmp_path, monkeypatch, capsys):
    page = _finding_page(tmp_path, monkeypatch)
    page.bus.write_text(json.dumps({"ts": "2026-10-05T01:00:00Z", "event": "finding_reopened", "comment_id": "f" * 12,
                                    "by": "chang@example.test", "deferred": True}) + "\n")
    assert cli.cmd_inbox(_args(json=False, category=None, unread=True, all_events=False)) == 0
    assert "finding_reopened" not in capsys.readouterr().out
    assert cli.cmd_inbox(_args(json=False, category=None, unread=False, all_events=True)) == 0
    assert "finding_reopened" in capsys.readouterr().out


# ── BE-3: compact inbox and cards show what to act on ───────────────────────

REOPEN_TEXT = "REOPEN-WORDS: contrast still fails on the dark theme, and the focus ring is invisible on the CTA"
VERDICT_TEXT = "VERDICT-WORDS: keep it, the brand team signed this off last week and we should not reopen it now"
DELTA_TEXT = "EDIT-DELTA: Ship faster with one page"
EDIT_TITLE = "EDIT-TITLE Homepage hero"
NOTE = "ROUND-NOTE overall looks good"


def _mixed_round(page):
    store = json.loads((page.directory / "comments.json").read_text())
    row = store["anchors"]["d:q1"][0]
    row.update(status="open", fixed_history=[{"by": "agent:test", "ts": "2026-10-05T00:00:00Z", "note": "fixed", "proof": []}],
               reopened=[{"by": "chang@example.test", "ts": "2026-10-05T01:00:00Z", "text": REOPEN_TEXT}],
               flagged_for_session=True)
    store["anchors"]["d:q2"] = [{"id": "e" * 12, "number": 2, "anchor_id": "d:q2", "text": "Rename?", "author": "agent:test",
                                 "status": "open", "version": "v1",
                                 "decision": {"verdict": "reject", "text": VERDICT_TEXT, "by": "chang@example.test",
                                              "ts": "2026-10-05T01:00:30Z"},
                                 "decision_request": {"prompt": "Rename the product?", "options": ["accept", "reject"]}}]
    (page.directory / "comments.json").write_text(json.dumps(store))
    edits = [{"category": "library", "block_id": "hero", "revision_id": "r2", "title": EDIT_TITLE,
              "delta": {"ops": [{"insert": DELTA_TEXT + "\n"}, {"insert": {"image": "x.png"}}, {"insert": "Second line\n"}]},
              "base_revision": "r1", "by": "chang@example.test", "ts": "2026-10-05T01:01:00Z"}]
    answers = [{"comment_id": "f" * 12, "number": 1, "category": "findings", "prompt": "Contrast",
                "verdict": "reopen", "text": REOPEN_TEXT, "by": "chang@example.test", "ts": "2026-10-05T01:00:00Z"},
               {"comment_id": "e" * 12, "number": 2, "category": "review", "prompt": "Rename the product?",
                "verdict": "reject", "text": VERDICT_TEXT, "by": "chang@example.test", "ts": "2026-10-05T01:00:30Z"}]
    common = {"comment_ids": ["f" * 12, "e" * 12], "verdict_counts": {"reject": 1}, "undecided_ids": [], "note": NOTE,
              "edits": edits, "edit_count": 1, "session_id": "browser-x"}
    events = [
        {"ts": "2026-10-05T01:00:00Z", "event": "finding_reopened", "comment_id": "f" * 12,
         "by": "chang@example.test", "deferred": True},
        {"ts": "2026-10-05T01:02:00Z", "event": "round_submitted", "by": "chang@example.test", "round_id": "rid1",
         "version": "v1", "answers": answers, **common},
        {"ts": "2026-10-05T01:02:00Z", "event": "session_push", "delivery": "delivered", "delivery_id": "rid1",
         "round": True, "automatic_delivery": True, "owner_session": "test-owner", "comment_count": 2,
         "author": "chang@example.test", **common},
    ]
    page.bus.write_text("".join(json.dumps(e) + "\n" for e in events))


def test_be3_compact_unread_inbox_shows_reopen_verdict_and_library_edit(tmp_path, monkeypatch, capsys):
    page = _finding_page(tmp_path, monkeypatch)
    _mixed_round(page)
    assert cli.cmd_inbox(_args(json=False, category=None, unread=True, all_events=False)) == 0
    out = capsys.readouterr().out
    assert NOTE in out and REOPEN_TEXT in out and VERDICT_TEXT in out
    edit_line = next(line for line in out.splitlines() if "hero" in line)
    assert EDIT_TITLE in edit_line and DELTA_TEXT + " Second line" in edit_line
    # One expansion per round, not again under the session_push line.
    assert out.count(DELTA_TEXT) == 1 and out.count(REOPEN_TEXT) == 1


@pytest.mark.parametrize("category, present, absent", [("findings", REOPEN_TEXT, DELTA_TEXT),
                                                       ("library", DELTA_TEXT, REOPEN_TEXT),
                                                       ("review", VERDICT_TEXT, REOPEN_TEXT)])
def test_be3_filtered_compact_inbox_shows_its_own_items(tmp_path, monkeypatch, capsys, category, present, absent):
    page = _finding_page(tmp_path, monkeypatch)
    _mixed_round(page)
    assert cli.cmd_inbox(_args(json=False, category=category, unread=False, all_events=False)) == 0
    out = capsys.readouterr().out
    assert present in out and absent not in out


def test_be3_compact_cards_show_reopen_and_whole_verdict_text(tmp_path, monkeypatch, capsys):
    page = _finding_page(tmp_path, monkeypatch)
    _mixed_round(page)
    assert cli.cmd_cards(_args(json=False, category=None)) == 0
    out = capsys.readouterr().out
    assert REOPEN_TEXT in out and VERDICT_TEXT in out


# ── BE-9: `finding --fixed N` takes the number `cards` shows ────────────────

def test_be9_fixed_resolves_the_number_cards_shows(tmp_path, monkeypatch, capsys):
    rows = [{"id": "u" * 12, "anchor_id": "d:unnumbered", "text": "Spacing", "author": "agent:test", "status": "open",
             "version": "v1", "category": "findings", "created_at": "2026-10-01T00:00:00Z",
             "finding": {"set": "design", "title": "Spacing"},
             "decision_request": {"prompt": "Fix spacing?", "options": ["fix", "keep"]}},
            {"id": "r" * 12, "number": 1, "anchor_id": "d:review", "text": "Q", "author": "agent:test", "status": "open",
             "version": "v1", "decision_request": {"prompt": "Q", "options": ["a", "b"]}}]
    page = _finding_page(tmp_path, monkeypatch, comments=rows)
    assert cli.cmd_cards(_args(category="findings")) == 0
    [card] = json.loads(capsys.readouterr().out)
    assert card["number"] == 2
    (page.work / "p.txt").write_text("ok")
    assert cli.cmd_finding(_args(fixed="2", proof=["p.txt"])) == 0, capsys.readouterr().err
    assert json.loads(capsys.readouterr().out)["id"] == "u" * 12
    # A number that belongs to a Review card is still not a finding.
    assert cli.cmd_finding(_args(fixed="1", proof=["p.txt"])) == 2
    assert capsys.readouterr().err.strip() == "ERROR: finding: finding 1 not found"


# ── BE-4: --exception / --standalone never demotes the project's main page ──

@pytest.mark.parametrize("running", [True, False])
@pytest.mark.parametrize("flag", [{"exception": "Orchestrator asked"}, {"standalone": True}])
def test_be4_exception_on_the_main_page_is_refused(tmp_path, monkeypatch, capsys, flag, running):
    estate = _make_estate(tmp_path, monkeypatch)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    if not running:
        estate.live.clear()
    capsys.readouterr()
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical", **flag)) == 2
    err = capsys.readouterr().err
    assert "is this project's main page" in err and "workspace --select" in err
    rec = _rec("canonical", "workspace")
    assert rec["workspace_primary"] is True and "exception" not in rec and not rec.get("standalone")
    assert workspace.workspace_data(estate.repo)["workspace"]["slug"] == "canonical/workspace"
    # The one-page rule still holds for a new page.
    other = _second(estate, "fresh")
    assert cli.cmd_publish(_publish_args(other, "canonical")) == 2


def test_be4_workspace_select_clears_exception(tmp_path, monkeypatch, capsys):
    estate = _make_estate(tmp_path, monkeypatch)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    # A record demoted by the earlier bug: exception with no parent page.
    state = cli._load_state_for_project("canonical")
    state["slugs"]["workspace"].update(workspace_primary=False, standalone=True,
                                       exception={"reason": "Orchestrator asked", "parent_slug": None})
    cli._save_state_for_project("canonical", state)
    capsys.readouterr()
    assert workspace.cmd_workspace(SimpleNamespace(select="canonical/workspace", project=None, root=None, json=True)) == 0
    assert json.loads(capsys.readouterr().out)["workspace"]["slug"] == "canonical/workspace"
    rec = _rec("canonical", "workspace")
    assert rec["workspace_primary"] is True and rec["standalone"] is False and "exception" not in rec
    estate.live.clear()
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    rec = _rec("canonical", "workspace")
    assert rec["workspace_primary"] is True and "exception" not in rec


def test_be4_stale_saved_reason_is_not_reapplied_to_the_main_page(tmp_path, monkeypatch, capsys):
    estate = _make_estate(tmp_path, monkeypatch)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    state = cli._load_state_for_project("canonical")
    state["slugs"]["workspace"].update(workspace_primary=False, standalone=True,
                                       exception={"reason": "Orchestrator asked", "parent_slug": None})
    cli._save_state_for_project("canonical", state)
    estate.live.clear()
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    rec = _rec("canonical", "workspace")
    assert rec["workspace_primary"] is True and "exception" not in rec and rec["standalone"] is False


def test_be4_a_real_second_page_keeps_its_saved_reason(tmp_path, monkeypatch, capsys):
    estate = _make_estate(tmp_path, monkeypatch)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    other = _second(estate)
    assert cli.cmd_publish(_publish_args(other, "canonical", exception="Requested worksheet")) == 0
    estate.live.clear()
    assert cli.cmd_publish(_publish_args(other, "canonical")) == 0
    rec = _rec("canonical", "worksheet")
    assert rec["workspace_primary"] is False and rec["exception"]["reason"] == "Requested worksheet"
    assert rec["exception"]["parent_slug"] == "canonical/workspace"


# ── BE-5: parent_slug is matched in both spellings ─────────────────────────

@pytest.mark.parametrize("spelling", ["canonical/workspace", "workspace"])
def test_be5_linked_pages_accept_both_parent_slug_spellings(tmp_path, monkeypatch, capsys, spelling):
    estate = _make_estate(tmp_path, monkeypatch, git=False)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    other = _second(estate)
    assert cli.cmd_publish(_publish_args(other, "canonical")) == 2
    assert cli.cmd_publish(_publish_args(other, "canonical", exception="Requested worksheet")) == 0
    assert _rec("canonical", "worksheet")["exception"]["parent_slug"] == "canonical/workspace"
    state = cli._load_state_for_project("canonical")
    state["slugs"]["worksheet"]["exception"]["parent_slug"] = spelling
    cli._save_state_for_project("canonical", state)
    primary = _rec("canonical", "workspace")
    assert [item["slug"] for item in project_state.linked_pages(primary)] == ["worksheet"]


def test_be18_stale_second_registration_keeps_linked_pages(tmp_path, monkeypatch, capsys):
    estate = _make_estate(tmp_path, monkeypatch, git=False)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    assert cli.cmd_publish(_publish_args(_second(estate), "canonical", exception="Requested worksheet")) == 0
    primary = _rec("canonical", "workspace")
    cli._save_state_for_project("default", {"project": "default", "slugs": {"workspace": {**primary, "port": 8801}}})
    assert [item["slug"] for item in project_state.linked_pages(primary)] == ["worksheet"]


def test_be5_parent_slug_of_another_project_is_not_matched(tmp_path, monkeypatch, capsys):
    estate = _make_estate(tmp_path, monkeypatch, git=False)
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    other = _second(estate)
    assert cli.cmd_publish(_publish_args(other, "canonical", exception="Requested worksheet")) == 0
    state = cli._load_state_for_project("canonical")
    state["slugs"]["worksheet"]["exception"]["parent_slug"] = "elsewhere/workspace"
    cli._save_state_for_project("canonical", state)
    assert project_state.linked_pages(_rec("canonical", "workspace")) == []


# ── BE-6: a malformed copy.json holds back only Library edits ───────────────

def test_be6_invalid_copy_json_does_not_block_a_review_send(server):
    httpd, directory, bus = server
    _, card = _call(httpd, "POST", "/api/comments", _card("d:review"))
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision", {"verdict": "accept", "defer_push": True},
          author="chang@example.com")
    (directory / "copy.json").write_text('{"schema_version": 1, "blocks": [{"id": "hero"}]}')
    status, result = _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    assert status == 200 and result["delivery"] != "noop" and result["comment_ids"] == [card["id"]]
    assert result["edit_count"] == 0 and "copy.json is invalid" in result["library_skipped"]
    assert len(_events(bus, "round_submitted")) == 1
    assert "round_pending" not in _store(directory)["anchors"]["d:review"][0]["decision"]
    status, categories = _call(httpd, "GET", "/api/categories", author="chang@example.com")
    assert status == 200 and "copy.json is invalid" in categories["library"]["error"]
    assert next(c for c in categories["categories"] if c["id"] == "review")["counts"]["done"] == 1


def test_be6_invalid_copy_json_with_nothing_else_is_a_noop_that_says_why(server):
    httpd, directory, _ = server
    (directory / "copy.json").write_text("{not json")
    status, result = _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    assert status == 200 and result["delivery"] == "noop" and "copy.json is invalid" in result["library_skipped"]


# ── BE-11: unexpected shapes get an answer, never a dropped connection ─────

ODD_SHAPES = {
    "decision-null-replies-null": {"status": "open", "decision": None, "replies": None},
    "response-text-number": {"status": "open", "response_text": 5, "replies": []},
    "target-string": {"anchor_id": "copy:yyy", "status": "open", "target": "legacy", "replies": []},
    "decision-string": {"status": "open", "decision": "accept", "replies": []},
    "reply-string": {"status": "open", "replies": ["hi"]},
}


@pytest.mark.parametrize("shape", sorted(ODD_SHAPES))
def test_be11_odd_comment_shapes_answer_every_route(server, shape):
    httpd, directory, _ = server
    comment = {"id": shape, "anchor_id": "s:a", "text": "t", "author": "chang@example.com",
               "created_at": "2026-09-01T00:00:00Z", "version": "v1", **ODD_SHAPES[shape]}
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {comment["anchor_id"]: [comment]},
                                                         "archived": {}}))
    for method, path in (("GET", "/api/categories"), ("GET", "/api/comments"), ("GET", "/api/history"),
                         ("POST", "/api/rounds/submit"), ("POST", "/api/push-session")):
        status, _ = _call(httpd, method, path, {} if method == "POST" else None, author="chang@example.com")
        assert status == 200, (method, path)


def test_be11_plans_folder_without_meta_is_not_a_plan(server):
    httpd, directory, _ = server
    (directory / "plans" / "notes").mkdir(parents=True)
    status, result = _call(httpd, "GET", "/api/categories", author="chang@example.com")
    assert status == 200 and result["plans"] == []


def test_be11_unexpected_page_data_is_a_400_with_a_message(server, monkeypatch):
    from agent_annotate import categories
    httpd, _, _ = server
    monkeypatch.setattr(categories, "list_plans", lambda page_dir: (_ for _ in ()).throw(KeyError("meta")))
    status, result = _call(httpd, "GET", "/api/categories", author="chang@example.com")
    assert status == 400 and "page data could not be read" in result["error"]


# ── BE-12: GETs work on a read-only page dir ────────────────────────────────

def test_be12_gets_work_on_a_read_only_page_dir(server):
    httpd, directory, _ = server
    _call(httpd, "POST", "/api/comments", _card("d:review"))
    (directory / ".comments.json.lock").unlink()
    (directory / "content").mkdir()
    (directory / "content" / "v1.html").write_text("<html><head></head><body><p>x</p></body></html>")
    modes = {path: path.stat().st_mode for path in [directory, *directory.rglob("*")]}
    try:
        for path in modes:
            path.chmod(path.stat().st_mode & ~0o222)
        for route in ("/api/comments", "/comments.json", "/content?v=v1", "/api/history", "/api/categories"):
            assert _call(httpd, "GET", route, author="chang@example.com")[0] == 200, route
        assert not (directory / ".comments.json.lock").exists()
    finally:
        for path, mode in modes.items():
            path.chmod(mode)


# ── BE-13: rounds/submit takes an empty body and ignores unknown fields ────

def test_be13_rounds_submit_accepts_empty_body_and_unknown_fields(server):
    httpd, _, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
    conn.request("POST", "/api/rounds/submit", body=b"", headers={
        "Host": "review.example.test", "Cf-Access-Authenticated-User-Email": "chang@example.com",
        "Cf-Access-Jwt-Assertion": "inert-proxy-validated-assertion", "Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200 and json.loads(resp.read())["delivery"] == "noop"
    conn.close()
    status, result = _call(httpd, "POST", "/api/rounds/submit", {"note": "x", "author": "someone@else"},
                           author="chang@example.com")
    assert status == 200 and result["note"] == "x"
    assert _call(httpd, "POST", "/api/rounds/submit", {"note": 5}, author="chang@example.com")[0] == 400


# ── BE-17: symlinks are refused only below the page dir ─────────────────────

def test_be17_store_lock_allows_symlinked_ancestors_but_not_symlinks_inside(tmp_path):
    from agent_annotate.categories import safe_path
    from agent_annotate.sync_server import _locked_store
    real = tmp_path / "real" / "page"
    real.mkdir(parents=True)
    (tmp_path / "alias").symlink_to(tmp_path / "real")
    with _locked_store(tmp_path / "alias" / "page"):
        pass
    (real / "outside").mkdir()
    (real / "plans").symlink_to(real / "outside")
    with pytest.raises(ValueError, match="symlink"):
        safe_path(tmp_path / "alias" / "page", "plans/p/meta.json")


def test_be17_finding_fix_through_a_symlinked_page_dir(tmp_path, monkeypatch, capsys):
    page = _finding_page(tmp_path, monkeypatch)
    (tmp_path / "alias").symlink_to(page.directory)
    page.record["slug_dir"] = str(tmp_path / "alias")
    assert cli.cmd_finding(_args(fixed="1", proof=["https://example.test/proof"])) == 0, capsys.readouterr().err


# ── BE-19: <base> goes inside a <head> that has attributes ──────────────────

@pytest.mark.parametrize("head", ['<head lang="en">', "<HEAD data-x>", "<head>"])
def test_be19_base_is_inserted_inside_head_with_attributes(server, head):
    from agent_annotate.categories import publish_plan_revision
    httpd, directory, _ = server
    publish_plan_revision(directory, "p", f"<!doctype html><html>{head}<title>t</title></head><body><p>x</p></body></html>")
    status, _, body = _raw(httpd, "/plans/p/v1.html")
    text = body.decode()
    assert status == 200 and text.lower().startswith("<!doctype html>")
    assert text.index(head) < text.index("<base ") < text.index("<title>")


def test_be19_base_without_head_follows_the_doctype(server):
    from agent_annotate.categories import publish_plan_revision
    httpd, directory, _ = server
    publish_plan_revision(directory, "p", "<!DOCTYPE html>\n<p>x</p>")
    text = _raw(httpd, "/plans/p/v1.html")[2].decode()
    assert text.startswith("<!DOCTYPE html>") and text.index("<base ") < text.index("<p>x")


# ── BE-14: a browser cannot file a comment into Findings or Library at will ─

@pytest.mark.parametrize("body", [
    {"anchor_id": "s:a", "text": "Not a finding", "category": "findings"},
    {"anchor_id": "s:a", "text": "Not a copy block", "category": "library"},
    {"anchor_id": "s:a", "text": "No plan", "category": "plans"},
])
def test_be14_browser_category_on_create_is_refused_off_its_anchor(server, body):
    httpd, directory, _ = server
    assert _call(httpd, "POST", "/api/comments", body, author="chang@example.com")[0] == 403
    status, _ = _call(httpd, "POST", "/api/comments/batch", {"items": [body]}, author="chang@example.com")
    assert status == 403
    assert _store(directory)["anchors"] == {}


def test_be14_browser_may_comment_into_library_and_onto_an_existing_finding(server):
    httpd, directory, _ = server
    status, comment = _call(httpd, "POST", "/api/comments",
                            {"anchor_id": "copy:hero", "text": "Shorter?", "category": "library"}, author="chang@example.com")
    assert status == 201 and comment["category"] == "library"
    card = finding(httpd)
    status, comment = _call(httpd, "POST", "/api/comments",
                            {"anchor_id": card["anchor_id"], "text": "Also the footer", "category": "findings"},
                            author="chang@example.com")
    assert status == 201 and comment["category"] == "findings"
    # The reviewer's own comment is not a finding that needs the reviewer.
    counts = category_counts(directory)["findings"]
    assert counts["needs_you"] == 1 and counts["ready"] == 1
    # The agent can still file into Findings.
    assert _call(httpd, "POST", "/api/comments", {"anchor_id": "s:b", "text": "x", "category": "findings"})[0] == 201


# ── BE-15: an export taken before a Send can still be imported ─────────────

def test_be15_copy_import_after_send_keeps_stored_round_pending(server):
    from agent_annotate.copy_state import load_copy, save_copy
    httpd, directory, bus = server
    _seed(directory)
    body = {"delta": {"ops": [{"insert": "Changed\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/revisions", body, author="chang@example.com")[0] == 200
    exported = load_copy(directory)
    exported["blocks"][0]["status"] = "ready"
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["edit_count"] == 1
    saved = save_copy(directory, exported)
    assert saved["blocks"][0]["status"] == "ready"
    assert saved["blocks"][0]["revisions"][-1]["round_pending"] is False
    # Nothing goes out a second time.
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"
    assert len(_events(bus, "round_submitted")) == 1


def test_be15_authored_revision_changes_are_still_refused(server):
    from agent_annotate.copy_state import load_copy, save_copy
    _, directory, _ = server
    _seed(directory)
    exported = load_copy(directory)
    exported["blocks"][0]["revisions"][0]["delta"] = {"ops": [{"insert": "Rewritten\n"}]}
    with pytest.raises(ValueError, match="read copy.json again"):
        save_copy(directory, exported)


# ── BE-16: Discard drops the reviewer's own pending reopens and edits ──────

def test_be16_discard_clears_pending_reopens_and_library_edits(server):
    from agent_annotate.copy_state import load_copy
    httpd, directory, bus = server
    _seed(directory)
    card = finding(httpd)
    mark_finding_fixed(directory, card["id"], by="agent:builder", note="first", proof=[])
    _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "Still broken"}, author="chang@example.com")
    body = {"delta": {"ops": [{"insert": "Changed\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/revisions", body, author="chang@example.com")[0] == 200
    other = {"delta": {"ops": [{"insert": "Theirs\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/revisions", other, author="other@example.com")[0] == 200
    status, result = _call(httpd, "POST", "/api/rounds/discard", {}, author="chang@example.com")
    assert status == 200 and result["comment_ids"] == [card["id"]] and result["edit_count"] == 1
    # Nothing of Chang's goes out with the next Send; the other reviewer's edit is untouched.
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"
    assert _events(bus, "round_submitted") == []
    revisions = load_copy(directory)["blocks"][0]["revisions"]
    assert [(r["author"]["id"], r.get("round_pending")) for r in revisions] == [("agent:builder", None),
                                                                                 ("other@example.com", True)]
    comment = _store(directory)["anchors"]["d:gap"][0]
    assert "round_pending" not in comment and comment["reopened"][-1]["text"] == "Still broken"
    assert [e["event"] for e in _events(bus) if e["event"] == "round_discarded"] == ["round_discarded"]


# ── BE-7 / BE-8: server counts follow the UI (A3a) on old data ─────────────

def _legacy_copy(directory):
    from agent_annotate.copy_state import save_copy
    delta = lambda text: {"ops": [{"insert": text + "\n"}]}  # noqa: E731
    save_copy(directory, {"schema_version": 1, "blocks": [
        {"id": "hero", "title": "Hero", "current": "r0", "revisions": [
            {"id": "r0", "created_at": "2026-09-30T10:00:00+00:00", "author": {"id": "agent:claude"}, "status": "approved",
             "delta": delta("Old hero")},
            {"id": "r_old", "created_at": "2026-09-30T11:00:00+00:00", "author": {"id": "chang@example.com", "name": "Chang"},
             "status": "proposed", "base_revision": "r0", "delta": delta("Chang's hero")}]},
        {"id": "tagline", "title": "Tagline", "current": "r0", "revisions": [
            {"id": "r0", "created_at": "2026-09-30T10:00:00+00:00", "author": {"id": "agent:claude"}, "status": "approved",
             "delta": delta("Tag")}]}]})


def test_be8_legacy_library_blocks_do_not_need_you(server):
    httpd, directory, _ = server
    _legacy_copy(directory)
    counts = category_counts(directory, "chang@example.com", read_state={})["library"]
    assert counts == {"needs_you": 0, "ready": 0, "waiting": 1, "done": 1, "unread": 0}
    status, result = _call(httpd, "GET", "/api/categories", author="chang@example.com")
    assert status == 200 and next(c for c in result["categories"] if c["id"] == "library")["counts"] == counts
    # Nothing old goes out again.
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"


def test_be8_an_explicit_needs_you_status_still_counts(server):
    from agent_annotate.copy_state import load_copy, save_copy
    _, directory, _ = server
    _legacy_copy(directory)
    document = load_copy(directory)
    document["blocks"][1]["status"] = "needs_you"
    save_copy(directory, document)
    assert category_counts(directory)["library"]["needs_you"] == 1


def test_be7_review_unread_is_the_rails_scope(server):
    """A3a: Review unread = unread cards on the current version plus cards that
    follow the viewer; a resolved comment on an older version is not counted."""
    _, directory, _ = server
    (directory / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]}))
    rows = [{"id": "old-done", "anchor_id": "s:a", "text": "x", "author": "chang@example.com", "status": "resolved_in_version",
             "version": "v1", "response_text": "Fixed"},
            {"id": "old-addressed", "anchor_id": "s:b", "text": "x", "author": "chang@example.com",
             "status": "addressed_by_agent", "version": "v1", "response_text": "Done"},
            {"id": "old-open-card", "anchor_id": "d:q", "text": "Q", "author": "agent:x", "status": "open", "version": "v1",
             "decision_request": {"prompt": "Q", "options": ["a", "b"]}},
            {"id": "current", "anchor_id": "s:c", "text": "x", "author": "chang@example.com", "status": "open", "version": "v2"}]
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {r["anchor_id"]: [r] for r in rows},
                                                         "archived": {}}))
    assert category_counts(directory, "chang@example.com", read_state={})["review"]["unread"] == 2


# ── helpers for exception tests (from the reviewer's probe) ────────────────

def _publish_args(directory, project=None, **extra):
    base = dict(slug_dir=str(directory), project=project, port=None, transport=None,
                hostname=None, path_prefix=None, standalone=False, exception=None, public=False,
                skip_js_lint=False, no_verify=False, verify_timeout=1)
    base.update(extra)
    return SimpleNamespace(**base)


def _make_estate(tmp_path, monkeypatch, git=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    if git:
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "remote.origin.url",
                        "https://example.test/team/project.git"], check=True)
    monkeypatch.chdir(repo)
    for name, path in {"STATE_DIR": tmp_path / "state", "LOCK_DIR": tmp_path / "locks",
                       "BUS_ROOT": tmp_path / "bus", "CONFIG_DIR": tmp_path / "config",
                       "PROJECTS_TOML": tmp_path / "config" / "projects.toml"}.items():
        monkeypatch.setattr(cli, name, path)
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cli, "_ensure_shim_installed", lambda: (False, "inert"))
    monkeypatch.setattr(cli, "_ensure_hook_installed", lambda: (False, "inert"))
    monkeypatch.setattr(cli, "_check_js_lint", lambda *a, **k: (True, []))
    monkeypatch.setattr(cli, "_run_gate", lambda *a: None)
    monkeypatch.setattr(cli, "_route_host", lambda record: None)
    monkeypatch.setattr(cli, "_inv", lambda: "annotate")
    monkeypatch.setattr(cli, "_api", lambda *a, **k: pytest.fail("Unexpected HTTP write"))
    live, starts = set(), []
    counter = iter(range(18000, 19000))
    mutex = threading.Lock()

    def start(directory, port, bus_dir, mount):
        with mutex:
            pid = 100000 + len(starts)
            starts.append(str(directory))
            live.add(pid)
        return pid

    def route(slug, port, **kwargs):
        url = f"https://reviews.example/{slug}/"
        return {"url": url, "details": {"transport": "funnel", "public_url": url}}

    monkeypatch.setattr(cli, "_find_free_port_after", lambda *a, **k: next(counter))
    monkeypatch.setattr(cli, "_start_server", start)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid in live)
    monkeypatch.setattr(delivery, "capture_target", lambda s, a: None)
    monkeypatch.setattr(transports, "load", lambda name: SimpleNamespace(publish=route))
    monkeypatch.setenv("CODEX_THREAD_ID", "original-owner")
    directory = tmp_path / "reviews" / "workspace"
    source = tmp_path / "initial.md"
    source.write_text("---\ntitle: Project\n---\n\n# Project\n\n## Progress\n\nBuild passed.\n")
    pagegen.generate(source, directory, version="v1")
    return SimpleNamespace(root=tmp_path, repo=repo, directory=directory, live=live, starts=starts)


def _second(estate, name="worksheet"):
    other = estate.root / "reviews" / name
    src = estate.root / f"{name}.md"
    src.write_text(f"# {name}\n\nEvidence.\n")
    pagegen.generate(src, other, version="v1")
    return other


def _rec(project, slug):
    return cli._load_state_for_project(project)["slugs"][slug]


# ── helpers for CLI tests ───────────────────────────────────────────────────

def _finding_page(tmp_path, monkeypatch, comments=None):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    directory = tmp_path / "page"
    directory.mkdir()
    rows = comments or [{"id": "f" * 12, "number": 1, "anchor_id": "d:q1", "text": "Contrast", "author": "agent:test",
                         "status": "open", "version": "v1", "category": "findings",
                         "finding": {"set": "design", "title": "Contrast"},
                         "decision_request": {"prompt": "Contrast", "options": ["fix", "keep"]}}]
    store = {"schema_version": 2, "anchors": {}, "archived": {}}
    for row in rows:
        store["anchors"].setdefault(row["anchor_id"], []).append(row)
    (directory / "comments.json").write_text(json.dumps(store))
    (directory / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [{"version": "v1"}]}))
    bus = tmp_path / "events.ndjson"
    bus.write_text("")
    record = {"project": "project", "slug": "main", "slug_dir": str(directory), "bus_file": str(bus),
              "url": "http://localhost:8987/", "local_url": "http://localhost:8987/",
              "owner_session": "test-owner", "workspace_primary": True}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "main", record)])
    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", tmp_path / "offsets")
    monkeypatch.setattr(cli, "_session_id", lambda: "test-owner")
    return SimpleNamespace(directory=directory, record=record, bus=bus, root=tmp_path, work=work)


def _args(**kwargs):
    base = dict(slug="project/main", project=None, json=True, note="", author=None)
    base.update(kwargs)
    return SimpleNamespace(**base)
