# Rename orders.status

Owner: payments-platform · Draft · 2026-09-26

## Why

`orders.status` carries two meanings. Checkout writes payment states
(`pending`, `authorized`, `captured`) and the warehouse writes fulfillment
states (`picking`, `shipped`, `delivered`) into the same text column. Every
reader branches on who wrote the row, and last month's refund bug (INC-4471)
came from a report that read `shipped` as "paid". We want one column per
meaning: `payment_state` belongs to checkout, `fulfillment_state` to the
warehouse.

## Readers and writers

| Service | Reads | Writes |
|---|---|---|
| checkout-api | yes | payment states |
| warehouse-worker | yes | fulfillment states |
| reporting (dbt) | yes | no |
| support-console | yes | no |

## Plan

1. Add `payment_state` and `fulfillment_state`, both nullable text.
2. Dual-write: each writer sets `status` and its new column.
3. Backfill the 41M existing rows (about 9 GB) by splitting `status` values
   by writer.
4. Move readers to the new columns, one service per deploy.
5. Stop writing `status`, then drop it.

Migrations go through sqitch; every step ships as its own change with a
revert. Peak write load is 1.8k orders/min between 17:00 and 21:00 UTC, so
nothing that locks the table runs in that window.

## Open questions

1. **Dual-write window.** One week covers the checkout and warehouse deploys.
   Two weeks also covers the reporting team's fortnightly dbt release. Which?
2. **Backfill method.** A batched `UPDATE` script (10k rows per batch, about
   6 hours, no lock) or a one-shot `CREATE TABLE AS` swap in the Sunday
   maintenance window (about 40 minutes, table locked)?
3. **When to drop `status`.** Drop it in the release that stops writes, or
   keep it read-only for a quarter in case an unknown reader turns up?
