# Decision cards — schema, rendering, rounds

A decision card is an ordinary comment that carries a `decision_request`. The
reviewer answers it with one click on the page, and the verdict comes back to
this session on the event bus. Cards are the only feedback primitive that
produces a machine-readable answer rather than prose.

## 1. Schema (`decision_request`)

Validated identically by `POST /api/comments`, `PUT /api/comments/<id>` and
`POST /api/comments/batch` (`_normalize_decision_request` in `sync_server.py`).

| Field | Type | Required | Notes |
|---|---|---|---|
| `prompt` | str | **yes** | The question. Keep it under ~200 chars; it is the card title on both surfaces. An empty or missing prompt is HTTP 400. |
| `context` | str | no | What is being decided and why it matters. ≤600 chars recommended. |
| `recommendation` | `"accept"` \| `"reject"` \| `"changes"` \| option id \| `null` | no | Puts a "Recommended" badge on that button. |
| `options` | list | no | Strings (any subset of `accept`/`reject`/`changes`; `comment` is the pre-D2 spelling of `changes` and still parses) **or** objects `{id, label, consequence, style}`. `id` must be a non-empty string. `style` is `primary`/`default`/`danger`. Defaults to `["accept", "reject", "changes"]`. |
| `consequences` | `{accept, reject, changes}` | no | Shortcut when `options` are strings. |
| `evidence` | `[{label, anchor}]` | no | `anchor` is a `data-anchor-id` on the page. Rendered as a link that scrolls to it and flashes it. |
| `impact` | `low`\|`medium`\|`high` | no | Anything else is HTTP 400. |
| `blocking` | bool | no | Renders a chip. |
| `requested_at` | ISO ts | server-set | Stamped on every create/update. Drives `latency_s`. |

**Limits.** The serialized request is capped at 8192 bytes
(`_DECISION_REQUEST_CAP`). Over the cap the server answers **HTTP 413** with a
JSON error and writes nothing — v2.18 silently dropped the request and still
returned 200, so agents believed cards existed that had never been posed.
`GET /api/capabilities` reports the live cap as `decision_request_cap`.

**Withdrawing.** `PUT` with `decision_request: null` clears an unanswered card.

**Every verdict answers.** `accept` closes the card
(`status: user_confirmed`). `reject` and `changes` leave it open, because the
agent still owes an answer. `changes` ("Request changes") **requires** `text`:
a request with no note is HTTP 400, and the note is the instruction — the auto
reply reads `↻ Changes requested: <text>`.

`comment` is the free-text answer verdict. The UI calls it **Answer in words**.
It requires `text`, writes the reply `💬 Answer in words: <text>`, collapses
the options, and moves the card from "Needs my review" to "Waiting on agent".
It is counted in `verdict_counts.comment` but never in `undecided_ids`. A plain
thread reply is the non-answer remark path. A `resolved_in_version` card is
historical and excluded from both.

Later-version cards also carry top-level `number`: one stable positive integer
per response item. Numbers are unique and strictly increasing in the one final
`## Questions for Chang` section. Use anchor `d:q<number>` for the card and
`decision_request.evidence` to link back to plan anchors; do not repeat Q/#
labels inside the prompt.

`GET /api/capabilities` advertises the live set as `verdicts`, and a chrome
that does not find `changes` there renders the pre-D2 "Comment" button in the
third slot instead (and no standing one). That legacy spelling is still a
free-text answer, and the server accepts it indefinitely.

**Verdict shape.** `comment.decision = {verdict, text, ts, by}` plus server-set
`latency_s` (seconds since `requested_at`; absent on pre-2.19 cards) and
`round_pending: true` while the verdict is deferred inside an open round. A
re-decision moves the prior verdict into `decision_history` (oldest first) and
marks both bus events `revised: true, prior_verdict: <old>`.

## 2. Writing a card that gets answered

Cards that carry a recommendation are answered 74% of the time; cards that only
ask are answered 34% of the time. The rule for every card:

1. `context` says what is being decided and why it matters now.
2. `recommendation` names the option you would take.
3. Each option says what it costs — `consequence` on the option object, or the
   `consequences` shortcut.

An unanswerable card is worse than no card: it burns a review round.

## 3. How each field renders

Both surfaces render the same fields: the rail card in the right-hand drawer,
and the inline body strip injected next to the anchored element itself (a
sibling `<tr>` for table rows, `afterend` for flow elements, an absolute
overlay where neither is possible, e.g. inside `<svg>`).

