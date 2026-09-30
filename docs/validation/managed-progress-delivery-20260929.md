# Managed project progress and completed-round delivery

## Confirmed causes

Fastlane Drive serves the project-local prototype at
`/Users/changlee/projects/FastLane Drive/local-stack/proto-server/annotate-server.py`
on M5Max, port 8814, behind HTTPS 8456. Its assets date from July and its
slug-prefixed capability endpoint returns 404. All seven v11 decision requests
expose only `["comment"]`; letter choices are prose, not controls. The installed
canonical CLI reports 2.19.0, but does not own this prototype server. Its source
checkout has unrelated uncommitted changes, preserved during this work.

## Resulting architecture

- The package compiles standard page content, decision controls, persistent
  project modules and native disclosures. Shared generated-page content styles
  update at serve time. Custom diagrams remain content extensions.
- Publishing or claiming binds the current Orca owner process and terminal.
  Only completed feedback rounds enter the durable delivery journal. Ownership
  validation, duplicate suppression, uncertainty and acknowledgment are explicit.
- GitHub tagged releases ship one tested wheel, checksums and a build identity.
  Each enrolled machine stages its own environment; activation preserves state,
  owners and routes, and rolls back failed restarts. Custom skill conflicts are
  preserved and reported. Prototype forks require explicit migration.
- Weekly reports derive local review/delivery metrics and existing transcript
  cost without model runs or consuming feedback cursors. Remote aggregation and
  browser timing/resource-open instrumentation remain future work.

## Validation

Unit and browser suites exercise the actual HTTP server, content rendering,
clickable choices, persistent project information, keyboard navigation, owner
validation, interrupted delivery, deployment rollback and report preservation.
The independent review found and fixed an inbox cursor race, metadata alias
exposure, stale owner-binding fallback, report revival ordering, local skill
path collisions and revived-server import isolation.

The frozen agent-facing benchmark compares main at 4fbe796 with the candidate:
three Opus/medium runs per scenario, v1-page and round-2. Both refs pass 6/6.
Candidate median cost changes are -5% for v1-page and +3% for round-2; median
time changes are +17% and +5%, respectively. This small sample does not prove
a speed or cost improvement. Source skill text falls from 7,945 to 5,687
characters (-28.4%). Full results are in bench-v220-20260929.json.

## Rollout boundary

Automatic updates apply only to enrolled canonical runtimes and registered
servers. They do not overwrite dirty source checkouts, project-local forks or
already-loaded agent context. Fastlane needs its project owner to migrate the
prototype and bind the page from that owner's live session. Existing reviewer
answers, history, URL and port must survive that migration.
