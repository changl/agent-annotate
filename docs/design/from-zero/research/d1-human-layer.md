**D1: 25,834 transcript files; 3,628 human turns; 265,762 input words across 3 Macs.**

Human turns are 2.53% of 143,657 user-side entries. Counts include pasted material, selected answer labels and client context inside user input; they are not measured keystrokes. Tool results are excluded except recognized structured human answers.

Native structured questions: 390 asked, 275 joined to recorded answers, 57 answers matching an explicitly recommended option. Implicit defaults and unstructured later prose are not inferred.

Last 60 days: 1,620 human turns in 419 defined sittings; 217 have one turn. Observed span median/p90 is 0/33.9 minutes, which cannot measure reading or actual attention.

All counts/tables below come from command C0, run from DATA with the findings path made absolute to the workspace. Machine-readable counts, coverage counters, source inputs and every histogram are also in `DATA/corpus/human-layer-counts.json`.

C0: `nice -n 19 python3 -I scripts/analyze_human_layer.py corpus/m1max.jsonl corpus/m5max.jsonl corpus/m1max16.jsonl --through 2026-11-12 --seed 20261117 --output corpus/human-layer-counts.json --findings /Users/changlee/orca/workspaces/codex/annotate-first-principles/docs/design/from-zero/research/d1-human-layer.md`

Origins H/B/W/K/C/X/S/O = human / Orca brief / Orca wake / hook / command / continuation / subagent prompt / other. Roles D/C/W/S = direct / coordinator / worker / subagent. Q = asked/answered/recommended. Wait = median/p90 minutes; >1h/>1d counts; n timestamped gaps. These are gaps since visible assistant text, not proof a helper was waiting. Sitting = last60 turns/sittings/singletons; median/p90 span and sum in minutes. Problems = sessions with API errors / compactions / a >30-minute gap while a turn was marked running.

| Scope | Sessions (D/C/W/S) | Human turns | Words; median/p90 per turn | Origins H/B/W/K/C/X/S/O | Q | Wait | Sitting | Problems |
|---|---:|---:|---:|---|---:|---|---|---:|
| Overall | 25834 (396/188/19591/5659) | 3628 | 265762; 35/154 | 3628/2966/10494/54841/3087/236/68384/21 | 390/275/57 | 4.27/256.24; 567/77; n=3240 | 1620/419/217; 0/33.9; sum=5,622.96 | 293/860/72 |
| m1max | 11550 (149/107/8881/2413) | 1314 | 93378; 37/155 | 1314/1025/4680/23192/1469/108/30908/13 | 231/199/46 | 7.66/447.52; 267/34; n=1179 | 387/187/114; 0/24.12; sum=1,380.44 | 246/297/50 |
| m1max16 | 101 (21/2/68/10) | 66 | 3274; 18.5/87 | 66/45/7/113/6/0/34/3 | 3/0/0 | 2.71/327.9; 8/3; n=47 | 20/15/10; 0/13.46; sum=47.09 | 1/2/0 |
| m5max | 14183 (226/79/10642/3236) | 2248 | 169110; 35/152.3 | 2248/1896/5807/31536/1612/128/37442/5 | 156/76/11 | 4.07/127.37; 292/40; n=2014 | 1213/314/173; 0/26.88; sum=3,771.54 | 46/561/22 |
| project:FastLane Drive | 4378 (65/48/2100/2165) | 827 | 53963; 21/134 | 827/1921/7246/23278/104/162/3268/3 | 53/29/3 | 4.06/9.84; 31/2; n=763 | 801/209/147; 0/17.9; sum=2,186.43 | 45/199/3 |
| project:connelly | 1774 (40/46/196/1492) | 588 | 38783; 35.5/149.9 | 588/155/686/1855/109/22/5359/5 | 166/162/31 | 9.14/606.27; 139/25; n=530 | 0/0/0; —/—; sum=0 | 151/170/43 |
| project:leadory | 9335 (40/31/7958/1306) | 400 | 37148; 43/194.8 | 400/210/1572/9668/2625/0/39997/0 | 7/4/0 | 8.87/305.41; 76/1; n=347 | 9/4/2; 4.03/9; sum=17.46 | 0/194/4 |
| project:i-want-to-set-up-a | 38 (2/0/0/36) | 302 | 8226; 20.5/49 | 302/0/0/70/0/0/5926/0 | 0/0/0 | 3.59/231.21; 51/7; n=300 | 0/0/0; —/—; sum=0 | 2/4/0 |
| project:dealcenter | 174 (15/2/62/95) | 190 | 15468; 37/141.6 | 190/0/0/149/151/0/2636/0 | 0/0/0 | 6.08/55.83; 14/2; n=171 | 0/0/0; —/—; sum=0 | 0/22/0 |
| project:projects | 358 (43/11/178/126) | 181 | 14181; 41/192 | 181/31/33/440/36/8/176/1 | 29/10/4 | 8.79/633.11; 37/10; n=134 | 157/84/55; 0/15.12; sum=393.39 | 19/27/3 |
| project:rebex | 399 (9/8/315/67) | 162 | 14683; 56/199.9 | 162/208/573/970/12/26/267/0 | 32/18/3 | 5.24/370.59; 30/6; n=148 | 150/72/41; 0/20.14; sum=516.76 | 2/39/4 |
| project:agent-annotate | 95 (12/12/38/33) | 126 | 9001; 53/136.5 | 126/46/143/648/19/10/52/0 | 13/12/6 | 17.52/415.95; 29/0; n=109 | 118/73/53; 0/19.66; sum=377.23 | 3/7/3 |
| project:New project | 14 (10/0/0/4) | 84 | 7894; 61.5/140.6 | 84/0/0/35/0/0/488/0 | 13/5/2 | 5.3/250.55; 19/0; n=74 | 21/12/10; 0/7.17; sum=38.43 | 0/5/0 |
| project:pitchpoint | 151 (3/5/67/76) | 73 | 7946; 93/205 | 73/16/98/197/0/0/78/0 | 31/11/0 | 14.91/241.38; 16/1; n=65 | 30/22/16; 0/4.66; sum=50.79 | 0/67/2 |
| project:crunchbase | 40 (3/2/15/20) | 69 | 3524; 29/107.8 | 69/17/16/139/7/0/37/0 | 1/1/0 | 2.21/44.22; 4/0; n=62 | 0/0/0; —/—; sum=0 | 1/3/0 |
| project:i-want-you-to-do-some | 8 (2/0/0/6) | 56 | 3833; 56/127 | 56/0/0/13/0/0/48/0 | 0/0/0 | 24.56/253.64; 18/3; n=54 | 0/0/0; —/—; sum=0 | 0/2/0 |
| project:hermes | 14 (3/2/0/9) | 46 | 1525; 18/57.5 | 46/0/0/27/0/0/9/0 | 0/0/0 | 2.25/67.89; 5/2; n=41 | 0/0/0; —/—; sum=0 | 0/2/0 |
| project:human-by-intent | 48 (2/2/4/40) | 41 | 3298; 70/156 | 41/0/74/275/0/5/72/0 | 5/3/0 | 113.06/3,854.93; 24/7; n=38 | 41/26/12; 0/4.52; sum=49.6 | 1/4/4 |
| project:orca:parrotfish | 18 (2/2/0/14) | 36 | 3198; 39/176.5 | 36/0/0/34/1/0/24/0 | 10/5/1 | 8.84/199.9; 8/0; n=32 | 36/18/12; 0/21.39; sum=121.03 | 0/7/0 |

