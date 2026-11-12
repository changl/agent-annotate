# D1. The human layer: every message the person typed

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

About 62 GB of agent transcripts exist on three Macs. Almost all of it is tool output. The design needs the thin layer where the person and a helper actually met: what he said, what he was answering, what he got back. Later workers classify that layer. Your job is to extract it with a script, exactly and completely. No model judgement in the extraction.

## Sources

- Claude Code: `~/.claude/projects/*/**/*.jsonl` (M1 Max: 2,493 files, 5.6 GB).
- Codex: `~/.codex/sessions/**/*.jsonl` (M1 Max: 9,022 files, 5.9 GB).
- M5 Max holds 19 GB and 32 GB of the same two kinds. M1 Max 16 holds a little.
- `DATA/scripts/inventory.py` shows how projects were named from the working folder. Reuse or improve it.

## Build

One script, `DATA/scripts/extract_human_layer.py`, standard library only, that reads transcripts from the Mac it runs on and writes one JSON object per line to standard output, each with a `kind`:

1. `kind: "turn"`, one per message that entered a session as the user side:
   - `id` (stable: mac + session + index), `mac`, `agent` (claude or codex), `project`, `cwd`, `session_id`, `file`, `ts`, `turn_index`.
   - `origin`, by fixed rules: `human` (typed by the person), `orca_brief` (a dispatched task brief), `orca_wake` (an orchestration wake or mail notice), `hook` (hook or system-reminder text only), `continuation` (a compaction summary), `command` (slash command or its output), `subagent_prompt` (a prompt written by a parent agent), `other`.
   - `text` (full for `human`; first 600 characters for the rest), `words`, `has_paste` (true if it carries pasted content).
   - `prev_assistant_tail`: the last 1,500 characters of visible assistant text before it. `next_assistant_head`: the first 1,500 characters of visible assistant text after it.
   - `seconds_since_prev_assistant`: how long the helper waited for him.
2. `kind: "session"`, one per transcript file: `mac`, `agent`, `project`, `session_id`, `file`, `start`, `end`, `model`, `role` (direct, coordinator, worker or subagent, by fixed rules, with the rule that fired), counts of human turns, assistant turns and tool calls, tokens in, out and cache-read where the file has them, number of compactions, number of API errors, number of orchestration wakes, `longest_gap_minutes` between any two events, `ended_how` if it can be told.
3. `kind: "ask"`, one per structured question the helper put to the person (Claude's AskUserQuestion calls and anything equivalent in Codex): the question, the options, which was marked recommended, the answer, any typed text, seconds waited.

Requirements:

- Deterministic. Same input, same output.
- Skips unreadable lines and counts them. Never crashes on one bad file.
- Has a `--self-test` that runs on three small built-in samples.
- Has `--since YYYY-MM-DD` and `--limit-files N` for quick runs.
- Drops the text of any row that matches a secret pattern, and counts those.

## Run

1. M1 Max, all files: write `DATA/corpus/m1max.jsonl`. Use `nice -n 19`.
2. Check: read 100 random `human` rows and 50 random non-human rows. Report how many were given the wrong `origin`. Fix the rules until fewer than 2 in 100 are wrong, and say what the remaining errors are.
3. Then M5 Max, with nothing written on that Mac: `ssh m5max "nice -n 19 python3 -I -" < DATA/scripts/extract_human_layer.py > DATA/corpus/m5max.jsonl`. If the script needs arguments, pass them after the `-`. Then the same for `ssh m1max16`.
   - If SSH fails, say whether the Mac is offline or asleep, or the login was refused, and skip that Mac. Do not try to fix SSH.
4. Write `DATA/corpus/README.md`: the schema, the origin rules, and the counts.

## Findings file

`docs/design/from-zero/research/d1-human-layer.md`, with these counts per Mac and per project (top 15), and overall:

- sessions by role; human turns; words he typed; median and 90th percentile words per human turn;
- how the user side of sessions splits by origin (how much is the person, how much is machinery);
- structured questions asked, answered, and answered with the recommended option;
- how long helpers waited for him: median, 90th percentile, and the count over one hour and over one day;
- human turns per day and per hour of day, for the last 60 days (when does he sit down, and for how long: a "sitting" is a run of his turns with gaps under 20 minutes);
- sessions with API errors, compactions, or gaps over 30 minutes while a turn was running.

Say plainly what the transcripts cannot tell us.

## Done means

- The three corpus files exist (or a clear note on why a Mac was skipped) with the README.
- The origin error rate is measured and under 2 in 100.
- The findings file has every count above, each with the command that produced it.
