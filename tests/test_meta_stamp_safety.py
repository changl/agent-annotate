"""Serving a page must never revert someone else's edit to current.meta.json.

current.meta.json is not owned by the server: the CLI rewrites it too
(`publish-version` swaps `current`). Caching a content stamp used to read the
whole document, mutate it and write it back, so a request that read the meta
before a version swap wrote back the OLD `current` — silently reverting the
page and making it appear to change on every reload while someone was
reviewing it.
"""

import json
import os
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

    whole = sync_server.compute_content_stamps(doc.read_text())["whole"]
    _write_meta(tmp_path, {
        "current": "v1",
        "content_stamps": {"v1": {"whole": whole, "_mtime": mtime}},
    })
    h = _Handler(tmp_path)
    before = (tmp_path / "current.meta.json").stat().st_mtime_ns

    h._ensure_content_stamp("v1", doc.read_text(), doc)

    assert (tmp_path / "current.meta.json").stat().st_mtime_ns == before
    assert _meta(tmp_path)["content_stamps"]["v1"]["whole"] == whole


def test_stamp_rebuilt_when_meta_bytes_change_with_same_stats(tmp_path, monkeypatch):
    doc = tmp_path / "v1.html"
    doc.write_text("<body>Published</body>")
    _write_meta(tmp_path, {"current": "v1"})
    h = _Handler(tmp_path)
    h._ensure_content_stamp("v1", doc.read_text(), doc)
    meta = h._meta_path()
    original = meta.read_text()
    stat = meta.stat()
    h._ensure_content_stamp("v1", doc.read_text(), doc)
    # A second mapped write can change bytes without changing any stat field.
    original_stat = Path.stat
    monkeypatch.setattr(Path, "stat", lambda path, **kw: stat if path == meta else original_stat(path, **kw))
    meta.write_text(original.replace('"content_stamps"', '"renamed_stamps"'))
    h._ensure_content_stamp("v1", doc.read_text(), doc)
    assert _meta(tmp_path)["content_stamps"] == json.loads(original)["content_stamps"]


def test_stamp_changes_when_content_is_replaced_with_preserved_mtime(tmp_path):
    doc = tmp_path / "v1.html"
    doc.write_text("<body>Old</body>")
    _write_meta(tmp_path, {"current": "v1"})
    h = _Handler(tmp_path)
    h._ensure_content_stamp("v1", doc.read_text(), doc)
    h._ensure_content_stamp("v1", doc.read_text(), doc)
    old = _meta(tmp_path)["content_stamps"]["v1"]["whole"]
    stat = doc.stat()
    replacement = tmp_path / "temp.html"
    replacement.write_text("<body>New</body>")
    os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    replacement.replace(doc)
    h._ensure_content_stamp("v1", doc.read_text(), doc)
    assert _meta(tmp_path)["content_stamps"]["v1"]["whole"] != old


def test_alternating_versions_reuse_verified_content_stamps(tmp_path, monkeypatch):
    markup = {f"v{i}": f"<body>Version {i}</body>" for i in (1, 2)}
    paths = {version: tmp_path / f"{version}.html" for version in markup}
    stamps = {}
    for version, html in markup.items():
        path = paths[version]
        path.write_text(html)
        stamps[version] = {**sync_server.compute_content_stamps(html), "_mtime": path.stat().st_mtime}
    _write_meta(tmp_path, {"current": "v2", "content_stamps": stamps})
    handler = _Handler(tmp_path)
    for version, html in markup.items():
        handler._ensure_content_stamp(version, html, paths[version])

    def unexpected_hash(_):
        raise AssertionError("unchanged version was rehashed")

    monkeypatch.setattr(sync_server, "compute_content_stamps", unexpected_hash)
    for _ in range(12):
        for version, html in markup.items():
            handler._ensure_content_stamp(version, html, paths[version])


def test_new_fingerprint_is_persisted_and_available_to_a_fresh_handler(tmp_path):
    (tmp_path / "content").mkdir()
    doc = tmp_path / "content/v1.html"
    doc.write_text('<section data-anchor-id="s:one">Published content</section>')
    _write_meta(tmp_path, {"current": "v1", "history": [{"version": "v1"}]})
    _Handler(tmp_path)._ensure_content_stamp("v1", doc.read_text(), doc)
    restarted = _Handler(tmp_path)
    stamp = restarted._read_meta()["content_stamps"]["v1"]
    assert stamp["whole"] == sync_server.compute_content_stamps(doc.read_text())["whole"]
    assert stamp["_mtime"] == doc.stat().st_mtime
