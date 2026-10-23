# dw4 browser half: new agent requests without reload; a post ready to send at once

Page: fresh APFS clone of `/tmp/fld-live-20261023` per run (1,029 comments, 214 versions, 4.2 MB `comments.json`), published with the sandboxed CLI (`annotate publish --transport local`, own state/bus/config dirs), served again with a local reviewer. Headless Chrome 1440×900 on the M1 Max. The agent acts exactly as the FLD orchestrator: `annotate ask fld/page --from cards.json` and `annotate new <dir> --from vN.md --version vN --publish --ask`. Script: `measure_live.py` in `prototypes-2.20/work/rail-2026-10-20/dw4/` (with `make_version.py`).

- **before** = origin/main 61f1b89 (2.27.3).
- **after** = `changl/dw4-live`.

## Time until the open page shows a new agent card

Each row: the page left alone 150 s first (so the poll has backed off), then the agent acts; seconds from the CLI returning until the card is in the rail's Needs you section (same instant the Needs-you badge moves).

| Scenario | before | after |
|---|---:|---:|
| `ask`, nothing open | 14.2 s (idle poll 15 s / 30 s) | 4.7 s |
| `new --publish --ask`, nothing open | 3.6 s; page stays on v214 behind a "Latest is v215" banner, for good | 1.4 s; page moves to v215 |
| `ask`, composer open with text | 4.7 s (card only as "Not in v214", page still behind) | 2.3 s (page on v215) |
| `new --publish --ask`, composer open with text | 4.1 s; banner; draft kept | 2.1 s; page stays, banner "Latest is v216, new from the agent — open v216 · your draft stays"; draft kept |
| `new --publish --ask`, typing in a rail answer box (focused) | never (75 s timeout); Send count meanwhile drops to 0 while the stale card stays | 2.3 s; banner as above |
| Worst case, idle page | 30 s; never while a rail box keeps focus | 8 s; 1.6 s after the reviewer stops typing |

Times under 8 s are the poll's phase at the moment the agent acted; the bound is the poll interval.

## Click → ready to send (median of 3 posts; reply and verdict n=3 / n=1)

| | before | after |
|---|---:|---:|
| Comment: shown and counted in Send (button enabled, count +1) | 31 ms | 28 ms |
| Comment: server answered | 57 ms | 57 ms |
| Comment: settled ("Sending…" gone) | 608 ms | 77 ms |
| Reply: counted / settled | 24 / 579 ms | 21 / 60 ms |
| Verdict: counted / settled | 33 / 83 ms | 41 / 82 ms |
| Answer in words: counted (no network) | 13 ms | 27 ms |
| Long tasks per post (click to settled + 1.5 s) | 850–930 ms | 0 |
| Main-thread task time per post (same window, CDP TaskDuration) | 535–590 ms | 130–150 ms |

The 2-3 s Chang sees on the M5 is the before column's settle: a 4 MB store re-read plus a full render, ~0.9 s of long tasks on the M1 headless, in which the page does not respond. Profile (CPU sampling, one post): 730 ms of each render was `renderVersionRail` calling `flattenStore` once per version (214 versions × 1,029 comments, copied each time).

## Causes found (before)

1. Review never moved to a newer version: a publish left the page on the old one behind the banner; cards posed on the new version showed as "Not in vN", and the page stayed behind for every later version.
2. A poll's render was held while any rail or document box had focus, until it lost focus: a reviewer leaving the cursor in a box saw no new cards at all, while the header counts (computed separately) moved, so rail and counts disagreed.
3. Idle backoff took every read, the store included, to 15 s then 30 s.
4. Every confirmed post re-read the whole store and rendered everything (three rail renders per comment); History walked the store once per version.
5. Not a cause: server caching. CLI writes (`ask`, `new --publish --ask`) were visible on the very next conditional GET in every run (comments.json?view=poll and current.meta.json 200 with new ETags). PR #52 covers the server half.

## What changed (after)

- Review follows the agent: on the latest version it moves to a newer one at the first poll with no draft open (composer, focused box, Send summary); a republish of the version on screen reloads the document. With a draft open the page stays, the new card shows in the rail, the banner offers the version and says the draft stays; the move happens at the first poll after the draft closes. Opening an older version deliberately stops following.
- A render waits only while the reviewer is typing (key in the last 1.5 s, or IME composing) and runs by itself 1.6 s after they pause; focus, caret and text are kept.
- Store and version list are asked every 8 s even when idle (two empty 304s, ~0.3 KB each); the other reads keep the 15 s / 30 s backoff.
- A post settles from the write's own answer (POST /api/comments, /reply, /decision return the comment): the card is drawn again in place (whole rail only if it changed section), its pin and the Send count updated; History, Library/Findings and the server's tab counts follow when idle. No store re-read. History counts all versions in one pass. Body-strip verdicts still re-read the store (the frame does not pass the server's answer).
- Header counts were computed twice per change notification; once now.

## Tests

`tests/browser/test_live_updates.py` (1,100 comments, 160 versions; polls on Playwright's clock): idle page gets an `ask` card ≤ 8.5 s, store/meta still polled every 8 s after two idle minutes while read-state backs off; a focused box neither blocks the card nor loses text/focus; a new version is followed with nothing open, offered with the composer open (text kept) and followed after the draft is posted; typing holds a render only until a pause (≤ 2.5 s); comment, reply and verdict are counted in Send < 100 ms and settle with no store read and no rail re-render. All three fail on 2.27.3.

Independent review (same PR) added three, each failing on the first dw4 commit: an older version opened by a link or Back while a move waited on the composer stays on screen (it was moved to the new version once the composer closed); a post that a poll already drew while Sending… settles as one card (it showed twice until a later poll); a focused box keeps its place when a card arrives above it (it moved down by the new card). Same review, not fixed here: a card the agent resolves while its box holds text loses the box, as in agent-annotate-5uy.

## Left

- A question the agent withdraws (`new --ask` withdraws unanswered cards it does not ask again) takes its rail box with it; text typed there stays in drafts storage but is no longer on screen. Same on 2.27.3 (on blur). Separate bead.
- kbv's < 50 ms: the confirmation step itself is ~15-20 ms wall from the server's answer to settled; the whole post window still costs ~135 ms of main thread (optimistic render, pin rebuild, deferred History/Library renders, header counts each walking the store).
