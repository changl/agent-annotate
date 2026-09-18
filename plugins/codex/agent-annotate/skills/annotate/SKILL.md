---
name: annotate
description: Publish an interactive HTML review page the user annotates in the browser — click-to-comment on any element, pinned decision cards answered in one click, and a submitted round of verdicts read back into this thread. Use for a reviewable or comment-able artifact (diagram, schema, mockup, table, doc, PRD), an "annotatable html", or a design the user will redline over rounds.
---

# Agent Annotate for Codex (v2.19)

Codex runs the same `annotate` CLI and page server as Claude Code. The only
difference is how feedback reaches you: no hook prepends a notice to your next
prompt and no push reaches a Codex session, so you read the bus yourself with
`annotate inbox`.

## 1. Invocation

```bash
annotate <cmd>                       # the agent-annotate entry point
python -m agent_annotate.cli <cmd>   # always works once the package imports
```

Run `annotate doctor` first. Use the `python -m` form whenever `command -v
annotate` is not this package.

## 2. The round, end to end

1. Write the page as markdown; `annotate new <slug-dir> --from page.md` turns
   front matter, `##` sections, tables, `kpi:` lines and a ` ```cards ` block
   into anchored HTML plus `cards.json`. `annotate new --example` prints a
   worked document; hand-build from `template.html` only for what markdown
   cannot express — `references/building-pages.md`.
2. `annotate publish <slug-dir>` — serves it, claims ownership for this thread
   (`CODEX_THREAD_ID`), prints a URL only once the page is proven to render.
3. `annotate ask <slug> --from cards.json` — the whole round in one call.
   Steps 1-3 collapse into `annotate new … --publish --ask`.
4. Stop and hand the URL over. Say you will read the review when they tell
   you the round is done.
5. `annotate inbox <slug> --unread` for everything new,
   `annotate cards <slug>` for verdicts only.
6. Act, then `annotate addressed <slug> <id> --response "…"`.
7. Next round: `annotate new <slug-dir> --from page.md --version v2
   --label "round 2" --publish` (or `publish-version` for a hand-built page).

## 3. Commands

| Command | Effect |
|---|---|
| `doctor` | invocation, roots, `node`/`lsof`/`codex`, thread id |
| `new <slug-dir> --from page.md [--version vN] [--publish] [--ask]` | markdown → `versions/vN.html` + `cards.json`; `--example` prints one |
| `publish <slug-dir>` | serve, route, claim owner, verify |
| `unpublish <slug>` | tear down the route, stop the server |
| `status [<slug>]` | running slugs and their health |
| `claim <slug>` | make this thread the owner |
| `ask <slug> --from cards.json [--version vN]` | create or refresh a whole round |
| `cards <slug>` | cards, verdicts, undecided anchors |
| `inbox <slug> [--unread] [--json]` | this thread's unread bus events |
| `monitor <slug> [--owner ID] [--takeover]` | exclusive lease + event stream |
| `sessions [--cwd DIR]` | Codex threads that can own a page |
| `connect <slug> --thread <id>` · `disconnect <slug>` | detached monitor relaying each round into a Codex thread; see §7 |
| `publish-version <slug-dir> <vN> [--label …]` | swap `current.html`, register history |
| `addressed <slug> <id> [--response …]` | mark a comment addressed_by_agent |

Also `eval` (baseline of the loop), `watch`, `archive-comment`, `migrate`,
`prune-bus` — `references/cli-reference.md`.

Every slug argument takes `<slug>` or `<project>/<slug>`; `--project` is
honoured wherever a slug is.

## 4. Anchor ids

```
<scope>:<key>[:<sub-key>][:<row-or-id>]   on every commentable element
s:intro · s:intro:p2 · d:1 · kpi:net-equity · tbl:items · tbl:items:row:42
tbl:items:col:status · dgm:schema:node:premiums · chart:funnel:bar:tier-a
Shift+click promotes the target to its ANCHOR_REGISTRY `parent`; anchors
absent from the registry surface as "Comments without anchor".
```

## 5. Decision cards

`cards.json` and a page's ` ```cards ` block take the same array:

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
`text` defaults to `prompt`. Option `style`, `evidence`, full schema and round
mode: `references/decision-cards.md`.

## 6. Comment lifecycle

`open` (blue) → `addressed_by_agent` (purple) → `user_confirmed` (green) →
`archived` (hidden). You may only set `addressed_by_agent`; confirming and
archiving belong to the reviewer, never to you.

## 7. Getting feedback back

**Read the inbox when the user says the round is done.** `annotate inbox
<slug> --unread` keeps a per-thread cursor and prints one line per event plus
a decisions/undecided summary; `annotate cards <slug>` lists verdicts with no
side effects. Never poll the bus in a loop.

**No push reaches a Codex prompt.** The `connect`/`monitor --provider
codex-app-server` path sends each submitted round into an idle Codex thread
through the local app-server as a new turn; it cannot interrupt the session
that published the page. Treat it as an experiment, not the delivery path.
Everything the reviewer does is on the bus and in `comments.json` whether or
not anything is listening.

**Never act on a partial round.** Wait for `round_submitted` on the bus (the
inbox shows it) or for every card to carry a verdict.

## 8. Verification

`publish` asserts rendered anchors at the `origin`, `tailscale` and `public`
hops. A status code proves nothing behind Cloudflare Access: a healthy route
and a dead one both answer 302 to the login page. `UNVERIFIED … (Access login)`
means live but unproven from here — open the URL in an authenticated browser.
Never curl a page; never call one live off a 200.

## 9. References

The references are shared with the Claude skill and live in the repository at
`src/agent_annotate/skills/claude/references/`: `building-pages.md` (markdown
page format, §1), `decision-cards.md`, `cli-reference.md`, `architecture.md`,
`telemetry-and-eval.md`, `interaction-contract.md`
(https://github.com/changl/agent-annotate/tree/main/src/agent_annotate/skills/claude/references).
