# Decision cards

Create cards only for decisions requiring Chang. Each asks one concise question with a recommendation and brief consequences. No cards for routine implementation, status reports, or an arbitrary retry count.

```cards
[{"number":1,"anchor_id":"d:q1","decision_request":{"prompt":"Use the shared runtime?","context":"One runtime keeps both clients consistent.","recommendation":"shared","options":[{"id":"shared","label":"Shared","consequence":"One maintained install."},{"id":"fork","label":"Fork","consequence":"Separate upkeep."}],"evidence":[{"label":"Scope","anchor":"s:scope"}]}}]
```

`prompt` is required. Optional fields: `context`, `recommendation` (option ID), `options` (strings or `{id,label,consequence,style?}`), `consequences`, `evidence` (`{label,anchor}`), `impact` (`low|medium|high`), `blocking` (boolean). Request limit: 8192 bytes; invalid/oversize input fails without writing. Optional `style`: `primary|default|danger`.

Options render once; the recommended choice has a green `rec` badge. Evidence stays collapsed. Nothing is preselected. **Answer in words** and notes remain available when changing a choice; custom choices support notes too. Clicking card text or padding opens a comment without interfering with its controls.

| Verdict | State |
| --- | --- |
| `accept` | Confirmed by reviewer |
| `reject`, `changes`, `select`, `comment` | Answered; waiting on agent |

`changes` and `comment` require text. Custom choices use `select`; read `decision.text` for the choice and explanation. A reply on an unanswered card counts as a text answer. A later reply on an answered card is a thread reply. Revisions preserve `decision_history`.

Clicks save pending verdicts. **Finish review** submits one round and one durable owner wake-up. Read `inbox --unread` and `cards` after submission; do not react separately to every click. `Send now` explicitly sends one item. Delivery acceptance is not implementation completion.

`ask SLUG --from cards.json` upserts canonical numbered decisions across agent authors, preserving replies and decisions. Legacy arbitrary anchors remain author-scoped. Feedback is never silently discarded across versions: apply it using `resolve --in-version vN --anchor ID`, or `carry --to-version vN --anchor ID`. Reviewer confirmation remains reviewer-owned. Replies reopen resolved items.
