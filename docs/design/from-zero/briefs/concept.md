# Design brief: what the person sees

You are one of four designers working separately. Each has a different starting premise (yours is in your task message). The four results will be walked through the same test week and compared. The best ideas are then combined.

## The job

Design what one person sees and touches when they get work done through many helpers using the method in `docs/design/from-zero-20261112.md`. Read that whole file first. Then read `docs/design/from-zero/scenario.md`: the test week your design must carry.

The aim is not a good-looking tool for managing work. The aim is the least attention a person can spend to turn what they want into finished, correct results made by others. The best screen is the one he does not need to open.

## Nothing is inherited

- Do not open `docs/design/first-attempt-20261112/`, `src/`, or any existing product's interface in this repository or on this machine. A first attempt failed because it copied what exists.
- Do not borrow the look, layout or vocabulary of any existing work-tracking, chat or developer tool. No boards of tickets, no ids, no helper names, no machine names, no status badges for their own sake. If you find yourself drawing a familiar product, stop and go back to the principles.
- Plain words only. A goal is shown in the person's own words.

## Deliver, in `docs/design/from-zero/concepts/<your-folder>/`

1. `index.html`: one self-contained file. No network requests, no libraries from the web, system fonts. A prototype he can click through, with the content of the test week in it.
   - Phone first (390 px wide), and a desk layout (1280 px). Light and dark. Both must be designed, not just flipped.
   - It carries all 14 events of the test week. Events that are about time passing can be stepped through with a small "next moment" control that is clearly outside the design.
   - It has a look of its own: type, spacing, colour and motion chosen for calm and for reading at a glance. Meet contrast and touch-size norms. It must work with a keyboard on the desk.
2. `concept.md`, at most 70 lines:
   - the idea in one sentence;
   - the core components: each thing that exists on the screen or behind it, what it is for, and which gap (intent, sight, trust) it closes;
   - how each of the ten principles shows up, in one line each, and which principle your design serves worst;
   - the count for the test week, using the list at the end of the scenario file. Count honestly from your own prototype;
   - what you chose to leave out, and what you would cut next;
   - the three weakest points of your own design;
   - where you departed from your premise, and why.

## How to work

- Start from the events, not from screens. For each event ask: does the person need to see anything at all? What is the least that would do?
- Decide how it reaches him when he is not looking (event 8) and how that is kept rare. Decide what he sees after three days away (event 12). Decide how a correction is made by pointing at the thing (event 4). These three are where designs of this kind usually fail.
- Render your file and look at it before you finish. Take screenshots with headless Chrome at 390 px and 1280 px, in light and dark, and read them. For example: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --screenshot=/tmp/<your-folder>-390.png --window-size=390,844 file://<path>`. Fix overflow, collisions, cramped touch targets and weak contrast. Do not open tabs in any visible browser. Start no servers.
- Write only inside your own concept folder and `/tmp`. No git commands that change anything. No messages to other sessions. Do not use the annotate skill. Create no beads.

## Finishing

Reply with at most 15 lines: the idea in one sentence, your component list, your counts for the week, your three weakest points, and anything in the method itself (the from-zero file) that you think is wrong or missing now that you have tried to draw it.
