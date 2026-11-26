"""uzd.9: settled feedback from older versions lives in a cold generation; every view reads as before."""
import argparse
import copy
import http.client
import itertools
import json
import os
import runpy
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_annotate import cold, delivery, store, sync_server
from agent_annotate.sync_server import _docs_sig, _page_keep, _page_rules


def _q(cid, aid, version, prompt, number, **extra):
    return {"id": cid, "anchor_id": aid, "version": version, "number": number, "author": "agent:test",
            "status": "open", "text": prompt, "replies": [],
            "decision_request": {"prompt": prompt, "options": [{"id": "a", "label": "A"}]}, **extra}


def _note(cid, aid, version, number, **extra):
    return {"id": cid, "anchor_id": aid, "version": version, "number": number, "author": "reviewer@example.test",
            "status": "addressed_by_agent", "text": f"Note {cid}", "replies": [], **extra}


ANSWERED = {"verdict": "accept", "by": "reviewer@example.test", "ts": "2026-01-01T00:00:00Z"}
COLD = {"settled", "body-new", "old-note", "gone", "plan-v1"}
HOT = {"now", "open-old", "peer", "body-old", "unsent", "plan-v2", "plan-v3", "plan-q", "draft", "mixed-open"}


def _store():
    done = {"status": "addressed_by_agent", "decision": ANSWERED}
    anchors = {
        # A current card that reuses an old number (4) and asks a prompt answered before.
        "d:now": [_q("now", "d:now", "v3", "Q2: Ship it?", 4)],
        "d:open-old": [_q("open-old", "d:open-old", "v1", "Still open?", 1)],
        "d:peer": [_q("peer", "d:peer", "v1", "Ship it?", 3, **done)],
        "d:settled": [_q("settled", "d:settled", "v1", "Old and done?", 4, **done)],
        "d:body": [_q("body-old", "d:body", "v2", "Baked in the body?", 5, **done),
                   _q("body-new", "d:body", "v2", "Asked again?", 6, **done)],
        "s:note": [_note("unsent", "s:note", "v1", 7,
                         replies=[{"author": "reviewer@example.test", "text": "Not sent", "sent_at": None}]),
                   _note("old-note", "s:note", "v2", 8)],
        "plan:p": [{**_note(f"plan-{v}", "plan:p", v, 9 + n, category="plans", doc="plan:p"), "status": "resolved_in_version"}
                   for n, v in enumerate(("v1", "v2", "v3"))]
                  + [_q("plan-q", "plan:p", "v1", "Plan question?", 12, category="plans", doc="plan:p", **done)],
        "d:draft": [_note("draft", "d:draft", "v9", 13)],
    }
    for k in range(40):
        aid = f"d:old{k % 8}"
        item = (_q(f"old-q-{k}", aid, ("v1", "v2")[k % 2], f"Old question {k}?", 20 + k, **done) if k % 2
                else _note(f"old-n-{k}", aid, ("v1", "v2")[k % 3 == 0], 20 + k,
                           replies=[{"author": "agent:test", "text": "Done", "sent_at": "2026-01-01T00:00:00Z"}]))
        if k % 5 == 0:
            item["carry_history"] = [{"from": "v1", "to": "v2"}]
        anchors.setdefault(aid, []).append(item)
    anchors["d:old0"].insert(2, _q("mixed-open", "d:old0", "v1", "Open between settled items?", 70))
    archived = {"d:gone": [_q("gone", "d:gone", "v1", "Archived?", 71, status="archived", decision=ANSWERED)]}
    return {"schema_version": 2, "anchors": anchors, "archived": archived}


CARDS = '<div class="card" data-anchor-id="d:body">Q</div><div class="card" data-anchor-id="d:now">Q</div>'


def _page(root, data=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "versions").mkdir()
    for v in ("v1", "v2", "v3"):
        (root / "versions" / f"{v}.html").write_text(CARDS)
    (root / "current.meta.json").write_text(json.dumps(
        {"current": "v3", "history": [{"version": v} for v in ("v1", "v2", "v3")]}))
    (root / "plans/p/versions").mkdir(parents=True)
    (root / "plans/p/meta.json").write_text(json.dumps(
        {"current": "v2", "history": [{"version": v} for v in ("v1", "v2", "v3")]}))
    (root / "plans/p/versions/v2.html").write_text('<div class="card" data-anchor-id="plan:p">Q</div>')
    (root / "comments.json").write_text(json.dumps(data or _store()))
    return root


def _publish_v4(root):
    (root / "versions/v4.html").write_text(CARDS)
    store.write_text(root / "current.meta.json", json.dumps(
        {"current": "v4", "history": [{"version": v} for v in ("v1", "v2", "v3", "v4")]}))


def _docs(root):
    meta = json.loads((root / "current.meta.json").read_text())
    whole = store.read_comments(root)
    return {**sync_server._review_docs(root, meta), **sync_server._plan_docs(root, whole)}


def _raw(root):
    return json.loads((root / "comments.json").read_text())


def _ids(data, areas=cold.AREAS):
    return {c["id"] for area in areas for items in (data.get(area) or {}).values() for c in items}


def _cold_path(root, gen=None):
    """The cold generation comments.json names."""
    return root / ".cold" / f"{gen or _raw(root)[cold.KEY]['gen']}.json"


def _cold_data(root, gen=None):
    return json.loads(_cold_path(root, gen).read_text())


def _split(root):
    """Does the page hold a cold generation?"""
    return bool(list((root / ".cold").glob("*.json")))


