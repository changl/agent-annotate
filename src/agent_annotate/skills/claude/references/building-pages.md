# Building a page

The chrome is the server's job, not yours. Author the document only. The server
serves `shell.html`, `shell.js`, `shell.css` and `adapter.js` fresh from the
package on every request and recovers your content from the artifact, so a UI
fix reaches every published page at once. Anything you hand-build into a
published page freezes at publish time and goes stale.

Write the document as markdown and let `annotate new` render it (§1). Reach for
the template and a `build.py` (§4) only for a page the markdown cannot express —
an inline SVG diagram, a plotted chart, a bespoke layout.

## 1. Writing a page in markdown

```bash
annotate new --example > page.md                  # a worked document, every construct
annotate new <slug-dir> --from page.md            # → versions/vN.html + cards.json
annotate new <slug-dir> --from page.md --publish --ask     # …and serve it, and pose the round
annotate new <slug-dir> --from page.md --version v2 --label "round 2" --publish
```

One run writes `versions/<vN>.html`, `cards.json`, `comments.json` and a copy of
the source at `source/<vN>.md`. The first version also creates `current.html`
and history; later versions remain staged until `publish-version` passes the
carry-over gate. It prints the anchor count and the commands that follow. The
parser is part of the package; there is no markdown dependency and no rendering
you cannot predict from the table below.

### Front matter

`---` fenced `key: value` lines. Every key is optional.

| Key | Default |
|---|---|
| `title` | the slug-dir name |
| `subtitle` | empty |
| `date` | today, ISO |
| `slug` | the slug-dir name (this is `DOC_ID`, the localStorage key) |
| `version` | `v1` — `--version` wins |
| `label` | `generated from <file>` — `--label` wins |
| `legend` | empty; renders into the legend drawer |
| `full_plan` | required as `true` after v1; every version is cumulative, never a delta |
| `other_files_required` | required after v1; use `none` or name every required file |

An unknown key is an error, not a silent typo.

### Body constructs and the anchors they mint

| Markdown | HTML | Anchor |
|---|---|---|
| `# Title` equal to the front-matter title | dropped (the header already shows it) | — |
| `## Scope` | `<section>` + `<h2>` | `s:scope` |
| `### Out of scope` | `<h3>` | `s:scope:out-of-scope` |
| paragraph | `<p>` (the first in a section gets `.lede`) | `s:scope:p1` |
| `- item` / `1. item` | `<ul>` / `<ol>` + `<li>` | `s:scope:li1` |
| pipe table | `<table>` inside a scroll wrapper | `tbl:scope`, `tbl:scope:col:<header>`, `tbl:scope:row:<first-cell>` |
| `kpi: 64% \| of 201 cards unanswered \| bad` | one `.kpi` tile; consecutive lines form one grid; tone is `bad`, `warn` or `ok` | `kpi:of-201-cards-unanswered` |
| ` ```sql ` fence | `<pre><code>`, escaped | `s:scope:code1` |
| ` ```cards ` fence | a visible `.card` per entry | `d:1`, or the entry's `anchor_id` |

Inline: `` `code` ``, `**bold**`, `*italic*`, `[text](url)`. Everything else is
escaped, and a `javascript:` URL is dropped.

Content before the first `##` lands in an implicit section anchored
`s:overview`. Repeated keys are deduped with `-2`, `-3` — two rows whose first
cell is `status` become `tbl:scope:row:status` and `…:status-2` — so a table
never silently loses a row anchor. Every anchor is written into
`ANCHOR_REGISTRY` with `{name, grp, parent, kind}`: `grp` is the section title,
`parent` is the enclosing element, so shift-click walks row → table → section.

### The cards block

A ` ```cards ` fence holds the same JSON array `annotate ask --from` takes:
`[{number, anchor_id, text, decision_request}]`, schema in
`decision-cards.md`. The
generator writes it to `<slug-dir>/cards.json` **and** renders each card in the
body — title, context, one line per option, a "Recommended" badge on the
recommended one, impact and blocking chips. The reviewer sees the question
where the evidence is, not only in the drawer.

For v2+, put exactly one cards block in the final `## Questions for Chang`
section. Each card needs a unique ascending positive integer `number`, uses
`anchor_id: d:q<number>`, and links back to plan anchors through
`decision_request.evidence`. The prompt carries no competing Q/# label.

On v1, `anchor_id` is optional; omitted, the card owns a fresh `d:<n>`. Name an anchor
the prose already mints (`tbl:columns:row:tier`) and the card is pinned to that
element instead: the body card renders bound, with a link, and no second
element claims the id. Order does not matter — a card may name an anchor
defined later in the document.

### Lint

The run fails, writes nothing, and names the problem when the page would carry
duplicate anchor ids, no anchors at all, invalid later-version full-plan/card
metadata, or text between `</style>` and the
first element. That last one is the rule that nine published versions broke:
all CSS lives in the single `<style>` the generator emits at the top of the
canvas, and nothing else does.

A later version that retains fewer than half of the prior top-level sections
also prints a full-plan warning naming the missing sections. Resolve the warning
before publishing; it is a restructure check, not permission to ship a delta.

## 2. Template placeholders

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

## 3. The CANVAS sentinels

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

## 4. The build.py pattern — for what markdown cannot express

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

## 5. The lint caveat

`publish` runs `node --check` over every inline `<script>` block that is not
`src=`, not self-closing, not empty, and not a non-JS `type`. A failure names
the block number and the approximate HTML line, and the publish stops.

Keep CSS inside `<style>` elements. A stray rule, an unquoted selector or a
templating artifact that lands inside a `<script>` is a JavaScript syntax
error, and that is the most common reason a publish stops before the URL is
printed. `<style>` content is not linted, so it is also where anything
CSS-shaped belongs. `--skip-js-lint` exists and is for emergencies only.

## 6. Verify in the browser, not on a status code

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

## 7. Cost baseline

A hand-built page cost a median of **6 minutes and 31 tool calls** end to end,
a bespoke `build.py` every time (one slug accumulated fifteen) and a separate
`cards.json` for the round. Through `annotate new` it is **two calls**:

```bash
annotate new reviews/items-model --from page.md --publish --ask
```

one write of `page.md`, one run. Reserve the `build.py` path for a page
markdown cannot express, and keep its cost in mind when you reach for it. Most
of the old overrun was hand-patching chrome into a published page and
re-checking a URL that was already verified. Neither is work.
