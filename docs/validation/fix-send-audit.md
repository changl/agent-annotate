# Explicit Send audit (2.28.0 / 064b1d5)

Canonical page: https://macbook-pro.tail2b8ab9.ts.net/annotate/reviews/annotate-conformity-20260927/

Read-only source audit before implementation. Live page files were read only;
all subsequent experiments use copies, sandbox state/bus, and ports 18700–18799.

| Path | Exposes unsent reviewer input today? | Evidence / mechanism |
| --- | --- | --- |
| `annotate inbox`, plain and `--unread` | **Yes** | `_inbox_visible` accepts create/reply/update events and most deferred decisions; `_comment_texts` hydrates historical events from mutable comments.json, including later draft edits. JSON also adds pending decision text. |
| `annotate cards`, inbox decision summaries | **Yes** | `_decision_cards` includes pending verdict, words, author, and timestamp; counts advertise unsent choices. |
| `annotate watch` | **Yes** | Prints every raw bus line, including draft event metadata and legacy decision choices. Fixed with the same draft-event filter. |
| `annotate eval`, metrics, publication blocker readout | **Yes** | Eval can quote draft verdicts from its raw store, metrics count saved choices before Send, and blocker counts include unsent comments. These read paths now use the same projection/event filter; metrics count choices from submitted round snapshots. |
| SessionStart notice / waiting count | **Yes, state/count** | `waiting_count` reads raw comments; a draft choice/reply changes needs-review state before Send. |
| UserPromptSubmit / comment bus notice | **Yes** | `_is_reviewer_event` ignores marked deferred events, but ordinary comment saves/replies lack that mark; `_load_cards` reads raw pending decisions and announces unsent counts. |
| MCP `list_comments`, `list_cards`, `read_inbox` | **Yes** | Raw comments.json and the same CLI event/card helpers expose drafts. |
| Local agent HTTP comments/store readers | **Yes** | `/api/comments`, `/comments.json` and `/api/copy` return the raw reviewer store. |
| Agent comment mutation responses | **Yes** | Replying or updating a card while a reviewer drafts returns the raw card, echoing private text. Successful agent mutation responses now use the same projection as reads. |
| Category counts exposed by CLI/MCP | **Yes, state/count** | Read raw comments and pending Library revisions, advertising ready drafts. |
| `session_push` / monitor / terminal typing | **Partly** | Modern chrome defers decisions; a decision POST without `defer_push` emits immediate session_push. Explicit round/push routes use durable bus → journal → captured owner target → Orca terminal send. Terminal wake-up contains routing, not reviewer prose. |
| Add note / Reply / Save comment | **Yes** | POST saves immediately and emits comment_reply/comment_created; reply on unanswered card becomes an immediately visible non-pending decision. Reply on addressed card also reopens immediately. |
| Auto-dispose / disposition | **No automatic reviewer submission found** | No auto-dispose implementation exists in this revision. Publish/resolve/withdraw are agent lifecycle actions; no timer, unload, visibility, poll, or disposal callback calls Send. |
| Reviewer archive / accept-and-archive / restore | **Yes, state/count** | These page disposal actions change stored state immediately. The agent projection now retains its prior state and emits no reviewer notification. |
| Answer in words / general feedback textarea | **No while only typed** | Local DRAFTS until preparation at Send; Add note/option actions save server-side and leak through the paths above. |
| Library edit / finding reopen | **Yes through state/read surfaces** | Revisions/reopens are deferred, but raw stores/counts expose them; finding_reopened is hidden from normal inbox when deferred. |
| Keyboard / Send dialog | **Explicit shortcut exists** | Cmd/Ctrl+Enter submits an open Send dialog; the task requires manually pressing Send, so this submission shortcut must be removed. |

## Every “Sent” presentation

| Page surface | What it actually checks in 2.28.0 |
| --- | --- |
| Send result (`app.js`) | `submitPage` checks only latest matching journal id, accepting states accepted/started/acknowledged; accepted can mean only Orca enqueue acceptance. Otherwise says “Feedback saved”. |
| Choice and note state badges (`stateTag`) | Only draft/pending boolean; non-pending reads bare “Sent”. |
| Comment badge (`sendStateHtml`) | flagged_for_session OR decision without round_pending; no owner receipt. |
| Send summary “Not in this Send” answer | Answer exists and has no pending flag; no delivery check. |
| History activity header | Literal “Sent”; persisted rounds prove acceptance, not owner delivery. Round result currently “Feedback saved”; legacyRound itself constructs “Sent (N)”. |
| Findings action/history/comments | round_pending/needsPush only; “sent” / “sent; waiting on agent” without owner receipt. |
| Library proposal status | Non-pending revision is described as sent; no owner receipt. |
| Delivery banner | Uses latest journal state and differentiates pending/uncertain/accepted/started/acknowledged, but is separate from the misleading bare badges. |

## Planned fix boundary

Use one submitted-only agent projection for CLI/MCP/hooks and agent HTTP reads;
save drafts safely but hide their events, text, choices and counts. Preserve the
last submitted view while editing it, and publish it only at explicit Send.
Force browser decision writes to defer, remove non-button submission, and base
all delivery language on matching durable receipts (owner input acceptance or
turn start / owner inbox acknowledgement, never enqueue acceptance alone).
Keep page refresh, draft persistence machinery, publishing, ports and numbering
unchanged; small send-result edits in shared web files are required.

## Implemented boundary

`submitted.py` provides the shared submitted store and event view. A saved
reviewer edit retains the last agent-visible snapshot; Send releases that
snapshot only after recording the durable round/outbox. Recovery from a recorded
round receipt releases it too. Pending notes, choices, Library revisions and
finding reopens remain private; one reviewer's Send excludes another's drafts.
Add note after accepting a card is included in the next Send rather than stranded.

All success wording uses the matching delivery ID and requires owner
`input_accepted`, `turn_started`, or an owner inbox acknowledgement. Queue-only
Orca acceptance is insufficient. Unknown historical receipts remain explicitly
unconfirmed. The existing poll updates delivery labels in place on every tab,
including while the reviewer types, without adding a timer or rebuilding inputs.
Cmd/Ctrl+Enter cannot submit the Send dialog, and activity arriving
after a round response is never automatically pushed in a second request.

The copied live-page proof is in `fix-send-live-proof.json`; no live server,
route, page or real terminal was modified. Diagnostic readouts now use the same
boundary. Raw files on disk remain the safety copy, not an agent feedback API.
