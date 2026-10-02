# Page format

Use built-in Markdown. Do not copy a server, shell, CSS, or build script into a project. One project workspace has Progress and Feedback tabs; optional short tabs retain existing reviews. External worksheets are links, not additional progress pages.

```yaml
---
title: Project name
---
```

Supported: headings, paragraphs, lists, tables, code, links, `kpi: value | label | ok|warn|bad`, and `cards`, `project`, `details` fences. `new --example` prints an example. Keep ordinary updates under 30 words. Supporting detail:

```details
Test evidence
Checks and links needed to assess the result.
```

Persistent project data lives in `project.json`, independently of review versions:

```project
{"title":"Project","modules":[{"id":"progress","title":"Progress","kind":"progress","items":[{"label":"Home speed check: #11 CHA-182","url":"https://linear.app/team/issue/CHA-182","status":"blocked","detail":"Rehearsal passed; test-script bug stopped it.","failed_count":3}]}],"tabs":[{"id":"content","label":"Content","url":"https://reviews.example/content/"}]}
```

Modules: `links` items `{label,url,description?}`; `progress` items `{label,status,detail?,url?,failed_count?}`; `notes` items `{text}`. Status: `todo`, `in_progress`, `done`, `blocked`. Stable module IDs preserve disclosure choices. Omitting the project fence preserves saved data. Annotation tabs use the same Funnel origin. External resources use links modules. Tabs use unique `{id,label,url}`; `progress` and `feedback` are reserved. Use HTTP(S) URLs without credentials. Link IDs directly to their real tickets; never guess a ticket URL.

New feedback uses one `cards` JSON array. Keep positive stable `number` values and `anchor_id: d:qN`; do not repeat numbers in prompts. Evidence can reference generated anchors: `s:scope`, `s:scope:p1`, `tbl:columns:row:status`. Existing replies survive version changes.

Ordinary progress requires no plan metadata. When a full-plan review is requested, use `full_plan: true`, `other_files_required: none` (or the file list), and one final `## Questions for Chang` cards section with ascending numbers and evidence. Later full-plan versions retain the current plan; unchanged sections fold automatically.

Custom diagrams may supply HTML content with stable `data-anchor-id` attributes. Preserve the template canvas sentinels and use `publish-version` to activate later versions. Never overwrite owner metadata or reviewer state.

Publish verifies the rendered page and prints the URL. An Access login means the external check is unverified; it is not a reason to rebuild or repeatedly probe. Diagnose the named failing hop once. Do not infer rendering from HTTP 200.
