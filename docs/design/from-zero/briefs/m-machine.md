# M. The machine behind the screen: one whole design

You are one of three designers working separately on the same problem. Each starts from a different centre (yours is in your task message). The three designs will be traced through the same test week and compared. The best parts are then combined.

## Read first

1. `docs/design/from-zero-20261112.md`: the method.
2. `docs/design/from-zero/plan.md`, sections 2 and 3: the counterpart is a role and not a long-lived helper; the nine parts.
3. `docs/design/from-zero/scenario.md`: the test week.
4. Any files present in `docs/design/from-zero/research/`: what the record shows. Use what is there. Do not wait for more.

Do not open `docs/design/first-attempt-20261112/`. Do not design around any existing tool: design what the method needs, then, in the last section only, say what could fill each need.

## The problem

Design how the work actually runs, so that:

- one sentence from the person becomes an agreement he can accept in about a minute;
- the work then proceeds in silence across several computers and several kinds of helper;
- nothing reaches him unless only he can decide it, and every question carries what happens if he does not answer, and when;
- every result is checked by something other than its maker before he sees it;
- a stall is caught by something other than him;
- every answer he gives becomes a rule that prevents the same question;
- trust earned for a kind of work reduces what he is shown;
- no part depends on a helper that stays alive or remembers. Helpers are cheap, forgetful, and should not judge their own work. A helper's effort costs little next to his attention, but it is not free: today the largest cost is helpers re-reading what they already knew and coordinating with each other.

## Deliver one file: `docs/design/from-zero/machine/<your-name>.md`, at most 260 lines

1. **The idea** in three sentences.
2. **What is kept in the record.** Each kind of thing, its fields, who may write it, and what is never stored. Show one goal from the test week as it would actually sit in the record at three moments.
3. **The runs.** Every job that happens: what starts it, what it reads, what it writes, whether a script or a helper does it, how long it lives, and roughly what it costs. Say which jobs need judgement and which never should.
4. **The gate.** The exact order of rules that decides whether something reaches him, waits for a sitting, goes ahead on a default, or is settled by a rule. Include the cap, expiry, and the narrow lane for what cannot wait.
5. **The checks.** How a "done" line written in plain words for him becomes something that can be checked. What a script checks, what a second helper checks, what only he can judge. How proof is kept and shown. How the checker is kept from rubber-stamping.
6. **The watch.** Every clock, what trips it, and what happens next, without a helper having to be awake.
7. **Rules and trust.** How an answer becomes a rule, how a rule is found again at the right moment, how a wrong or stale rule is caught, how conflicts between rules are settled. How trust is counted for a kind of work and what it changes.
8. **The meter.** What is counted, where, so that cycles per goal against par, his minutes and the cost per goal come out with no extra work.
9. **Trace the test week.** For each of the 14 events: what runs, what is written, what reaches him. One or two lines each.
10. **What breaks it.** Walk these failures and say what catches each, and how soon: a helper stops silently; a helper waits on something that never comes; a message is lost; a helper says "done" falsely; a helper restarts and forgets; two helpers change the same thing; a computer is off; the record itself is unreachable; a rule is wrong; he answers nothing for five days.
11. **Cost.** For a medium goal: how many runs, and how the effort compares with today's pattern of a long-lived coordinating helper plus workers. Where does your design spend more, and where less?
12. **Taking part from anywhere.** How a helper of any kind, on any computer, joins, gets work, and reports, and what it must be able to do at minimum. The minimum set that must be able to take part: helpers run by Orca, Claude Code and Codex command-line helpers, a Beads board, and Windmill. You may read their `--help` and public documentation, read-only. Say what each could fill, and what none of them fills.
13. **The smallest first version** that would already beat today on cycles to done, with the meter in it. What is in, what is left out, and what it would take to build.
14. **Your three weakest points**, and anything in the method that you now think is wrong.

## Limits

Write only your one file. No code. No git commands that change anything. No installs. No changes to any tool, board, schedule, page, skill or instruction file. No messages to other sessions. Do not use the annotate skill. Create no beads. Plain words: a reader who has never seen any of today's tools must be able to follow sections 1 to 11.

## Finishing

Reply with at most 15 lines: the idea, the three choices that most set your design apart, your weakest points, and what you think is wrong in the method.