Daily vectors run from 2026-09-14 through 2026-11-12 inclusive (60 positions); hourly vectors run 00–23 (24 positions), America/Los_Angeles. A sitting joins consecutive turns with gaps strictly under 20 minutes, across sessions/Macs. Top 15 projects rank by human-turn count; unresolved Orca cwd groups retain `orca:` names.

| Scope | Human turns per day | Human turns per hour |
|---|---|---|
| Overall | 17,12,4,3,6,4,5,17,1,7,6,3,8,33,47,80,206,45,34,62,29,13,15,16,5,9,8,0,18,35,4,8,13,3,11,3,5,10,37,33,13,12,27,19,16,52,37,27,24,54,282,10,13,22,13,0,32,43,44,5 | 114,57,33,30,40,30,30,31,66,102,122,123,73,60,85,60,58,60,36,48,71,53,91,147 |
| m1max | 5,4,1,0,3,4,5,8,1,0,0,0,0,6,0,17,27,3,13,4,17,3,11,0,0,9,2,0,0,0,0,0,9,0,3,0,1,2,9,10,1,5,5,0,3,39,37,25,23,6,12,3,1,6,12,0,9,5,14,4 | 33,9,2,0,0,0,0,5,19,18,39,51,19,12,13,12,16,14,8,17,17,15,29,39 |
| m1max16 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,2,0,1,0,0,0,1,2,0,0,0,0,4,0,0,0,0,0,0,0,0,2,0,0,1,0,0,0,0,0,0,0,1,3,1,0,0,0,0,0,0,1,0,0 | 1,0,0,0,0,0,0,0,0,4,2,4,3,0,0,0,1,2,0,0,0,0,0,3 |
| m5max | 12,8,3,3,3,0,0,9,0,7,6,3,8,27,47,62,177,42,20,58,12,10,3,14,5,0,6,0,14,35,4,8,4,3,8,3,4,6,28,23,11,7,22,19,13,13,0,2,0,45,269,7,12,16,1,0,23,37,30,1 | 80,48,31,30,40,30,30,26,47,80,81,68,51,48,72,48,41,44,28,31,54,38,62,105 |
| project:FastLane Drive | 0,2,3,3,0,0,0,9,0,7,6,3,0,0,11,28,165,0,4,2,0,1,0,1,0,0,0,0,0,31,4,8,4,3,8,3,4,6,27,16,11,4,7,6,8,13,16,7,16,45,275,7,2,6,8,0,1,5,2,3 | 50,33,28,29,40,30,29,27,42,65,70,58,28,37,25,26,21,11,10,12,31,12,28,59 |
| project:connelly | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:leadory | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,7,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,0,0,0,0 | 0,0,0,0,0,0,0,0,1,5,3,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:i-want-to-set-up-a | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:dealcenter | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:projects | 5,4,1,0,0,0,0,0,0,0,0,0,8,7,7,1,7,1,5,24,22,6,3,4,0,4,0,0,0,0,0,0,0,0,0,0,0,2,1,4,1,0,2,0,1,8,5,2,4,4,2,0,3,0,0,0,6,2,0,1 | 10,2,0,0,0,0,0,1,4,5,12,6,7,4,25,11,7,4,2,4,8,6,16,23 |
| project:rebex | 0,5,0,0,0,0,0,0,0,0,0,0,0,0,12,8,1,0,0,0,0,0,0,5,5,0,6,0,14,4,0,0,0,0,0,0,0,0,0,0,0,0,15,13,2,1,0,0,0,0,0,3,3,3,0,0,1,12,37,0 | 8,7,2,0,0,0,0,0,2,5,14,17,8,0,1,1,7,11,3,8,9,16,19,12 |
| project:agent-annotate | 0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,1,0,2,2,0,0,5,2,0,0,0,0,0,9,0,0,0,1,2,9,8,1,3,3,0,3,24,16,12,3,1,4,0,0,0,0,0,1,0,4,1 | 10,1,0,0,0,0,0,3,6,3,14,23,4,2,5,7,2,5,2,3,3,6,7,12 |
| project:New project | 0,0,0,0,3,0,0,0,0,0,0,0,0,4,0,7,7,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 3,1,0,0,0,0,0,0,2,0,1,4,0,0,1,0,2,0,0,0,0,0,0,7 |
| project:pitchpoint | 12,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,6,3,1,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 2,0,0,0,0,0,0,0,0,1,1,0,2,2,0,1,3,0,1,4,0,4,1,8 |
| project:crunchbase | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:i-want-you-to-do-some | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:hermes | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 |
| project:human-by-intent | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,5,0,3,0,0,2,6,0,2,0,0,0,0,5,11,0,0,7,0,0,0 | 4,0,0,0,0,0,0,0,0,3,0,4,2,3,5,6,2,1,1,3,3,2,1,1 |
| project:orca:parrotfish | 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,10,17,0,9,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 | 9,6,1,0,0,0,0,0,3,1,1,1,1,0,2,0,0,2,0,3,2,0,4,0 |

