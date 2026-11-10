# Card 53 context audit — agent-annotate-j8g

The reported mid-word context cutoff was **not reproduced** on main `b0043a5`.
This change adds regression coverage and changes no rendering behavior. After
the initial reproduction attempt, the coordinator explicitly authorized a
regression-only PR if the additional surfaces also passed.

## Sandbox and reproduction

The registry entry for project `FLD usage audit`, slug `page`, located the source
at `/Users/changlee/projects/FastLane Drive/planning/operations/usage-audit-2026-11-06/page`.
Its directory was copied to `/tmp/annotate-j8g-evidence/page`. Only the copy was
served, on loopback port 18700, using this worktree's `src` through `PYTHONPATH`
and temporary state/config/data/bus directories. The live directory and server
were never changed or contacted.

Card 53 (`e4e8e90603a7`, anchor `d:q53`) had since been resolved in v40.
The copy's current version was restored to v39, and only the copied card's
answer/resolution fields were cleared. A second pass supplied a pending worded
answer in the copy, owned by the sandbox reviewer, to inspect answered and
collapsed states without sending anything. Copied SQLite files were removed
before serving so the sandbox used the copied JSON records.

The actual stored decision context is **236 characters**, ending
`could turn the 6-hour sweep back on.`; it is not truncated in the parser or
stored data. In Chrome at normal text size its rail element has equal visible
and scroll heights: **50/50 px at 1400 px**, **66/66 px at 390 px**.

## Surfaces checked

Chrome and Playwright WebKit were each checked at widths **1400, 390, 820 and
1024 px**, in **light and dark**, with **100% and 200%** text, both unanswered
and answered: **64 cases, zero errors**. Desktop/phone viewport heights were
1000/844 px; the iPad-sized views were 820×1180 and 1024×768.

| Surface | Finding | Existing route to full text |
| --- | --- | --- |
| Unanswered rail card / Needs you list | `.decision-context` has no clamp or overflow; all 236 characters fit | Already shown in full |
| Question card in the document | `.annotate-decision-context` has no clamp or overflow | Already shown in full |
| Rail evidence excerpt | `.decision-excerpt-text` clamps to two lines (33 px at normal text size); this is evidence, not the decision context | Visible Show more expands to 314 px desktop / 363 px phone; Show less restores the clamp |
| Document evidence excerpt | `.annotate-excerpt-text` uses the established four-line clamp and disclosure | Show more / Show less |
| Collapsed answered rail card | `.citem-line-q` uses a one-line ellipsis on the **question**, with no context in this state | Card or pencil expands the full question; Choose reopens the full decision context |
| Expanded answered card | Shows question and worded answer; does not render decision context | Choose reopens the full decision context |
| Send / Finish review dialog | Card 53 uses `.rl-q` with no clamp, not `.sum-q`; its full question is readable in both Answers and Not in this Send | Question is already shown in full; context is not part of these summary rows |

`.sum-q` is currently used for a different document's general-feedback preview,
not card 53's question or context. That preview provides Edit. No new expansion
pattern or runtime change was justified by these observations.

## Evidence and checks

All screenshots and full per-case DOM geometry receipts are retained under
`/tmp/annotate-j8g-evidence/` on the worker's Mac:

| View | Initially clamped evidence | After existing Show more |
| --- | --- | --- |
| Desktop light | `before-desktop-light.png` | `expanded-desktop-light.png` |
| Desktop dark | `before-desktop-dark.png` | `expanded-desktop-dark.png` |
| Phone light | `before-phone-light.png` | `expanded-phone-light.png` |
| Phone dark | `before-phone-dark.png` | `expanded-phone-dark.png` |

These are before/after **interaction** screenshots of unchanged code, not
before/after a bug fix. The 200% text context and summary captures use
`{unanswered,answered}-{chrome,webkit}-{1400,390,820,1024}-{light,dark}-2-{context,summary}.png`.
Raw geometry receipts: `unanswered-surfaces.json`, `answered-surfaces.json`.
Runners: `/tmp/annotate-j8g-reproduce.py`, `/tmp/annotate-j8g-surfaces.py`.

`test_long_decision_context_is_fully_readable` uses a 240+ character context,
asserts the exact full text and nonzero unclipped layout on both card surfaces,
and opens/closes the real phone feedback sheet before measuring each surface.
It covers the four widths and both themes at 100% and 200% text:
**8 passed, 4 deselected in 83.74s**. It passes on the unchanged rendering code;
there is no claim of a fails-before reproduction.
The other existing card-layout browser tests also pass:
**4 passed, 8 deselected in 43.00s**.

The required fast gate used the worktree venv on `PATH` and the absolute worktree
`src` as `PYTHONPATH`: `python3 scripts/ci.py` exited 0. Ruff passed and every
JavaScript syntax check passed; the fast-suite tail is:

```text
..................................                                       [100%]
1468 passed, 7 skipped in 177.65s (0:02:57)
```

Fast-gate log: `/tmp/annotate-j8g-evidence/fast-suite.log`.
The full suite was not run.

All test/reproduction servers and browsers are stopped by their runners.
The original reviewer's browser state and screenshot were unavailable, so the
historical cutoff remains unverified. No live-page test, deployment or merge.