def request(httpd, path, method="GET", payload=None, headers=None):
    connection = http.client.HTTPConnection(*httpd.server_address, timeout=5)
    try:
        connection.request(method, path, json.dumps(payload) if payload is not None else None, headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    (state / "project.json").write_text('{"slugs": {}}')
    from agent_annotate import cli
    for module in (sync_server, delivery, cli):
        monkeypatch.setattr(module, "STATE_DIR", state)
    monkeypatch.setattr(delivery, "_target_ready", lambda _: (True, ""))
    monkeypatch.setattr(delivery, "_orca", lambda *a: {"send": {"accepted": True}})
    monkeypatch.setattr(sync_server, "_now_iso", lambda: "2026-11-26T00:00:00Z")
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    monkeypatch.setattr(cold, "SPLIT", True, raising=False)  # 2.35.0
    counter = {"n": itertools.count(1)}
    monkeypatch.setattr(sync_server.uuid, "uuid4", lambda: uuid.UUID(int=next(counter["n"]) << 80))
    servers = []

    def serve(root, name, *, split=True):
        handler = sync_server.make_handler(root, slug="page", bus_dir=root / name, local_author="reviewer@example.test")
        if not split:
            handler._split_store = lambda self: None
        httpd = sync_server.ReviewHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append((httpd, thread))
        return httpd, handler

    serve.reset_ids = lambda: counter.update(n=itertools.count(1))
    yield serve
    for httpd, thread in servers:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


VIEWS = ("/comments.json?view=page", "/comments.json?view=poll", "/comments.json", "/api/comments",
         "/api/categories", "/api/history", "/api/history?latest=1")


def _views(httpd, headers=None):
    out = {}
    for path in VIEWS:
        status, _, body = request(httpd, path, headers=headers)
        assert status == 200, (path, body[:300])
        data = json.loads(body)
        if isinstance(data, dict):
            data.pop("store_mark", None)
        out[path] = json.dumps(data, ensure_ascii=False)
    return out


def _same(a, b, root_a, root_b):
    for name in ("proj-a/page.ndjson",):  # the bus carries wall-clock seconds: History reads one copy
        source = root_a / name
        if source.exists():
            (root_b / "proj-b").mkdir(exist_ok=True)
            shutil.copyfile(source, root_b / "proj-b/page.ndjson")
    for headers in (None, {"X-Annotate-Agent": "agent:test"}):
        va, vb = _views(a, headers), _views(b, headers)
        for path in VIEWS:
            assert va[path] == vb[path], path
    assert json.dumps(store.read_comments(root_a)) == json.dumps(store.read_comments(root_b))
    assert json.dumps(store.snapshot(root_a).comments) == json.dumps(store.snapshot(root_b).comments)


def _writes(httpd, serve):
    serve.reset_ids()
    agent = {"X-Annotate-Agent": "agent:test"}
    steps = [
        ("POST", "/api/comments/settled/reply", {"text": "Back to this"}, None),      # cold: reopens it
        ("POST", "/api/comments/old-q-3/decision", {"verdict": "changes", "text": "Revise"}, None),  # cold, answered
        ("PUT", "/api/comments/old-note", {"status": "archived"}, None),               # cold, moves area
        ("POST", "/api/comments", {"anchor_id": "d:now", "text": "New note", "version": "v3"}, None),
        ("POST", "/api/comments/batch", {"idempotency": "anchor", "items": [
            {"anchor_id": "d:old1", "text": "Old question 1?", "version": "v4", "number": 21,
             "decision_request": {"prompt": "Old question 1?", "options": [{"id": "a", "label": "A"}]}}]}, agent),
        ("POST", "/api/rounds/submit", {}, None),
    ]
    out = []
    for method, path, payload, headers in steps:
        status, _, body = request(httpd, path, method, payload, headers)
        assert status in (200, 201), (path, body[:300])
        out.append(json.loads(body))
    return out


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_split_page_reads_and_writes_exactly_as_one_file(tmp_path, sandbox, backend):
    root_a, root_b = _page(tmp_path / "a"), _page(tmp_path / "b")
    original = json.dumps(_store())
    if backend == "sqlite":
        for root in (root_a, root_b):
            store.import_page(root, project="p", slug="page")
    a, _ = sandbox(root_a, "proj-a")
    b, _ = sandbox(root_b, "proj-b", split=False)

    # The first page view migrates: settled older feedback moves out, nothing else changes.
    _same(a, b, root_a, root_b)
    raw = _raw(root_a)
    assert cold.KEY in raw and _split(root_a) and not _split(root_b)
    cold_ids = _ids(_cold_data(root_a))
    assert COLD <= cold_ids and not (HOT & cold_ids) and not (_ids(raw) & cold_ids)
    assert json.dumps(store.read_comments(root_a)) == original
    if backend == "sqlite":
        assert store.backend(root_a) == "sqlite"
        conn = store.connect(root_a / store.DB_NAME)
        assert json.loads(store.export_texts(conn)["comments.json"]) == raw
        conn.close()

    marks = [json.loads(request(s, "/comments.json?view=page")[2])["store_mark"] for s in (a, b)]
    results = [_writes(s, sandbox) for s in (a, b)]
    assert results[0] == results[1]
    assert results[0][3]["number"] == 72  # one past the highest number, cold ones included
    _same(a, b, root_a, root_b)
    hot = _ids(_raw(root_a))
    assert {"settled", "old-q-3", "old-note"} <= hot  # written: moved back
    assert cold.KEY in _raw(root_a) and "body-new" not in hot
    since = []
    for s, mark in zip((a, b), marks):
        page = json.loads(request(s, "/comments.json?view=page", headers={"X-Annotate-Store-Mark": mark})[2])
        since.append(sorted(page.get("changed_after", [])))
    assert since[0] == since[1] and "settled" in since[0] and "body-new" not in since[0]

    # A new version re-splits for the new documents; a generation never changes once written.
    gen = _raw(root_a)[cold.KEY]["gen"]
    before = _cold_path(root_a).read_bytes()
    for root in (root_a, root_b):
        _publish_v4(root)
    _same(a, b, root_a, root_b)
    raw = _raw(root_a)
    assert raw[cold.KEY]["docs"] == _docs_sig(_docs(root_a))
    assert _cold_path(root_a, gen).read_bytes() == before
    assert raw[cold.KEY]["gen"] >= gen  # numbers only grow
    # Reopened and changes-requested items are not settled: they stay hot.
    assert {"settled", "old-q-3"} <= _ids(raw)


def test_reader_of_a_page_without_cold_store_is_unchanged(tmp_path):
    root = _page(tmp_path / "p")
    assert json.dumps(store.read_comments(root)) == json.dumps(_store())
    assert cold.merged(root, _store()) == _store() and not _split(root)


def test_small_page_stays_one_file_until_it_grows(tmp_path, sandbox, monkeypatch):
    # Big enough to try a split, too little would go cold.
    monkeypatch.setattr(cold, "MIN_ITEMS", cold.count_items(_store()))
    root = _page(tmp_path / "p")
    calls = []
    real = cold.rebalance
    monkeypatch.setattr(cold, "rebalance", lambda *a, **k: calls.append(1) or real(*a, **k))
    httpd, handler = sandbox(root, "proj")
    for _ in range(3):
        assert request(httpd, "/comments.json?view=page")[0] == 200
        request(httpd, "/api/comments/now/reply", "POST", {"text": "More"})
    assert not _split(root) and cold.KEY not in _raw(root)
    assert str(root) in handler._cold_declined and calls == [1]


def _split_with(root, failing_call=None, monkeypatch=None, failing_name=None):
    """One server split, with store.write_bytes failing (before its rename) on call `failing_call`
    or on the first write to a file named `failing_name`."""
    monkeypatch.setattr(cold, "SPLIT", True, raising=False)  # 2.35.0
    handler = sync_server.make_handler(root, slug="page", bus_dir=None, local_author="reviewer@example.test")
    real, count = store.write_bytes, itertools.count(1)

    def write_bytes(path, body, **kw):
        if next(count) == failing_call or Path(path).name == failing_name:
            raise OSError("disk full")
        return real(path, body, **kw)

    monkeypatch.setattr(store, "write_bytes", write_bytes)
    try:
        handler._split_store(handler.__new__(handler))
    finally:
        monkeypatch.setattr(store, "write_bytes", real)


@pytest.mark.parametrize("reuse", [True, False])
def test_a_crash_at_any_write_of_a_split_leaves_the_whole_store(tmp_path, monkeypatch, reuse):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    if not reuse:  # as when newly settled items or stale copies call for a new generation
        monkeypatch.setattr(cold, "_reuse", lambda *a: None)
    # A split writes a new generation, then comments.json; a re-split that keeps its generation writes comments.json only.
    for resplit, failing in ((False, 1), (False, 2), (True, 1)) + (() if reuse else ((True, 2),)):
        root = _page(tmp_path / f"p{resplit}{failing}")
        if resplit:
            _split_with(root, None, monkeypatch)
            hot = _raw(root)
            assert cold.KEY in hot
            hot["anchors"]["d:old0"].append(_note("fresh", "d:old0", "v3", 90))  # goes cold with v4
            store.write_json(root / "comments.json", hot)
            _publish_v4(root)
        original = json.dumps(store.read_comments(root))
        with pytest.raises(OSError):
            _split_with(root, failing, monkeypatch)
        assert json.dumps(store.read_comments(root)) == original
        _split_with(root, None, monkeypatch)  # the next page view finishes it
        raw = _raw(root)
        assert cold.KEY in raw and raw[cold.KEY]["docs"] == _docs_sig(_docs(root))
        assert json.dumps(store.read_comments(root)) == original
        assert reuse or not resplit or "fresh" in _ids(_cold_data(root)) - _ids(raw)
        # comments.json names the newest generation; nothing half-written is left.
        assert raw[cold.KEY]["gen"] == max(int(p.stem) for p in (root / ".cold").glob("*.json"))
        assert not list((root / ".cold").glob(".new-*"))


def test_a_cold_file_from_another_split_is_never_merged(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root = _page(tmp_path / "p")
    _split_with(root, None, monkeypatch)
    other = _cold_data(root)
    other["anchors"].popitem()
    _cold_path(root).chmod(0o644)  # a deliberate change (out of scope for the read-only files)
    _cold_path(root).write_text(json.dumps(other))
    with pytest.raises(ValueError):
        cold.attach(root, _raw(root), fresh=True)
    with pytest.raises(ValueError):
        store.read_comments(root)


def _split_hot(root, whole):
    docs = _docs(root)
    rules, sig = _page_rules(docs), _docs_sig(docs)
    hot, data, count = cold.split(whole, rules, _page_keep(whole, docs, rules), sig)
    index = cold._write_generation(root, data)
    hot[cold.KEY].update(gen=index.gen, digest=index.digest)
    return cold.attach(root, json.loads(json.dumps(hot))), rules, sig


def test_an_item_cold_again_is_read_from_its_new_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    monkeypatch.setattr(cold, "_reuse", lambda *a: None)  # a new generation
    root = _page(tmp_path / "p")
    whole = _store()
    hot, rules, sig = _split_hot(root, whole)
    old, digest = hot.index.gen, hot.index.digest
    item = cold.anchor_items(hot, "d:old2", lambda c: True)[1]
    item["text"] = "edited"
    cold.settle(hot, rules, sig)  # moved back, the generation keeps the old copy
    docs = _docs(root)
    hot = cold.rebalance(root, hot, rules, lambda w: _page_keep(w, docs, rules), sig,
                         lambda h: store.write_json(root / "comments.json", h))
    assert hot.index.gen > old and _cold_path(root, old).exists()  # kept for readers that named it
    assert item["id"] not in _ids(hot) and len(hot.index.ids()[item["id"]]) == 1
    area, aid, i = cold.live_id(hot, item["id"])
    assert hot.index.lists[area][aid][i]["text"] == "edited"
    assert cold.load_index(root, old, digest, fresh=True).lists[area][aid][1]["text"] != "edited"  # the old generation is untouched
    expected = copy.deepcopy(whole)
    expected["anchors"]["d:old2"][1]["text"] = "edited"
    assert json.dumps(store.read_comments(root)) == json.dumps(expected)


def test_a_settle_that_moves_nothing_normalizes_once(tmp_path, monkeypatch):
    root = _page(tmp_path / "p")
    hot, rules, sig = _split_hot(root, _store())
    hot["anchors"]["d:old0"].pop(0)                      # a hot edit: the first normalize re-syncs it
    calls, normalize = [], cold.normalize
    monkeypatch.setattr(cold, "normalize", lambda h: calls.append(1) or normalize(h))
    cold.settle(hot, rules, sig)
    assert len(calls) == 1
    settled = json.dumps(hot)
    normalize(hot)                                       # the second pass it skipped changes nothing
    assert json.dumps(hot) == settled
    cold.anchor_items(hot, "d:old2", lambda c: True)[1]["status"] = "open"
    cold.settle(hot, rules, sig)                         # a checkout moved back: normalized again
    assert len(calls) == 3


def test_a_changed_checkout_moves_back_in_place(tmp_path):
    root = _page(tmp_path / "p")
    whole = _store()
    hot, rules, sig = _split_hot(root, whole)
    assert json.dumps(cold.merge(hot)) == json.dumps(whole)
    items = cold.anchor_items(hot, "d:old2", lambda c: True)
    assert [c["id"] for c in items] == [c["id"] for c in whole["anchors"]["d:old2"]]
    items[1]["status"] = "open"
    expected = copy.deepcopy(whole)
    expected["anchors"]["d:old2"][1]["status"] = "open"
    cold.settle(hot, rules, sig)
    assert items[1]["id"] in _ids(hot)
    assert json.dumps(cold.merge(cold.attach(root, json.loads(json.dumps(hot))))) == json.dumps(expected)
    # A writer that removes and appends hot items keeps every cold item in place.
    hot = cold.attach(root, json.loads(json.dumps(hot)))
    gone = hot["anchors"]["d:old0"].pop(0)
    fresh = _note("fresh", "d:old0", "v3", 90)
    hot["anchors"]["d:old0"].append(fresh)
    store.write_json(root / "comments.json", hot)
    expected["anchors"]["d:old0"] = [c for c in expected["anchors"]["d:old0"] if c["id"] != gone["id"]] + [fresh]
    assert json.dumps(store.read_comments(root)) == json.dumps(expected)


# ── PR #180 review (orch-20261124): one regression test per finding, each failing on d6640fa1 ──

def test_review_1_2_34_serves_a_page_2_35_split_and_leaves_it_split(tmp_path, sandbox, monkeypatch):
    """Rolling 2.35.0 back to 2.34.0 touches no data: 2.34.0 reads, writes and promotes a split page."""
    root_a, root_b = _page(tmp_path / "a"), _page(tmp_path / "b")
    _split_with(root_a, None, monkeypatch)  # 2.35.0
    gen = _raw(root_a)[cold.KEY]["gen"]
    monkeypatch.setattr(cold, "SPLIT", False)  # 2.34.0
    (a, _), (b, _) = sandbox(root_a, "proj-a"), sandbox(root_b, "proj-b")
    _same(a, b, root_a, root_b)
    assert not _split(root_b)  # 2.34.0 never splits
    results = [_writes(s, sandbox) for s in (a, b)]
    assert results[0] == results[1]
    _same(a, b, root_a, root_b)
    assert {"settled", "old-q-3", "old-note"} <= _ids(_raw(root_a))  # promoted
    for root in (root_a, root_b):
        _publish_v4(root)
    _same(a, b, root_a, root_b)
    assert _raw(root_a)[cold.KEY]["gen"] == gen and [p.name for p in (root_a / ".cold").glob("*.json")] == [f"{gen}.json"]
    assert not _split(root_b)


def test_review_2_a_prior_cold_file_put_back_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    monkeypatch.setattr(cold, "_reuse", lambda *a: None, raising=False)  # v4 files "fresh" cold
    root = _page(tmp_path / "p")
    _split_with(root, None, monkeypatch)
    v3 = _cold_path(root).read_bytes()
    hot = _raw(root)
    hot["anchors"]["d:old0"].append(_note("fresh", "d:old0", "v3", 90))
    store.write_json(root / "comments.json", hot)
    _publish_v4(root)
    _split_with(root, None, monkeypatch)
    assert "fresh" in _ids(_cold_data(root)) and "fresh" in _ids(store.read_comments(root))
    _cold_path(root).chmod(0o644)
    _cold_path(root).write_bytes(v3)  # the v3 cold file back under the v4 comments.json
    with pytest.raises(ValueError):
        store.read_comments(root)
    with pytest.raises(ValueError), store.transaction(root) as tx:
        tx.comments  # a writer cannot load it to persist
    handler = sync_server.make_handler(root, slug="page", bus_dir=None, local_author="reviewer@example.test")
    with pytest.raises(ValueError):
        handler.__new__(handler)._v2_load()


def test_review_3_plans_restore_after_an_interrupted_split_is_readable(tmp_path, monkeypatch):
    from test_plans_backfill import page as plans_page

    from agent_annotate.plans_backfill import backfill_page, restore_page
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root = tmp_path / "p"
    plans_store, _ = plans_page(root)
    plans_store["anchors"].update({f"d:n{k}": [_note(f"n{k}", f"d:n{k}", "v1", 10 + k)] for k in range(8)})
    (root / "comments.json").write_text(json.dumps(plans_store))
    (root / "versions/v2.html").write_text("<p>v2</p>")
    (root / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]}))
    _split_with(root, None, monkeypatch)
    assert cold.KEY in _raw(root)
    original = json.dumps(store.read_comments(root))
    backup = backfill_page(root, apply=True)["backup"]
    assert cold.KEY not in _raw(root)
    with pytest.raises(OSError):
        _split_with(root, None, monkeypatch, "comments.json")  # the next split stops after its cold generation
    assert _split(root) and cold.KEY not in _raw(root)
    restore_page(root, backup)
    assert json.dumps(store.read_comments(root)) == original


