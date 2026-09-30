"""Earlier items are disposed from the new version itself.

The bench caught agents resolving v1 items before v2 existed (HTTP 400), then
`new --version v2 --publish` refusing because the items had no disposition:
two failures and a retry on every round. The new version already says where
each item went, so publish-version records it: a card with the same number
carries the item, and the first element naming it as #N resolves it there.
"""

import http.server
import json
import threading
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.sync_server import make_handler


def _card(cid, number, verdict):
    return {"id": cid, "anchor_id": f"d:q{number}", "number": number, "text": f"Q{number}?",
            "status": "open", "version": "v1", "author": "agent:claude",
            "decision_request": {"prompt": f"Q{number}?"},
            "decision": {"verdict": verdict, "text": "x", "by": "r@x"}}


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
        "d:q1": [_card("aaaaaaaaaaaa", 1, "select")],
        "d:q2": [_card("bbbbbbbbbbbb", 2, "comment")],
        "d:q3": [_card("cccccccccccc", 3, "select")],
    }, "archived": {}}))
    (slug_dir / "cards.json").write_text(json.dumps(
        [{"number": 3, "anchor_id": "d:q3", "decision_request": {"prompt": "Q3 again?"}}]))
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


def test_mentions_pick_the_innermost_anchor_and_skip_non_mentions(page):
    html = (page / "versions" / "v2.html").read_text()
    assert cli._mentions_by_anchor(html) == {2: "s:plan:li1"}


def test_an_unmentioned_item_still_blocks_and_the_error_says_how(page, capsys):
    assert _publish(page) == 2
    err = capsys.readouterr().err
    assert "aaaaaaaaaaaa" in err
    assert "Name each as #N" in err
    store = _store(page)
    # The others were recorded on the way: no retry needed for them.
    assert store["bbbbbbbbbbbb"]["status"] == "resolved_in_version"
    assert store["bbbbbbbbbbbb"]["resolution_anchor_id"] == "s:plan:li1"
    assert store["cccccccccccc"]["version"] == "v2"


def test_a_version_that_accounts_for_every_item_publishes_in_one_call(page, capsys):
    html = (page / "versions" / "v2.html").read_text()
    (page / "versions" / "v2.html").write_text(html.replace(
        "Still open", "Still open").replace(
        '<li data-anchor-id="s:plan:li2">', '<li data-anchor-id="s:plan:li2">#1 done. '))
    assert _publish(page) == 0
    out = capsys.readouterr().out
    assert "earlier items: resolved #1, resolved #2, carried #3" in out
    store = _store(page)
    assert store["aaaaaaaaaaaa"]["resolution_anchor_id"] == "s:plan:li2"
    assert store["cccccccccccc"]["status"] == "open"
