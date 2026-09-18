"""Publish must prove a page renders, not that a request returned a number.

Behind Cloudflare Access every interesting outcome answers with a misleading
status: an unauthenticated hit on a healthy route 302s to the login page, and
an authenticated hit on a dead origin 200s with Cloudflare's "Bad gateway"
page. Pages were repeatedly declared published on that evidence. These tests
pin the content-based assertions that replaced it.
"""

import http.server
import socket
import threading

import pytest

from agent_annotate import verify

SHELL = """<!doctype html><html><head><title>annotate</title></head>
<body><iframe id="content-frame" class="content-frame"></iframe></body></html>"""

CONTENT = """<!doctype html><html><body>
<section data-anchor-id="s:intro">intro</section>
<section data-anchor-id="s:body">body</section>
</body></html>"""

CF_502 = """<!doctype html><html><head><title>leadory.net | 502: Bad gateway</title>
</head><body>Bad gateway Error code 502</body></html>"""

CF_LOGIN = """<!doctype html><html><body>
<a href="https://weathered-hat-07df.cloudflareaccess.com/cdn-cgi/access/login/x">go</a>
</body></html>"""


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Server:
    """Serves a fixed {path: (status, body)} map on loopback."""

    def __init__(self, routes):
        self.port = _free_port()
        routes = dict(routes)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                status, body = routes.get(self.path, (404, "nope"))
                raw = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self._httpd = http.server.HTTPServer(("127.0.0.1", self.port), Handler)

    def __enter__(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
        return False

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}/"


def test_shell_plus_content_with_anchors_passes():
    with _Server({"/": (200, SHELL), "/content": (200, CONTENT)}) as s:
        result = verify.probe_http("origin", s.base, timeout=3)
    assert result.status == verify.PASS
    assert result.anchors == 2


def test_shell_whose_content_is_empty_fails():
    """A 200 with an empty iframe document is the exact 'looks fine, renders
    nothing' state that kept getting shipped."""
    with _Server({"/": (200, SHELL), "/content": (200, "   ")}) as s:
        result = verify.probe_http("origin", s.base, timeout=2)
    assert result.status == verify.FAIL
    assert "empty" in result.detail


def test_shell_whose_content_has_no_anchors_fails():
    with _Server({"/": (200, SHELL), "/content": (200, "<html><body>hi</body></html>")}) as s:
        result = verify.probe_http("origin", s.base, timeout=2)
    assert result.status == verify.FAIL
    assert "data-anchor-id" in result.detail


def test_direct_serve_page_passes_on_its_own_anchors():
    """Slugs that never went through template.html are served whole at the
    root; they have no /content route and must still verify."""
    with _Server({"/": (200, CONTENT)}) as s:
        result = verify.probe_http("origin", s.base, timeout=3)
    assert result.status == verify.PASS
    assert result.anchors == 2


def test_cloudflare_502_body_is_named_not_just_rejected():
    """A 502 page is served with status 200 through the tunnel. The gate must
    key off the body and say which hop is broken."""
    with _Server({"/": (200, CF_502)}) as s:
        result = verify.probe_http("public", s.base, timeout=2)
    assert result.status == verify.FAIL
    assert "502" in result.detail
    assert "tailscale" in result.detail


def test_access_login_page_is_unverified_not_failed():
    """v2.19: a login page says nothing about the page behind it. Calling it a
    failure printed NOT PUBLISHED over five healthy pages; calling it healthy
    would be the original bug. It is UNAVAILABLE with reason access_login, and
    the probe answers at once rather than polling for a login that cannot
    happen from here."""
    with _Server({"/": (200, CF_LOGIN)}) as s:
        result = verify.probe_http("public", s.base, timeout=2)
    assert result.status == verify.UNAVAILABLE
    assert result.reason == verify.ACCESS_LOGIN
    assert "Access" in result.detail
    assert not result.ok
    report = verify.VerifyReport([result])
    assert report.access_blocked == [result]
    assert report.failed == []
    assert "LOGIN" in verify.format_report(report)[0]


