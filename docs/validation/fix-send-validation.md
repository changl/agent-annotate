# Explicit Send validation

Base: `064b1d5` (2.28.0). Branch: `changl/fix-send`. Bead: `agent-annotate-6yn`.

The path-by-path audit is [fix-send-audit.md](fix-send-audit.md).
The copied-page receipt is [fix-send-live-proof.json](fix-send-live-proof.json).

## Before and after

All 12 cases in `tests/test_explicit_send.py` fail against an extracted,
unmodified `064b1d5` source tree and pass against this change. They cover new
comments, replies, choices, note/comment edits, agent mutation responses and
status validation, accepted-card notes, foreign-reviewer drafts, Library edits,
finding reopens, watch/eval/blocker readouts and reviewer disposal actions.
The reply-as-answer goes into the submitted round once.

All seven cases in `tests/browser/test_explicit_send_browser.py` pass together:
failed/queued delivery cannot say Sent; confirmed input can; keyboard shortcuts
cannot submit; later receipts update the header and badges in every tab without
replacing a typed draft. The four receipt-poll cases were added after the full
A–F browser run and were verified in this focused seven-case run.

## Requested full-suite chunks

Each chunk used `PYTHONPATH=$PWD/src` and
`/Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest`.
File groups use the first letter after `test_`; monitor is separate.

| Chunk | Full-run result / follow-up |
| --- | --- |
| Non-browser A–F | 721 passed, 2 skipped |
| Non-browser G–P | 614 passed |
| Non-browser Q–Z | 364 passed |
| Monitor | 16 passed |
| Browser A–F | 105 passed, 1 page-startup timeout; exact unchanged retry passed. With the four added receipt-poll cases, 110 distinct cases have passing coverage. |
| Browser G–P | 46 passed |
| Browser Q–Z | 88 passed, 4 failed. The historical receipt-count regression was fixed and its exact retest passed; the remaining three popup failures also fail on the untouched base. |

The final focused backend carryover/send/server check passed 29 tests.
`ruff check src tests scripts/ci.py scripts/release.py`, parsing all seven
JavaScript assets with `node --check`, and `git diff --check` passed.
No timeout was increased and no popup test was weakened or skipped.

### Baseline popup failures

These time out at `link.click()` while opening a mocked new tab, on both the
branch and an extracted unmodified `064b1d5` source tree:

- `test_rounds_links_contrast.py::test_rounds_are_readonly_and_ticket_links_preserve_current_drafts[light-1440]`
- `test_rounds_links_contrast.py::test_rounds_are_readonly_and_ticket_links_preserve_current_drafts[light-390]`
- `test_workspace_intent.py::test_extra_page_is_listed_in_documents`

They were reported to the coordinator for integration triage. They are outside
the send/delivery change. The full browser suite is therefore not claimed green.

## Copied live-page proof

On a copy of live v56, with a unique sandbox reviewer and bus:

1. Picked an answer, added a note, and typed general feedback. Before Send,
   inbox text, hook notices and owner prompts were absent; waiting counts did
   not change.
2. Clicked Send. One submitted round contained both texts and produced exactly
   one sandbox owner prompt, with an `input_accepted` delivery receipt.
3. Read the owner inbox and verified the receipt became `acknowledged` and the
   page showed the confirmed Sent result.

All 330 source-file hashes remained unchanged. The server bound within
18700–18799 and both it and its browser were stopped. Terminal delivery was
mocked at the Orca boundary; no real agent terminal, live page/server, M5,
release, installation or skill synchronization was touched.
