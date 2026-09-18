---
name: annotate
description: Publish an interactive HTML review page the user annotates in the browser — click-to-comment on any element, pinned decision cards answered in one click, and a submitted round of verdicts read back into this thread. Use for a reviewable or comment-able artifact (diagram, schema, mockup, table, doc, PRD), an "annotatable html", or a design the user will redline over rounds.
---

# Agent Annotate for Codex (v2.19)

Codex runs the same `annotate` CLI and the same page server as Claude Code.
The only difference is how feedback reaches you: there is no hook that
prepends a notice to your next prompt and no working push into a Codex
session, so you read the bus yourself with `annotate inbox`.

## 1. Invocation

```bash
annotate <cmd>                       # the agent-annotate entry point
python -m agent_annotate.cli <cmd>   # always works once the package imports
```

Run `annotate doctor` first. Use the `python -m` form whenever `command -v
annotate` is not this package.

## 2. The round, end to end

1. Build `<slug-dir>/versions/v1.html` from the packaged `template.html`
   placeholders — `references/building-pages.md`. Every commentable element
   carries a stable `data-anchor-id`.
2. `annotate publish <slug-dir>` — serves it, claims ownership for this thread
   (`CODEX_THREAD_ID`), prints a URL only once the page is proven to render.
3. `annotate ask <slug> --from cards.json` — pose the whole round in one call.
4. Stop and hand the URL over. Tell the user you will read the review when
   they say the round is done.
5. `annotate inbox <slug> --unread` for everything new,
   `annotate cards <slug>` for verdicts only.
6. Act, then `annotate addressed <slug> <id> --response "…"`.
7. Next round: write `versions/v2.html`, then
   `annotate publish-version <slug-dir> v2 --label "round 2"`.

## 3. Commands

| Command | Effect |
|---|---|
| `doctor` | invocation, roots, hook registration, `node`/`lsof`/`codex`, session id |
| `publish <slug-dir>` | start server, register route, claim owner, verify |
| `unpublish <slug>` | tear down route and stop the server |
| `status [<slug>]` | list running slugs and their health |
| `claim <slug>` | make this thread the owner (handoff, or a pre-ownership page) |
| `ask <slug> --from cards.json [--version vN]` | create or refresh a whole round of cards |
| `cards <slug>` (`open-cards`) | list cards, verdicts, undecided anchors |
| `inbox <slug> [--unread] [--json] [--all-events]` | this thread's unread bus events, compact |
| `watch <slug>` | tail the bus to stdout |
| `monitor <slug> [--owner ID] [--takeover]` | exclusive lease + actionable-event stream |
| `sessions [--cwd DIR]` | list Codex threads that can own a page |
| `connect <slug> --thread <id>` · `disconnect <slug>` | a detached monitor that relays each round into a Codex thread via app-server; see §7 |
| `publish-version <slug-dir> <vN> [--label …]` | swap `current.html`, register history once |
| `addressed <slug> <id> [--response …]` | mark a comment addressed_by_agent |
| `archive-comment <slug> <id>` | archive a comment |
| `migrate <legacy.html>` | one-shot v1 → v2 conversion |
| `eval [--since YYYY-MM-DD]` | read-only baseline of the whole review loop |
| `prune-bus [--days N] [--apply]` | archive quiet buses with their cursors |

Every slug argument takes `<slug>` or `<project>/<slug>`; `--project` is
honoured wherever a slug is.

## 4. Anchor ids

```
<scope>:<key>[:<sub-key>][:<row-or-id>]      on every commentable element
tbl:items · tbl:items:row:42 · tbl:items:col:status
dgm:schema:domain-x · dgm:schema:node:premiums
s:intro · s:intro:p2 · kpi:net-equity · chart:funnel:bar:tier-a
Shift+click promotes the target to its ANCHOR_REGISTRY `parent`.
Anchors absent from the registry surface as "Comments without anchor".
```

## 5. Decision cards

```json
[{"anchor_id": "tbl:items:col:status",
  "text": "Rename status → lifecycle_state?",
  "decision_request": {
    "prompt": "Rename status → lifecycle_state?",
    "context": "Three services read this column, so the rename needs a dual-write window before v3 ships.",
    "recommendation": "accept",
    "options": [{"id": "accept", "label": "Rename", "consequence": "One week of dual writes.", "style": "primary"},
                {"id": "reject", "label": "Keep status", "consequence": "The name stays ambiguous in v3.", "style": "default"}],
    "evidence": [{"label": "current column", "anchor": "tbl:items:col:status"}],
    "impact": "medium", "blocking": true}}]
```

Every card states the context, a recommendation, and what each option costs.
Cards that recommend are answered 74% of the time; cards that only ask, 34%.
Full schema, rendering and round mode: `references/decision-cards.md`.

## 6. Comment lifecycle

`open` (blue pin) → `addressed_by_agent` (purple) → `user_confirmed` (green) →
`archived` (hidden). You may only move a comment to `addressed_by_agent`;
confirming and archiving belong to the reviewer, never to you.

## 7. Getting feedback back

**Read the inbox when the user says the round is done.** `annotate inbox
<slug> --unread` keeps a cursor per thread and prints one compact line per
event plus a decisions/undecided summary; `annotate cards <slug>` lists
verdicts with no side effects. Do not poll the bus in a loop.

**No push reaches a Codex prompt.** The `connect`/`monitor --provider
codex-app-server` path sends each submitted round into a Codex thread through
the local app-server as a new turn. It works only for a thread that is idle
and is not a way to interrupt the session that published the page; treat it
as an experiment, not as the delivery path. Everything the reviewer does is on
the bus and in `comments.json` whether or not anything is listening.

**Never act on a partial round.** Wait for `round_submitted` on the bus (the
inbox shows it) or for every card to carry a verdict.

## 8. Verification

`publish` asserts rendered anchors at the `origin`, `tailscale` and `public`
hops. A status code proves nothing behind Cloudflare Access: a healthy route
and a dead one both answer 302 to the login page. `UNVERIFIED … (Access login)`
means live but unproven from here — open the URL in an authenticated browser
to confirm. Never curl a page. Never call one live off a 200.

## 9. References

The references are shared with the Claude skill and live in the repository at
`src/agent_annotate/skills/claude/references/`: `building-pages.md`,
`decision-cards.md`, `cli-reference.md`, `architecture.md`,
`telemetry-and-eval.md`, `interaction-contract.md`
(https://github.com/changl/agent-annotate/tree/main/src/agent_annotate/skills/claude/references).
