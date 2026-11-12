# C2. Final critique of the round 2 designs, before they are shown to the person

Two combined designs and two deep studies came out of round 2. Within hours the person these are for will sit down for about twenty minutes, click through them, and decide. He has already rejected one attempt for being derivative of the tools he has today. Your job is to find what would embarrass us or mislead him, while it can still be fixed, and to tell the lead which design to put forward.

Another critic is doing this separately with a different emphasis. Do not look for their work.

## Read first

1. `docs/design/from-zero-20261112.md`, revision 3. Note the top section: the agreement no longer waits for him; a fully checked, undoable result is told, not asked; the centre is showing something cheap and checked, early.
2. `docs/design/from-zero/briefs/concept-v2.md`: what round 2 was asked for, the three unsolved problems, the stress week, the limits on every screen.
3. `docs/design/from-zero/research/critique-count.md`, sections "The frozen rule and its limits" and the first table: the counting rule used on round 1. Use the same rule, so round 2 can be compared with round 1.
4. The round 2 work in `docs/design/from-zero/concepts/`: `v2-sitting/` and `v2-letter/` (the two whole designs), `v2-showing/` (how each of twelve kinds of work is shown and marked) and `v2-return/` (coming back and staying in control). Each has `index.html` and `notes.md`. Open each prototype before reading its notes.

Do not open `docs/design/first-attempt-20261112/` or `src/`.

## How to look

Headless Chrome only. Desk: `--window-size=1280,900`. Phone: headless Chrome on this Mac will not lay out narrower than about 500 px, so frame the prototype in a 390 px iframe inside a small page of your own in `/tmp`. Light and dark. Each prototype has a self-check at `#check` and a "next moment" control: use them and distrust them. Drive every state yourself with a small headless script in `/tmp`. Open no tabs in a visible browser. Start no servers.

## Do

1. **Walk both whole designs through the stress week**: the 14 events of `docs/design/from-zero/scenario.md` plus the additions in the round 2 brief (things that move; a bad day; five days away; a week opened twice; forty goals; day 30 with a wrong rule and a lost grant). For each event: what he sees, what he must do, what could go wrong. Mark `missing` and `faked` honestly.
2. **Count both by the frozen rule.** Give the table beside round 1's numbers.
3. **Check revision 3 is really followed.** Any item that still asks him to agree before ordinary work? Any acceptance of a result a check had already passed that could have been told? Any default that acts outside what he allowed, or on something that cannot be undone? Any "nothing needs you" shown while something is unseen or waiting? Any word of the method on a screen (par, cycle, gate, counterpart, ledger)? Any id, helper name or computer name above the level he asked for?
4. **Judge the three unsolved problems**: showing and correcting a thing that moves without leaving the doorway; coming back; rhythm. For each, in each design: solved, partly, or not, with the state where you saw it. Say what from `v2-showing` and `v2-return` has not yet been merged into each whole design and should be.
5. **Find real defects** in the screenshots: overflow, collisions, cramped touch targets, weak contrast, text cut off, states that cannot be reached or left, dead buttons, broken keyboard paths on the desk, anything that differs between light and dark. Give the state and the size for each.
6. **Find what would mislead him.** Anything the prototype shows as working that could not work as drawn. Anything that depends on a phone feature, a notification, or a recording that is assumed and not shown. Anything a careful person would call wishful.
7. **Compare the two whole designs** and say which to put forward as the main one and why, what the other does better, and whether the difference between them is now only a matter of feel.

Then go deepest on the emphasis in your task message.

## Output

One file, named in your task message, under `docs/design/from-zero/research/`, at most 180 lines, with these parts in this order: the verdict in five lines; the count table; a **punch list** of things to fix before he sees it, most serious first, each with the file, the state, the size and what is wrong; what is still unsolved; the comparison.

Write nothing else in the repository. No git commands that change anything. No messages to other sessions. Do not use the annotate skill. Create no beads.

## Finishing

At most 12 lines: which design to put forward, the five most serious items on the punch list, and what remains unsolved.
