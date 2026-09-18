# Building a page

The chrome is the server's job, not yours. Author the document only. The server
serves `shell.html`, `shell.js`, `shell.css` and `adapter.js` fresh from the
package on every request and recovers your content from the artifact, so a UI
fix reaches every published page at once. Anything you hand-build into a
published page freezes at publish time and goes stale.

## 1. Template placeholders

Substitute these in `template.html` (they are literal `{{NAME}}` tokens). The
file ships in the package as `agent_annotate/web/template.html`;
`python -c 'from agent_annotate.paths import WEB_DIR; print(WEB_DIR)'` prints
the directory.

| Placeholder | Inject |
|---|---|
| `{{TITLE}}` | Short action title. Appears in `<title>` and the header. |
| `{{SUBTITLE}}` | One-line description. |
| `{{DATE}}` | ISO date or a status badge string. |
| `{{DOC_ID}}` | The slug. Used as the localStorage key. |
| `{{VERSION}}` | Fallback version label when no `current.meta.json` is present. |
| `{{CANVAS}}` | Your content. Every commentable element carries `data-anchor-id`. |
| `{{ANCHOR_REGISTRY}}` | JS object literal `{ 'anchor-id': {name, grp, parent?, kind?} }`. |
| `{{LEGEND}}` | Optional legend HTML, or empty. |

`{{TITLE}}` appears twice. Replace every occurrence, not the first.

## 2. The CANVAS sentinels

```html
<!-- CANVAS CONTENT — injected by Claude ── -->
{{CANVAS}}
<!-- END CANVAS CONTENT ──────────────────── -->
```

These two comments are the contract that lets the server find your content when
it re-serves the page with current chrome. Keep them byte-intact and put
everything you author between them. Write `content/<version>.html` only to
deliberately override the automatic extraction — it always wins when present.

Interactive elements keep their native behavior: links, form controls, ARIA
widgets, `contenteditable` and focusable regions do not open a comment. Mark a
custom widget `data-annotate-interactive` for the same treatment. Alt/Option
click comments on an excluded element anyway.

## 3. The build.py pattern

Write a small generator next to the slug dir and run it. Do not hand-edit a
`versions/vN.html` after it is published.

```python
#!/usr/bin/env python3
"""Render versions/vN.html from template.html. Idempotent; re-runnable."""
import json, os, pathlib

from agent_annotate.paths import WEB_DIR   # the packaged template.html
SLUG_DIR = pathlib.Path(__file__).resolve().parent
VERSION = "v1"

registry = {
    "tbl:items": {"name": "Items table", "grp": "Data", "kind": "table"},
    "tbl:items:row:42": {"name": "Acme Corp", "grp": "Data · Tier A",
                          "parent": "tbl:items", "kind": "row"},
}
canvas = """<table data-anchor-id="tbl:items"> … </table>"""

html = (WEB_DIR / "template.html").read_text(encoding="utf-8")
for token, value in {
    "{{TITLE}}": "Items model review",
    "{{SUBTITLE}}": "Round 1 — column semantics",
    "{{DATE}}": "2026-09-17",
    "{{DOC_ID}}": SLUG_DIR.name,
    "{{VERSION}}": VERSION,
    "{{CANVAS}}": canvas,
    "{{ANCHOR_REGISTRY}}": json.dumps(registry, indent=2),
    "{{LEGEND}}": "",
}.items():
    html = html.replace(token, value)          # replace(), not replace(…, 1)

out = SLUG_DIR / "versions" / f"{VERSION}.html"
out.parent.mkdir(parents=True, exist_ok=True)
tmp = out.with_suffix(".html.tmp")
tmp.write_text(html, encoding="utf-8")
os.replace(tmp, out)                            # atomic: servers read this live

cur = SLUG_DIR / "current.html"
tmp_link = SLUG_DIR / ".current.html.tmp"
tmp_link.unlink(missing_ok=True)
os.symlink(out.relative_to(SLUG_DIR), tmp_link) # relative target, not absolute
os.replace(tmp_link, cur)

meta = SLUG_DIR / "current.meta.json"
data = json.loads(meta.read_text()) if meta.exists() else {"history": []}
data["current"] = VERSION
meta.write_text(json.dumps(data, indent=2), encoding="utf-8")
(SLUG_DIR / "comments.json").touch()            # empty file is a valid v2 store
```

For versions after the first, write `versions/vN.html` and let
`annotate publish-version <slug-dir> vN --label "round 2"` do the symlink,
the meta `current` and the history append. Do not write `history` by hand.

**Never rewrite `current.meta.json` wholesale while a server is running.** The
server stamps `owner` and `content_stamp` into the same file under its own
lock. Read, mutate your own keys, write back — or let the CLI do it.

## 4. The lint caveat

`publish` runs `node --check` over every inline `<script>` block that is not
`src=`, not self-closing, not empty, and not a non-JS `type`. A failure names
the block number and the approximate HTML line, and the publish stops.

Keep CSS inside `<style>` elements. A stray rule, an unquoted selector or a
templating artifact that lands inside a `<script>` is a JavaScript syntax
error, and that is the most common reason a publish stops before the URL is
printed. `<style>` content is not linted, so it is also where anything
CSS-shaped belongs. `--skip-js-lint` exists and is for emergencies only.

## 5. Verify in the browser, not on a status code

Publish's own gate asserts rendered anchors at `origin`, `tailscale` and
`public`, and the public hop runs inside the authenticated Orca browser.
Verify by hand the same way:

```bash
orca tab create --profile default --url "https://<host>/<slug>/" --json
orca eval --page <browserPageId> --expression \
  'JSON.stringify({anchors: document.querySelectorAll("[data-anchor-id]").length, title: document.title})' --json
```

The iframe loads asynchronously, so an immediate read returns 0 anchors on a
perfectly healthy page. Poll until anchors are non-zero, then assert on the
count and on text you know is in the content. Behind Cloudflare Access a
healthy route and a 502-ing route both answer 302 to a login page, and an
authenticated request to a dead origin answers 200 with a "Bad gateway" body,
so **a status code carries no information here**. Never `curl` a published URL
to decide whether it works, and never ask the user to check for you.

## 6. Cost baseline

Building and publishing a page currently costs a median of **6 minutes and 31
tool calls** end to end. Target under 15 tool calls: one read of
`template.html`, one write of `build.py`, one run, one `publish`, one `ask`.
Most of the overrun is hand-patching chrome into a published page and
re-checking a URL that was already verified. Neither is work.
