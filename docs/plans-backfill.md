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
- A `rounds.ndjson` snapshot from the same reviewer containing an exact match on
  comment ID, reviewer, decision timestamp, verdict and answer text. When present,
  decision IDs must match too. Pending decisions never qualify.

Agents, explicitly ineligible/legacy decisions, non-review cards and opted-out
cards are excluded. Missing provenance or sent-round receipts are conflicts,
with branch counts distinguishing browser-only, sent-only and neither. Old
unsent votes are never treated as committed just because they lack a pending flag.

Evidence must be an intact, complete sealed bundle, or a unique versioned card
plus HTML from the sent round's version. Both snapshot files must predate the
vote, and the prompt must match the sent receipt. Missing anchors, later edits,
ambiguous versions, and historical media without vote-time hashes are conflicts.
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
that might race another writer. Re-applying creates no additional entries or backups.

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
