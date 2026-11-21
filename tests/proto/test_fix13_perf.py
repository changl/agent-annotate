"""r12 fix13 perf: on a loaded host no read may hold the GIL the version and counts reads wait on. Replies are masked and
gzipped once per body, and the 0.3-1 s builds (Copy library, Pages & links, History) run in a worker process."""

import gzip
import json
import os

import agent_annotate.proto_data as P


def test_a_reply_is_masked_and_gzipped_once_per_body(monkeypatch):
    body = json.dumps({"who": "x@real-mail.com", "pad": "y" * 4000}).encode()
    first = P.packed(body, False, True)
    assert first[1] and b"member@example.com" in gzip.decompress(first[0]) and b"real-mail" not in gzip.decompress(first[0])
    monkeypatch.setattr(P, "scrub_json", lambda *a: 1 / 0)
    monkeypatch.setattr(gzip, "compress", lambda *a, **k: 1 / 0)
    assert P.packed(body, False, True) is first  # the same body again: neither masked nor gzipped again
    # a body given gzipped (the meta's cached reply) is masked once too, and goes out plain to a client without gzip
    monkeypatch.undo()
    plain = P.packed(gzip.compress(body), True, False)
    assert not plain[1] and b"member@example.com" in plain[0]
    assert P.packed(b"console.log(1)", False, True, scrubbed=False) == (b"console.log(1)", False)  # gzip only when smaller


def _pid_area(page_dir):
    return {"pid": os.getpid()}


def test_heavy_areas_build_outside_the_server(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "POOLED", P.POOLED | {"pidarea"})
    monkeypatch.setattr(P, "_pool", None)
    import sys
    import types
    mod = types.ModuleType("agent_annotate.proto_data.pidarea")
    mod.build = _pid_area
    monkeypatch.setitem(sys.modules, "agent_annotate.proto_data.pidarea", mod)
    from concurrent.futures.process import BrokenProcessPool

    class Broken:
        def submit(self, *a):
            raise BrokenProcessPool("worker died")
    monkeypatch.setattr(P, "_pool", Broken())
    assert json.loads(P._pooled("pidarea", tmp_path))["pid"] == os.getpid()  # a dead worker: built here, nothing lost
    assert P._pool is None  # and a new worker starts on the next read
    got = {}

    class H:
        artifact_dir, skill_dir = tmp_path, None

        def _respond(self, code, body, *a, **k):
            got.update(code=code, body=body)
    try:
        P.serve(H(), "/proto/data/reference.json")  # a real pooled area, in the worker
        assert got["code"] == 200 and isinstance(json.loads(got["body"]), dict)
    finally:
        if P._pool is not None:
            P._pool.shutdown()
