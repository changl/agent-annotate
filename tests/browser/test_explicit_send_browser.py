"""Only the Send button publishes drafts; delivery badges require owner receipts."""

import http.server
import io
import json
import threading
from contextlib import contextmanager, redirect_stdout
from types import SimpleNamespace

import pytest
from single_page import feedback, go, ready, section
from test_card_layout import CHROME
from test_single_page_acceptance import workspace  # noqa: F401
from test_workspace_intent import _page

from agent_annotate import cli, delivery, sync_server
from agent_annotate.hooks import check_comment_bus as hook

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


@contextmanager
def sandbox_page(tmp_path, monkeypatch, stages, directory=None, reviewer="reviewer@example.com"):
    directory = directory or _page(tmp_path)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    bus = tmp_path / "bus" / "sandbox"
    target = {"handle": "sandbox-only", "pid": 123, "process_start": "sandbox", "agent": "codex"}
    record = {"slug_dir": str(directory), "bus_file": str(bus / "review.ndjson"),
              "owner_session": "sandbox-owner", "owner_target": target}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("sandbox", "review", record)])
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sandbox-owner")
    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", state / "bus-offsets")
    monkeypatch.setattr(hook, "STATE", str(state))
    monkeypatch.setattr(hook, "BUS_ROOT", str(bus.parent))
    monkeypatch.setattr(hook, "HOOK_OFFSET_ROOT", str(state / "hook-offsets"))
    monkeypatch.setattr(hook, "INBOX_OFFSET_ROOT", str(state / "bus-offsets"))
    (state / "sandbox.json").write_text(json.dumps({"project": "sandbox", "slugs": {"review": record}}))
    meta_path = directory / "current.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["owner"] = {"owner_session": "sandbox-owner", "target": target}
    meta_path.write_text(json.dumps(meta))
    for module in (cli, delivery, sync_server):
        monkeypatch.setattr(module, "STATE_DIR", state)
    monkeypatch.setattr(cli, "LOCK_DIR", state / "locks")
    monkeypatch.setattr(delivery, "_target_ready", lambda target: (True, ""))
    monkeypatch.setattr(delivery, "_process", lambda pid: ("sandbox", "codex"))
    sends = []
    def fake_orca(*args):
        assert args[:2] == ("terminal", "send") and args[3] == "sandbox-only"
        sends.append(args)
        if stages is None:
            raise TimeoutError("sandbox owner delivery failed")
        return {"send": {"accepted": True, "prompt": {"stages": stages}}}
    monkeypatch.setattr(delivery, "_orca", fake_orca)
    handler = sync_server.make_handler(artifact_dir=directory, public_base_path="", slug="review", bus_dir=bus,
                                       local_author=reviewer, skill_dir=sync_server.WEB_DIR)
    # Synchronous fake owner dispatch makes the receipt deterministic; no real terminal is touched.
    monkeypatch.setattr(handler, "_wake_feedback_owner", lambda self: delivery.dispatch_record(record, "sandbox", "review"))
    for port in range(18700, 18800):
        try:
            httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    else:
        pytest.fail("no sandbox port available in 18700-18799")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}/"
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_default_timeout(5000)
                page.set_default_navigation_timeout(15000)
                page.goto(base, wait_until="networkidle")
                ready(page)
                yield page, directory, record, sends
            finally:
                browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("stages, received", [(None, False), (["queued"], False), (["input_accepted"], True)])
def test_only_manual_send_and_confirmed_owner_receipt_can_say_sent(tmp_path, monkeypatch, stages, received):
    with sandbox_page(tmp_path, monkeypatch, stages) as (page, directory, record, sends):
        feedback(page)
        page.locator('.citem[data-comment-id="question-11"] .decision-btn').first.click()
        section(page, "ready")
        assert sends == []
        assert not cli._load_store(record)["anchors"]["d:q11"][0].get("decision")
        page.locator("#send-btn").click()
        page.locator("#sum-gf-ta").fill("PRIVATE GENERAL FEEDBACK")
        page.locator("#sum-gf-ta").press("Control+Enter")
        page.wait_for_timeout(250)
        assert sends == []
        assert not (directory / "rounds.ndjson").exists()
        before = io.StringIO()
        with redirect_stdout(before):
            cli.cmd_inbox(SimpleNamespace(slug="review", project="sandbox", unread=True, json=True, all_events=False))
        assert "PRIVATE GENERAL FEEDBACK" not in before.getvalue()
        assert hook._scan("sandbox-owner") == []
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        assert len(sends) == 1
        status = delivery.delivery_status("sandbox", "review")["latest"]
        assert status["delivered"] is received
        note = page.locator("#send-note")
        if received:
            playwright.expect(page.locator('.citem[data-comment-id="question-11"] .send-state').first).to_have_text("Sent", timeout=15000)
        else:
            playwright.expect(note).to_contain_text("owner delivery pending")
        if not received:
            assert "Sent" not in note.inner_text()
            assert page.locator('.send-state:text-is("Sent")').count() == 0
        assert hook._scan("sandbox-owner")[0].startswith("ROUND SUBMITTED")
        after = io.StringIO()
        with redirect_stdout(after):
            cli.cmd_inbox(SimpleNamespace(slug="review", project="sandbox", unread=True, json=True, all_events=False))
        assert "PRIVATE GENERAL FEEDBACK" in after.getvalue()
        assert delivery.delivery_status("sandbox", "review")["latest"]["state"] == "acknowledged"
        rounds = [json.loads(line) for line in (directory / "rounds.ndjson").read_text().splitlines()]
        assert any("PRIVATE GENERAL FEEDBACK" in json.dumps(r) for r in rounds)


@pytest.mark.parametrize("view", ["review", "library", "findings", "plans"])
def test_owner_receipt_updates_badges_without_replacing_a_typed_draft(tmp_path, monkeypatch, workspace, view):  # noqa: F811
    with sandbox_page(tmp_path, monkeypatch, ["queued"], directory=workspace) as (page, _, _, sends):
        feedback(page)
        page.locator('.citem[data-comment-id="question-11"] .decision-btn').first.click()
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        section(page, "waiting")
        card = page.locator('.citem[data-comment-id="question-11"]')
        card.locator('[data-action="open-card"]').click()
        draft = card.locator('textarea[data-decision-say-ta="question-11"]')
        draft.fill("Keep typing while delivery finishes")
        if view != "review":
            go(page, view)
        journal = tmp_path / "state/deliveries/sandbox/review.json"
        data = json.loads(journal.read_text())
        row = next(iter(data["deliveries"].values()))
        row["receipt"]["prompt"]["stages"] = ["input_accepted"]
        journal.write_text(json.dumps(data))
        playwright.expect(page.locator("#delivery-status")).to_contain_text("Sent to owner session", timeout=15000)
        playwright.expect(page.locator("#send-note")).to_contain_text("Sent to session")
        if view == "review":
            playwright.expect(card.locator('[data-delivery-ids]').first).to_have_text("Sent")
            assert draft.input_value() == "Keep typing while delivery finishes"
        assert len(sends) == 1