def test_review_4_a_rejected_put_never_reaches_merged_reads(tmp_path, sandbox):
    root = _page(tmp_path / "p")
    httpd, _ = sandbox(root, "proj")
    assert request(httpd, "/comments.json?view=page")[0] == 200 and cold.KEY in _raw(root)
    assert request(httpd, "/comments.json")[0] == 200  # warms the merged cache
    status, _, body = request(httpd, "/api/comments/now", "PUT", {"text": "Rejected text", "decision_request": {}})
    assert status == 400, body
    assert "Rejected text" not in (root / "comments.json").read_text()
    for path in ("/comments.json?view=poll", "/comments.json", "/api/comments"):
        assert b"Rejected text" not in request(httpd, path)[2], path


def test_review_5_a_publish_during_a_cold_write_keeps_the_write(tmp_path, sandbox, monkeypatch):
    root = _page(tmp_path / "p")
    httpd, handler = sandbox(root, "proj")
    assert request(httpd, "/comments.json?view=page")[0] == 200 and "old-note" not in _ids(_raw(root))
    real = handler._v2_put_comment

    def put(self, cid, parsed):  # the request paused after routing: a publish and a page view land first
        _publish_v4(root)
        self._split_store()
        return real(self, cid, parsed)

    monkeypatch.setattr(handler, "_v2_put_comment", put)
    status, _, body = request(httpd, "/api/comments/old-note", "PUT", {"status": "archived"})
    assert status == 200, body
    assert [c["status"] for items in store.read_comments(root)["anchors"].values() for c in items
            if c["id"] == "old-note"] == ["archived"]


