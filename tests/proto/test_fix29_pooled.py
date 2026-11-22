"""r12 fix29: the pooled worker's minute-old rebuild behind the answer keeps the reader's hash (audit25 questions 4)."""
import json
import time

import pytest

import agent_annotate.proto_data as P
from agent_annotate.proto_data import links, published, reference


@pytest.mark.parametrize("mod", [reference, links])
def test_rebuild_behind_the_answer_keeps_the_readers_hash(tmp_path, monkeypatch, mod):
    """In the pool worker the module's reviewer is None: only the hash passed in says whose notes are his own."""
    d = tmp_path / "page"
    d.mkdir()
    (d / "current.meta.json").write_text(json.dumps({"current": "v1", "history": []}))
    monkeypatch.setattr(published, "_viewer", {"h": None})
    monkeypatch.setattr(published, "homes", lambda page_dir: [])
    monkeypatch.setattr(mod, "_built", {})
    seen = []
    monkeypatch.setattr(mod, "_build", lambda p: seen.append(published.reader()) or {"viewer": published.reader(), "n": len(seen)})
    me, peer = published._hash("me@example.test"), published._hash("peer@example.test")
    read = lambda who: json.loads(P.prepared(mod.__name__.rsplit(".", 1)[1], d, who))
    assert read(me)["viewer"] == me and read(peer)["viewer"] == peer  # first build: one per reader
    assert {k[1] for k in mod._built} == {me, peer}
    for k in mod._built:
        mod._built[k] = type(mod._built[k])([mod._built[k][0], mod._built[k][1] - 120, mod._built[k][2]])
    read(me)  # a minute old: the answer is the last build, and it is built again behind
    for _ in range(100):
        if len(seen) == 3:
            break
        time.sleep(0.02)
    assert seen == [me, peer, me]  # the refresh is built for its reader, never for nobody
    assert mod._built[(str(d), me)][2]["viewer"] == me and read(me)["viewer"] == me
    assert not hasattr(published._here, "h")  # the thread's reader goes when its read ends