def test_unreachable_origin_fails_with_the_connection_error():
    port = _free_port()  # nothing bound
    result = verify.probe_http("origin", f"http://127.0.0.1:{port}/", timeout=1)
    assert result.status == verify.FAIL
    assert result.detail


def test_anchor_count_ignores_selector_strings_in_scripts():
    """shell.js is full of `[data-anchor-id]` selectors. A substring count
    would score a chrome-only page as commentable."""
    assert verify.count_anchors("<script>q('[data-anchor-id]')</script>") == 0
    assert verify.count_anchors('<div data-anchor-id="s:x"></div>') == 1


# ── the report contract publish depends on ──────────────────────────────────

def _stage(name, status):
    return verify.StageResult(name, "http://x/", status, "detail")


def test_unavailable_browser_is_not_counted_as_verified():
    """'I could not check' must never read as 'I checked and it is fine'."""
    report = verify.VerifyReport([_stage("origin", verify.PASS),
                                  _stage("public", verify.UNAVAILABLE)])
    assert report.ok is True            # nothing failed, so do not block
    assert report.fully_verified is False   # ...but do not claim success either
    assert [s.name for s in report.unavailable] == ["public"]


def test_any_failure_makes_the_report_not_ok():
    report = verify.VerifyReport([_stage("origin", verify.PASS),
                                  _stage("tailscale", verify.FAIL)])
    assert report.ok is False
    assert report.failed[0].name == "tailscale"


def test_browser_probe_reports_unavailable_when_orca_is_missing(monkeypatch):
    def _boom(argv, timeout=60.0):
        raise FileNotFoundError("orca")

    monkeypatch.setattr(verify, "_orca", _boom)
    result = verify.probe_browser("public", "https://example.test/x/", timeout=1)
    assert result.status == verify.UNAVAILABLE
    assert "orca" in result.detail


def test_browser_probe_polls_until_the_iframe_fills(monkeypatch):
    """An immediate read of a healthy page returns 0 anchors — the iframe loads
    async. Failing on the first read would reject working pages."""
    calls = {"n": 0}

    def _fake(argv, timeout=60.0):
        if argv[0] == "tab" and argv[1] == "create":
            return {"result": {"browserPageId": "p1"}}
        if argv[0] == "eval":
            calls["n"] += 1
            payload = ({"title": "annotate", "contentLen": 0, "anchors": 0, "text": ""}
                       if calls["n"] < 3 else
                       {"title": "annotate", "contentLen": 900, "anchors": 4, "text": ""})
            import json as _json
            return {"result": {"result": _json.dumps(payload)}}
        return {"result": {"closed": True}}

    monkeypatch.setattr(verify, "_orca", _fake)
    result = verify.probe_browser("public", "https://example.test/x/",
                                  timeout=10, poll_interval=0.01)
    assert result.status == verify.PASS
    assert result.anchors == 4
    assert calls["n"] >= 3


def test_browser_probe_fails_on_a_rendered_502(monkeypatch):
    def _fake(argv, timeout=60.0):
        if argv[0] == "tab" and argv[1] == "create":
            return {"result": {"browserPageId": "p1"}}
        if argv[0] == "eval":
            import json as _json
            return {"result": {"result": _json.dumps({
                "title": "leadory.net | 502: Bad gateway",
                "contentLen": 0, "anchors": 0,
                "text": "Bad gateway Error code 502"})}}
        return {"result": {"closed": True}}

    monkeypatch.setattr(verify, "_orca", _fake)
    result = verify.probe_browser("public", "https://example.test/x/",
                                  timeout=0.2, poll_interval=0.01)
    assert result.status == verify.FAIL
    assert "502" in result.detail


@pytest.mark.parametrize("status", [verify.PASS, verify.FAIL, verify.UNAVAILABLE])
def test_format_report_renders_every_status(status):
    lines = verify.format_report(verify.VerifyReport([_stage("origin", status)]))
    assert any("origin" in line for line in lines)
