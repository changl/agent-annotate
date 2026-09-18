# Telemetry and eval

One NDJSON bus per slug at `<bus root>/<project>/<slug>.ndjson` (default
`~/.claude/annotate-bus`).
Every line carries `ts` and `slug`. Agent and CLI requests that send
`X-Annotate-Session: <id>` also get `session_id` spread into every event that
request emits; browser requests never carry one. Telemetry never raises: a
failed append cannot fail a publish.

## 1. Events

### Comment lifecycle (`sync_server.py`)

| Event | Emitted at | Fields beyond `ts`/`slug` |
|---|---|---|
| `comment_created` | `POST /api/comments`, and per item of `POST /api/comments/batch` | `comment_id`, `anchor_id`, `author`, `version`, `target`, `decision_requested` (when the comment carries a request), `batch` (batch route only), `session_id` |
| `comment_updated` | `PUT /api/comments/<id>` | `comment_id`, `anchor_id`, `old_status`, `new_status`, `author`, `repinned` + `target` on a re-anchor, `decision_requested` when a request was posed, `session_id` |
| `comment_updated` | `POST /api/comments/<id>/decision` | as above plus `decision` (the verdict), `latency_s`, `deferred: true` in round mode, and `revised: true` + `prior_verdict` on a re-decision |
| `comment_reply` | `POST /api/comments/<id>/reply` | `comment_id`, `anchor_id`, `author`, `auto_reopened` + `old_status`/`new_status` when a user reply reopened an addressed comment, `session_id` |
| `comment_archived` | `POST /api/comments/<id>/archive` | `comment_id`, `anchor_id`, `author`, `session_id` |
| `comment_accepted` | `POST /api/comments/<id>/accept` | `comment_id`, `anchor_id`, `author`, `session_id` |
| `comment_restored` | `POST /api/comments/<id>/restore` | `comment_id`, `anchor_id`, `author`, `session_id` |
| `bulk_overwrite` | legacy whole-store `POST /api/comments` | `author` |
| `seen_updated` | every page load (`PUT /api/seen`) | `author`, `version`. Bookkeeping — roughly one line in nine on a busy bus. |

### Decisions and rounds (v2.19, `sync_server.py`)

| Event | Emitted at | Fields |
|---|---|---|
| `decision_requested` | create, `PUT`, or batch item that sets a `decision_request` | `comment_id`, `anchor_id`, `prompt_len`, `has_context`, `options_n`, `by`, `session_id` |
| `comments_seeded` | once per `POST /api/comments/batch` | `comment_ids`, `created`, `updated`, `by`, `session_id` |
| `round_submitted` | `POST /api/rounds/submit` | `comment_ids`, `verdict_counts {accept, reject, changes, comment}`, `undecided_ids`, `note`, `by`, `session_id` |
| `round_discarded` | `POST /api/rounds/discard` | `comment_ids`, `by`, `session_id`. No push follows. |
| `session_push` | `POST /api/push-session`, `POST /api/comments/<id>/push`, an immediate (non-deferred) verdict, and exactly once per round submit | `delivery` (`active_monitor`\|`queued`), `monitor_count`, `monitor_owner`, `delivery_id`, `comment_count`, `comment_ids`, `author`, plus `anchor_id`/`decision` on a single push and `round: true` + `verdict_counts` + `undecided_ids` + `note` on a round |

### Publish, ownership and reads (v2.19, `cli.py`)

| Event | Emitted at | Fields |
|---|---|---|
| `page_published` | `_print_publish`, after the verify gate clears | `owner_session`, `owner_agent`, `version`, `url`, `transport`, `verified`, `verify_stages [{name, status}]`, `transport_error`, `publish_ms` |
| `page_publish_failed` | `_print_publish`, failure branch | `stage`, `detail`, `url`, `owner_session` |
| `version_published` | `cmd_publish_version` | `version`, `label`, `owner_session` |
| `page_claimed` | `cmd_claim` | `owner_session`, `owner_agent`, `previous_owner` |
| `page_closed` | `cmd_close`, once per run that archived something | `archived_ids`, `archived_count`, `remaining_open`, `by`, `session_id`, `older_than` |
| `inbox_read` | `cmd_inbox` with `--unread`, when the cursor moved | `session_id`, `offset_from`, `offset_to`, `event_count` |
| `monitor_armed` | `cmd_monitor`, after the lease is taken | `owner_session`, `owner_agent`, `pid` |
| `monitor_exited` | `cmd_monitor` finally block, including on SIGTERM | `owner_session`, `pid`, `lease_released` |

### Notices (`hooks/check_comment_bus.py`)

| Event | Emitted at | Fields |
|---|---|---|
| `notice_emitted` | `_scan`, once per slug that produced a notice | `session_id`, `slug`, `count`, `offset_from`, `offset_to` |

### Bookkeeping set

