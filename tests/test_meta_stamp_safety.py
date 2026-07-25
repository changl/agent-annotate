"""Serving a page must never revert someone else's edit to current.meta.json.

current.meta.json is not owned by the server: the CLI rewrites it too
(`publish-version` swaps `current`). Caching a content stamp used to read the
whole document, mutate it and write it back, so a request that read the meta
before a version swap wrote back the OLD `current` — silently reverting the
page and making it appear to change on every reload while someone was
reviewing it.
"""

import json
from pathlib import Path

from agent_annotate import sync_server


class _Handler(sync_server.AnnotateHandler):
    """Bypass BaseHTTPRequestHandler's socket setup; we only need meta I/O."""

    def __init__(self, artifact_dir):
        self.artifact_dir = Path(artifact_dir)
        self.slug = "demo"


def _meta(tmp_path):
    return json.loads((tmp_path / "current.meta.json").read_text())


def _write_meta(tmp_path, data):
    (tmp_path / "current.meta.json").write_text(json.dumps(data))


def test_stamp_write_preserves_a_concurrent_version_swap(tmp_path):
    _write_meta(tmp_path, {"current": "v1", "history": [{"version": "v1"}]})
    h = _Handler(tmp_path)

    # Another process swaps the current version *after* the handler has read
    # the meta but before it persists its stamp — the real interleaving.
    stale = h._read_meta()
    assert stale["current"] == "v1"
    _write_meta(tmp_path, {"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]})

    h._merge_content_stamp("v2", {"whole": "abc", "_mtime": 123.0})

    after = _meta(tmp_path)
    assert after["current"] == "v2", "serving a page reverted a version swap"
    assert len(after["history"]) == 2
    assert after["content_stamps"]["v2"]["whole"] == "abc"


def test_stamp_write_keeps_existing_stamps(tmp_path):
    _write_meta(tmp_path, {
        "current": "v2",
        "content_stamps": {"v1": {"whole": "one", "_mtime": 1.0}},
    })
    h = _Handler(tmp_path)
    h._merge_content_stamp("v2", {"whole": "two", "_mtime": 2.0})

    stamps = _meta(tmp_path)["content_stamps"]
    assert stamps["v1"]["whole"] == "one"
    assert stamps["v2"]["whole"] == "two"


def test_up_to_date_stamp_does_not_rewrite_meta(tmp_path):
    """No write at all when the stamp is current — no window to race."""
    content = tmp_path / "versions"
    content.mkdir()
    doc = content / "v1.html"
    doc.write_text("<div id='s:one'>x</div>")
    mtime = doc.stat().st_mtime

    _write_meta(tmp_path, {
        "current": "v1",
        "content_stamps": {"v1": {"whole": "cached", "_mtime": mtime}},
    })
    h = _Handler(tmp_path)
    before = (tmp_path / "current.meta.json").stat().st_mtime_ns

    h._ensure_content_stamp("v1", doc.read_text(), doc)

    assert (tmp_path / "current.meta.json").stat().st_mtime_ns == before
    assert _meta(tmp_path)["content_stamps"]["v1"]["whole"] == "cached"