def test_review_6_promoting_the_last_cold_item_keeps_key_order(tmp_path, sandbox):
    root_a, root_b = _page(tmp_path / "a"), _page(tmp_path / "b")
    (a, _), (b, _) = sandbox(root_a, "proj-a"), sandbox(root_b, "proj-b", split=False)
    for s in (a, b):
        assert request(s, "/comments.json?view=page")[0] == 200
    assert "settled" not in _ids(_raw(root_a)) and "d:settled" not in _raw(root_a)["anchors"]
    for s in (a, b):  # a note at an anchor holding only cold items, then an edit of its last cold item
        assert request(s, "/api/comments", "POST", {"anchor_id": "d:settled", "text": "New note", "version": "v3"})[0] in (200, 201)
        assert request(s, "/api/comments/settled/reply", "POST", {"text": "Back to this"})[0] in (200, 201)
    orders = [list(store.read_comments(r)["anchors"]) for r in (root_a, root_b)]
    assert orders[0] == orders[1] == list(_store()["anchors"])


def test_review_7_close_finds_unanswered_cards_in_cold_storage(tmp_path, monkeypatch, capsys):
    from agent_annotate import cli
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    data = _store()
    data["anchors"]["d:ask"] = [_q("old-ask", "d:ask", "v1", "Never answered?", 80, status="addressed_by_agent",
                                   created_at="2026-01-01T00:00:00Z")]
    root = _page(tmp_path / "p", data)
    _split_with(root, None, monkeypatch)
    assert "old-ask" not in _ids(_raw(root)) and "old-ask" in _ids(_cold_data(root))
    record = {"slug_dir": str(root), "bus_file": None}
    monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda slug, project=None: ("proj", "page", record))
    monkeypatch.setattr(cli, "_live_server_for", lambda record: None)
    args = argparse.Namespace(slug="page", project=None, older_than="1d", dry_run=False, author="agent:test")
    assert cli.cmd_close(args) == 0
    out = capsys.readouterr().out
    assert "old-ask" in out and "archived 1 card(s); 3 unanswered card(s) remain" in out
    whole = store.read_comments(root)
    assert [c["status"] for items in whole["archived"].values() for c in items if c["id"] == "old-ask"] == ["archived"]


