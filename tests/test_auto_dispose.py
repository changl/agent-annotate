"""New versions withdraw only agent questions that were not asked again."""

import http.server
import json
import threading
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.sync_server import make_handler


def _card(cid, number, verdict=None):
    return {"id": cid, "anchor_id": f"d:q{number}", "number": number, "text": f"Q{number}?",
            "status": "open", "version": "v1", "author": "agent:claude",
            "decision_request": {"prompt": f"Q{number}?"},
            **({"decision": {"verdict": verdict, "text": "x", "by": "r@x"}} if verdict else {})}


@pytest.fixture
def page(tmp_path, monkeypatch):
    slug_dir = tmp_path / "reviews" / "demo"
    (slug_dir / "versions").mkdir(parents=True)
    (slug_dir / "versions" / "v1.html").write_text(
        '<p data-anchor-id="d:q1"></p><p data-anchor-id="d:q2"></p><p data-anchor-id="d:q3"></p>')
    (slug_dir / "versions" / "v2.html").write_text(
        '<section data-anchor-id="s:plan"><h2>Plan</h2>'
        '<ul><li data-anchor-id="s:plan:li1">Backfill runs nightly (#2).</li>'
        '<li data-anchor-id="s:plan:li2">Colour #fff and issue#1 are not mentions.</li></ul>'
        '</section><div data-anchor-id="d:q3">Still open</div>'
        '<script>var x = "#1";</script>')
    (slug_dir / "current.html").symlink_to("versions/v1.html")
    (slug_dir / "current.meta.json").write_text(json.dumps(
        {"current": "v1", "history": [{"version": "v1", "ts": "", "label": ""}]}))
    (slug_dir / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {
        "d:q1": [_card("aaaaaaaaaaaa", 1)],
        "d:q2": [_card("bbbbbbbbbbbb", 2, "comment")],
        "d:q3": [_card("cccccccccccc", 3)],
    }, "archived": {}}))
    (slug_dir / "cards.json").write_text(json.dumps(
        [{"number": 3, "anchor_id": "d:q3", "decision_request": {"prompt": "Q3 again?", "evidence": [{"anchor": "s:plan"}]}}]))
    bus_dir = tmp_path / "bus" / "reviews"
    handler = make_handler(artifact_dir=slug_dir, public_base_path="", slug="demo",
                           bus_dir=bus_dir, v2_mode=True)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    record = {"slug": "demo", "slug_dir": str(slug_dir), "project": "reviews",
              "port": httpd.server_address[1],
              "local_url": f"http://127.0.0.1:{httpd.server_address[1]}/",
              "bus_file": str(bus_dir / "demo.ndjson")}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("reviews", "demo", record)])
    try:
        yield slug_dir
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _store(slug_dir):
    return {c["id"]: c for _a, c in cli._iter_comments(
        cli._coerce_store_file(slug_dir))}


def _publish(slug_dir):
    return cli.cmd_publish_version(SimpleNamespace(
        slug_dir=str(slug_dir), version="v2", label="round 2", project=None))


def test_new_version_withdraws_unasked_and_preserves_reviewer_content(page):
    before = _store(page)
    store = cli._coerce_store_file(page)
    store["anchors"]["s:reviewer"] = [{"id": "reviewer", "anchor_id": "s:reviewer",
        "author": "reviewer@example.com", "version": "v1", "status": "open", "text": "Please keep this."}]
    replied = _card("replied", 4)
    replied["replies"] = [{"author": "reviewer@example.com", "text": "My answer"}]
    pending = _card("pending", 5, "comment")
    pending["decision"]["round_pending"] = True
    store["anchors"]["d:q4"] = [replied]
    store["anchors"]["d:q5"] = [pending]
    (page / "comments.json").write_text(json.dumps(store))

    assert _publish(page) == 0
    after = _store(page)
    assert "decision_request" not in after["aaaaaaaaaaaa"]
    assert after["aaaaaaaaaaaa"]["withdrawn"]["reason"] == "not asked again in v2"
    assert after["aaaaaaaaaaaa"]["withdrawn"]["decision_request"] == before["aaaaaaaaaaaa"]["decision_request"]
    assert after["aaaaaaaaaaaa"]["version"] == "v1"
    assert after["bbbbbbbbbbbb"] == before["bbbbbbbbbbbb"]
    assert after["cccccccccccc"] == before["cccccccccccc"]  # asked again in cards.json
    assert after["reviewer"] == store["anchors"]["s:reviewer"][0]
    assert after["replied"] == replied
    assert after["pending"] == pending
    assert cli._read_meta(page)["current"] == "v2"
    assert cli._decision_cards(cli._coerce_store_file(page))[0]["id"] != "aaaaaaaaaaaa"


