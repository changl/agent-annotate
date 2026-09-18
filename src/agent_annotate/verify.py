"""Prove a published page actually renders before anyone is handed its URL.

Every stage asserts on RENDERED CONTENT, never on a status code. Behind
Cloudflare Access an unauthenticated request to a healthy route and to a
502-ing route both answer 302 to the login page, and an authenticated request
to a dead origin answers 200 with Cloudflare's "Bad gateway" page. A status
code carries no information here; the presence of the reviewer's anchors does.

Three stages, reported separately so a failure names the hop that broke:

    origin     http://127.0.0.1:<port><base>/   the sync server itself
    tailscale  https://<host>:<serve>/<base>/   the endpoint the tunnel dials
    public     https://<hostname>/<slug>/       what the reviewer opens

The public stage has to run inside the authenticated browser, so it shells out
to `orca`. When `orca` is not reachable the stage reports UNAVAILABLE — never
PASS. "I could not check" and "I checked and it is fine" are different answers
and this module refuses to conflate them.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

PASS = "pass"
FAIL = "fail"
UNAVAILABLE = "unavailable"

# Why a stage came back UNAVAILABLE. "access_login" means the probe met
# Cloudflare Access's login page: this session cannot see the page, which says
# nothing at all about whether the page renders. Reporting that as FAIL is what
# printed "NOT PUBLISHED — the page does not render" over five live pages and
# cost 5-10 recovery tool calls each time.
ACCESS_LOGIN = "access_login"
NO_BROWSER = "no_browser"

# Attribute form only. `[data-anchor-id]` inside a script would match a bare
# substring search, and shell.js is full of those selectors.
_ANCHOR_ATTR_RE = re.compile(r"data-anchor-id\s*=", re.IGNORECASE)
_SHELL_MARKER = 'id="content-frame"'

_BROWSER_PROBE_JS = """(() => {
  const f = document.getElementById('content-frame');
  const d = f ? f.contentDocument : null;
  const doc = d || document;
  const body = d ? d.body : document.body;
  return JSON.stringify({
    title: document.title || '',
    hasFrame: !!f,
    contentLen: body ? body.innerHTML.length : 0,
    anchors: doc ? doc.querySelectorAll('[data-anchor-id]').length : 0,
    text: document.body ? document.body.innerText.slice(0, 200) : ''
  });
})()"""


@dataclass
class StageResult:
    name: str
    url: str
    status: str
    detail: str
    anchors: int | None = None
    content_len: int | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == PASS


@dataclass
class VerifyReport:
    stages: list[StageResult] = field(default_factory=list)

    @property
    def failed(self) -> list[StageResult]:
        return [s for s in self.stages if s.status == FAIL]

    @property
    def unavailable(self) -> list[StageResult]:
        return [s for s in self.stages if s.status == UNAVAILABLE]

    @property
    def access_blocked(self) -> list[StageResult]:
        """Stages this session was not authenticated for. Not failures."""
        return [s for s in self.stages if s.reason == ACCESS_LOGIN]

    @property
    def ok(self) -> bool:
        """True only when nothing failed. UNAVAILABLE is not a failure, but
        callers must still refuse to describe the result as verified."""
        return not self.failed

    @property
    def fully_verified(self) -> bool:
        return bool(self.stages) and all(s.status == PASS for s in self.stages)


def count_anchors(html: str) -> int:
    return len(_ANCHOR_ATTR_RE.findall(html or ""))


def _is_access_login(html: str) -> bool:
    head = (html or "")[:4000].lower()
    return "cloudflareaccess.com" in head or "/cdn-cgi/access/login" in head


def _diagnose_html(html: str) -> str | None:
    """Name the well-known failure pages instead of dumping bytes."""
    head = (html or "")[:4000].lower()
    if "bad gateway" in head or "error code 502" in head:
        return ("Cloudflare 502 — the tunnel reached Cloudflare but could not reach the "
                "origin. A `http://localhost:<port>` ingress service does this even when "
                "cloudflared runs on the same host; the origin must be the tailscale "
                "serve endpoint.")
    if "cloudflareaccess.com" in head or "/cdn-cgi/access/login" in head:
        return ("Cloudflare Access login page — the probe was not authenticated. The "
                "public stage must run through the authenticated browser, not curl.")
    if "error 1033" in head or "argo tunnel error" in head:
        return "Cloudflare 1033 — no cloudflared connector is registered for this tunnel."
    return None


def _fetch(url: str, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "annotate-verify/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body


def probe_http(name: str, base_url: str, timeout: float = 20.0,
               poll_interval: float = 0.5) -> StageResult:
    """Assert that `base_url` serves a document carrying reviewer anchors.

    Handles both serving modes: a universal-shell slug answers the root with
    shell.html and keeps its anchors behind /content, while a direct-serve slug
    puts them in the root document itself. Polls, because publish calls this
    within a second of spawning the server.
    """
    base = base_url if base_url.endswith("/") else base_url + "/"
    deadline = time.monotonic() + timeout
    last = "no response"
    while True:
        try:
            code, html = _fetch(base, min(10.0, timeout))
            if code >= 400:
                last = f"HTTP {code} at {base}"
            else:
                if _is_access_login(html):
                    # Polling cannot turn an unauthenticated probe into an
                    # authenticated one. Answer now, and answer honestly.
                    return StageResult(
                        name, base, UNAVAILABLE,
                        "Cloudflare Access login page — not verified from this "
                        "session. Open the URL in the authenticated browser to "
                        "confirm; nothing here says the page is broken.",
                        reason=ACCESS_LOGIN)
                diagnosis = _diagnose_html(html)
                if diagnosis:
                    last = diagnosis
                elif _SHELL_MARKER in html:
                    ccode, chtml = _fetch(base + "content", min(10.0, timeout))
                    anchors = count_anchors(chtml)
                    if ccode >= 400:
                        last = f"shell served, but /content answered HTTP {ccode}: {chtml[:200]}"
                    elif not chtml.strip():
                        last = "/content served an empty document"
                    elif anchors == 0:
                        last = (f"/content served {len(chtml)} bytes with no "
                                "data-anchor-id attributes — nothing is commentable")
                    else:
                        return StageResult(name, base, PASS,
                                           f"shell + {anchors} anchors in /content",
                                           anchors=anchors, content_len=len(chtml))
                else:
                    anchors = count_anchors(html)
                    if anchors == 0:
                        last = (f"served {len(html)} bytes with neither the shell "
                                "(#content-frame) nor any data-anchor-id attribute")
                    else:
                        return StageResult(name, base, PASS,
                                           f"direct-serve document, {anchors} anchors",
                                           anchors=anchors, content_len=len(html))
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        if time.monotonic() >= deadline:
            return StageResult(name, base, FAIL, last)
        time.sleep(poll_interval)


def _orca(argv: list[str], timeout: float = 60.0) -> dict:
    proc = subprocess.run(["orca", *argv], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"`orca {' '.join(argv)}` exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:400]}"
        )
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"`orca {' '.join(argv)}` produced no output")
    return json.loads(raw)


def probe_browser(name: str, url: str, timeout: float = 45.0,
                  poll_interval: float = 1.5) -> StageResult:
    """Open `url` in the authenticated Orca browser and read the rendered DOM.

    The iframe loads asynchronously; an immediate read returns 0 anchors on a
    perfectly healthy page, so this polls until the content is actually there.
    """
    page_id = None
    try:
        created = _orca(["tab", "create", "--url", url, "--json"])
        page_id = (created.get("result") or {}).get("browserPageId")
        if not page_id:
            return StageResult(name, url, UNAVAILABLE,
                               f"orca tab create returned no page id: {created}")
    except FileNotFoundError:
        return StageResult(name, url, UNAVAILABLE,
                           "`orca` is not on PATH — the authenticated browser could "
                           "not be reached", reason=NO_BROWSER)
    except (RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as e:
        return StageResult(name, url, UNAVAILABLE,
                           f"could not open a browser tab: {e}", reason=NO_BROWSER)

    try:
        deadline = time.monotonic() + timeout
        last = "page never reported content"
        while True:
            try:
                res = _orca(["eval", "--page", page_id, "--expression",
                             _BROWSER_PROBE_JS, "--json"])
                payload = (res.get("result") or {}).get("result")
                data = json.loads(payload) if isinstance(payload, str) else (payload or {})
                anchors = int(data.get("anchors") or 0)
                content_len = int(data.get("contentLen") or 0)
                blob = f"{data.get('title', '')} {data.get('text', '')}"
                if _is_access_login(blob):
                    return StageResult(
                        name, url, UNAVAILABLE,
                        "Cloudflare Access login page — this browser profile is "
                        "not signed in, so the page could not be verified from "
                        "this session. It is not evidence of a broken page.",
                        reason=ACCESS_LOGIN)
                diagnosis = _diagnose_html(blob)
                if diagnosis:
                    last = diagnosis
                elif anchors > 0 and content_len > 0:
                    return StageResult(
                        name, url, PASS,
                        f"rendered {content_len} bytes with {anchors} anchors "
                        f"(title {data.get('title', '')!r})",
                        anchors=anchors, content_len=content_len)
                else:
                    last = (f"rendered {content_len} bytes with {anchors} anchors "
                            f"(title {data.get('title', '')!r})")
            except (RuntimeError, json.JSONDecodeError, ValueError,
                    subprocess.SubprocessError) as e:
                last = f"could not read the page: {e}"
            if time.monotonic() >= deadline:
                return StageResult(name, url, FAIL, last)
            time.sleep(poll_interval)
    finally:
        try:
            _orca(["tab", "close", "--page", page_id, "--json"], timeout=20.0)
        except Exception:
            pass


def format_report(report: VerifyReport) -> list[str]:
    """Human-readable lines. Verified stages are boring; failures are loud."""
    mark = {PASS: "PASS", FAIL: "FAIL", UNAVAILABLE: "SKIP"}
    lines = []
    for s in report.stages:
        label = "LOGIN" if s.reason == ACCESS_LOGIN else mark[s.status]
        lines.append(f"  {label:<5} {s.name:<10} {s.url}")
        lines.append(f"        {s.detail}")
    return lines
