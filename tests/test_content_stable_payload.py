"""GET /content must return a byte-identical payload on repeated requests.

A slug whose extracted content references diagram-plot.js — but which has no
diagram-plot.js in either the slug dir or the skill dir — used to have its
`<script src="../diagram-plot.js">` tag re-stamped from the wall clock on every
request: _mtime_stamp() fell back to str(int(time.time())) when the file could
not be statted. That made GET /content byte-different on every reload, so a
reviewer watching the page saw it change under them and HTTP caching was
defeated. Regression guard: serve one version three times >1s apart and assert
exactly one distinct payload.
"""

import hashlib
import time
import urllib.parse
from pathlib import Path

from agent_annotate import sync_server

_CONTENT_HTML = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<title>demo</title>\n<script src="../diagram-plot.js"></script>\n</head>\n'
    '<body>\n<div id="s:one">hello</div>\n</body>\n</html>\n'
)


class _CapturingHandler(sync_server.AnnotateHandler):
    """Drive _v2_serve_content directly, capturing the response body instead
    of writing it to a real socket."""

    def __init__(self, artifact_dir: Path, skill_dir: Path):
        self.artifact_dir = artifact_dir
        self.skill_dir = skill_dir
        self.slug = "demo"
        self.public_base_path = "/demo"
        self.bus_dir = None
        self.v2_mode = True
        self._last_body = b""

    def _respond(self, code, body, content_type="application/json",
                 cache_control="no-cache"):
        self._last_body = body


def _serve_content_once(handler: _CapturingHandler) -> bytes:
    handler._v2_serve_content(urllib.parse.urlparse("/demo/content?v=v1"))
    return handler._last_body


def test_content_payload_is_stable_across_repeated_requests(tmp_path):
    # A slug with a content doc that references diagram-plot.js ...
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "v1.html").write_text(_CONTENT_HTML, encoding="utf-8")
    (tmp_path / "current.meta.json").write_text('{"current": "v1"}', encoding="utf-8")

    # ... but neither the slug dir nor the skill dir actually has the file.
    # The skill dir *does* have adapter.js so its injected stamp is a stable
    # mtime — isolating diagram-plot.js as the only candidate source of drift.
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "adapter.js").write_text("// adapter\n", encoding="utf-8")
    assert not (tmp_path / "diagram-plot.js").exists()
    assert not (skill_dir / "diagram-plot.js").exists()

    handler = _CapturingHandler(tmp_path, skill_dir)

    digests = set()
    for i in range(3):
        digests.add(hashlib.sha256(_serve_content_once(handler)).hexdigest())
        if i < 2:
            time.sleep(1.1)  # cross a wall-clock second, per the measured repro

    assert len(digests) == 1, (
        f"GET /content returned {len(digests)} distinct payloads across 3 "
        "requests >1s apart; expected exactly 1"
    )
