# Measuring annotate use across Macs

Run the checkout's `annotate eval --since 2026-10-01 --codex --json` and
`annotate cost --since 2026-10-01 --codex --json` on **each Mac**. Save stdout
outside page directories. Each command reads only its local filesystem; neither
connects to another Mac. Copy the JSON exports through your existing transport,
then repeat each local command with `--merge /path/to/other-mac.json --json`.
`--merge` is repeatable and accepts merged exports. A fresh local observation
replaces that host in an older export. Settings must match, including cutoff,
Codex inclusion and cost's development-session filter.

Both exports are schema 1 objects with `measurement`, `settings`, `sources`, and
`measures`. Cost also includes `rows` (previously its entire JSON output was this
array). Host identity separates identical transcript paths and session IDs. Eval
keeps project/slug identities separate, including legacy bus-only pages, and
reads current comment stores, categories, and immutable `rounds.ndjson` snapshots.
Submitted rounds take precedence over inferred ten-minute verdict clusters.
`eval --json` writes no cache or report; without it, eval retains its Markdown
and JSON report files under `--out-dir`.

The `measures` fields support the simplification baseline:

- Reviewer correction **candidates** per Monday-start week: human user messages
  mentioning annotate/review cards and a correction/reminder phrase. Agent text,
  tool output, system scaffolding and common relayed worker prompts are excluded.
  Identical normalized text is deduplicated across files and hosts. These are
  heuristic candidates, not a claim that every match is a correction. Hashes,
  timestamp and source file permit auditing without exporting message text.
- Open cards, and open cards whose owner session is absent from a successful
  local process snapshot or whose page has an explicit moved/superseded marker.
  Owner absence is an inventory observation; unknown owners stay separate.
  Supersession inferred by a human but absent from metadata cannot be counted.
- Rail-only open cards: neither the card anchor nor an evidence anchor is in the
  current document. Missing documents have a separate unknown count.
- Bulk-approval candidate cards created since the cutoff: explicit accept/approve/
  confirm-all wording in prompts or options, including archived cards.
- Visual-change candidate versions published since the cutoff with zero `<img>`
  elements: visual terms in document text identify candidates. This heuristic
  does not prove that a version changed visuals; SVG/video-only documents can
  require manual review. Script/style text does not count as document content.
- Agent output tokens and estimated result-context tokens per **closed authoring
  round** in cost. Output usage is allocated across the issuing message's tool
  calls; result tokens are characters/4. This measures annotate tool overhead,
  not all model tokens or billing. It is distinct from eval's submitted reviewer
  rounds. Unclosed authoring rounds are excluded. Median values are null if no
  rounds close, rather than reporting a misleading zero.

Backlog measures are current snapshots across all registered pages, regardless
of cutoff. The correction, bulk and visual measures use the cutoff. Eval's
in-window page totals include pages with version/event/card activity since the
cutoff, even if created earlier. Merge recomputes aggregates and medians from
observations rather than averaging host medians. No page, bus, cursor, registry,
owner claim or live server is written by these measurements.
