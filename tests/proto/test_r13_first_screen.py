"""r13 speed: what the first screen reads stays the same size however many versions or notes the page has."""

import json
from pathlib import Path

from agent_annotate import proto_data


class _H:
    def __init__(self, d):
        self.artifact_dir = d

    def _meta_path(self):
        return self.artifact_dir / "current.meta.json"

    def _project_payload(self):
        return {"name": "Page"}


def _page(tmp_path, n):
    d = tmp_path / f"p{n}"
    d.mkdir()
    hist = [{"version": f"v{i}", "ts": "2026-11-20T10:00:00Z", "summary": "x" * 120} for i in range(1, n + 1)]
    (d / "current.meta.json").write_text(json.dumps({"current": f"v{n:05d}", "history": hist}))
    notes = {f"d:q{i}": [{"id": f"c{i}", "text": "note " * 40, "status": "resolved"}] for i in range(n)}
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": notes}))
    return d


def test_first_screen_head_is_flat_in_versions_and_notes(tmp_path):
    small = json.dumps(proto_data.head(_H(_page(tmp_path, 10))))
    big = json.dumps(proto_data.head(_H(_page(tmp_path, 1000))))
    assert len(big) == len(small) < 200 and '"current": "v01000"' in big


def test_frame_reads_the_whole_meta_only_after_the_first_draw():
    js = (Path(proto_data.__file__).parents[1] / "web" / "proto" / "frame.js").read_text()
    start = js[js.index("async function start()"):]
    assert "api('proto/data/head.json')" in start and "firstShown.then(() => api.meta())" in start
    before = start[:start.index("firstShown.then(() => api.meta())")]
    assert "api.meta()" not in before.replace("firstShown.then(() => api.meta())", "")
