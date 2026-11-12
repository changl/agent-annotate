# M1. The machine, designed from the record outward

Your full brief is `docs/design/from-zero/briefs/m-machine.md`. Read it first and follow it exactly.

Your file: `docs/design/from-zero/machine/record-first.md`.

Your starting centre: **the record is everything.** Start from one append-only record of facts (a goal was stated; an agreement was accepted; a "done" line passed; a question was raised; he ruled). Everything else, including what he sees, what is waiting, what is stalled and what is trusted, is worked out from that record by small jobs that start, read, write one thing and end. Scripts do everything that needs no judgement. A helper is called only where judgement is needed, for one job, with exactly what it needs to read.

The known way this centre fails: the record becomes a swamp that every job must re-read; small jobs multiply until nobody can say why something happened; and judgement gets split across so many short runs that no run understands the goal. Your design must beat that or say honestly that it cannot.

You may leave the centre wherever the method demands it. Say where and why.

Where the brief says "reply", put that text in your `worker_done` message. Send `worker_done` once.
