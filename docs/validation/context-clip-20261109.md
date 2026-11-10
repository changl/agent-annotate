# Card 53 context cutoff — agent-annotate-j8g

**Reproduced:** FLD card 53's expanded evidence quote ends at
`could turn the 6-hour swee…` on main `b0043a5`. The adapter cuts its text to
1,200 characters before the existing Show more control receives it. Its section
quote includes the static card, repeating the card's 236-character context;
the character boundary falls inside that repeated context. Expanding the CSS
clamp cannot recover characters already removed by JavaScript.

The fix removes the character cap and the associated early traversal cutoff
in `adapter.js::excerptText`. `excerptMap` already limits extraction to the
anchors question cards cite and caches the result; its callers and the shared
renderer require no changes. The existing two-line rail / four-line document
previews, `.is-open`, Show more and Show less continue to control presentation.
Long evidence now produces a larger excerpt message; previews remain clamped.

## Sandbox reproduction

The registry entry for project `FLD usage audit`, slug `page`, located the source
at `/Users/changlee/projects/FastLane Drive/planning/operations/usage-audit-2026-11-06/page`.
Its directory was copied to `/tmp/annotate-j8g-evidence/page`. Only the copy was
served, on loopback ports in **18700–18799**, using this worktree's `src` through
`PYTHONPATH` and temporary state/config/data/bus directories. The live directory
and server were never changed or contacted.

Card 53 (`e4e8e90603a7`, anchor `d:q53`) had since been resolved in v40.
The copy's current version was restored to v39, and only the copied card's
answer/resolution fields were cleared. A second pass supplied a pending worded
answer owned by the sandbox reviewer to inspect answered and collapsed states
without sending anything. Copied SQLite files were removed before serving so
the sandbox used the copied JSON records.

The expanded quote is exactly **1,200 characters** before the fix. The ending
matches the reviewer's report. The standalone `.decision-context` was never
clamped: normal-text visible/scroll heights were 50/50 px at 1400 px and
66/66 px at 390 px. Checking DOM overflow alone initially missed the loss; the
expanded screenshots and the actual quoted text exposed it.

## Other surfaces checked

The baseline audit recorded **64 cases**: Chrome and Playwright WebKit at widths
**1400, 390, 820 and 1024 px**, **light and dark**, **100% and 200%** text, both
unanswered and answered. Desktop/phone heights were 1000/844 px; iPad-sized
views were 820×1180 and 1024×768.

| Surface | Finding |
| --- | --- |
| Unanswered rail / Needs you card | Standalone `.decision-context` is complete; the section's `.decision-excerpt-text` loses its tail in JavaScript, even after Show more |
| Document card | Standalone `.annotate-decision-context` is complete; `.annotate-excerpt-text` receives the same shortened evidence |
| Collapsed answered rail card | `.citem-line-q` ellipsizes the question; card or pencil expands it fully |
| Expanded answered card | Shows question and worded answer; Choose reopens complete decision context |
| Send / Finish review | Card 53 uses unclamped `.rl-q`, not `.sum-q`; question is complete in Answers and Not in this Send; context is not part of these rows |

`.sum-q` currently serves another document's general-feedback preview and
provides Edit. No parser, summary, context-style or disclosure changes are needed.

## Browser regression and evidence

`test_long_decision_context_is_fully_readable` puts 240+ characters of context
after **4,000+ characters of evidence**, beyond both old JavaScript cutoffs.
It checks exact standalone context on both surfaces, clicks the existing
Show more, asserts the entire context survives in the quote, and checks the
expanded text's layout. It covers four widths, both themes, and 100%/200% text.

Before the fix, `[light-desktop]` fails after Show more because its quote still
ends at 1,200 characters and omits the context:
`1 failed in 17.70s`. Log: `/tmp/annotate-j8g-evidence/fails-before.log`.

After the fix, the complete card-layout browser module passes:
**12 passed in 123.05s**. Log: `/tmp/annotate-j8g-evidence/card-layout-after.log`.

Final `python3 scripts/ci.py` used the worktree venv on `PATH` and its absolute
`src` as `PYTHONPATH`, with the suite's temporary state roots. It exited 0;
Ruff and all JavaScript syntax checks passed. Fast-suite tail:

```text
..................................                                       [100%]
1468 passed, 7 skipped in 176.01s (0:02:56)
```

Log: `/tmp/annotate-j8g-evidence/fast-suite-after.log`.

All screenshots and per-case baseline DOM/text receipts are retained under
`/tmp/annotate-j8g-evidence/` on the worker's Mac. For each of
`desktop-light`, `desktop-dark`, `phone-light`, `phone-dark`:

- `before-expanded-{view}.png`: old Show more still ends mid-word.
- `after-expanded-{view}.png`: the fixed quote contains the full context and following options.
- `before-{view}.png` / `after-{view}.png`: collapsed previews.
- `before-expanded-document-{view}.png` / `after-expanded-document-{view}.png`: expanded document evidence.

The before runner uses a temporary source copy with the original adapter from
`git show b0043a5:src/agent_annotate/web/adapter.js`; after uses this worktree.
No working-tree source was reverted for screenshots. Initial matrix captures
use `{unanswered,answered}-{chrome,webkit}-{width}-{theme}-2-{context,summary}.png`;
raw receipts are `unanswered-surfaces.json`, `answered-surfaces.json`.
Runners: `/tmp/annotate-j8g-reproduce.py`, `/tmp/annotate-j8g-surfaces.py`.

All test/reproduction servers and browsers are stopped by their runners.
No full-suite run, live-page test, deployment or merge.
