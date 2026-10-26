# Historical approval reconciliation

`annotate plans backfill [--dry-run | --apply] [PROJECT/SLUG ...] [--json]`
is an operator command, hidden from the ten-verb agent help. It reads only this
Mac's registry and processes active, running pages, deduplicating directories.
Omit slugs to inspect all of them. The default is a dry run; it creates no locks,
evidence, backups, registry records or page files. `--json` returns per-page
counts, provenance branches, and per-approval candidates and reasons.

Historical eligibility requires both:

- Browser reviewer provenance: `decision.by` is an email, with a same-timestamp
  generated verdict reply whose `author` and `author_email` match it. The reply
  starts with `✓ Accepted` or `☑ Selected:` (including revised-verdict prefixes).
  New decisions may instead use the authenticated `catalog_eligible: true` marker.
- A sent receipt, using either an exact `rounds.ndjson` snapshot answer match on
  comment ID, reviewer, decision timestamp, verdict and answer text (including
  decision ID when present), or a `round_submitted` comment-bus event by that
  reviewer after the vote that includes the card's ID. For the bus branch, the
  vote must be the latest decision on that card when Send happened; an earlier
  vote replaced before Send is excluded as `superseded_before_send`. Explicit bus
  answers must match too. Pending decisions never qualify.

Bus receipts are read from the registry's configured `bus_file` (otherwise the
local project's default bus), including its retained bus archives. The first
qualifying Send is used. When a legacy event has no version, the published page
history determines the version active at Send; a missing version remains an
evidence conflict. JSON reports separately count `snapshot` and `bus` receipts.

Agents, explicitly ineligible/legacy decisions, non-review cards and cards not
marked `catalog: true` (a plan or design approval) are excluded. Missing provenance or sent-round receipts are conflicts,
with branch counts distinguishing browser-only, sent-only and neither. Old
unsent votes are never treated as committed just because they lack a pending flag.

Evidence must be an intact, complete sealed bundle, or a unique versioned card
plus HTML from the sent round's version. Both snapshot files must predate the
vote, and the prompt must match the sent receipt. Missing anchors, later edits,
ambiguous versions, absent historical decision requests, and historical media
without vote-time hashes are conflicts. CSS URLs and imports are rejected even
when the stylesheet itself was sealed; its dependencies have no vote-time hashes.
The frozen request's `catalog: true` is required for sealed evidence too.
Selections use the existing catalog's **Decided** semantics; they do not imply an
affirmative interpretation of labels such as "not now".

An exact catalog decision/evidence match repairs the card's link. Other existing
Plans, multiple approvals for an item, and later corrections/reopens remain
conflicts. No fuzzy title/content matching or supersession happens during backfill.
New entries use the normal approval catalog promoter and preserve historical votes.

After reviewing the dry run and obtaining approval for live writes, run the same
command with `--apply`. Apply takes the existing server comment-store lock,
rechecks the page, and backs up every file it will touch under
`PAGE/.plans-backfill-backups/TIMESTAMP-ID/`. The command prints that full path.
If the server lock does not exist, apply refuses rather than creating an inode
that might race another writer. Symlinked backup paths are refused just like
other page storage paths. Re-applying creates no additional entries or backups.

Restore with:

```sh
annotate plans restore PROJECT/SLUG --backup /absolute/page/.plans-backfill-backups/TIMESTAMP-ID
```

Restore verifies all backup hashes and checks that each target still equals its
before or backfill hash before writing anything. It refuses later content changes,
restores original files, and deletes newly created evidence files. Backups and
empty evidence directories remain for inspection. The manifest is durable before
the first page write, so restore also handles an interrupted apply; restore
`comments.json` and evidence together, never just the catalog index.

The M1 task authorizes live dry runs only. No live apply, M5 operation, server
restart, installation or deployment is part of this change.

## Plans sections

`annotate plans section PROJECT/SLUG tracking|approved|reference|hidden [PLAN_ID ...] [--decisions] [--apply] [--json]`
moves plans between the Plans picker's sections: tracking the reviewer asked
for, approved plans, agent reference (listed last), and hidden (out of the
picker; the plan, its history and the decisions behind it stay, and a link still
opens it). `--decisions` adds every plan filed from a reviewer decision. The
default is a dry run listing each move. `--apply` needs the server's lock, writes
`comments.json` and the plans' `meta.json` files, and keeps a backup that
`annotate plans restore` reverts.