The hook counts an event as reviewer activity only when it has a non-empty
author that does not start with `agent:` **and** its name is outside this set:
`seen_updated`, `comments_seeded`, `decision_requested`, `page_published`,
`page_publish_failed`, `version_published`, `notice_emitted`, `inbox_read`,
`bulk_overwrite`, `page_claimed`, `monitor_armed`, `monitor_exited`,
`round_discarded`, `session_push`, `page_closed`. `session_push` is excluded because it
mirrors the `comment_updated` that caused it one for one, which was most of
the ~2x count inflation measured on the live buses.

`annotate inbox` hides `seen_updated`, `notice_emitted` and `inbox_read` unless
`--all-events` is passed. `annotate monitor` advertises `comment_created`,
`comment_updated`, `comment_reply`, `comment_accepted`, `comment_archived`,
`comment_reanchored`, `comment_restored`, `session_push`, `round_submitted` and
`round_discarded` in its lease, but prints only `session_push` and
`round_submitted` — each printed line costs the reading agent a turn, and the
actionable unit is the round.

## 2. `annotate eval`

```bash
annotate eval [--since YYYY-MM-DD] [--out-dir DIR] [--refresh-transcripts]
```

Runs `eval.py` over every bus, every comment store and the Claude transcripts,
writes `eval-baseline.md` and `eval-baseline.json` into `<state>/logs` (or
`--out-dir`), and prints a headline covering the window, cards, verdicts, time
to verdict, event mix, rounds and verdict-to-reaction.

**Run it by hand, twice per change.** `eval` is a manual step: once before an
improvement round to record what the loop does today, and once after it to see
what moved. There is no scheduled run and nothing runs it for you — a number
nobody asked for is a number nobody reads, and a weekly job would produce a
report every week whether or not anything changed. Two runs bracketing one
deliberate change are what make the difference attributable.

It is **read-only**: no annotate command is run, no cursor moves, nothing is
appended to a bus. `eval.py` is exec'd as a subprocess rather than imported
precisely so it cannot reach `inbox`, which would advance the cursor it is
measuring. `--since` defaults to 2026-09-01. The transcript scan is cached at
`<state>/logs/eval-transcript-cache.json`; `--refresh-transcripts` ignores it.
`--state-dir`, `--bus-dir` and `--transcript-glob` point it at another estate
(a fixture, a copied backup) without touching the live one.

`eval` classifies `session_push` and `seen_updated` as machinery rather than
reviewer activity, for the same reason the hook does: a push mirrors its
`comment_updated` one for one. That reclassification moved 116 in-window events
and took the measured agent share from 72.1% to 89.6%, so a baseline taken
before v2.19 is not comparable to one taken after.

The seven sections of the report:

1. **Per-slug shape.** Comments, decision requests, the
   accept/reject/changes/undecided/closed split, median and p90 time to
   verdict, agent against reviewer event counts, 15-minute authoring bursts,
   pushes by delivery, versions. A card archived unanswered by
   `annotate close` counts as **closed**, not undecided.
2. **Reviewer round shape.** Rounds inferred from verdict gaps over 10 minutes:
   verdicts per round, duration, time from the first verdict to the agent's
   reaction, and whether the agent reacted **mid-round**.
3. **Verdict to agent reaction, and unanswered requests.** Median and p90
   reaction latency, verdicts that drew no reaction at all, unanswered requests
   bucketed by age, how many were closed rather than answered, and the fifteen
   oldest with their prompts.
4. **Text-verdict taxonomy.** Every free-text verdict classified — `changes`
   and its pre-D2 spelling `comment` together — counted
   both across all free text and across verdict text alone, with each item
   listed so the classification is auditable.
5. **Decision-prompt quality against outcome.** Answered, changes and accept
   rates by prompt feature, with median prompt length. This is where the
   74%-against-34% recommendation finding comes from.
6. **Trace join.** For each slug, how many verdict comment ids ever appeared in
   any session transcript, how long after the verdict, and through which
   channel they were first seen.
7. **Hook notice — owner or bystander?** Notices found in transcripts split
   into owner and bystander, strict and loose, plus slugs in no registry and
   the hook's own logged notice count.

## 3. Thresholds — guidance, not gates

These are the lines worth looking at when comparing a before-run to an
after-run. They are guidance: nothing enforces them, no build fails on them,
and crossing one is a reason to go and read sections 2, 3 and 7, not a verdict
on its own.

| Signal | Guidance line |
|---|---|
| Cards unanswered after 7 days | above 30% of cards posed |
| Verdict to agent reaction, p90 | above 1 hour |
| Queued `session_push` while an owner was recorded | any occurrence |
| False `NOT PUBLISHED` (gate failed, page was fine) | any occurrence |
| Notice delivered to a session that does not own the slug | any occurrence |

The last three describe correctness bugs rather than rates, so any occurrence
is worth chasing. Read them off sections 7 (bystander, loose), 1 (delivery) and
the publish events. The first two come from sections 3 and 2: an unanswered card usually means the card did
not say what it would cost to answer either way, and a slow reaction usually
means a session acted on a partial round and then waited for the rest.
