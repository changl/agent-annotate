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


def _areas(n):
    """Each heavy area as its build shapes it, with n versions, notes and answers."""
    note = lambda i: {"id": f"c{i}", "a": f"ref:p~{i}", "text": "note " * 40}
    vers = {f"v{i}": {"ts": "2026-11-20T10:00:00Z", "sum": "x" * 100} for i in range(1, n + 1)}
    return {
        "reference": {"plans": [{"id": "p", "t": "Plan", "revs": [["1", "2026-11-20"]]}], "flows": [], "topics": ["A"],
                      "extras": [{"id": "x", "t": "Guide", "kind": "plan", "d": "2026-11-20", "from": "a/b.md", "md": "words " * 50 * n}],
                      "notes": [note(i) for i in range(n)]},
        "running": {"workers": [], "board": {"tasks": [], "beads": {"FLD-1": {"t": "Task", "st": "open", "desc": "d" * 10 * n,
                                                                           "cm": [["2026-11-20", "comment"]] * n}}}},
        "history": {"count": n, "sends": n, "current": f"v{n}", "versions": vers, "plans": [], "waiting": [],
                    "answers": [{"id": f"a{i}", "v": f"v{i + 1}", "n": i, "q": "Q?", "a": "Yes"} for i in range(n)],
                    "withdrawn": [{"n": i, "v": f"v{i + 1}", "q": "Q?", "why": "gone"} for i in range(n)]},
        "links": {"name": "Page", "versions": n, "pages": [], "links": [], "archived": [],
                  "docs": {"files": [{"n": "a.md", "g": "planning", "k": "md", "md": "text " * 50 * n}], "groups": {}},
                  "kept": [{"id": "k", "t": "Kept", "sub": "s", "blocks": [["p", "line " * 20]] * n}], "notes": [note(i) for i in range(n)]},
    }


def test_each_heavy_tabs_first_screen_is_flat_in_versions_and_notes():
    from agent_annotate.proto_data.first import AREAS, cut
    small, big = _areas(300), _areas(3000)  # past each list's first-screen cap
    assert set(small) == AREAS
    for area in AREAS:
        s, b = (cut(area, json.dumps(d[area]).encode()) for d in (small, big))
        whole = len(json.dumps(big[area]))
        assert len(b) <= len(s) * 1.02 + 64 and len(b) < whole / 20, (area, len(s), len(b), whole)  # longer version names only
        assert json.loads(b)["part"] is True


def test_each_heavy_tab_draws_its_slice_then_the_whole_read():
    web = Path(proto_data.__file__).parents[1] / "web" / "proto"
    for name, area in (("reference", "reference"), ("running", "running"), ("history", "history"), ("links", "links")):
        js = (web / f"{name}.js").read_text()
        assert f"first('{area}')" in js and f"data('{area}')" in js, name
    links = (web / "links.js").read_text()
    assert "if (was) ctx.data('links', true)" in links  # the visit's first read is not made twice
    frame = (web / "frame.js").read_text()
    assert "api(`proto/data/${area}.first.json`)" in frame and "base, api, data, first, early," in frame


def test_each_slice_takes_input_and_the_whole_read_keeps_it():
    """A slice is not inert: a click on it runs on the whole read's draw, and what he typed, his focus and scroll stay."""
    web = Path(proto_data.__file__).parents[1] / "web" / "proto"
    for name in ("reference", "running", "history", "links"):
        js = (web / f"{name}.js").read_text()
        assert ".early(" in js and "after(" in js and "inert = true" not in js and 'class="h-wrap" inert' not in js, name
    frame = (web / "frame.js").read_text()
    early = frame[frame.index("const early = (w, now) =>"):frame.index("// Unsent answers, notes and task changes")]
    for part in ("addEventListener('click', on, true)", "removeEventListener('click', on, true)", "!t.closest('[data-slice]')",
                 "dispatchEvent(new Event('input'", "fe.focus(", "scrollTo(scrollX, sy)", "t.click()"):
        assert part in early, part


def test_card_pictures_with_a_size_load_near_the_screen_and_copy_checks_wait_for_the_first_draw():
    web = Path(proto_data.__file__).parents[1] / "web" / "proto"
    qs = (web / "questions.js").read_text()
    assert "i.loading = i.getAttribute('width') && i.getAttribute('height') ? 'lazy' : 'eager'" in qs
    frame = (web / "frame.js").read_text()
    assert "if (COPY) firstShown.then(checkNewer)" in frame
    top = frame[frame.index("function refreshTop()"):]
    assert top.index("await firstShown;") < top.index("readRun(),")


def test_frame_reads_the_whole_meta_only_after_the_first_draw():
    js = (Path(proto_data.__file__).parents[1] / "web" / "proto" / "frame.js").read_text()
    start = js[js.index("async function start()"):]
    assert "api('proto/data/head.json')" in start and "firstShown.then(() => api.meta())" in start
    before = start[:start.index("firstShown.then(() => api.meta())")]
    assert "api.meta()" not in before.replace("firstShown.then(() => api.meta())", "")
