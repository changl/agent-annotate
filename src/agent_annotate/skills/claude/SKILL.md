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

`annotate doctor` says which form this machine has — the name is also libgd's
image tool. `publish` writes a `~/.local/bin/annotate` shim if none exists.

## 2. The round, end to end

1. `annotate new <slug-dir> --from page.md --publish --ask` — markdown (front
   matter, `##` sections, tables, `kpi:` lines, a ` ```cards ` block) becomes
   an anchored page plus `cards.json`, published and posed in one call.
   `annotate new --example` prints a worked document; hand-build from
   `template.html` only for what markdown cannot express
   (`references/building-pages.md`). `publish` prints a URL only once the page
   is proven to render, and claims the page for this session.
2. Stop and hand the URL over. Wait for the hook notice (§7).
3. `annotate inbox <slug> --unread` for everything new, `annotate cards <slug>`
   for verdicts only.
4. Act, then `annotate addressed <slug> <id> --response "…"`.
5. Next round: the same `new` line with `--version v2 --label "round 2"`.

## 3. Commands

| Command | Effect |
|---|---|
| `doctor` | invocation, roots, hook, `node`/`lsof`, session id |
| `new <slug-dir> --from page.md [--version vN] [--publish] [--ask]` | markdown → `versions/vN.html` + `cards.json`; `--example` prints one |
| `publish <slug-dir>` | serve, route, claim owner, verify, install shim + hook |
| `unpublish <slug>` | tear down the route, stop the server |
| `status [<slug>] [--retired]` | running slugs, health, owner; `(gone)` = owner session dead |
| `claim <slug>` | make this session the owner |
| `ask <slug> --from cards.json [--version vN]` | create or refresh a whole round |
| `cards <slug>` | cards, verdicts, undecided anchors |
| `inbox <slug> [--unread] [--json]` | this session's unread bus events |
| `monitor <slug> [--owner ID] [--takeover]` | exclusive lease + event stream |
| `publish-version <slug-dir> <vN> [--label …]` | swap `current.html`, register history |
| `addressed <slug> <id> [--response …]` | mark a comment addressed_by_agent |
| `close <slug> [--older-than 30d] [--dry-run]` | archive cards nobody answered |
| `retire <slug>\|--dead [--dry-run]` | move dead registry rows to `state/retired/` |

Also `eval`, `watch`, `install-shim`, `archive-comment`, `migrate`,
`prune-bus`, `sessions`/`connect`/`disconnect`/`send` —
`references/cli-reference.md`. Every slug argument takes `<slug>` or
`<project>/<slug>`.

## 4. Anchor ids

`<scope>:<key>[:<sub-key>][:<row-or-id>]` on every commentable element:
`s:intro` · `s:intro:p2` · `d:1` · `kpi:net-equity` · `tbl:items` ·
`tbl:items:row:42` · `tbl:items:col:status` · `dgm:schema:node:premiums`.
Shift+click promotes the target to its `ANCHOR_REGISTRY` parent; unregistered
anchors surface as "Comments without anchor".

## 5. Decision cards

`cards.json` and a page's ` ```cards ` block share one array:

```json
[{"anchor_id": "tbl:items:col:status",
  "decision_request": {"prompt": "Rename status → lifecycle_state?",
    "context": "Three services read it; the rename needs a dual-write week before v3.",
    "recommendation": "accept",
    "options": [{"id": "accept", "label": "Rename", "consequence": "One dual-write week."},
                {"id": "reject", "label": "Keep status", "consequence": "Ambiguous through v3."}],
    "impact": "medium", "blocking": true}}]
```

Every card states the context, a recommendation, and what each option costs.
Cards that recommend are answered 74% of the time; cards that only ask, 34%.
`text` defaults to `prompt`. Verdicts are `accept`, `reject` and `changes`
("Request changes", the default third option): `accept` closes the card, the
other two leave it open, and `changes` requires a note — read `decision.text`,
not just the verdict. Option `style`, `evidence`, full schema and round mode:
`references/decision-cards.md`.

A serving page marked `(gone)` in `status` is notifying nobody — `claim` it
first. `close` and `retire` never delete: they archive and set aside.

## 6. Comment lifecycle

`open` (blue) → `addressed_by_agent` (purple) → `user_confirmed` (green) →
`archived` (hidden). You may only set `addressed_by_agent`; confirming and
archiving are the reviewer's.

## 7. Getting feedback back — one policy

**Attended is the default.** The `UserPromptSubmit` hook reports on the next
user turn and costs nothing while quiet:

```
[annotate] <project>/<slug>: N reviewer event(s) since your last read — verdicts: …; undecided: N of M cards. Read: annotate inbox <slug> --unread
```

It speaks only to the owning session, counts reviewer events only, and never
advances the `inbox --unread` cursor.

**Unattended only:** with no user turn coming, run `annotate monitor <slug>`
in Claude Code's Monitor tool, `timeout_ms: 1800000`, re-armed on expiry.
Heartbeats are off. One lease per slug; `--takeover` only for a handoff. Never
arm one for a page a human is reviewing while you still have turns.

**Never act on a partial round.** Wait for `ROUND SUBMITTED` in the notice (bus
event `round_submitted`), or for every card to carry a verdict.

## 8. Verification

`publish` asserts rendered anchors at the `origin`, `tailscale` and `public`
hops. Behind Cloudflare Access a status code proves nothing: healthy and dead
routes both answer 302. `UNVERIFIED … (Access login)` means live but unproven
from here — check it with `orca tab create --url <url> --json` plus `orca
eval` on the authenticated profile. Never curl a page; never call one live off
a 200.

## 9. References

`references/building-pages.md` (markdown format, §1) ·
`references/decision-cards.md` ·
`references/cli-reference.md` · `references/architecture.md` ·
`references/telemetry-and-eval.md` · `references/interaction-contract.md` ·
release history in the repo's `CHANGELOG.md` (`annotate doctor` prints the path).
