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
   Every version after v1 is the complete cumulative plan, never a delta.
2. Stop and hand the URL over. Chat says only what changed, what Chang must
   answer, and the URL; never repeat page substance as a chat wall of text.
   Wait for the hook notice (§7).
3. `annotate inbox <slug> --unread` for everything new, `annotate cards <slug>`
   for verdicts only.
4. Act. Use `addressed` only while reviewer confirmation is still needed;
   it cannot demote an already confirmed card.
5. Before a new version, disposition every earlier `open` or
   `addressed_by_agent` item: `resolve` it with the exact version + anchor
   where the answer landed, or `carry` it onto a new-version anchor.
6. Next round: the same `new` line with `--version v2 --label "round 2"`.
   Publication fails closed while any earlier item lacks that disposition.

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
| `resolve <slug> <id> --in-version <vN> --anchor <id> [--response …]` | record where an earlier item was applied; hide it from later rounds |
| `carry <slug> <id> --to-version <vN> --anchor <id>` | move an unresolved earlier item onto a real anchor in the new round |
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
[{"number": 14, "anchor_id": "d:q14",
  "decision_request": {"prompt": "Rename status → lifecycle_state?",
    "context": "Three services read it; the rename needs a dual-write week before v3.",
    "recommendation": "accept",
    "options": [{"id": "accept", "label": "Rename", "consequence": "One dual-write week."},
                {"id": "reject", "label": "Keep status", "consequence": "Ambiguous through v3."}],
    "evidence": [{"label": "status column", "anchor": "tbl:items:col:status"}],
    "impact": "medium", "blocking": true}}]
```

Every card states the context, a recommendation, and what each option costs.
Cards that recommend are answered 74% of the time; cards that only ask, 34%.
`text` defaults to `prompt`. Every verdict answers a card: `accept` closes it;
`reject`, `changes`, `select`, and free-text `comment` leave it waiting on the
agent. The UI calls `comment` **Answer in words**; a reviewer's reply on an
unanswered card is stored as one (`decision.via: "reply"`). Always read `decision.text`, not just the verdict. Option
`style`, `evidence`, full schema and round mode:
`references/decision-cards.md`.

For v2+ sources, front matter must say `full_plan: true` and
`other_files_required: none` (or name the required files). Put every response
item in one final `## Questions for Chang` section. Each card needs a stable,
unique, ascending positive integer `number`, anchor `d:q<number>`, a prompt
without another Q/# label, and `decision_request.evidence` links back into the
plan. Rail, body card, and pin all use `#<number>` in that order. Page text
refers to items the same way, as `#19`, never `Q19` or `d:q19`, and never
restates an item's status: the page shows live status on each card.

A serving page marked `(gone)` in `status` is notifying nobody — `claim` it
first. `close` and `retire` never delete: they archive and set aside.

## 6. Comment lifecycle

`open` (blue) → `addressed_by_agent` (purple) → `user_confirmed` (green) →
`archived` (hidden). Cross-version resolution is
`open|addressed_by_agent` → `resolved_in_version` with a required version and
anchor pointer; it is hidden on later versions, remains visible as history on
its origin version, and a reviewer reply reopens it. `carry` preserves origin
provenance but moves the live card to the new version/anchor. You may not
confirm or archive for the reviewer.

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
