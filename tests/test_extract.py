import json

import pytest

from agent_annotate.extract import (
    ExtractionError,
    build_content_document,
    extract_canvas,
    extract_registry,
    has_canvas_sentinels,
)

BAKED = """<!doctype html>
<html><head><title>T</title>
<script src="../diagram-plot.js"></script>
<style>.chrome{color:red}</style>
</head>
<body>
<header>chrome header</header>
<div class="canvas-wrapper" id="canvas-wrapper">
<!-- CANVAS CONTENT - injected by Claude -->
<div class="no" id="s:one"><h2>One</h2><p>Body</p></div>
<div data-anchor-id="s:two">Two</div>
<!-- END CANVAS CONTENT -->
<div id="badge-layer"></div>
</div>
<aside class="panel" id="panel">chrome panel</aside>
<script>
const ANCHOR_REGISTRY = {"s:one": {"name": "One"}, "s:two": {"name": "Two"}};
document.addEventListener('click', e => {});
</script>
</body></html>
"""


def test_detects_sentinels():
    assert has_canvas_sentinels(BAKED)
    assert not has_canvas_sentinels("<html><body>no sentinels</body></html>")


def test_extracts_only_the_canvas():
    canvas = extract_canvas(BAKED)
    assert 's:one' in canvas
    assert 's:two' in canvas
    # Chrome must not survive into the content document.
    assert "chrome header" not in canvas
    assert "chrome panel" not in canvas
    assert "ANCHOR_REGISTRY" not in canvas
    assert "badge-layer" not in canvas


def test_registry_json_form():
    assert extract_registry(BAKED) == {"s:one": {"name": "One"}, "s:two": {"name": "Two"}}


def test_registry_js_literal_form():
    """Older artifacts baked a JS object literal, not JSON."""
    html = BAKED.replace(
        'const ANCHOR_REGISTRY = {"s:one": {"name": "One"}, "s:two": {"name": "Two"}};',
        "const ANCHOR_REGISTRY = {'s:one': {name:'One', parent:'root'}, 's:two': {name:'Two'},};",
    )
    assert extract_registry(html) == {
        "s:one": {"name": "One", "parent": "root"},
        "s:two": {"name": "Two"},
    }


def test_registry_brace_inside_label_does_not_truncate():
    html = BAKED.replace(
        '{"s:one": {"name": "One"}, "s:two": {"name": "Two"}}',
        '{"s:one": {"name": "a } brace"}, "s:two": {"name": "Two"}}',
    )
    reg = extract_registry(html)
    assert reg["s:one"]["name"] == "a } brace"
    assert "s:two" in reg


def test_missing_registry_is_empty_not_fatal():
    html = BAKED.replace("const ANCHOR_REGISTRY = ", "const SOMETHING_ELSE = ")
    assert extract_registry(html) == {}


def test_build_document_is_chrome_free_and_carries_registry():
    doc = build_content_document(BAKED, title="Demo")
    assert "chrome header" not in doc
    assert "chrome panel" not in doc
    assert ".chrome{color:red}" not in doc
    # No baked click handler can survive to fight adapter.js in the iframe.
    assert "document.addEventListener" not in doc

    assert 'id="anchor-registry-data"' in doc
    start = doc.index('id="anchor-registry-data">') + len('id="anchor-registry-data">')
    payload = json.loads(doc[start:doc.index("</script>", start)])
    assert payload == {"s:one": {"name": "One"}, "s:two": {"name": "Two"}}

    # Anchor attributes — what comments key off — must be intact.
    assert 'id="s:one"' in doc
    assert 'data-anchor-id="s:two"' in doc
    # diagram-plot.js is relocated so /content can rewrite its path.
    assert 'src="../diagram-plot.js"' in doc


def test_document_without_sentinels_raises():
    with pytest.raises(ExtractionError):
        build_content_document("<html><body>nothing</body></html>")
