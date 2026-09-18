---
name: annotate
description: Publish an interactive HTML review page the user annotates in the browser — click-to-comment on any element, pinned decision cards answered in one click, and a submitted round of verdicts read back into this session. Use for a reviewable or comment-able artifact (diagram, schema, mockup, table, doc, PRD), an "annotatable html", a design they will redline over rounds, or /annotate.
---

# annotate v2.19

## 1. Invocation

```bash
annotate <cmd>                    # the agent-annotate entry point (uv tool install / pip)
python -m agent_annotate.cli <cmd>   # always works once the package imports
```

`annotate doctor` says which form this machine has. Use the `python -m` form
whenever `command -v annotate` is not this package — on some machines the
name is libgd's image tool. `publish` and `install-shim` write a
`~/.local/bin/annotate` shim when no entry point is there yet.

## 2. The round, end to end

1. Build `<slug-dir>/versions/v1.html` from the packaged `template.html`
   placeholders — `references/building-pages.md`.
2. `annotate publish <slug-dir>` — serves it, claims ownership for this
   session, prints a URL only once the page is proven to render.
3. `annotate ask <slug> --from cards.json` — pose the whole round in one call.
4. Stop and hand the URL over. Wait for the hook notice (§7).
5. `annotate inbox <slug> --unread` for everything new,
   `annotate cards <slug>` for verdicts only.
6. Act, then `annotate addressed <slug> <id> --response "…"`.
7. Next round: write `versions/v2.html`, then
   `annotate publish-version <slug-dir> v2 --label "round 2"`.

## 3. Commands

| Command | Effect |
|---|---|
| `doctor` | invocation, roots, hook registration, `node`/`lsof`/`codex`, session id |
| `publish <slug-dir>` | start server, register route, claim owner, verify, install shim + hook |
| `unpublish <slug>` | tear down route and stop the server |
| `status [<slug>] [--retired]` | list running slugs, their health and their owners |
| `claim <slug>` | make this session the owner (handoff, or a pre-ownership page) |
| `close <slug> [--older-than 30d] [--dry-run]` | archive decision cards nobody ever answered |
| `retire <slug>\|--dead [--dry-run]` | move dead registry rows to `state/retired/` |
| `install-shim [--force]` | (re)write `~/.local/bin/annotate` |
| `ask <slug> --from cards.json [--version vN]` | create or refresh a whole round of cards |
| `cards <slug>` (`open-cards`) | list cards, verdicts, undecided anchors |
| `inbox <slug> [--unread] [--json] [--all-events]` | this session's unread bus events, compact |
| `watch <slug>` | tail the bus to stdout |
| `monitor <slug> [--owner ID] [--takeover]` | exclusive lease + actionable-event stream |
| `publish-version <slug-dir> <vN> [--label …]` | swap `current.html`, register history once |
| `addressed <slug> <id> [--response …]` | mark a comment addressed_by_agent |
| `archive-comment <slug> <id>` | archive a comment |
| `migrate <legacy.html>` | one-shot v1 → v2 conversion |
| `eval [--since YYYY-MM-DD]` | read-only baseline of the whole review loop |
| `prune-bus [--days N] [--apply]` | archive quiet buses with their cursors |
| `sessions` · `connect` · `disconnect` · `send` | Codex thread delivery (`references/cli-reference.md` §10) |

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

The three verdicts are `accept`, `reject` and `changes` ("Request changes"),
which is the default option list when a card names none. `accept` closes the
card; `reject` and `changes` leave it open. `changes` requires a note, and
that note is the instruction — read `decision.text`, not just the verdict.
Full schema, rendering and round mode: `references/decision-cards.md`.

## 5a. Closing stale work

`status` marks a serving page whose owning session is gone with `(gone)`: the
hook is notifying nobody, so `claim` it before answering anything on it.

`close <slug> --older-than 30d` archives the cards on a page that nobody ever
answered — never a decided card, never a plain reviewer comment — and appends
one `page_closed` event. `retire --dead` moves registry rows whose server is
gone to `state/retired/`, keeping every field. Run both with `--dry-run`
first; neither deletes anything.

## 6. Comment lifecycle

`open` (blue pin) → `addressed_by_agent` (purple) → `user_confirmed` (green) →
`archived` (hidden). You may only move a comment to `addressed_by_agent`;
confirming and archiving belong to the reviewer, never to you.

## 7. Getting feedback back — one policy

**Attended is the default.** The `UserPromptSubmit` hook reports on the next
user turn and costs nothing while quiet:

```
[annotate] <project>/<slug>: N reviewer event(s) since your last read — verdicts: …; undecided: N of M cards. Read: annotate inbox <slug> --unread
```

It speaks only to the session that published or claimed the slug, counts only
reviewer events, and never advances the `inbox --unread` cursor.

**Unattended only:** when no user turn is coming, run `annotate monitor <slug>`
inside Claude Code's Monitor tool with `timeout_ms: 1800000`, re-armed when it
expires. Heartbeats are off by default: the July idle-reap no longer occurs, so
they were pure turn noise. One lease per slug, `--takeover` only for an explicit
handoff. Do not arm a monitor for a page a human is reviewing while you still
have turns.

**Never act on a partial round.** Wait for `ROUND SUBMITTED` in the notice (bus
event `round_submitted`), or for every card to carry a verdict.

## 8. Verification

`publish` asserts rendered anchors at the `origin`, `tailscale` and `public`
hops. A status code proves nothing behind Cloudflare Access: a healthy route
and a dead one both answer 302 to the login page. `UNVERIFIED … (Access login)`
means live but unproven from here — open it with `orca tab create --url <url>
--json` plus `orca eval` in the authenticated default profile. Never curl a
page. Never call one live off a 200.

## 9. References

`references/building-pages.md` · `references/decision-cards.md` ·
`references/cli-reference.md` · `references/architecture.md` ·
`references/telemetry-and-eval.md` · `references/interaction-contract.md` ·
`CHANGELOG.md`
