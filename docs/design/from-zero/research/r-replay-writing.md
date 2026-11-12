# R — Blind agreement writing

**36 goals; A 36, B 36, C 23: 95 blind agreements, all at most 180 words; 13 C skips.**
Counts and timings: `python3 -I DATA/replay/replay.py check`. DATA is `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`.
Selection: `nice -n 19 python3 -I DATA/replay/replay.py build`; all six files existed at first inspection and were checked again before selection finished. No wait or remote read.

| File | Chosen IDs |
|---|---|
| A | a04, a05, a08, a12, a13, a14 |
| B | B02, B04, B05, B06, B10, B12 |
| C | C01, C02, C08, C10, C13, C14 |
| D | D01, D02, D04, D07, D09, D11 |
| E | E02, E06, E07, E11, E14, E15 |
| F | F1-2, F2-1, F3-1, F4-1, F4-2, F8-1 |

Rejected 44 other goals: duplicate first statements, opaque assent/context fragments, or the six-per-file size/outcome cap. Exact per-ID reasons: DATA/replay/selection.json and README.md.
Purposive coverage; size is analyst-assigned. F supplies no large goals; B’s only final acceptance starts with an opaque assent and was rejected. Open/censored paths do not establish failure.

| Way | Count | Words min / median / max | Seconds min / median / max |
|---|---:|---|---|
| A | 36 | 160 / 167.5 / 177 | 9.829 / 20.329 / 41.689 |
| B | 36 | 162 / 170.0 / 179 | 10.157 / 17.607 / 24.207 |
| C | 23 | 161 / 168 / 180 | 13.754 / 18.444 / 22.115 |

Summed successful process duration: 1855.043 seconds, not concurrent-batch elapsed time. Includes sandbox/CLI startup, account/network/model response and exit; excludes packet preparation and judging.
Writers: native `codex exec --model gpt-6.1-sol -c model_reasoning_effort="medium"`; nice -n 19; initially one, then two at a time. Exact per-run argv, stdin, duration and event path are in DATA/replay/agreements.jsonl.
Batch commands: `nice -n 19 python3 -I DATA/replay/replay.py run --partition 0` and separately `--partition 1`; earlier sequential pilot/run commands are retained in README.md.
The Node launcher aborted before a model run. One 185-word output was rejected and rerun fresh with a tighter target; two C runs were redone after excluding source rows containing review-access URLs. The 180-word ceiling is enforced. No output text was edited. Failure receipts remain under setup-failure/.

Descriptive comparison: at least 32/95 agreements reserve a decision topic explicitly raised in later owner messages; at least 2/95 state an explicit assumption later contradicted. Counts: `python3 -I DATA/replay/report.py` after `python3 -I DATA/replay/compare.py`; quotes and cycle indices in observations.jsonl.
Unmatched cases remain unobserved, not negative labels. These lower bounds describe stated topics/assumptions only; no estimate of cycles saved is made.

What each way could not know:

- A: project referents, current state, private preferences and any subsequent discovery/correction; no hindsight title or actual par supplied.
- B: A’s project-state gaps remain. The 30 mandatory seed rules are undated and retrospective: later-learned preferences may be present. Dated extras use conservative earlier-day cutoffs and keyword matching (top 12), with scope/date reliability limits.
- C: only earlier dated snapshot excerpts; reported state may be stale, incomplete or wrong. No repository inspection or later outcome. Thirteen goals have no usable earlier reported state and skip C.

Blindness: fresh ephemeral /tmp runs; user config/rules ignored; memory disabled; global instructions, DATA, projects, workspaces and memory paths denied by macOS sandbox. Writers receive only protocol + packet through stdin; every successful trace has zero tool calls.
Two read-denial probes returned 1; exact probe commands/paths are in DATA/replay/blindness-probes.json. This enforces source blindness, not the historical validity of undated seeds or an information-flow proof against pretrained knowledge.

Audit: `nice -n 19 python3 -I DATA/replay/audit.py` checked 95 packets/2472 field comparisons; fixed-seed manual sample 50, observed provenance/date errors 0/50. Seven plainly machine-written human-labeled rows were excluded from project context. A context-purpose excerpt was corrected before that writer ran.
For judging, DATA/replay/README.md is the self-contained entry point, with full A/B/C packet examples, selection/rejection list, schemas, commands, all limits and file paths. Agreements and actual paths remain separate.