def test_answering_or_noting_a_cold_undecided_question_lands(tmp_path, sandbox):
    """An old question the agent addressed without a decision is done on the page, so it goes cold;
    answering or noting it from the page promotes it under the lock and saves it."""
    data = _store()
    data["anchors"]["d:ask"] = [_q(f"old-ask-{k}", "d:ask", "v1", f"Never answered {k}?", 80 + k,
                                   status="addressed_by_agent") for k in range(2)]
    root_a, root_b = _page(tmp_path / "a", copy.deepcopy(data)), _page(tmp_path / "b", data)
    (a, _), (b, _) = sandbox(root_a, "proj-a"), sandbox(root_b, "proj-b", split=False)
    for s in (a, b):
        assert request(s, "/comments.json?view=page")[0] == 200
    assert {"old-ask-0", "old-ask-1"} <= _ids(_cold_data(root_a)) - _ids(_raw(root_a))
    for s in (a, b):
        sandbox.reset_ids()
        status, _, body = request(s, "/api/comments/old-ask-0/decision", "POST", {"verdict": "changes", "text": "Answer now"})
        assert status in (200, 201), body
        status, _, body = request(s, "/api/comments/old-ask-1/reply", "POST", {"text": "A note"})
        assert status in (200, 201), body
    whole = store.read_comments(root_a)
    asks = {c["id"]: c for c in whole["anchors"]["d:ask"]}
    assert asks["old-ask-0"]["decision"]["text"] == "Answer now"
    assert [r["text"] for r in asks["old-ask-1"]["replies"]][-1:] == ["A note"]
    assert {"old-ask-0", "old-ask-1"} <= _ids(_raw(root_a))
    assert json.dumps(whole) == json.dumps(store.read_comments(root_b))


