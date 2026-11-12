# D3. The rule book that already exists: every standing instruction the person has given

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

Principle 4 of the method is "decide once": every answer the person gives is also a rule, kept so that the question is never asked again. He has already given hundreds of such rules. They are scattered through memory notes and instruction files. The design needs to know what they are, what shape they take, how they came about, and above all whether writing them down actually stopped the mistake from happening again.

## Sources (read-only)

- Memory notes: `~/.claude/projects/*/memory/*.md` (each has a name, a type, a date, and usually "Why" and "How to apply").
- Instruction files: `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, and any `CLAUDE.md` or `AGENTS.md` at the top of a project under `~/projects/` or `~/orca/workspaces/`.
- Skills written for his setup: `~/.agents/skills/*/SKILL.md` and `~/.claude/skills/*/SKILL.md`. Read the headings and any rule lines only.
- Handover notes: `/Users/changlee/projects/agent-annotate/shared/agents/handoff-*.md`.
- If `DATA/corpus/m1max.jsonl` exists when you reach step 3, use its `human` rows. If it does not exist yet, do steps 1 and 2, then wait for it up to 40 minutes, checking every 10. If it never appears, finish without step 3 and say so.

## Build

1. `DATA/corpus/rules.jsonl`, one row per distinct rule: `id`, `text` in plain words (one sentence), `source_file`, `date` first given, `project` or `global`, `kind` (how to talk to him; what he must approve; what a helper may decide alone; how work is checked; which tool or machine to use; taste and look; safety limit; other), `born_from` (a correction after a mistake; an answer to a question; stated up front; unknown), the incident behind it in one sentence, and `duplicates` (ids of rows that say the same thing elsewhere).
2. Group the rules. Which are really about this one person and would carry to any project and any helper? Which are about one tool's quirks? Which are permissions (who may do what without asking)?
3. Repeats: for the 40 rules most clearly born from a correction, search the `human` rows dated after the rule for the same correction made again. Record `violated_after`: count, dates, and how long after. Use a script to find candidates and read each candidate before counting it.

## Findings file

`docs/design/from-zero/research/d3-rules.md`:

- how many distinct rules, by kind, by where they live, and how many are duplicates;
- how many came from a correction, from an answer, or were stated up front;
- how many would carry to any project (the person's own preferences);
- how often a written rule was broken again, and what the broken ones have in common (too long, wrong place, not loaded, vague, in conflict with another rule);
- how many rules contradict another rule, with the pairs;
- the 30 rules that matter most, in plain words, as the seed of the new rule book;
- what a rule needs to carry to actually prevent a repeat.

## Done means

`rules.jsonl` exists; the repeat check covers 40 rules or says why not; every number names its command.
