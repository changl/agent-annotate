"""The fixture's minimal HTML import preserves observable formatted copy."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "work/product/fixture/build_fixture.py"
_SPEC = importlib.util.spec_from_file_location("rebex_fixture", _PATH)
fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fixture)


def test_html_delta_preserves_inline_spacing_and_line_formatting():
    result = fixture.delta(html='<h2>Heading</h2><p><strong>Hello</strong> <em>world</em> <a href="https://example.com">link</a></p><ul><li>First</li></ul>')
    ops = result["ops"]
    assert "".join(op["insert"] for op in ops) == "Heading\nHello world link\nFirst\n"
    assert {"insert": "Hello", "attributes": {"bold": True}} in ops
    assert {"insert": "world", "attributes": {"italic": True}} in ops
    assert {"insert": "link", "attributes": {"link": "https://example.com"}} in ops
    assert {"insert": "\n", "attributes": {"header": 2}} in ops
    assert {"insert": "\n", "attributes": {"list": "bullet"}} in ops


def test_html_delta_omits_embeds_scripts_and_unsafe_links():
    result = fixture.delta(html='<p>Safe<script>evil()</script><img src="x"><a href="javascript:evil()">text</a></p>')
    assert result == {"ops": [{"insert": "Safe"}, {"insert": "text"}, {"insert": "\n"}]}


def test_fixture_state_refuses_other_state_roots():
    with pytest.raises(ValueError, match="state must be"):
        fixture.sandbox_environment(Path("/private/tmp/unrelated-fixture"))
