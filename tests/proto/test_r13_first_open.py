"""r13 speed: the first open after a restart or a copy never waits on a build (Reference's took 17-56 s cold on a loaded host).
The pooled areas' last builds are kept on disk, masked, and sent at once while the build runs behind the read."""

import json
import sys
import threading
import time
import types
from pathlib import Path

import agent_annotate.proto_data as P
from agent_annotate.proto_data import prebuilt


def _page(tmp_path) -> Path:
    page = tmp_path / "reviews" / "fld-proto"
    page.mkdir(parents=True)
    (page / "current.meta.json").write_text(json.dumps({"ui": "proto", "current": "v1"}))
    (page / "comments.json").write_text(json.dumps({"anchors": {}}))
    return page


def _restart(monkeypatch):
    """A new server process: nothing of the last one's memory."""
    for name in ("_runs", "_last", "_kept", "_saved", "_sums"):
        monkeypatch.setattr(prebuilt, name, {})
    monkeypatch.setattr(P, "_ready", {})


def test_the_first_open_after_a_restart_does_not_run_the_build_on_the_request(tmp_path, monkeypatch):
    page, gate, calls = _page(tmp_path), threading.Event(), []

    def build(d):
        calls.append(threading.current_thread().name)
        if len(calls) > 1:
            assert gate.wait(20)  # a cold build on a loaded host: it takes as long as it takes
        return {"n": len(calls), "who": "someone@real-mail.com"}
    mod = types.ModuleType("agent_annotate.proto_data.slowarea")
    mod.build = build
    monkeypatch.setitem(sys.modules, "agent_annotate.proto_data.slowarea", mod)
    monkeypatch.setattr(P, "POOLED", P.POOLED | {"slowarea"})

    class Here:  # the pooled worker, in this process
        def submit(self, fn, *a):
            out = fn(*a)
            return types.SimpleNamespace(result=lambda timeout=None: out)
    monkeypatch.setattr(P, "_pool", Here())
    got = {}

    class H:
        artifact_dir, skill_dir = page, None
        _identity, _reviewer_authors = (lambda self: {"email": None}), (lambda self, a: {a})

        def _respond(self, code, body, *a, **k):
            got.update(code=code, body=body)
    read = lambda: (P.serve(H(), "/proto/data/slowarea.json"), json.loads(got["body"]))[1]
    _restart(monkeypatch)
    assert read()["n"] == 1  # the page's first build ever: nothing kept, so it is waited for
    kept = list((tmp_path / "built").rglob("slowarea-*.json"))
    assert len(kept) == 1 and "real-mail" not in kept[0].read_text() and "member@example.com" in kept[0].read_text()

    _restart(monkeypatch)
    t0 = time.monotonic()
    first = read()
    assert first["n"] == 1 and time.monotonic() - t0 < 5  # the kept build, at once
    for _ in range(200):
        if len(calls) == 2:
            break
        time.sleep(0.01)
    assert len(calls) == 2 and calls[1] != threading.current_thread().name  # its build started, behind the read, and still runs
    # the slice may be any last build; the whole read only one from the page as it is now
    assert prebuilt.get("slowarea", page, None, False, P._pooled) == prebuilt._known(("slowarea", str(page), None))[1]
    gate.set()
    for _ in range(500):
        if not prebuilt._runs:
            break
        time.sleep(0.01)
    (page / "comments.json").write_text(json.dumps({"anchors": {"ref:x": [{"id": "c1", "text": "new"}]}}))
    assert read()["n"] >= 3  # a new note: the whole read waits for a build that has it


def test_servers_build_ahead_at_start_and_after_a_copy(tmp_path, monkeypatch):
    page, built = _page(tmp_path), []
    copy = tmp_path / "reviews" / "proto-rebex"
    copy.mkdir()
    (copy / "current.meta.json").write_text(json.dumps({"ui": "proto", "proto_copy_of": "rebex"}))
    _restart(monkeypatch)
    prebuilt.warm(prebuilt.pages(page), {"reference", "links"}, lambda *k: built.append(k) or b"{}")
    for _ in range(500):
        if len(built) == 4:
            break
        time.sleep(0.01)
    assert sorted((a, Path(d).name) for a, d, _ in built) == [("links", "fld-proto"), ("links", "proto-rebex"),
                                                              ("reference", "fld-proto"), ("reference", "proto-rebex")]
    src = (Path(P.__file__).parents[1] / "sync_server.py").read_text()
    assert "from .proto_data import warm" in src and "warm(slug_dir)" in src
    copies = (Path(P.__file__).parent / "copies.py").read_text()
    assert "warm([Path(at)], POOLED, _pooled)" in copies and "shutil.copyfile(dest / SNAP, tmp / SNAP)" in copies