| Field | Rail card and body strip |
|---|---|
| `prompt` | Card title. |
| `context` | Muted paragraph. Inline up to 160 chars; longer sits behind a "Why / details" WAI-ARIA disclosure (`aria-expanded`), which on mobile opens inline rather than in a new sheet. |
| `recommendation` | "Recommended" badge on the matching button. |
| `options` | One button each, wrapping to as many lines as the label needs. Object options render `label`; `style` sets primary/default/danger. |
| `consequence` / `consequences` | One line under its own button. Buttons switch to a column layout when any consequence is present. |
| `impact`, `blocking` | Chips beside the title. |
| `evidence` | Links. A click scrolls to the anchor and flashes it, using the same highlight mechanism as pin hover. |

Unanswered cards also mark their page pin in pulsing indigo, so a reviewer can
find a pending decision without opening the drawer. Under Accept/Reject there
is an "+ Add a note" toggle that attaches text to that verdict. "Request
changes" opens the same textarea, but there the note is required: the Send
button does nothing while it is empty. The standing "Answer in words" button has its
own box, so neither can borrow the other's text.

Clicking into any of those boxes — or into the card's reply box — also takes
the document to the card's anchored location, the same as clicking the card
itself, and leaves what is being typed alone.

**Object options with custom ids.** When an option's `id` is not one of the
known ids, the reviewer's click posts verdict `select` with `text` set to the
chosen option's label (the auto reply reads `☑ Selected: <label>`). A choice
answers the card while leaving it open, because the agent still has to act on
it. Read `decision.text`, not just `decision.verdict`, whenever a card used
custom ids — `annotate cards <slug>` prints it. Against a server that predates
`select` the same click posts `comment` with text `Selected: <label>`, as it
did before D3.

## 4. Round mode

Round mode is active only when `GET /api/capabilities` reports
`{"rounds": true}`. Against an older server the chrome runs in legacy mode and
each click pushes immediately, exactly as in v2.18.

| Element | Behavior |
|---|---|
| Verdict click | Posts `POST /api/comments/<id>/decision {defer_push: true}`. The verdict is stored, `decision.round_pending` is set, `comment_updated` carries `deferred: true`, and **no** `session_push` is emitted. |
| Pending chip | The card shows "Pending — not sent". |
| Round bar | Sticky: bottom on mobile, above the rail footer on desktop. Shows "Finish review (N)" and "D of M decided"; every verdict, including Answer in words, counts in D. |
| Finish review | Opens a confirm dialog with a note textarea, "Submit review" (primary) and "Discard pending" (danger). |
| Submit review | `POST /api/rounds/submit {note}` → "Sent to session" or "Queued — no session listening (N)". |
| Discard pending | `POST /api/rounds/discard` → clears the pending flags, keeps the verdicts recorded, emits `round_discarded` and **never** a `session_push`. |
| Send now | Per-card link on a pending card. Posts `POST /api/comments/<id>/push` for that one card and clears its pending flag client-side. |

`POST /api/rounds/submit` clears every `round_pending` flag, then emits exactly
one `round_submitted` and one `session_push {round: true, …}`. Its response is
`{ok, delivery, comment_count, comment_ids, verdict_counts, undecided_count,
undecided_ids}`.

**This is why you wait.** One click used to mean one push, so a session reacted
to the first verdict of a ten-card round. Do not act until `round_submitted`
appears or every card carries a verdict.

## 5. Posing a round

```bash
annotate ask <slug> --from cards.json [--version vN]
```

`cards.json` is a JSON array (or `{"cards": [...]}`) of
`{anchor_id, text, decision_request}`; `text` defaults to
`decision_request.prompt`, and `anchor_label` is optional. `ask` posts one
`POST /api/comments/batch {items, idempotency: "anchor"}`: an existing
non-archived card by the same author on the same anchor is **updated**, not
duplicated, so re-running `ask` refreshes a round in place. Max 200 items, and
one bad or oversize item rejects the whole batch (400/413) with nothing
written. Against a server without the batch route (404/405/501) `ask` falls
back to per-card `POST` + `PUT` under the same idempotency contract.

## 6. Events a card emits

| Event | When |
|---|---|
| `comment_created` | Card created. Carries `decision_requested: true`. |
| `decision_requested` | `{comment_id, anchor_id, prompt_len, has_context, options_n, by}` — on every create, PUT or batch item that sets a request. |
| `comments_seeded` | `{comment_ids, created, updated, by}` — once per batch. |
| `comment_updated` | Verdict posted. Carries `decision`, `latency_s`, `deferred` in round mode, and `revised`/`prior_verdict` on a re-decision. |
| `round_submitted` | `{comment_ids, verdict_counts, undecided_ids, note, by}`. |
| `round_discarded` | `{comment_ids, by}`. No push follows. |
| `session_push` | One per round submit (`round: true`), or one per immediate/`Send now` push. |

Full field lists and where each is emitted: `telemetry-and-eval.md`.
