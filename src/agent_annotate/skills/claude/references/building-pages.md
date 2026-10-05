# Page format

Use built-in Markdown. One page per project holds Review, Library, Findings, and Plans. Post new work into the appropriate category on the existing page; do not create pages for tasks, reports, rounds, or handoffs. A second page requires `--exception "REASON"`, explicitly requested by the orchestrator. The registry records its reason and parent; the main page lists it under Linked pages. `--standalone` is a compatibility alias with reason `standalone`.

Do not copy a server, shell, CSS, or build script into a project. Keep status concise and supporting resources in Documents. History holds past published documents and submitted rounds. Categories with no data may be absent; legacy pages with no category data keep Review and declared tabs.

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

Modules: `links` items `{label,url,description?}`; `progress` items `{label,status,detail?,url?,failed_count?}`; `notes` items `{text}`. Status: `todo`, `in_progress`, `done`, `blocked`. Stable module IDs preserve disclosure choices. Omitting the project fence preserves saved data. Annotation resources use the same Funnel origin. External resources use links modules. Existing `{id,label,url}` tabs and native `copy`/`document` tabs remain compatible. Library, Findings, and Plans are discovered from their stored data. Use HTTP(S) URLs without credentials. Link IDs directly to their real tickets; never guess a ticket URL.

New feedback uses one `cards` JSON array. Keep positive stable `number` values and `anchor_id: d:qN`; do not repeat numbers in prompts. Evidence can reference generated anchors: `s:scope`, `s:scope:p1`, `tbl:columns:row:status`. Existing replies survive version changes.

Ordinary progress requires no plan metadata. When a full-plan review is requested, use `full_plan: true`, `other_files_required: none` (or the file list), and one `cards` source section (the shell presents these in Review) with ascending numbers and evidence. Later full-plan versions retain the current plan; unchanged sections fold automatically.

Custom diagrams may supply HTML content with stable `data-anchor-id` attributes. Preserve the template canvas sentinels and use `publish-version` to activate later versions. Never overwrite owner metadata or reviewer state.

Publish verifies the rendered page and prints the URL. An Access login means the external check is unverified; it is not a reason to rebuild or repeatedly probe. Diagnose the named failing hop once. Do not infer rendering from HTTP 200.

## Library

Use `library PROJECT/SLUG --from copy.json --json` (`copy` is an alias). Show each current block once, with an editable proposal and collapsed immutable history. Do not replace current copy merely because a reviewer proposes a change. Read `copy PROJECT/SLUG --block ID` after a copy delivery to inspect that proposal.

```json
{"schema_version":1,"blocks":[{"id":"hero","title":"Homepage hero","current":"r1","revisions":[{"id":"r1","created_at":"2026-10-02T00:00:00+00:00","author":{"id":"agent:builder","name":"Builder"},"status":"draft","delta":{"ops":[{"insert":"Current headline\n"}]}}]}]}
```

Copy uses Quill Delta text with bold, italic, underline, strike, code, links, headings, lists and blockquotes. It accepts no embedded images, scripts or arbitrary HTML. Keep IDs and old revisions; append new revisions and move `current` only when implementing an actual approved change. Preserve undecided alternatives as draft history; never invent product claims.

Linear links: include `"issue_links":{"CHA-182":"https://linear.app/workspace/issue/CHA-182/actual-slug"}` in project data using URLs returned by the orchestrator's Linear connector. Referenced IDs become links across the workspace. Unknown IDs stay plain text; do not guess URLs. Ordinary progress writes preserve saved links when the field is omitted.

History opens past published documents and submitted review answers read-only. Send preserves the submitted choices and explanations with their document version; later corrections do not rewrite that snapshot. Copy or migrate `rounds.ndjson` alongside comments and versions.

Library blocks accept optional `group`, `where`, `number`, `status` (`needs_you`, `ready`, `waiting`, `done`, `held`), `alternatives: [{label, delta}]`, `question_comment_id`, and `held_note`. Top-level `groups: [{id, label}]` preserves group order. Revisions are immutable; browser edits are proposed and round-pending until the shared Send.

## Findings and Plans

Post finding cards with `ask PROJECT/SLUG --from cards.json --category findings --set design`. Each can carry `finding: {set, title}`, or `category` and `set`; decisions use the usual options such as fix/keep. Mark fixed only with proof: `finding PROJECT/SLUG --fixed 11 --proof evidence.png --note "Checked the actual result"`. Chang can reopen a finding with an explanation; its previous fix remains in history.

Use `plan PROJECT/SLUG rollout --from plan.md --title "Rollout plan" --label "Rehearsed" --json`. Markdown uses the same renderer and anchors as `new`; HTML is also accepted. Plans have independent revisions under `plans/rollout/versions/vN.html`, with metadata in `plans/rollout/meta.json`. Inline comments use `category: plans`, `doc: plan:rollout`, and the plan version. Plan IDs use lowercase letters/digits/hyphens, start with a letter/digit, and are at most 64 characters.
