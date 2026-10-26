# Page format

Author page.md with built-in Markdown; `annotate new --example` prints a complete example. Review, Library, Findings and Plans share the project page; History preserves published versions and submitted rounds. Do not copy servers or styles into the project.

## Document

Names: one stable `current.meta.json.name` per page; set/rename with `new --title` or `publish --title`, initially seeded from the document title if omitted.
Use sentence case and proper nouns: **Agent Annotate** for the project; `agent-annotate` for package/repository IDs.
Use lowercase ASCII kebab-case directory slugs from the initial name; `-YYYYMMDD` only for separate dated reports/events; preserve existing URLs.
Parent page references derive the target's name; omit duplicate labels. Slugs are route/CLI identities, never display names.
Markdown `title`, version labels and Plan titles describe their documents/revisions; they never implicitly rename an existing page. Keep `page.md`, `source/vN.md`, `versions/vN.html`.

Front matter accepts `title`, `version` and `label`. A requested full-plan review also uses `full_plan: true` and `other_files_required: none` (or the file list); retain the complete plan in later versions, with cards in a final `## Questions for reviewer` section.

````markdown
---
title: Checkout
version: v1
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

KPI states: `ok`, `warn`, `bad`. A details fence's first line is its summary. Image paths are relative to page.md; supported local PNG/JPEG/GIF/WebP assets are copied into the page. URLs and SVG images are refused. Captions come from alt text. Compare accepts repeated current/proposed pairs for a flow, optional `title`, and optional `layout: side|stack|auto`.

Anchors derive from content: heading `## Scope` → `s:scope`, a nested `### Detail` → `s:scope:detail`, its first paragraph → `s:scope:p1`, table row → `tbl:scope:row:receipt`, image → `fig:current-receipt`, compare title → `cmp:checkout`. Inspect the generated HTML anchor registry if unsure; keep anchors stable across versions.

## Cards

````markdown
```cards
[{"number":1,"anchor_id":"d:q1","decision_request":{"prompt":"Use one-step payment?","context":"The receipt remains visible in the comparison.","recommendation":"one-step","options":[{"id":"one-step","label":"One step","consequence":"Payment and receipt share a screen."},{"id":"keep","label":"Keep current","consequence":"Payment stays on a separate screen."}],"evidence":[{"label":"Checkout comparison","anchor":"cmp:checkout"}]}}]
```
````

Use positive, ascending, stable numbers and matching `d:qN` anchors. `prompt` is required; context, recommendation (option ID), options and evidence explain the decision. Options accept strings or `{id,label,consequence,style?}`; style is `primary|default|danger`. Optional `impact`: `low|medium|high`; `blocking`: boolean; `catalog: true` only when the card approves a plan or design, which files the answer under Plans > Approved plans (other answers stay in Review history). Evidence entries use `{label,anchor}` and must exist in this version. Cards render after their last evidence target, so put the sections that carry open questions first and completed work or supporting detail after. At least one evidence anchor is required; every cited anchor must exist in this version, and a card cannot cite its own decision anchor. Explicit bulk approvals are refused before writing.

The reviewer can choose, answer in words, or attach explanations. Clicks remain pending until Send. Submitted snapshots preserve prompts and answers even if a later version changes a question. Reviewer confirmation belongs to the reviewer.

## Project progress and links

Persistent project modules are independent of review versions. A `project` fence or `annotate project SLUG --from project.json` updates them; omitting the fence preserves them.

````markdown
```project
{"title":"Checkout","modules":[{"id":"progress","title":"Progress","kind":"progress","items":[{"label":"Receipt checks","status":"done","detail":"Twelve checks passed","url":"https://example.com/checks"}]},{"id":"resources","title":"Resources","kind":"links","items":[{"label":"Preview","url":"https://example.com/preview","description":"Checkout prototype"}]}]}
```
````

Progress statuses: `todo`, `in_progress`, `done`, `blocked`; optional `failed_count` records repeated failures. Links use `{label,url,description?}`; notes modules use `{text}` items. Keep module IDs stable and use verified HTTP(S) links without credentials. Publish independent plans with `annotate plan SLUG rollout --from plan.md --section tracking|approved|reference`: tracking for lists the reviewer asked you to keep current, approved for plans the reviewer approved, reference (the default, listed last) for agent material. Library copy uses `annotate copy SLUG --from copy.json`; read a proposed block with `annotate copy SLUG --block ID`. Copy revisions use the existing Library JSON schema and immutable Quill Delta revisions.
