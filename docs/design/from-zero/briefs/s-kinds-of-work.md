# S. Kinds of work: how each can be shown, and how each can be checked

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

Two parts of the method depend on knowing what kinds of work the person actually asks for:

- **Showing.** Principle 7: he is shown the thing itself, not a report about it, and he corrects by pointing at what is wrong. What "the thing itself" is differs for a phone app screen, a web page, a background job, a report, a price change, a document, a fix to something broken.
- **Trust.** Principle 9: trust is earned for each kind of work. That needs a list of kinds that he would recognise and that is stable enough to count against.

Nobody has listed the kinds. You are deriving the list from what he has actually asked for.

## Sources (read-only)

- Boards: in each project folder under `~/projects/` and each repo under `~/orca/workspaces/`, `bd where`; where a board answers, read items with `bd list --json` and `bd show`. Never create, claim, edit or close anything.
- `DATA/corpus/items.jsonl`, `questions.jsonl`, `pages.jsonl` if present when you start (other workers are producing them).
- Merged pull requests and release notes in the repos, with `git log` and files only.
- The repos themselves, to see what kinds of thing get built (phone apps, web apps, command-line tools, background jobs, documents).

## Do

1. **Sample.** Take at least 300 finished pieces of work from the last 90 days, spread across all projects that have records. Say how you sampled.
2. **Sort them into kinds.** Let the kinds come from the sample. Aim for a list short enough to hold in the head (about 8 to 15). Name each kind in plain words he would use. For each kind: share of the sample; typical size; how often it came back for rework if the record shows it.
3. **For each kind, answer:**
   - What is "the thing itself" that he would look at? Where can it be seen: on a phone, on a desk, both? How long does looking take?
   - Can he point at what is wrong on it? How?
   - Which "done" lines could a script check with no judgement (it builds, tests pass, the number matches, the page loads in time)?
   - Which could a second helper judge (matches the agreement, reads well, follows his known preferences)?
   - What is left that only he can judge?
   - What proof would let him accept without looking at all, once trust is earned?
   - How reversible is it if accepted wrongly: undone in a minute, undone with effort, or cannot be undone (money, data, messages sent to real people, a public release)?
4. **Find the hard cases.** Kinds where the thing cannot easily be shown (a background job, a speed-up, a security fix), where checking needs a real device or a real account, or where a wrong acceptance cannot be undone. For each, say what the least-attention honest showing would be.
5. **Decisions of taste.** From the questions data if present: which kinds of work produce decisions that only he can make, and what are those decisions about (look, wording, price, risk, direction)?

## Findings file

`docs/design/from-zero/research/s-kinds-of-work.md`, under 150 lines: the table of kinds with shares; the showing-and-checking table per kind; the hard cases; where taste decisions come from; and a proposed first trust ladder (which kinds could soonest move from "show everything" to "show a sample" to "do and report", and which never should).

Raw rows in `DATA/kinds/`.

## Done means

At least 300 pieces of work sorted, every kind has all seven answers, and the sorting was re-done blind on 60 rows with the agreement rate reported.
