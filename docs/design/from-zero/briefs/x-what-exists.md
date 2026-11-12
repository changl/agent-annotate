# X. What the available pieces can actually do: facts only

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

The new method is being designed without regard to any existing tool. Tools are chosen last, each only if it fills a need well. When that moment comes, the choice must rest on what each piece can really do today on these computers, not on memory or marketing. You are writing the fact sheet. You are not designing anything and not recommending anything.

The method needs four things:

1. something that holds the record: goals, agreements, "done" lines, rulings, rules, results, and every event, readable and writable from several computers;
2. something that starts short-lived helpers and checkers on the computers, gives each exactly what it should read, and collects what it wrote;
3. something that runs checks and clocks with no judgement in them, on a schedule or on an event, at no helper cost;
4. something that shows the person a few simple screens, the same on a phone and a desk, takes a spoken or typed line from him, and can reach him with a rare push.

## The pieces (the minimum set that must be able to take part)

Orca; the Claude Code command-line helper; the Codex command-line helper; Beads; Windmill. Also note, briefly, anything else already installed on this Mac that plainly fills one of the four needs (for example Git, Tailscale, a database, a notification service).

## For each piece, establish from its own `--help`, its installed documentation, its public documentation, and safe read-only commands

- What it is, in two plain sentences.
- Which of the four needs it could fill, and how well. Be specific about the mechanism.
- **Short runs.** Can it start a helper for one job with a given prompt and a given set of files, have it write a result, and end, with no person present? How long does a cold start take? What does the smallest run cost? How does it report failure? You may measure this with at most three tiny runs per helper kind, in a fresh folder under `/tmp`, with a prompt that asks for one line of output. Record the timings.
- **Across computers.** Can it start or reach work on the other Macs? What must be running there? What happens when a Mac is asleep?
- **Events and clocks.** Can it run something when an event happens (a file changes, a message arrives, a job ends, a web request comes in) or at a time? With what delay?
- **Asking a person.** Does it have any built-in way to put a question to a person and wait, with a default or a deadline? Reachable from a phone?
- **Records.** What can it store, with what structure, and can other pieces read and write it? Does it keep history?
- **What it knows about a helper's state**: working, waiting, stopped, failed. How reliable is that, from its own documentation and from the notes below?
- **Limits and known trouble**: from its documentation, and from the memory notes in `~/.claude/projects/*/memory/` that record what has gone wrong with it here. Paraphrase; give the note's name.
- **What it cannot do** that the method needs.

## Hard limits for this task

Read-only against every live system. Do not create, change or delete any Windmill script, flow, schedule or app; any board item; any Orca worktree, run, terminal or setting; any hook, skill or instruction file. Do not send any Orca message except your own `worker_done`. Never run a plain `orca orchestration check`: it takes mail away from its owner. The only things you may create are files in `DATA/exists/`, your findings file, and the tiny timing runs in `/tmp`.

## Findings file

`docs/design/from-zero/research/x-what-exists.md`, under 180 lines:

1. A grid: the four needs down the side, the pieces across the top, each cell one line: how it would fill the need, or "cannot".
2. One short section per piece with the facts above.
3. The timings you measured.
4. Gaps: needs, or parts of needs, that no piece fills.
5. Surprises: abilities that are there and unused, or assumed and absent.

## Done means

Every cell of the grid is filled from a source you can name, the short-run timings are measured for both helper kinds, and nothing is recommended.
