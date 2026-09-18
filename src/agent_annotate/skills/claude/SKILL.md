---
name: annotate
description: Publish an interactive HTML review page the user annotates in the browser — click-to-comment on any element, pinned decision cards answered in one click, and a submitted round of verdicts read back into this session. Use for a reviewable or comment-able artifact (diagram, schema, mockup, table, doc, PRD), an "annotatable html", a design they will redline over rounds, or /annotate.
---

# annotate v2.19

## 1. Invocation

```bash
annotate <cmd>                       # agent-annotate entry point
python -m agent_annotate.cli <cmd>   # always works once the package imports
```

`annotate doctor` says which form this machine has; use `python -m` whenever
`command -v annotate` is not this package (the name is also libgd's image
tool). `publish` writes a `~/.local/bin/annotate` shim if no entry point exists.

## 2. The round, end to end

1. Build `<slug-dir>/versions/v1.html` from the packaged `template.html`
   placeholders — `references/building-pages.md`.
2. `annotate publish <slug-dir>` — serves it, claims ownership for this
   session, prints a URL only once the page is proven to render.
3. `annotate ask <slug> --from cards.json` — pose the whole round in one call.
4. Stop and hand the URL over. Wait for the hook notice (§7).
5. `annotate inbox <slug> --unread` for everything new, `annotate cards <slug>`
   for verdicts only.
6. Act, then `annotate addressed <slug> <id> --response "…"`.
7. Next round: write `versions/v2.html`, then
   `annotate publish-version <slug-dir> v2 --label "round 2"`.

## 3. Commands

| Command | Effect |
|---|---|
| `doctor` | invocation, roots, hook registration, tools, session id |
| `publish <slug-dir>` | serve, route, claim owner, verify, install shim + hook |
| `unpublish <slug>` | tear down route and stop the server |
| `status [<slug>]` | list running slugs and their health |
| `claim <slug>` | make this session the owner (handoff, or an unowned page) |
| `install-shim [--force]` | (re)write `~/.local/bin/annotate` |
| `ask <slug> --from cards.json [--version vN]` | create or refresh a round of cards |
| `cards <slug>` (`open-cards`) | list cards, verdicts, undecided anchors |
| `inbox <slug> [--unread] [--json] [--all-events]` | this session's new bus events |
| `watch <slug>` | tail the bus to stdout |
| `monitor <slug> [--owner ID] [--takeover]` | exclusive lease + actionable-event stream |
| `publish-version <slug-dir> <vN> [--label …]` | swap `current.html`, log history |
| `addressed <slug> <id> [--response …]` | mark a comment addressed_by_agent |
| `archive-comment <slug> <id>` | archive a comment |
| `migrate <legacy.html>` | one-shot v1 → v2 conversion |
| `eval [--since YYYY-MM-DD]` | read-only baseline of the whole review loop |
| `prune-bus [--days N] [--apply]` | archive quiet buses with their cursors |
| `sessions` · `connect` · `disconnect` · `send` | Codex thread delivery |

Every slug argument takes `<slug>` or `<project>/<slug>`; `--project` works too.

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
    "consequences": {"accept": "One week of dual writes.",
                     "reject": "The name stays ambiguous in v3."},
    "evidence": [{"label": "current column", "anchor": "tbl:items:col:status"}],
    "impact": "medium"}}]
```

Every card states its context, a recommendation, and what each option costs:
cards that recommend are answered 74% of the time, cards that only ask 34%.
Full schema, rendering and round mode: `references/decision-cards.md`.

## 6. Comment lifecycle

`open` (blue pin) → `addressed_by_agent` (purple) → `user_confirmed` (green) →
`archived` (hidden). You may only set `addressed_by_agent`; confirming and
archiving belong to the reviewer, never to you.

## 7. Getting feedback back — one policy

**Attended is the default.** The `UserPromptSubmit` hook reports on the next
user turn and costs nothing while quiet:

```
[annotate] <project>/<slug>: N reviewer event(s) since your last read — verdicts: …; undecided: N of M cards. Read: annotate inbox <slug> --unread
```

It speaks only to the owning session, counts reviewer events only, and never
advances the `inbox --unread` cursor.

**Unattended only:** with no user turn coming, run `annotate monitor <slug>`
inside Claude Code's Monitor tool, `timeout_ms: 1800000`, re-armed on expiry.
Heartbeats are off (the idle-reap that needed them is gone). One lease per
slug, `--takeover` only for an explicit handoff. Never arm a monitor for a page
a human is reviewing while you still have turns.

**Never act on a partial round.** Wait for `ROUND SUBMITTED` in the notice (bus
event `round_submitted`), or for every card to carry a verdict.

## 8. Verification

`publish` asserts rendered anchors at the `origin`, `tailscale` and `public`
hops. Behind Cloudflare Access a status code proves nothing: a healthy route
and a dead one both answer 302. `UNVERIFIED … (Access login)` means live but
unproven from here — check it with `orca tab create --url <url> --json` plus
`orca eval` on the authenticated profile. Never curl a page, never call one
live off a 200.

## 9. References

`references/building-pages.md` · `references/decision-cards.md` ·
`references/cli-reference.md` · `references/architecture.md` ·
`references/telemetry-and-eval.md` · `references/interaction-contract.md` ·
release history in the repo's `CHANGELOG.md` (`annotate doctor` prints the path).
