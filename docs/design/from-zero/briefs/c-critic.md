# C. Walk the four concepts through the test week

You are a critic. Another critic is doing the same job separately. Do not look for their work.

## Read first

1. `docs/design/from-zero-20261112.md`: the method, with its ten principles.
2. `docs/design/from-zero/scenario.md`: the test week and what is counted.
3. Any files present in `docs/design/from-zero/research/`: what the record shows about how the person actually works. Use them to judge realism.

Do not open `docs/design/first-attempt-20261112/` or `src/`.

## The four concepts

`docs/design/from-zero/concepts/thread/`, `sitting/`, `picture/`, `letter/`. Each has `index.html` (a clickable prototype) and `concept.md` (the designer's own account). Open each prototype yourself before reading its `concept.md`, so your first impression is the person's, not the designer's.

Render with headless Chrome only, at 390 px and 1280 px, light and dark, and read the screenshots. Step through every state the prototype offers. For example: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --screenshot=/tmp/critic-<you>-<concept>-390.png --window-size=390,844 file://<path>`. If a state can only be reached by clicking, read the file's script and drive it with a small headless script of your own in `/tmp`. Open no tabs in any visible browser. Start no servers.

## For each concept

1. **Walk all 14 events as the person.** For each event write one line: what he sees, what he must do, and what could go wrong. Mark an event `missing` if the prototype does not carry it, and `faked` if it is asserted in text but not actually designed.
2. **Count the week** using the list at the end of the scenario file. Count from the prototype, not from the designer's claims. Where your count differs from theirs, say why.
3. **Score each of the ten principles** 0 to 3 (0 broken, 1 weak, 2 met, 3 met in a way worth copying), with one line of evidence each.
4. **Find where it will fail in real use.** Think about: day 30 rather than day 1; a bad day with three stalls and a flood; a week he does not open it; a result that is visual and needs comparing; a correction that is hard to point at; ten goals becoming forty; the moment he stops believing "nothing needs you".
5. **Readability and craft.** Is the most important thing the most visible? Can each screen be taken in at a glance? Plain words? Anything cryptic? Does it work at both sizes and in both themes? Anything that looks like a familiar work-tracking or chat product?
6. **Name what is worth stealing** from this concept even if the concept as a whole loses.

## Then, across all four

- Rank them, with your reasoning in five lines.
- Describe the combination you would build: which idea from which concept, and what none of the four solved.
- State anything in the method itself that the concepts show to be wrong, missing or impossible to draw.

## Output

One file: `docs/design/from-zero/research/critique-<your-name>.md`, under 200 lines, with a comparison table first. Write nothing else in the repository. No git commands that change anything. No messages to other sessions. Do not use the annotate skill. Create no beads.

Finish with at most 12 lines: your ranking, your combination, and the single biggest unsolved problem.