def test_withdraw_by_display_number_and_counts(page, capsys):
    from agent_annotate.categories import category_counts
    from agent_annotate.hooks.check_comment_bus import _load_cards

    assert cli.cmd_withdraw(SimpleNamespace(slug="reviews/demo", comment_id="1", why="No longer needed",
                                           project=None, author="agent:test", json=False)) == 0
    assert "withdrawn aaaaaaaaaaaa #1" in capsys.readouterr().out
    withdrawn = _store(page)["aaaaaaaaaaaa"]
    assert withdrawn["withdrawn"]["reason"] == "No longer needed"
    assert category_counts(page)["review"]["needs_you"] == 1
    assert "aaaaaaaaaaaa" not in _load_cards(str(page))
    assert "aaaaaaaaaaaa" not in [c["id"] for c in cli._decision_cards(cli._coerce_store_file(page))]


def test_withdraw_refuses_an_answered_card_without_writing(page, capsys):
    before = (page / "comments.json").read_bytes()
    assert cli.cmd_withdraw(SimpleNamespace(slug="reviews/demo", comment_id="2", why="Stale",
                                           project=None, author="agent:test", json=False)) == 2
    assert "only open, unanswered agent questions" in capsys.readouterr().err
    assert (page / "comments.json").read_bytes() == before


def test_ask_version_withdraws_omitted_questions_and_reposes_open_card(page):
    assert cli.cmd_ask(SimpleNamespace(slug="reviews/demo", from_file=str(page / "cards.json"),
                                      version="v2", project=None, author="agent:claude", json=True)) == 0
    store = _store(page)
    assert store["aaaaaaaaaaaa"]["withdrawn"]["reason"] == "not asked again in v2"
    assert store["cccccccccccc"]["version"] == "v2"
    assert store["bbbbbbbbbbbb"]["decision"]["text"] == "x"


def test_new_publish_with_no_cards_does_not_reuse_stale_cards_json(page, monkeypatch):
    from agent_annotate import pagegen
    source = page / "next.md"
    source.write_text("---\ntitle: New review\n---\n\n## Plan\n\nA revised plan.\n")
    monkeypatch.setattr(pagegen, "_call_publish", lambda *a: 0)
    assert pagegen.cmd_new(SimpleNamespace(slug_dir=str(page), from_file=str(source), version="v2",
        label=None, project="reviews", publish=True, ask=False, exception=None)) == 0
    store = _store(page)
    assert all(store[cid]["withdrawn"]["reason"] == "not asked again in v2"
               for cid in ("aaaaaaaaaaaa", "cccccccccccc"))
    assert json.loads((page / "cards.json").read_text()) == []
    assert json.loads((page / "versions" / "v2.cards.json").read_text()) == []


def test_publishing_a_staged_version_uses_its_own_cards(page):
    (page / "versions" / "v2.cards.json").write_text("[]")
    assert _publish(page) == 0
    assert "withdrawn" in _store(page)["cccccccccccc"]


def test_older_version_never_withdraws_a_newer_question(page):
    store = cli._coerce_store_file(page)
    store["anchors"]["d:q1"][0]["version"] = "v3"
    (page / "comments.json").write_text(json.dumps(store))
    assert _publish(page) == 0
    assert "withdrawn" not in _store(page)["aaaaaaaaaaaa"]
