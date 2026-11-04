# Page format

Author page.md with built-in Markdown; `annotate new --example` prints a complete example. Review, Library, Findings and Plans share the project page; History preserves published versions and submitted rounds. Do not copy servers or styles into the project.

Publish page and cards together with `annotate publish SLUG --from page.md`: annotate picks the next version (one past every shown or staged one) and numbers new cards. `annotate publish SLUG --from part.md --section Results` replaces one `##` section (matched by heading or `s:results`) of the newest version; a part without its own `##` keeps the heading, and other sections stay as they are with their open questions. The stored `source/vN.md` names images by the page's own copies, so the part file needs only its own pictures. `--stage` stages without showing; `annotate publish SLUG --version vN` shows a staged version. Failed checks or cards leave the previous version visible and print one `not live: … · fix: …` line. A shown version cannot be rewritten, republished or extended with `annotate ask`: use the next version, optionally `--fixes vN` for a follow-up fix. The metadata History entry exposes `fixes`. `annotate new DIR --from page.md --publish` does the same as `publish --from`.

## Document

Names: one stable `current.meta.json.name` per page; set/rename with `new --title` or `publish --title`, initially seeded from the document title if omitted.
Use sentence case and proper nouns: **Agent Annotate** for the project; `agent-annotate` for package/repository IDs.
Use lowercase ASCII kebab-case directory slugs from the initial name; `-YYYYMMDD` only for separate dated reports/events; preserve existing URLs.
Parent page references derive the target's name; omit duplicate labels. Slugs are route/CLI identities, never display names.
Markdown `title`, version labels and Plan titles describe their documents/revisions; they never implicitly rename an existing page. Keep `page.md`, `source/vN.md`, `versions/vN.html`.

Front matter accepts `title`, `label` and, rarely, `version`. A requested full-plan review also uses `full_plan: true` and `other_files_required: none` (or the file list); retain the complete plan in later versions (`--section` does this), with JSON cards in a final `## Questions for reviewer` section.

````markdown
---
title: Checkout
label: Design review
---

kpi: 12 | checks passed | ok

## Scope

The proposed checkout keeps the receipt visible.

| Item | Status |
| --- | --- |
| Receipt | Verified |

```details
Test evidence
Twelve checks passed. [Run log](https://example.com/checks).
```

![Current receipt](shots/receipt.png)

```compare
title: Checkout
current: shots/checkout-current.png | Today
proposed: shots/checkout-proposed.png | One-step payment
```
````

KPI states: `ok`, `warn`, `bad`. A details fence's first line is its summary. Image paths are relative to page.md; supported local PNG/JPEG/GIF/WebP assets are copied into the page. URLs and SVG images are refused. Captions come from alt text. Compare accepts repeated current/proposed pairs for a flow, optional `title`, and optional `layout: side|stack|auto`. Use matching crops: by default phone/portrait pairs sit side by side (current left, proposed right) and desktop/landscape pairs stack (current above, proposed below).

Anchors derive from content: heading `## Scope` → `s:scope`, a nested `### Detail` → `s:scope:detail`, its first paragraph → `s:scope:p1`, table row → `tbl:scope:row:receipt`, image → `fig:current-receipt`, compare title → `cmp:checkout`. Inspect the generated HTML anchor registry if unsure; keep anchors stable across versions.

Tables: at most 5 columns. Column 1 is a short row label (at most 4 words). Numbers, dates, states and codes get their own short columns; a cell of up to 12 characters stays on one line, up to 24 wraps to two. Long prose goes in one column, the last. Two prose columns side by side, or more than 5 columns, means sections or a list instead.

## Cards

One `ask` fence per card, placed after the block it asks about:

````markdown
```ask
Use one-step payment?
The receipt remains visible in the comparison.
+ One step: Payment and receipt share a screen.
- Keep current: Payment stays on a separate screen.
see: cmp:checkout
impact: high
```
````

The first line is the question; plain lines before the options are context. `+ Label: consequence` marks the recommended option (at most one), `- Label: consequence` the others; the option ID is the label in kebab-case. Optional trailing lines: `see:` with one or more anchors (default: the enclosing section), `impact: low|medium|high`, `blocking: yes`, and `catalog: yes` only when the card approves a plan or design, which files the answer under Plans > Approved plans (other answers stay in Review history). annotate numbers new cards after every number on the page and writes the number into the stored source; `#12 Use one-step payment?` keeps question 12 when you rewrite its section. Every cited anchor must exist in this version; a card cannot cite itself, and bulk approvals are refused. Cards render after their last evidence target, so put the sections that carry open questions first and completed work or supporting detail after.

Older JSON `cards` fences still work with their rules: positive, ascending, stable `number`s with matching `d:qN` anchors, `prompt` required, options as strings or `{id,label,consequence,style?}` (style `primary|default|danger`), `recommendation` an option ID, at least one `evidence` `{label,anchor}`, in a final `## Questions for reviewer` section on a full plan. `annotate ask SLUG --from cards.json` takes the same JSON.

The reviewer can choose, answer in words, or attach explanations. Clicks remain pending until Send. Submitted snapshots preserve prompts and answers even if a later version changes a question. Reviewer confirmation belongs to the reviewer.

## Project progress and links

Persistent project modules are independent of review versions. A `project` fence or `annotate project SLUG --from project.json` updates them; omitting the fence preserves them.

````markdown
```project
{"title":"Checkout","modules":[{"id":"progress","title":"Progress","kind":"progress","items":[{"label":"Receipt checks","status":"done","detail":"Twelve checks passed","url":"https://example.com/checks"}]},{"id":"resources","title":"Resources","kind":"links","items":[{"label":"Preview","url":"https://example.com/preview","description":"Checkout prototype"}]}]}
```
````

Progress statuses: `todo`, `in_progress`, `done`, `blocked`; optional `failed_count` records repeated failures. Links use `{label,url,description?}`; notes modules use `{text}` items. Keep module IDs stable and use verified HTTP(S) links without credentials. Publish independent plans with `annotate plan SLUG rollout --from plan.md --section tracking|approved|reference`: tracking for lists the reviewer asked you to keep current, approved for plans the reviewer approved, reference (the default, listed last) for agent material. Library copy uses `annotate copy SLUG --from copy.json`; read a proposed block with `annotate copy SLUG --block ID`. Copy revisions use the existing Library JSON schema and immutable Quill Delta revisions.