Origin QA (C1: the seeded `--sample` mode of C0, manual source/envelope review and the named decision ledgers; corrected samples are rechecked/refilled, not an independent error bound):

| Mac | Human checked/errors | Nonhuman checked/errors | Observed errors per 100 | Ledger |
|---|---:|---:|---:|---|
| m1max | 100/0 | 50/0 | 0 | DATA/corpus/audit-m1max-verified-decisions.json |
| m1max16 | 66/1 | 50/0 | 0.8621 | DATA/corpus/audit-m1max16-verified-decisions.json |
| m5max | 100/1 | 50/0 | 0.6667 | DATA/corpus/audit-m5max-verified-decisions.json |

Remaining origin error: `m1max16:01a1138b-5ea9-70c2-8014-0a4cf57a85a0:a2972ad57bae:1` — explicit third-person installation handoff; recorded human, expected subagent_prompt (C1).

Remaining origin error: `m5max:01a0f431-7c36-7081-bc3f-b2dcb3a8cf65:88df12158973:4` — legacy retirement control instruction; recorded human, expected subagent_prompt (C1).

No known origin mismatches remain unless named in those ledgers. The executable origin rules and schema are in `DATA/corpus/README.md` and `DATA/scripts/extract_human_layer.py`; full input text stays in DATA. The extractor uses fixed rules and literal sender fingerprints, with no model classification.

Coverage (C0): 0 unreadable lines, 0 file failures, 12,543 secret-pattern source rows, 849 redacted input turns, 3 additional emitted-text guard redactions, 0 human turns without timestamps. Matched source rows keep metadata/word counts and drop their text.

Limits: physical sender identity is not authenticated. Unmarked relays, one-word continuation prompts and manual noninteractive exec prompts can be misattributed; role labels describe rules, not verified authority. The reviewed human samples include 18 bare continuations with unverified writer identity (C1); the error rate measures visible envelopes, not true authorship. File copies/replays are not globally deduplicated, and Mac means file location. External page feedback, clicks, reading, voice/keyboard effort and actual attention duration are not recoverable from these input rows. Recorded API/compaction markers are incomplete evidence of all failures; running-gap flags are a start/final-event proxy and cannot establish continuous execution. No result proves a goal was completed or accepted.
