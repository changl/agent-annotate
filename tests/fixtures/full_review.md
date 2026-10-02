---
title: Items model review
subtitle: Round 1 — column semantics and the two renames that block v3
date: 2026-09-18
slug: items-model-review
version: v1
label: round 1
legend: Red KPI = failing · Amber = costly · Green = working. Answer every card, then press Finish review.
full_plan: true
other_files_required: none
---

# Items model review

The `items` table backs three services and **two of its columns mean different
things to each of them**. This round decides the renames only; the archive path
remains outside this decision. Background: *the v3 cutover note* and the
[schema history](https://example.com/items/history).

kpi: 64% | of 201 decision cards never got a verdict | bad
kpi: 6.0 m | median page build before this generator | warn
kpi: 147 | unit tests green on the packaged runtime | ok

## Scope

What this round decides, and what it deliberately leaves alone. Nothing here
touches the write path; every change is a rename plus a dual-write window.

- The `status` column rename, and the window it needs
- Which service owns `tier` after the split
- Nothing about the archive path or its retention

1. Read the column table
2. Answer the three cards
3. Press Finish review — nothing reaches the session until you do

### Out of scope

The archive path, retention policy, and backfill job are outside this decision.

## Columns

| Column | Type | Services | Note |
|---|---|---|---|
| status | text | 3 | Ambiguous: lifecycle and delivery both write it |
| tier | text | 2 | Stable, but ownership is unassigned |
| updated_at | timestamptz | 3 | Written by the trigger, never by hand |
| status | jsonb | 1 | The shadow column added during the last migration |

## Migration sketch

Two statements and a week of dual writes. The trigger is recreated because it
names the column literally.

```sql
ALTER TABLE items RENAME COLUMN status TO lifecycle_state;
CREATE TRIGGER items_touch BEFORE UPDATE ON items
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
```

## Questions for Chang

Three cards. Each states its context, my recommendation, and what each option
costs.

```cards
[
  {
    "number": 1,
    "anchor_id": "d:q1",
    "text": "Rename status to lifecycle_state. Three services read the column, so the rename needs a dual-write window before v3 ships.",
    "decision_request": {
      "prompt": "Rename status → lifecycle_state?",
      "context": "Lifecycle and delivery both write `status` today, so every consumer branches on a value whose meaning depends on the writer.",
      "recommendation": "accept",
      "options": [
        {"id": "accept", "label": "Rename with a dual-write week", "consequence": "One week of dual writes, three deploys.", "style": "primary"},
        {"id": "reject", "label": "Keep status", "consequence": "The name stays ambiguous through v3.", "style": "default"}
      ],
      "evidence": [{"label": "the column", "anchor": "tbl:columns:row:status"}],
      "impact": "medium",
      "blocking": true
    }
  },
  {
    "number": 2,
    "anchor_id": "d:q2",
    "text": "Give tier to the catalog service.",
    "decision_request": {
      "prompt": "Does catalog own tier after the split?",
      "context": "Two services write it and neither claims it. Unowned columns are how the last drift started.",
      "recommendation": "accept",
      "options": ["accept", "reject", "comment"],
      "consequences": {"accept": "Billing reads it through the catalog API.", "reject": "It stays shared and undocumented."},
      "evidence": [{"label": "tier row", "anchor": "tbl:columns:row:tier"}],
      "impact": "low"
    }
  },
  {
    "number": 3,
    "anchor_id": "d:q3",
    "text": "Drop the shadow status column left by the last migration.",
    "decision_request": {
      "prompt": "Drop the jsonb shadow column?",
      "context": "It has had no reader since March and it doubles the row width.",
      "recommendation": "reject",
      "options": [
        {"id": "accept", "label": "Drop it now", "consequence": "Irreversible without a restore.", "style": "danger"},
        {"id": "reject", "label": "Drop it after v3", "consequence": "One more quarter of dead bytes.", "style": "primary"}
      ],
      "evidence": [{"label": "migration sketch", "anchor": "s:migration-sketch"}],
      "impact": "high"
    }
  }
]
```
