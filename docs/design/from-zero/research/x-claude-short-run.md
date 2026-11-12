# X, addition: what one Claude short run costs

The fact-sheet worker could time Codex short runs (about 40 seconds for a tiny run) but not Claude ones, because its test replaced the configured sign-in. The lead measured one on M1 Max, 12 Nov 2026, from this project's folder with nothing changed:

`/usr/bin/time -p claude -p "Reply with the single word: ok" --output-format json`

| | |
|---|---|
| Wall-clock time | 5.25 seconds |
| Time to first word | 2.1 seconds |
| Context loaded before the one-word answer | 29,845 tokens (standing instructions, memory and tools for this project) |
| Notional list-price cost of that load | $0.24 |

One run only, so it is a first figure and not a distribution. What it shows: a Claude short run starts in seconds, but every run carries about 30,000 tokens of standing context before it reads its packet. For short runs to stay cheap, that standing context has to be cut down for them, or they have to run from a folder that carries none.
