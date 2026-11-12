# B1. One baseline for the headline number: cycles to done today

Follow `docs/design/from-zero/briefs/common-data.md` and read `docs/design/from-zero/briefs/wave2-m1max.md`. They override anything below.

## Why

Six workers each rebuilt goals for one project and counted how many times each goal came back to the person. Their rows are in `DATA/goals/a.jsonl` to `f.jsonl`, their findings in `docs/design/from-zero/research/g-a.md` to `g-f.md`. Together that is about 80 goals and about 770 returns. The design needs one combined, honest baseline, and it needs to know which part of the new method would have removed which returns.

The six workers did not count identically. Your first job is to make them comparable.

## Do

1. **Reconcile.** Read the six findings files and the scripts each worker left in `DATA/goals/`. Write down how each defined a goal, a cycle and par, and where they differ. Apply one rule to all rows: a cycle is one time the work came back to him and he sent it on (a typed message to a helper, or a round of answers sent from a review page, counted once for each goal it touched). Where a file cannot be brought to that rule, say so and keep it separate.
2. **Combine.** One table of all goals: project letter, size, cycles, par, cycles by cause, whether there is a clear first statement and a clear acceptance, calendar days, words he typed.
3. **Report**, overall and per project, with the spread (median, quartiles, worst):
   - cycles per goal against par, for all goals and separately for the goals that have both a clear start and a clear acceptance;
   - cycles by cause; and for each cause, the share of all cycles and of his typed words;
   - how cycles relate to size, to calendar days, and to whether the goal had "done" checks written before work;
   - what the first statement lacked, by kind: things he knew and did not say; things nobody knew yet; things already written down that the helper did not use;
   - the ten worst goals: what happened, in three lines each, paraphrased.
4. **Map each cause to the part of the method that addresses it**, and estimate, with the assumptions stated and a low and a high figure, how many of today's cycles each part could remove:
   - the agreement before work (intent said back, "done" lines, what only he decides);
   - checks by something other than the maker before he is shown anything;
   - the rule book (he had already said it);
   - defaults inside authority he already gave;
   - the watch (stalls and silence caught by something other than him);
   - one doorway and one record (he was carrying messages, or re-supplying what was written down).
   Then say what is left that nothing in the method removes: decisions that are truly his, and discovery that could not have been known up front.
5. **Check the method's par rule against reality.** Par is 2 per goal plus 1 for each decision of taste that needs something to look at first. For the goals that went best, was par achievable? What would par have had to be for the large goals? Should par depend on size or kind?
6. **If label files exist** (`DATA/labels/m1max-a.jsonl`, `m1max-b.jsonl`), cross-check: do the labels on his typed messages tell the same story about causes as the goal paths do? Report agreement and the largest disagreement. Do not wait for them.

## Output

- `DATA/baseline/goals-combined.jsonl` and the script that builds it.
- `docs/design/from-zero/research/b-baseline.md`, under 130 lines, numbers first. Name no project other than agent-annotate; use the letters A to F as the goals files do.

## Done means

Every number names its command; the reconciliation rules are written down; the estimates in step 4 state their assumptions and give a range, not a point; and you say plainly how far these lower-bound counts can be trusted.
