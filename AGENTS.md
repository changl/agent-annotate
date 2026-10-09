# Agent instructions

## Issue tracking: Beads

This project tracks work in [Beads](https://github.com/gastownhall/beads) (`bd`). The board lives on the maintainer's private server; `.beads/` is not committed. If `bd where` fails in your checkout, you have no board: say so and do not track the work anywhere else.

- Use the board when a task is a bug, feature, revision, or multi-step change. Skip it for questions, reviews, and one-off turns.
- Find the issue with `bd ready` or `bd search "<words>"`, take it with `bd update <id> --claim`, and close it with `bd close <id> --reason "<what shipped, PR or commit>"`.
- File work you discover with `bd create "<title>" -t bug|task|feature -p <0-4> --deps discovered-from:<id>`.
- `bd prime` prints the full workflow.
