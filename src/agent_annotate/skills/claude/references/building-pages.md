# Page format

Use built-in Markdown. Do not copy a server, shell, CSS, or build script into a project. One project workspace has Progress and Feedback tabs; optional short tabs contain supporting detail. External review tabs are read-only; native Details permits anchored reviewer comments into the same Feedback store. Feedback is the primary decision surface; never duplicate cards, decision indexes, or status tables in document tabs. External worksheets are links, not additional progress pages.

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

Modules: `links` items `{label,url,description?}`; `progress` items `{label,status,detail?,url?,failed_count?}`; `notes` items `{text}`. Status: `todo`, `in_progress`, `done`, `blocked`. Stable module IDs preserve disclosure choices. Omitting the project fence preserves saved data. Annotation tabs use the same Funnel origin. External resources use links modules. Read-only tabs use unique `{id,label,url}`; native Copy uses `{id:"copy",label:"Copy",kind:"copy"}` and primary supporting detail uses `{id:"details",label:"Details",kind:"document"}`, both without URLs; `progress`, `feedback`, and `rounds` are reserved. Use HTTP(S) URLs without credentials. Link IDs directly to their real tickets; never guess a ticket URL.

New feedback uses one `cards` JSON array. Keep positive stable `number` values and `anchor_id: d:qN`; do not repeat numbers in prompts. Evidence can reference generated anchors: `s:scope`, `s:scope:p1`, `tbl:columns:row:status`. Existing replies survive version changes.

Ordinary progress requires no plan metadata. When a full-plan review is requested, use `full_plan: true`, `other_files_required: none` (or the file list), and one `cards` source section (the shell presents these directly in Feedback) with ascending numbers and evidence. Later full-plan versions retain the current plan; unchanged sections fold automatically.

Custom diagrams may supply HTML content with stable `data-anchor-id` attributes. Preserve the template canvas sentinels and use `publish-version` to activate later versions. Never overwrite owner metadata or reviewer state.

Publish verifies the rendered page and prints the URL. An Access login means the external check is unverified; it is not a reason to rebuild or repeatedly probe. Diagnose the named failing hop once. Do not infer rendering from HTTP 200.

## Formatted copy

Use `copy PROJECT/SLUG --from copy.json`; add the native Copy tab. Show each current block once, with an editable proposal and collapsed immutable history. Do not replace current copy merely because a reviewer proposes a change. Read `copy PROJECT/SLUG --block ID` after a copy delivery to inspect that proposal.

```json
{"schema_version":1,"blocks":[{"id":"hero","title":"Homepage hero","current":"r1","revisions":[{"id":"r1","created_at":"2026-10-02T00:00:00+00:00","author":{"id":"agent:builder","name":"Builder"},"status":"draft","delta":{"ops":[{"insert":"Current headline\n"}]}}]}]}
```

Copy uses Quill Delta text with bold, italic, underline, strike, code, links, headings, lists and blockquotes. It accepts no embedded images, scripts or arbitrary HTML. Keep IDs and old revisions; append new revisions and move `current` only when implementing an actual approved change. Preserve undecided alternatives as draft history; never invent product claims.

Linear links: include `"issue_links":{"CHA-182":"https://linear.app/workspace/issue/CHA-182/actual-slug"}` in project data using URLs returned by the orchestrator's Linear connector. Referenced IDs become links across the workspace. Unknown IDs stay plain text; do not guess URLs. Ordinary progress writes preserve saved links when the field is omitted.

Rounds opens past published documents and submitted review answers read-only. Finish review preserves the submitted choices and explanations with their document version; later corrections do not rewrite that snapshot. Copy or migrate `rounds.ndjson` alongside comments and versions.
