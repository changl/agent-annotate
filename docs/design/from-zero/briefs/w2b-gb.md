# GB2. Project B again, now with its chat

Read `docs/design/from-zero/briefs/w2b-m5.md`, then `docs/design/from-zero/briefs/g-goals.md`.

The first count for Project B (`docs/design/from-zero/research/g-b.md`, data in `DATA/goals/b.jsonl` and `DATA/goals/b-working/`) rebuilt 12 goal paths with 115 returns, almost all from review pages, because its chat on M5 Max was missing. That chat is now in `DATA/wave2/m5max-new-snapshot.jsonl`: about 750 messages he typed, under the project name `FastLane Drive`.

Do:

1. For each of the 12 existing paths, find the chat that belongs to it: his original request if it is there (the first count had no opening for most paths), and every later typed message about that goal. Recount the path by the one rule in `docs/design/from-zero/research/b-baseline.md` ("Unit"). Report old and new counts side by side, and how many paths now have a clear opening and a clear acceptance.
2. Rebuild up to 12 further goals that exist only in the chat, by the same rule, spread across small, medium and large.
3. Give each cycle one cause, using the same eight causes as the baseline.
4. Say what the chat changes about the picture: are the causes the same as on the pages? Does he type different things in chat than he answers on pages?

Outputs: `DATA/goals/b2.jsonl` and `docs/design/from-zero/research/g-b2.md` (under 100 lines), in the same shape as the first count so the two can be added. Done means: every recounted path shows old and new, a second pass over three paths chosen at random gives the same count within one, and every number names its command.
