# M5. The combined machine, and how to build it in stages

## Read first

1. `docs/design/from-zero-20261112.md`, revision 2: the method, thirteen principles.
2. The four machine designs in `docs/design/from-zero/machine/`: `record-first.md`, `check-first.md`, `office-first.md`, `capsule-first.md`.
3. The three critiques of them in `docs/design/from-zero/research/`: `machine-critique-breaks.md`, `machine-critique-cost.md`, `machine-critique-person.md`. Each ends with a proposed combination, a smallest first version, and tests to run before building. Two rank record-first first; the one that judged from the person's side ranks office-first first.
4. What the record shows, same folder: `t-labels.md` (the check before showing is the biggest lever; then the agreement; then sight), `p-stalls.md` (87 failures, 78 first noticed by him; a heartbeat is not progress), `d2-questions.md`, `d3-rules.md` (what a rule must carry), `d4-goals.md` (what a record needs so that cycles can be counted), `s-kinds-of-work.md` (twelve kinds, what a script can check for each, the trust ladder), `g-a.md` to `g-f.md` (how goals actually went), and `b-baseline.md`, `e-effort.md`, `r-replay-*.md` if present.
5. `docs/design/from-zero/research/x-what-exists.md`: what the available pieces can really do. Facts only.
6. `docs/design/from-zero/scenario.md`.

Do not open `docs/design/first-attempt-20261112/`.

## Write one file: `docs/design/from-zero/machine/combined.md`, at most 320 lines

### Part 1. The design (tool-free; a reader who knows none of today's tools must follow it)

1. **The idea**, in five sentences.
2. **Settle every fork** the critics raised, one line each: the fork, the choice, the reason. Where the three critics disagree, decide and say why.
3. **The record**: each kind of thing, its fields, who may write it. Include what `d4-goals.md` says is needed to count cycles: one goal identity from his first sentence through every agreement, showing, correction and acceptance, with a cause on each cycle. Show one goal from the test week at three moments.
4. **The runs**: every job, what starts it, what it reads (the exact packet), what it writes, script or helper, how long it lives.
5. **The gate**: the exact order of rules. Defaults of two kinds. The one interruption and its three-part test. The limit by minutes and age.
6. **The checks**: how a "done" line becomes a check, for each of the twelve kinds of work. What a script checks, what a second helper checks, what only he judges. How proof is bound to the exact result. How "not checked" is listed. How the check is shown to be able to fail. The pause before anything that cannot be undone.
7. **The watch**: every clock; progress on the result, not a pulse; what watches the watch; the state "I cannot see".
8. **Rules and trust**: case first; what a wider rule carries; how it reaches the helper at the decision and how its use is recorded; how a wrong rule is found and undone. Trust by kind of work: what earns it, the grant, the random sample, the reset.
9. **The way back**: stop, change the agreement, take back a permission, undo; reopening an accepted result and tracing what was built on it.
10. **Rhythm and absence**: sittings, what "goes ahead at 5 pm" means against them, pulling early, five days away and the return.
11. **The meter**: what is counted so that cycles per goal against par, days, his minutes, his words, interruptions, misses, discoveries and cost per goal come out with no extra work. One frozen rule for counting a cycle.
12. **Walk the 87**: take the kinds of failure in `p-stalls.md` and say, for each, what in this design catches it, how soon, and what he sees.

### Part 2. Building it

13. **The four needs and what could fill each**, from `x-what-exists.md`: for each need, the candidate pieces, what each lacks, and your choice with the reason. The minimum set that must be able to take part: helpers run by Orca, the Claude Code and Codex command-line helpers, a Beads board, and Windmill. Say plainly where something must be built new. Where the record should live and what happens when that computer is off.
14. **Stages.** The evidence says what to build first: the check before showing; then the agreement; then the watch and the glance; then rules, defaults and trust. For each stage: what is built; what he can do at the end of it that he cannot do today; what is measured to know it worked; what it replaces in today's way of working; and the paper tests from the critiques that must pass before it starts. Stage 1 must be small enough to build and use on real goals within days, must include the meter, and must beat today on cycles to done for the goals that go through it.
15. **Running both ways during the change.** How real work moves from today's way to this one, one project at a time, without stopping any project.
16. **Cost.** For a medium goal: runs, helper effort and wall-clock time against today's pattern. Use `e-effort.md` if present; otherwise use the 40-second start figure from `x-what-exists.md` and say what is assumed.
17. **What could make this fail**, the five most likely ways, and the earliest sign of each.

## Limits

Write only that one file. No code. No git commands that change anything. No installs. No changes to any tool, board, schedule, page, skill or instruction file. No messages to other sessions. Do not use the annotate skill. Create no beads. Plain words throughout.

## Finishing

Send `worker_done` once, with at most 15 lines: the idea, how you settled the three forks that mattered most, what stage 1 is, and the five ways it could fail.
