# Design brief, round 2: one design from the best of four

Round 1 produced four separate concepts. Four critics walked them. Their verdicts agree on most things: the letter and the sitting are the strongest wholes; the picture has the best single screens and the best desk layout; the thread has the best direct marking. No concept solved three problems, listed below. Round 2 builds toward one design.

Your role in this round is in your task message. This file is what every designer in the round needs.

## Read first

1. `docs/design/from-zero-20261112.md`, revision 2. The method has changed since you read it: thirteen principles, a rhythm, a way back, one interruption with a three-part test, defaults in two kinds. Read all of it.
2. The critiques in `docs/design/from-zero/research/`: `critique-craft.md`, `critique-showing.md`, `critique-day30.md`, and `critique-count.md` if it is there.
3. What the record shows, same folder: `t-labels.md` (what his typed messages were), `p-stalls.md` (how work stalls and who notices), `s-kinds-of-work.md` (the twelve kinds of work he asks for, and how each is shown and checked), the table of question kinds in `d2-questions.md`, the complaints table in `d6-directing-helpers.md`, and "Wordings worth copying" and "Numbers worth knowing" in `d7-other-fields.md`.
4. The other three concepts: you may now open them all, prototypes and notes, in `docs/design/from-zero/concepts/`. Take anything that is good.

Still do not open `docs/design/first-attempt-20261112/` or `src/`. Nothing of any existing product is inherited.

## What the evidence asks of the screen

- **The check is the biggest lever.** A third of his avoidable messages came from work that reached him wrong or unfinished. So a showing must make three things plain at a glance and without reading a report: someone other than the maker checked it; against which "done" lines; and what was not checked.
- **He is the watch today.** He noticed 78 of 87 failures first. The glance must make silence believable: how fresh, what it cannot see, and what it will do about it.
- **More than half of what he types is properly his.** New goals carry the most words. Saying a goal must be effortless, by voice or keys, and must never feel like filling a form.
- **Screens, layouts and behaviour are most of what he is asked about.** The largest kinds of question are how the work should behave (574), accepting a screen or layout (564) and correcting an instruction (470). Most showings are of things that move or that depend on width and device.
- **The safeguards cost reading.** Adding them raised reading by 13% to 28% in round 1. Carry them without making him read them every time: a safeguard that has nothing to report should take no words.

## The three unsolved problems

1. **Showing and correcting a thing that moves, without leaving the one doorway.** A journey in a phone app. A web page at two widths. A route. A background job. A speed-up. And keeping the exact result, its proof and his pointing tied together, so that what he marks is what was checked.
2. **Coming back.** After five days away, after a week of skipped sittings, after a rule turned out wrong, after an accepted result was found bad and other work was built on it. A bounded, honest recovery: what changed, what was lost, what was decided for him, what waits, in an order he can act on, without making him the curator of rules and permissions.
3. **Rhythm.** When he sits; what "goes ahead at 5 pm" means against that; how he pulls something early; how the one interruption is kept rare and how each one is accounted for.

## The stress week

Use the test week in `docs/design/from-zero/scenario.md` and add these, so the design is tested where round 1 was not:

- **Things that move.** "Faster sign-up" is a three-screen journey in the phone app. "Price page" must be judged at phone and desk width. "Move photos to cheaper storage" is a background job with nothing to look at. "Speed up the test run" is a number. Thursday's release cannot be undone once it is out.
- **A bad day.** Three helpers stall (two recover unseen, one moves a promise). Seventeen questions arrive. One thing cannot wait. One accepted result is found wrong, and a second goal was built on it.
- **Five days away**, then the return. And one week in which he opens it only twice.
- **Forty goals**, not nine, across four projects.
- **Day 30.** Thirty rules learned, one of them wrong. Trust granted for two kinds of work; one grant is lost after a miss.

## Limits on every screen

- Plain words. No word of the method on any screen: no "par", "cycle", "gate", "counterpart", "ledger" unless he would say it himself. No ids, helper names or computer names above the level he asks for.
- Phone first at 390 px, and a desk layout at 1280 px that is designed for a desk. Light and dark, both designed.
- One self-contained file. No network requests. System fonts. Keyboard works on the desk. Contrast and touch sizes meet the norms.
- A self-check: opening the file with `#check` runs through every state and reports on screen.
- Screenshots: headless Chrome will not lay out narrower than about 500 px. For the phone width, frame your page in a 390 px iframe inside a small page of your own in `/tmp`. Open no tabs in a visible browser. Start no servers.

## Deliver, in the folder your task message names

1. `index.html`.
2. `notes.md`, at most 80 lines: what you built; what you took from each concept; how each of the three unsolved problems is answered, or an honest statement that it is not; the count for the stress week by this rule: places to look, interruptions, things held in his head including habits, words he must read to act (separately from words merely available), words typed and spoken, taps, decisions (only-his, and acceptances of what a check had passed), minutes; your three weakest points; and anything in revision 2 of the method that still cannot be drawn.

Write only inside your folder and `/tmp`. Do not change the round 1 folders. No git commands that change anything. No messages to other sessions. Do not use the annotate skill. Create no beads.

## Finishing

Reply with at most 15 lines: what you built, the count, how you answered the three problems, your weakest points.