def test_review_8_open_feedback_on_old_versions_stays_hot(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    data = _store()
    sent = {"verdict": "changes", "text": "Revise", "by": "reviewer@example.test", "ts": "2026-01-01T00:00:00Z"}
    data["anchors"]["d:old5"].append(_q("changes-sent", "d:old5", "v1", "Change this?", 81, decision=sent,
                                        flagged_for_session=True, flagged_at="2026-01-02T00:00:00Z"))
    from agent_annotate.categories import comment_section
    assert comment_section(data["anchors"]["d:old5"][-1]) == "waiting"
    root = _page(tmp_path / "p", data)
    _split_with(root, None, monkeypatch)
    assert cold.KEY in _raw(root) and "changes-sent" in _ids(_raw(root))
    assert {"open-old", "mixed-open"} <= _ids(_raw(root))


def test_review_9_a_deleted_cold_item_frees_its_id(tmp_path, sandbox):
    root = _page(tmp_path / "p")
    httpd, _ = sandbox(root, "proj")
    assert request(httpd, "/comments.json?view=page")[0] == 200 and "old-note" not in _ids(_raw(root))
    status, _, body = request(httpd, "/api/comments/old-note", "DELETE")
    assert status == 200, body
    assert "old-note" not in _ids(store.read_comments(root))
    status, _, body = request(httpd, "/api/comments", "POST",
                              {"id": "old-note", "anchor_id": "s:note", "text": "Again", "version": "v3"})
    assert status in (200, 201), body


def test_review_10_review_saves_reuse_plan_documents(tmp_path, sandbox, monkeypatch):
    from agent_annotate import categories
    root = _page(tmp_path / "p")
    httpd, _ = sandbox(root, "proj")
    assert request(httpd, "/comments.json?view=page")[0] == 200 and cold.KEY in _raw(root)
    reads = []
    real_json, real_anchors = categories._json, sync_server._card_anchors
    monkeypatch.setattr(categories, "_json", lambda path, *a: reads.append(str(path)) or real_json(path, *a))
    monkeypatch.setattr(sync_server, "_card_anchors", lambda body: reads.append(str(body())) or real_anchors(body))
    for text in ("One", "Two"):
        assert request(httpd, "/api/comments/now/reply", "POST", {"text": text})[0] in (200, 201)
    assert not [path for path in reads if "/plans/" in path]


# ── Second review (orch-20261124/review-cold-store-2.md): one test per finding left after the redesign ──

def _damage(path):
    """Same-length damage with the mtime put back: only the content and ctime tell."""
    before, body = path.stat(), path.read_bytes()
    path.chmod(0o644)  # deliberate: the read-only mode is what stops an accidental write
    path.write_bytes(body.replace(b'"id":"old-note"', b'"id":"bad-note"'))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert (path.stat().st_size, path.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_round2_1_a_changed_generation_is_never_served_from_a_cache(tmp_path, sandbox, backend):
    root = _page(tmp_path / "p")
    if backend == "sqlite":
        store.import_page(root, project="p", slug="page")
    server, handler = sandbox(root, "proj")
    paths = ("/comments.json?view=page", "/comments.json", "/api/history", "/api/categories")
    for path in paths:
        assert request(server, path)[0] == 200
    assert "old-note" in _ids(store.snapshot(root).comments)
    _damage(_cold_path(root))
    with pytest.raises(ValueError, match="does not match its content"):  # cold.Unreadable
        store.read_comments(root)
    with pytest.raises(ValueError):
        store.snapshot(root).comments
    with pytest.raises(ValueError):
        handler.__new__(handler)._v2_load(read_only=True, merged=True)
    for path in paths[1:3]:
        assert request(server, path)[0] == 500, path
    hot = (root / "comments.json").read_bytes()
    assert request(server, "/api/comments/now", "PUT", {"status": "archived"})[0] == 500
    assert (root / "comments.json").read_bytes() == hot


@pytest.mark.parametrize("cid", ["old-note", "now"])  # cold, and hot as in 2.33.0
def test_round2_5_a_receipt_shows_its_own_write_not_the_next_writers(tmp_path, sandbox, monkeypatch, cid):
    root = _page(tmp_path / "p")
    server, handler = sandbox(root, "proj")
    assert request(server, "/comments.json?view=page")[0] == 200
    real, injected = handler._session_fields, []

    def after_commit(self):  # the handler paused after its commit; a rejected writer runs meanwhile
        if not injected:
            injected.append(1)
            status, _, body = request(server, f"/api/comments/{cid}", "PUT",
                                      {"status": "open", "text": "Rejected text", "decision_request": {}})
            assert status == 400, body
        return real(self)

    monkeypatch.setattr(handler, "_session_fields", after_commit)
    status, _, body = request(server, f"/api/comments/{cid}", "PUT", {"status": "archived"})
    assert status == 200 and injected, body
    assert json.loads(body)["text"] != "Rejected text" and json.loads(body)["status"] == "archived"
    assert "Rejected text" not in (root / "comments.json").read_text()
    events = [json.loads(line) for line in (root / "proj/page.ndjson").read_text().splitlines()]
    assert events[-1]["new_status"] == "archived"


@pytest.mark.parametrize("live", [False, True])
def test_round2_6_close_leaves_a_card_answered_after_it_was_listed(tmp_path, sandbox, monkeypatch, capsys, live):
    from agent_annotate import cli
    data = _store()
    data["anchors"]["d:ask"] = [_q("old-ask", "d:ask", "v1", "Never answered?", 80, status="addressed_by_agent",
                                   created_at="2026-01-01T00:00:00Z")]
    root = _page(tmp_path / "p", data)
    server, _ = sandbox(root, "proj")
    assert request(server, "/comments.json?view=page")[0] == 200 and "old-ask" not in _ids(_raw(root))
    record = {"slug_dir": str(root), "bus_file": None, "port": server.server_address[1]}
    monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *_: ("proj", "page", record))

    def answered_after_selection(_):
        status, _, body = request(server, "/api/comments/old-ask/decision", "POST", {"verdict": "changes", "text": "Please revise"})
        assert status == 200, body
        return {"port": server.server_address[1]} if live else None

    monkeypatch.setattr(cli, "_live_server_for", answered_after_selection)
    args = argparse.Namespace(slug="page", project=None, older_than="1d", dry_run=False, author="agent:test")
    assert cli.cmd_close(args) == 0
    out = capsys.readouterr().out
    assert "archived 0 card(s)" in out and "left 1 answered while closing: old-ask" in out
    whole = store.read_comments(root)
    assert "old-ask" in _ids(whole, ("anchors",)) and "old-ask" not in _ids(whole, ("archived",))
    status, _, body = request(server, "/api/rounds/submit", "POST", {})
    assert status == 200 and b"old-ask" in body, body


def test_round2_7_generations_are_numbered_written_once_and_cleaned_by_age(tmp_path):
    root = _page(tmp_path / "p")
    data = {"anchors": {"d:x": [_note("x", "d:x", "v1", 1)]}, "archived": {}}
    first = cold._write_generation(root, data)
    inode, body = _cold_path(root, first.gen).stat().st_ino, _cold_path(root, first.gen).read_bytes()
    second = cold._write_generation(root, data)  # identical data: a new file all the same
    assert second.gen == first.gen + 1 and second.digest == first.digest
    assert (_cold_path(root, first.gen).stat().st_ino, _cold_path(root, first.gen).read_bytes()) == (inode, body)
    assert cold.cleanup(root, keep=second.gen) == []  # inside the grace: a reader may still name it
    later = time.time() + cold.GRACE + 1
    assert cold.cleanup(root, keep=second.gen, now=later) == [first.gen]
    assert cold.cleanup(root, keep=None, now=later) == []  # the newest stays: numbers never repeat
    assert cold._write_generation(root, data).gen == second.gen + 1
    assert cold._write_generation(root, data, floor=10).gen == 11


def test_round2_7_a_re_split_of_the_same_data_writes_a_new_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    monkeypatch.setattr(cold, "_reuse", lambda *a: None)
    root = _page(tmp_path / "p")
    _split_with(root, None, monkeypatch)
    old = _raw(root)[cold.KEY]
    before = _cold_path(root, old["gen"]).stat()
    _publish_v4(root)
    _split_with(root, None, monkeypatch)
    new = _raw(root)[cold.KEY]
    assert new["gen"] > old["gen"] and _cold_path(root, old["gen"]).stat().st_ino == before.st_ino
    assert json.dumps(store.read_comments(root)) == json.dumps(_store())


def test_round2_8_an_item_named_batch_takes_a_reply_when_cold(tmp_path, sandbox):
    data = _store()
    data["anchors"]["s:note"][1]["id"] = "batch"
    root_a, root_b = _page(tmp_path / "a", copy.deepcopy(data)), _page(tmp_path / "b", data)
    (a, _), (b, _) = sandbox(root_a, "a"), sandbox(root_b, "b", split=False)
    assert request(a, "/comments.json?view=page")[0] == 200 and "batch" not in _ids(_raw(root_a))
    for s in (a, b):
        assert request(s, "/api/comments/batch/reply", "POST", {"text": "Reply"})[0] == 200
    assert json.dumps(store.read_comments(root_a)) == json.dumps(store.read_comments(root_b))


def test_round2_9_readers_over_many_pages_report_unreadable_not_empty(tmp_path, monkeypatch):
    from agent_annotate import cli, metrics
    from agent_annotate import eval as evaluate
    from agent_annotate.hooks import check_comment_bus
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root = _page(tmp_path / "p")
    monkeypatch.setattr(evaluate, "load_registry", lambda: {"proj/page": {"project": "proj", "slug_dir": str(root)}})
    monkeypatch.setattr(evaluate, "load_bus", lambda *_: (None, []))
    whole = evaluate.collect_slugs()["proj/page"]["comments"]
    _split_with(root, None, monkeypatch)
    assert evaluate.collect_slugs()["proj/page"]["comments"] == whole
    _cold_path(root).rename(root / "moved-aside.json")
    info = evaluate.collect_slugs()["proj/page"]
    assert "is missing" in info["unreadable"] and info["store"] is None
    aggregate = metrics._empty()
    metrics._quality(str(root), aggregate)
    assert aggregate["unreadable_pages"] == 1 and aggregate["decision_quality"]["cards"] == 0
    with pytest.raises(cold.Unreadable):
        cli._load_store({"slug_dir": str(root)})
    with pytest.raises(cold.Unreadable):
        check_comment_bus._load_cards(str(root))


def test_round2_10_bench_checks_read_a_split_page_whole(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root = _page(tmp_path / "p")
    bench = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/bench.py"))
    spec = {"version": "v2", "count": 1}
    before = bench["chk_posed"](spec, {}, root)
    _split_with(root, None, monkeypatch)
    assert cold.KEY in _raw(root) and bench["chk_posed"](spec, {}, root) == before


# ── Third review (orch-20261124/review-cold-store-3.md) ──

def test_round3_3_a_generation_cannot_be_opened_for_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root = _page(tmp_path / "p")
    _split_with(root, None, monkeypatch)
    path = _cold_path(root)
    assert path.stat().st_mode & 0o777 == 0o444
    for mode in ("r+b", "ab", "wb"):  # r+b is what a writable mapping needs
        with pytest.raises(PermissionError):
            open(path, mode)


def test_round3_4_a_retried_split_gives_the_old_generation_its_grace(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    monkeypatch.setattr(cold, "_reuse", lambda *_: None)
    root = _page(tmp_path / "p")
    _split_with(root, None, monkeypatch)
    first = _cold_path(root)
    _publish_v4(root)
    with pytest.raises(OSError, match="disk full"):
        _split_with(root, None, monkeypatch, "comments.json")
    orphan = _cold_path(root, 2)
    assert orphan.is_file() and _cold_path(root) == first
    then = time.time() - cold.GRACE - 5
    os.utime(orphan, (then, then))  # written long ago, never named
    reader = _raw(root)  # a reader holding the pointer to 1
    _split_with(root, None, monkeypatch)
    assert _cold_path(root).name == "3.json" and first.exists()
    assert _ids(cold.merged(root, reader)) == _ids(_store())
    assert cold.cleanup(root, keep=3, now=time.time() + cold.GRACE + 1) == [1, 2]


def test_round3_5_a_server_keeps_two_parsed_generations_and_none_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    monkeypatch.setattr(cold, "GRACE", -1)
    root = _page(tmp_path / "p")
    _split_with(root, None, monkeypatch)
    versions = ["v1", "v2", "v3"]
    for number in range(4, 10):  # each publish files enough new feedback for a new generation
        hot = _raw(root)
        for i in range(20 * number):
            cid = f"extra-{number}-{i}"
            hot["anchors"][f"d:{cid}"] = [_note(cid, f"d:{cid}", versions[-1], number * 1000 + i)]
        store.write_json(root / "comments.json", hot)
        versions.append(f"v{number}")
        (root / "versions" / f"v{number}.html").write_text("<p>new</p>")
        store.write_text(root / "current.meta.json", json.dumps({"current": versions[-1], "history": [{"version": r} for r in versions]}))
        _split_with(root, None, monkeypatch)
    cached = {key[1] for key in cold._FILES if key[0] == str(root)}
    assert _raw(root)[cold.KEY]["gen"] >= 7 and len(cached) <= 2 and cached <= set(cold._numbers(root))


def test_round3_6_parallel_bench_jobs_each_read_through_their_own_build(tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root, whole = _page(tmp_path / "p"), _page(tmp_path / "whole")
    old = tmp_path / "old-src/agent_annotate"  # a build before the cold store: comments.json is all
    old.mkdir(parents=True)
    (old / "__init__.py").write_text("")
    (old / "store.py").write_text("import json\n\ndef read_comments(d):\n    return json.load(open(d + '/comments.json'))\n")
    g = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/bench.py"))["run_checks"].__globals__
    monkeypatch.setitem(g, "page_record", lambda home, slug: {"slug_dir": str(home)})
    new = {"python": sys.executable, "src": Path(__file__).resolve().parents[1] / "src"}
    scenario = {"checks": [{"check": "posed", "version": "v2", "count": 1}]}
    want = g["run_checks"]({"home": root, "build": new}, scenario, "page")
    _split_with(root, None, monkeypatch)
    real, entered, started = g["CHECKS"]["posed"], threading.Event(), threading.Event()

    def paused(spec, rec, slug_dir):  # the split page's job reads only after the other job started
        if Path(slug_dir) == root:
            entered.set()
            assert started.wait(5)
        else:
            started.set()
        return real(spec, rec, slug_dir)

    monkeypatch.setitem(g["CHECKS"], "posed", paused)
    with ThreadPoolExecutor(2) as pool:
        split_job = pool.submit(g["run_checks"], {"home": root, "build": new}, scenario, "page")
        assert entered.wait(5)
        whole_job = pool.submit(g["run_checks"], {"home": whole, "build": {"src": tmp_path / "old-src"}}, scenario, "page")
        assert split_job.result(timeout=60) == want == whole_job.result(timeout=60)


@pytest.mark.parametrize("split", [False, True])
def test_round3_a_writer_never_saves_over_a_comments_json_it_could_not_read(tmp_path, sandbox, monkeypatch, split):
    root = _page(tmp_path / "p")
    if split:
        _split_with(root, None, monkeypatch)
    hot = root / "comments.json"
    before = hot.read_bytes()
    server, _ = sandbox(root, "proj")
    _eio(monkeypatch)
    status, _, body = request(server, "/api/comments", "POST", {"id": "new", "anchor_id": "d:new", "text": "New"})
    assert status == 500 and b"unreadable" in body, body
    with pytest.raises(store.Unreadable), store.transaction(root) as tx:
        tx.comments
    assert request(server, "/comments.json")[0] == 500  # readers too (round 4)
    with open(hot, "rb") as handle:
        assert handle.read() == before


def _eio(patch):
    """Reading comments.json fails with EIO (a flaky disk or mount); every other file reads."""
    def failing(real):
        def read(path, *args, **kwargs):
            if path.name == "comments.json":
                raise OSError(5, "Input/output error")
            return real(path, *args, **kwargs)
        return read

    patch.setattr(Path, "read_text", failing(Path.read_text))
    patch.setattr(Path, "read_bytes", failing(Path.read_bytes))


# ── Fourth review (orch-20261124/review-cold-store-4.md) ──

@pytest.mark.parametrize("split", [False, True])
def test_round4_3_a_read_error_caches_nothing(tmp_path, sandbox, monkeypatch, split):
    root = _page(tmp_path / "p")
    if split:
        _split_with(root, None, monkeypatch)
    server, _ = sandbox(root, "proj")
    with monkeypatch.context() as fault:
        _eio(fault)
        for path in ("/comments.json", "/comments.json?view=page", "/api/categories"):
            status, headers, body = request(server, path)  # categories reports page data errors as 400
            assert status in (400, 500) and b"unreadable" in body, (path, status, body)
            assert "etag" not in {k.lower() for k in headers}, path
    status, _, body = request(server, "/comments.json")  # the file never changed: no new signature
    assert status == 200 and _ids(json.loads(body)) == _ids(_store()) - {"draft"}  # drafts stay the agent's


@pytest.mark.parametrize("private", [True, False])
def test_round4_a_generation_is_as_private_as_its_hot_file(tmp_path, monkeypatch, private):
    monkeypatch.setattr(cold, "MIN_ITEMS", 5)
    root = _page(tmp_path / "p")
    (root / "comments.json").chmod(0o600 if private else 0o644)
    _split_with(root, None, monkeypatch)
    assert _cold_path(root).stat().st_mode & 0o777 == (0o400 if private else 0o444)
