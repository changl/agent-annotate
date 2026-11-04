"""The header's refresh button, state by state (Chang #136, 2026-11-03).

"the reload button should only have the red outline/background and number
when there are actual new feedback/question items. otherwise, it can just be
the reload (which will simply reload the same version if there is no newer
one. or if there is a new version but no new feedback/question items, then it
will show the reload and type out the v number. and if the new version has
feedback/question items, then it can show the count for that as well."

(a) nothing newer, nothing new: a plain icon; a tap reloads the same version,
    typed text kept. (b) a newer version only: its name as plain text, no red.
(c) new questions or feedback: a red border and their count, plus the newer
    version's name when there is one. (d) the newer version fixes the one on
    screen (History's `fixes`): "fix" in orange after its name.
The Review tab's version label never sits in a red pill.
"""

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_keep_drafts import _agent, _directory, _poll, _publish_v2  # noqa: E402
from test_live_updates import _box, _open  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402

TYPED = "Typed before the tap"
QUESTION = {"anchor_id": "s:checks", "text": "Question 12",
            "decision_request": {"prompt": "New question 12?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}}

STATE = """() => {
  const b = document.getElementById('aa-fresh'), shown = s => { const el = b.querySelector(s); return el && !el.hidden ? el.textContent : null; };
  const css = getComputedStyle(b), fix = b.querySelector('.aa-fresh-fix');
  const rgb = c => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c; x.fillRect(0, 0, 1, 1); return [...x.getImageData(0, 0, 1, 1).data]; };
  const tab = document.querySelector('#aa-tabs .aa-tab-ver');
  return { waiting: b.classList.contains('is-waiting'), count: shown('.aa-fresh-n'),
    version: shown('.aa-fresh-v'), fix: shown('.aa-fresh-fix'), fixColour: fix && rgb(getComputedStyle(fix).color), border: rgb(css.borderTopColor),
    tabPill: !!(tab && tab.closest('.badge')), versionPill: !!b.querySelector('.aa-fresh-v.badge, .badge .aa-fresh-v'),
    label: b.getAttribute('aria-label') };
}"""


def _state(page):
    return page.evaluate(STATE)


def _transparent(rgba):
    return rgba[3] == 0


def _publish_fix(tmp_path, directory):
    source = tmp_path / "review.md"
    source.write_text(source.read_text().replace("version: v1", "version: v2"))
    generate(source, directory, fixes="v1")
    from review_fixtures import complete
    complete(directory)


@pytest.mark.parametrize("engine", ["chrome", "ipad"])
def test_a_nothing_waits_plain_icon_and_a_tap_reloads_this_version_keeping_text(tmp_path, engine):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, engine) as (page, _):
        _poll(page)
        s = _state(page)
        assert (s["waiting"], s["count"], s["version"], s["fix"]) == (False, None, None, None)
        assert _transparent(s["border"]) and not s["tabPill"]
        assert s["label"] == "Reload this version"
        _box(page, "document").fill(TYPED)  # the rail's box mirrors the same draft
        page.evaluate("() => { document.getElementById('content-frame').contentWindow.__before = 1; }")
        page.locator("#aa-fresh").click()
        page.wait_for_function("() => !document.getElementById('content-frame').contentWindow.__before")
        page.frame_locator("#content-frame").locator('textarea[data-strip-say="question-11"]').wait_for()
        assert page.evaluate("() => document.getElementById('content-frame').dataset.version") == "v1"
        for where in ("rail", "document"):
            page.wait_for_function("([sel, want]) => { const f = document.getElementById('content-frame').contentDocument;"
                                   " const el = (sel[0] === 'rail' ? document : f).querySelector(sel[1]); return el && el.value === want; }",
                                   arg=[[where, '#comment-list [data-decision-say-ta="question-11"]' if where == "rail"
                                         else 'textarea[data-strip-say="question-11"]'], TYPED])


@pytest.mark.parametrize("engine", ["chrome", "ipad"])
def test_b_a_newer_version_only_shows_its_name_in_plain_text(tmp_path, engine):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, engine) as (page, _):
        _publish_v2(tmp_path, directory)
        _poll(page, 2)
        s = _state(page)
        assert (s["waiting"], s["count"], s["version"], s["fix"]) == (False, None, "v2", None)
        assert _transparent(s["border"]) and not s["versionPill"] and not s["tabPill"]
        page.locator("#aa-fresh").click()
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v2'")
        page.wait_for_function("() => document.querySelector('#aa-fresh .aa-fresh-v').hidden")


@pytest.mark.parametrize("engine", ["chrome", "ipad"])
@pytest.mark.parametrize("newer", [False, True])
def test_c_new_questions_turn_it_red_with_their_count(tmp_path, engine, newer):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, engine) as (page, base):
        if newer:
            _publish_v2(tmp_path, directory)
        _agent(base, "api/comments/batch", {"items": [dict(QUESTION, version="v2" if newer else "v1")]})
        _poll(page, 2)
        s = _state(page)
        assert (s["waiting"], s["count"], s["version"], s["fix"]) == (True, "1", "v2" if newer else None, None)
        assert not _transparent(s["border"]) and not s["tabPill"]
        page.locator("#aa-fresh").click()
        page.locator("#comment-list", has_text="New question 12?").wait_for()
        page.wait_for_function("() => document.querySelector('#aa-fresh .aa-fresh-n').hidden")
        if newer:
            assert page.evaluate("() => document.getElementById('content-frame').dataset.version") == "v2"


def test_c_a_changed_card_alone_does_not_turn_it_red(tmp_path):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, "chrome") as (page, base):
        _agent(base, "api/comments/question-11", {"decision_request": None, "withdraw_reason": "no longer needed"}, method="PUT")
        _poll(page, 2)
        s = _state(page)
        assert (s["waiting"], s["count"], s["version"]) == (False, None, None)


@pytest.mark.parametrize("engine", ["chrome", "ipad"])
@pytest.mark.parametrize("with_items", [False, True])
def test_d_a_fix_of_this_version_says_fix_in_orange(tmp_path, engine, with_items):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, engine) as (page, base):
        _publish_fix(tmp_path, directory)
        if with_items:
            _agent(base, "api/comments/batch", {"items": [dict(QUESTION, version="v2")]})
        _poll(page, 2)
        s = _state(page)
        assert (s["version"], s["fix"]) == ("v2", "fix")
        assert (s["waiting"], s["count"]) == ((True, "1") if with_items else (False, None))
        r, g, b, _ = s["fixColour"]
        assert r > g > b and r - b > 80, s["fixColour"]  # orange: red high, green middle, blue low
        assert "v2 fixes this version" in s["label"]
