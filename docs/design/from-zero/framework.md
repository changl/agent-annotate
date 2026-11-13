# Review surface: a rough framework

> **Rejected, 13 Nov 2026.** Chang: this frame looked more and more like agent-annotate and was at least as taxing. A lighter screen that followed it was rejected too, as worse and less flexible than agent-annotate. A new lead restarts from zero. Kept only as a record of what was tried; the findings about live readings near the end still stand as evidence.

## What it is

This is a review surface: a tool, never an assistant.
It builds on Orca, Beads, Windmill, Claude Code and Codex.
The goals are three passes or fewer, and never checking by hand that work continues.
Chang's desk with three screens comes first; then an iPad or laptop, with phone for exceptions.
This is enough to steer building and iteration; the screens will change through real use.

## The frame

Keep the same places to work, even when the material changes.

- **Queue:** named reviews, what needs Chang, the pass and estimated effort; where to start.
- **Stage:** the actual thing being judged, large enough to see and use.
- **Reference:** the accepted example, earlier version or surrounding context, kept beside the current thing.
- **Record:** the request, earlier answers, checks, delivery and acceptance; what happened and what remains.
- **Pass bar:** the current pass against the aim of three, decisions left and the way to Send.
- **Work in progress:** work by project and Mac, grouped as moving, needs you, stopped or contradictory, and cannot see.

Keep a short work line visible with the queue; open the whole view when needed.
At the desk, parts can occupy separate screens; on a smaller device, switch between the same parts.
The later surface notes supersede the earlier critiques and large-review findings: current work comes first, with an outline and find by name.

## What flexes

Change the stage to suit the judgement, while keeping the same notes, selection and place.

| Kind | What the stage shows | What “one at a time” means |
|---|---|---|
| Plan | Whole plan, order, coverage and choices | A section or claim, with the whole plan available |
| Architecture | Current and proposed paths, responsibilities and consequences | A choice or relationship, with alternatives nearby |
| Flow | Journey and related states across devices | A step or branch, with its entry and next states |
| Diagram | Whole map with readable detail and named paths | A box, connection or path within the map |
| Screens | Related states and accepted references at reading size | A state, keeping its matching reference |
| Behaviour | Playable motion, storyboards or a running preview | An interaction or moment that can be replayed or tried |
| Performance | Comparable runs, charts, conditions and limits | A result or proposed action, with its comparison |
| Data | Filterable records, actual fields, sources and missing values | A row or field, with the set still available |
| Occasional code | Actual changed lines, affected files and findings | A coherent change or finding, with its context |
| Decision | Question, visible options and consequences | A decision, answered independently |
| Status | Current ordered work, dated evidence and blockers | A piece of work and its latest evidence |

**Together** shows relationships and shared faults. **One** lowers the load without hiding the whole.
**Side by side** compares chosen items, or reference, before and now; each can still have its own answer.
Pictures stay whole at Fit. Viewing a recording and trying the real behaviour remain distinct.
These kinds come from Project B, Project C, agent-annotate and smaller projects; see [the census](research/v1-census.md), [Project B](research/v2-kinds.md), [other kinds](research/v3-kinds.md) and [review mechanics](research/v4-review-surfaces.md).

## What never changes

Feedback belongs at the thing being judged, with its version kept.

- Make a note at a picture, point, passage, row, connection, step, moment or number; never cover its evidence.
- Apply one correction to many named targets; show and let Chang edit that set and its exceptions.
- Stop on a shared fault and hold the rest; held does not mean checked or accepted.
- Let the question be wrong; an answer can replace its premise rather than choose an option.
- Always show what someone other than the maker checked, what the maker says, and what was not checked; flag missing or repeated pictures.
- Collect the notes, offer a last word and the exact outgoing message, then one Send per pass.
- Put needs-you work first and fold settled work, retaining earlier answers beside later changes.
- Counts say what is Chang's to do; pictures used as evidence and already settled questions do not inflate it.

## Passes

Aim for direction, the whole thing, then exceptions: three passes, without relabelling extra passes away.
A pass is a checked candidate shown for Chang's judgement on the same piece of work; reopening it or retrying Send adds none.
The [baseline](research/b-baseline.md) counts observed returns, often without clear acceptance; it is not an average of completed work.
[Checks alone](research/v5-passes.md) save 7–16 of 70 observed passes across 24 selected pieces.
With accept on a condition and direction first, 20–21 of those 24 pieces reach three or fewer [in the later study](research/v6-levers.md).
These are replays, not proof; some pieces have no recorded acceptance.
Setting values directly saved no whole pass on its own.
Accept on a condition means a specific correction can go to a separate checker without another judgement from Chang; keep its proof and a way to reopen.
The prototype records that condition but runs no checker and has no confirmation to show in these cases.
New scope part-way through is new work with its own count; it must not hide the earlier passes.
Replay with `python3 DATA/v3/passes/build.py` and `python3 DATA/v3/passes2/build.py`, separately; expand DATA to the private evidence folder named in the linked studies.
The [foundations](machine/on-foundations.md) define the work and showing links needed for future counting.

## Work in progress

The live reading can report observed signs and gaps; it cannot certify useful progress or acceptance.
It reads Orca sessions and tasks, discovered Beads records, review status, file and saved-conversation times, and stored Windmill results.
Show when it was read, what each state rests on and what could not be reached; stale coverage must age visibly.
Needs-you takes priority. A failed, blocked or void result overrides a successful job badge.
“Stopped” needs evidence: open work without a live owner, or overdue signs on work tied to a session.
The later live notes, changed that evening, supersede the earlier rule: a recently updated unlinked task may look moving; otherwise it is unknown.
Without a task-to-session link, continuing but unlinked work cannot be told apart from stalled work; that link is the addition that matters most.
No reading has yet caught an agent waiting on an approval; an untyped wait cannot safely be called one.
Undiscovered boards, custom agent locations and unavailable hosts stay visible as gaps; execution finished is not accepted.

## What it adds to the foundations

Extend the existing pieces with the [four small additions](machine/on-foundations.md).

- **Work/pass links:** join the Beads work record to each exact showing, check, feedback submission and explicit acceptance.
- **Checked showing and flexible viewing:** prepare evidence and decisions together on the existing review web surface.
- **Checks before showing and progress watch:** use Windmill to read real results, require separate judgement where needed and compare promised checkpoints with observations.
- **Feedback delivery:** extend the owner journal to reach the right host and session, retain receipts and give a replacement enough context to continue.

Build no new record service, board, scheduler, model launcher or assistant; use Beads, Orca, Windmill and existing review storage.

## Deliberately not settled

Iterate these on real work rather than treating the prototype as a finished specification.

- Exact layout at each width and which parts travel to another screen.
- Per-kind viewers beyond the first few, wording and the accepted shelf's rules.
- Phone comfort and dark theme.

## Not proved

Real-device use, following across Macs and three passes on new work remain unproved.
The live reading is also too costly to call settled: the brief's about 30 seconds of one processor core per reading is superseded by the later live notes.
Those notes measure 54 local processor-seconds plus about 4 on the other Macs per reading, with 26–34 seconds elapsed; no resident model is needed.

## Next step

Run one real piece of work through the surface from request to explicit acceptance.
Keep the exact showings, checks, feedback receipts and any new scope; count Chang's passes.
Use what happens to revise the framework and test whether work continues without his checking.
