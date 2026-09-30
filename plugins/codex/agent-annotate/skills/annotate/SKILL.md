---
name: annotate
description: Publish shared project progress and interactive review pages with persistent links, collapsible modules, clickable decision cards, and completed-round delivery to the owning agent.
---

# annotate v2.20

## 1. Invocation

```bash
annotate <cmd>
python3 -m agent_annotate.cli <cmd>  # fallback if annotate names another tool
```

`annotate doctor` identifies installed build. Claude Code and Codex use the same runtime; skill copies contain no server code.

## 2. Publish and respond

1. Write one Markdown source, then run `annotate new <slug-dir> --from page.md --publish --ask`.
2. Share the verified `URL:` plus only what changed and what needs an answer. Review substance stays on the page.
3. Reviewer clicks a choice or **Answer in words**, then **Finish review**. Never ask them to type an option letter or number.
4. Read `annotate inbox <slug> --unread` and `annotate cards <slug>` after **ROUND SUBMITTED**. Read every `decision.text` and reply; partial answers stay pending.
5. Update persistent project information when progress, blockers, hosted URLs, or useful artifacts change. These updates do not require a new decision round.
6. Publish later rounds with `new ... --version vN --publish --ask`. Each is the complete cumulative plan. Mention an applied prior item as `#N` at its answer, or retain a same-numbered card to carry it forward. An omitted open item blocks publication.

`publish`/`claim` binds an Orca-managed owner terminal automatically. The server queues one durable prompt per submitted round, validates current owner/process/terminal before input, and retries unavailable delivery. No agent-owned monitor is required. Accepted input is not completed work; `inbox --unread` acknowledges receipt. Ambiguous sends remain visible and are not automatically repeated. A successor runs `annotate claim <slug>` from their own session; never claim other projects' pages. Outside Orca, hook notices remain attended-only; see `deliver <slug> --dry-run` for delivery state.

## 3. One controlled page format

Use built-in Markdown renderer for standard progress and review pages. Do not copy a server, stylesheet, or shell into the project. Runtime owns layout, controls, and shared `content.css`; custom diagrams remain content extensions.

Supported source: `---` front matter, headings, paragraphs, lists, pipe tables, code, `kpi: value | label | ok|warn|bad`, and the three data fences below. `annotate new --example` prints a complete review.

For v2+, front matter includes `full_plan: true` and `other_files_required: none` (or named requirements). Put decision cards in one final `## Questions for Chang` section. Stable positive `number`, anchor `d:q<number>`, ascending order; no Q/# prefixes in prompt. Evidence names real plan anchors such as `s:scope:p1` or `tbl:columns:row:status`.

```cards
[{"number":1,"anchor_id":"d:q1","decision_request":{"prompt":"Use the shared runtime?","context":"The prototype fork misses updates.","recommendation":"shared","options":[{"id":"shared","label":"Shared runtime","consequence":"One migration; later updates are shared."},{"id":"fork","label":"Keep fork","consequence":"Maintain updates separately."}],"evidence":[{"label":"Plan","anchor":"s:scope"}]}}]
```

Choices belong in `options`, not only in prose. Custom choices use `{id,label,consequence}`. `accept` confirms; `select`, `reject`, `changes`, and `comment` await agent action. Intentional text questions may offer `comment` alone. Never preselect an answer.

```project
{"title":"Project workspace","modules":[{"id":"resources","title":"Open project","kind":"links","items":[{"label":"CMS","url":"https://host.example/admin","description":"Current admin workspace"}]},{"id":"progress","title":"Progress","kind":"progress","items":[{"label":"CMS setup","status":"done"}]},{"id":"blockers","title":"Current blockers","kind":"notes","items":[{"text":"Waiting for published content."}]}]}
```

Project data persists in `project.json` across versions; omitting the fence preserves it. Stable module IDs retain collapse preferences. `annotate project <slug> --from project.json` updates it independently. Link URLs are HTTP/HTTPS; no credentials in URLs. Progress states: `todo`, `in_progress`, `done`, `blocked`.

```details
Supporting evidence
Paragraphs, lists, tables, and KPIs render behind this native disclosure.
```

## 4. Commands and history

`status` lists live pages/owners; `(gone)` means owner absent. `claim` transfers your page ownership. `addressed` requests reviewer confirmation; `resolve` records a real later-version anchor; `carry` preserves origin and moves an unresolved item. Never confirm or archive for the reviewer. Reviewer replies reopen resolved items.

`update --check` identifies stable release; `update --apply` stages a checksum-verified runtime, preserves owners/routes/state and custom edits, and rolls back failed restarts. `update --enable` opts this machine into daily stable checks via `revive --install`. Generated skills refresh through `sync-skills`; running agents must reload already-loaded instructions. GitHub push alone does not update a machine or a prototype fork.

`report <slug-dir> --publish` generates the short usage page without a model; `--install` schedules it weekly on macOS. `eval` and `cost` read local evidence without consuming inbox cursors.

`publish` verifies origin/tailnet rendering before printing a URL. `--public` adds an outside-tailnet route. Never curl a page or infer rendering from HTTP 200.

References: `references/building-pages.md`, `decision-cards.md`, `cli-reference.md`, `architecture.md`, `interaction-contract.md`, `telemetry-and-eval.md`.
