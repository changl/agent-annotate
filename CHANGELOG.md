# agent-annotate — changelog

## 2.24.0

One page per project (#9), a version guard (#10) and page consolidation (#11).

- Keep one project page with Review, Library, Findings, and Plans; record explicitly requested second-page exceptions and list Linked pages. Preserve --standalone as an alias.
- Add finding fixes with proof, independently versioned Markdown/HTML plans, Library metadata and the library alias, findings-set questions, and category filters for CLI/MCP reads.
- Keep the three provider/plugin skills identical and document category authoring, shared Send, proof, and compatibility.
- Replace the 2.21–2.23 front end with the accepted single-page design: project-name header, Review · Library · Findings · Plans · Linked pages tabs, one feedback rail, one History tagged by tab, one Send grouped by tab, stock daisyUI light/dark with lighter dark-mode borders, Roboto and the chosen font sizes, A/F shortcuts. Main's reviewer access, origin boundary, round history and Linear links are kept.
- Library edits use Quill with comments on selected words, History with Restore, alternatives, and a 409 on edits made over a newer revision. Findings show proof and can be reopened. Plans show changes since the previous revision.
- Proof files and assets are served with `Content-Security-Policy: sandbox` and `nosniff`; only images and PDF display inline, other types download, and the CLI accepts an allowlist of proof types.
- Send reports partial failures, keeps failed items pending, and records each round's delivery result.
- `annotate consolidate PROJECT/SLUG --from PROJECT/PAGE:TAB …` merges a project's pages into one new page (one Review document; plans, findings sets and Library items for the rest), keeping every comment, verdict, reply, decision history, number, read state and submitted round. `--dry-run` prints the counts per page and per tab. The old pages are kept, refuse writes, redirect to their tab and show read-only with `?archived=1`.
- A Review version is gated only by Review items, and re-asking a Review card never rewrites a plan card on the same anchor.
- `annotate doctor --versions [--json]` exits 1 when `annotate` on PATH, a skill directory, the Codex plugin or a running page server differs from the installed release, and prints the fix commands without running them. Page servers log the mismatch at start and report it in `/api/capabilities`; the prompt hook and `workspace` show one line per session. Skill install stamps now record the build id.

## 2.23.0

- Rounds restores read-only access to saved documents and immutable submitted answers.
- Verified Linear issue URLs turn ticket references into links across the workspace.
- Dark mode separates sections and rows with theme backgrounds and borders.
- Lightweight PR checks and versioned releases replace duplicate full-suite CI runs.

## 2.22.0

- Feedback opens to unified actionable cards; Progress holds status and reference tabs are read-only.
- Compact headers, panels, popovers and scrollable tables use consistent dark/light themes.
- Copy supports locally bundled WYSIWYG editing, immutable proposals and collapsed history.
- Explicit feedback sends use durable owner delivery; unanswered agent questions and draft rounds are excluded.
- Increased the HTTP request queue for simultaneous theme/editor asset loads.

## 2.21.0

- One canonical project workspace across providers and worktrees; concise progress updates and no-op saves.
- Shared daisyUI dark/light UI, Progress/Feedback tabs, short supporting tabs, accessible named owner, editable decision explanations.
- Default Tailscale Funnel with private external review links and Copy link; scoped route migration and cleanup.
- Submitted-round-only notifications, stable cross-provider decisions and reviewer identity, complete packaged skill references.


The entries from v2.19 down are the live skill directory's history, carried
into the repo unchanged. The package release below is the first one cut from
this repository.

## v2.20.4 Review reliability and request boundaries (unreleased)

- Project information uses a compact native disclosure inside the document,
  scrolling away with content. The redundant header Project toggle is removed.
  Expansion preferences and pins remain correct across versions and srcdoc.
- Generated and legacy managed pages retain a visible title; the shell title
  follows the selected version. Tables preserve words and scroll when needed.
  Decision numbers remain stable across live, archived and resolved history,
  including the CLI's real store loader.
- Iframe messages check both sender origin and window, with exact target
  origins for regular and nested srcdoc pages. Foreign navigation cannot receive
  review commands or inject feedback.
- Server requests enforce recorded hosts, origins and mount boundaries;
  human reviewer identity comes from a declared loopback reviewer or trusted
  proxy. Arbitrary email headers no longer establish a reviewer. Version and
  legacy comment paths stay within their artifact root, while safe legacy
  basenames with spaces and Unicode remain supported.
- Internal state, hidden files and backups are excluded from static serving.
  JSON/settings writes preserve permissions and avoid predictable temp paths.
  Mounted roots redirect to their directory URL without losing query state.
- Runtime updates leave user-managed skills alone. The Codex MCP plugin uses
  the installed CLI instead of independently launching moving Git main.
  Installation, reviewer identity and component removal are documented.
- CI no longer persists checkout credentials; benchmark archive extraction
  fails closed if safe tarfile filters are unavailable.
- Reconstructed anchor metadata retains script-end escaping; authenticated
  Cloudflare API calls refuse redirects and create private, distinct backups.
  The development lock updates cryptography and PyJWT past the reviewed
  advisories without changing the installed MCP SDK version.

## v2.20.3 Fleet runtime and delivery observations (2026-09-29)

- Fleet snapshots combine local registered pages with an explicit remote page
  inventory. Collection uses bounded read-only requests, verifies TLS, refuses
  redirects, and exports only runtime, capability, owner-presence and latest
  delivery observations. Missing observations remain unknown.
- Existing weekly reports include enrolled fleet coverage without a model run,
  new service, reviewer text, or owner-session identifiers. Inventory labels and
  owner metadata are explicitly distinguished from attested host/live ownership.

## v2.20.2 Progress-page feedback store initialization (2026-09-29)

- Generated pages initialize a valid empty feedback store. Progress and weekly
  pages with no decisions can publish their next version without requiring an
  intervening browser write. Existing feedback is preserved exactly, including
  damaged stores that still need explicit recovery.

## v2.20.1 Weekly report publishing and capability preservation (2026-09-29)

- Owner status uses captured process identity when available, avoiding false
  inactive labels when a live session ID is absent from process arguments.
- MCP server construction supports both the 1.x FastMCP and 2.x MCPServer
  SDK entry points, with schema-generation checks.
- Staged updates preserve an installed MCP capability at its existing SDK
  version and validate server construction, rather than silently dropping it.
- Weekly reports reuse the standard complete publish options, fixing first
  publication on a configured transport. Existing report verification uses the
  same options and keeps ownership unchanged.

## v2.20.0 Managed progress and completed-round delivery (2026-09-29)

- Automatic Orca owner prompts for completed feedback rounds, with durable
  delivery IDs, current-owner validation, duplicate suppression, visible delivery
  states and separate owner acknowledgment. No agent-owned monitor is required.
- Persistent project links, progress and notes; native collapsible modules and
  author-written details fences. Shared content styles update generated versions
  at serve time; custom content remains an extension.
- Choice-authoring warnings and legacy custom-string options that render as
  actual controls. Keyboard-operable version navigation.
- Hidden tabs stop polling; visible refreshes cannot overlap. Conditional store
  and metadata responses avoid downloading unchanged history. Asset keys derive
  from content hashes, not install timestamps.
- Checksum-verified stable-release staging, owner-preserving activation and
  rollback, build/asset identity, and conflict-aware generated-skill refresh.
  Per-machine automatic checks are opt-in; prototype forks are not overwritten.
- Local weekly usage pages without a model run, including submission/delivery/
  acknowledgment metrics, failures, card quality and existing transcript cost.

## Earlier unreleased changes carried into 2.20.0

- **Routes follow a machine rename in both directions.** `revive` (every
  60 s under launchd) and `publish` on a live page re-run the route when the
  page's tailnet name differs from the machine's current one, without
  restarting the server. On 2026-09-27 the Mac went macbook-pro, m1max and
  back within hours, and each page kept whichever name it had.

- **A new version records where earlier items went; no resolve or carry
  calls.** `publish-version` (and `new --version vN --publish`) carries an
  earlier open item onto the new card with the same number, and resolves it
  at the first element that names it as `#N`. Only an item the new version
  never names still blocks. The bench caught agents resolving before v2
  existed and then hitting the publish gate. Benchmark, round-2, 6 runs a
  side, opus/medium: annotate failures median 1 to 0, turns 11 to 9, output
  tokens -13%, cost -11%, outcome 6/6 (main 5/6, one harness crash).

- **Before/after bench.** `scripts/bench.py` runs real `claude -p` sessions
  against main and a candidate build, each in a throwaway sandbox with its own
  state, bus, config, hook and skill, and prints tokens, cost, time, turns,
  annotate calls and failures, and outcome checks side by side. Agent-facing
  changes (skill text, CLI output, markdown format, gates) are gated on it.
  Scenarios `v1-page` and `round-2`; fixtures in `bench/`, not the package.
- **One card, with its context inside it.** The rail card and the body strip
  share one layout: `#N` and the prompt, the context in full (the "Why /
  details" disclosure hid it on 94% of cards), a "Recommended: <option>" line,
  a quoted excerpt of the first evidence anchor read from the page, the
  options as full-width rows with their consequence under the label and
  nothing preselected, then a collapsed "Evidence (n)" whose items preview
  their target in the card; "Go to" leaves a "Back to #N" marker on the target
  that returns to the card. In a generated page the strip replaces the baked
  question card instead of rendering under it, so a question appears once in
  the body; the baked card stays as the no-JavaScript fallback. Verdicts,
  rounds, Answer in words, notes and Request changes are unchanged.

- **Unchanged sections fold on v2+.** `new` compares each `##` section with
  the same section of the previous version and stamps the identical ones
  `data-unchanged-since`; the page opens them folded behind "Unchanged since
  vN — show". A section holding an open card or its evidence stays open, and a
  jump into a folded section opens it. No authoring change and no agent cost.


- **A broken Cloudflare route no longer withholds a working page.** With
  the tailnet URL primary, a failed `public` stage prints a one-line WARN and
  the URL; only `origin` and `tailscale` failures print NOT PUBLISHED.
- **One URL per page: Tailscale.** `publish` prints the tailnet URL as `URL:`
  and nothing else to choose from; 26 of 30 sessions had been handing over the
  Cloudflare URL because it was the only `URL:` line. `--public` (also on `new
  --publish`) adds the Cloudflare route for a reviewer outside the tailnet and
  prints it as `Public URL:`. Pages that already had a route keep it through
  publish and revive. The success output drops pid, port, transport, slug dir,
  bus and state paths; `status` has them.

- **Fewer failed rounds, less output.** Measured over 60 days of transcripts,
  62% of recent page rounds hit a gate error. `resolve`, `carry` and
  `addressed` print one line instead of the whole comment (about 530 tokens
  each; `--json` keeps it). A miss on the target anchor names the closest
  anchors in that version, or says the version has not been generated yet.
  Addressing or carrying an item the reviewer already confirmed is a no-op,
  not an error. A slug registered under two projects resolves to the one this
  session owns, or the only live one. `inbox` leaves out this session's own
  echo (cards it posed, items it resolved, its publishes) and prints a
  reviewer's answer whole; `--json` events carry `decision_text`.

- **`annotate cost` measures what agents spend on annotate, and prices a
  change before it ships.** A read-only scan of Claude transcripts (Codex
  with `--codex`) turns every annotate call and skill/reference read into a
  row: result tokens, the issuing turn's output tokens (read once per
  message id), CLI seconds, failure reason and the retry that followed. The
  report shows calls, failure rate, tokens and round medians per week (or
  per release, or between given dates) and per subcommand. `--estimate
  model.json` replays those past rows with smaller results or fixed
  failures and prints before and after totals.

- **Pages come back by themselves after a reboot or crash.** `annotate
  revive` restarts every registered page whose server is gone, on its recorded
  port, re-runs its route and keeps its owner (`publish` would have made the
  caller the owner). `annotate revive --install` runs it from launchd at login
  and every 60 seconds. A dead page's port stays reserved: `publish` no longer
  hands it to a new page.
- **Tailscale routes follow a machine rename.** The transport reads the live
  tailnet name and ignores serve entries keyed on an old one.

- **The page body and the rail always agree about a question.** Question
  cards are baked into the page when a version is generated. They kept reading
  "Answer it on the card" after the rail had moved the item to Addressed or
  Done. The shell now sends each card's live status, computed by the same
  `statusLabel()` the rail uses. The adapter stamps it on the baked card as
  the same label, dims cards that no longer need the reviewer, and hides
  their "Answer it" prompt. The skills say page text names items only as
  `#N` and never restates their status.
- **One number per item; answered and withdrawn items leave "Needs my
  review".** Chang, 2026-09-23 (the fourth report): one item showed as `#19`,
  `v5` and `d:q19` at once, and a card he had replied to still asked for his
  review.
  - The rail and the pin popover show only `#N`. The version chip and raw
    anchor ids are gone, and so is a legacy `Q10` prompt prefix that repeats
    its own number.
  - A reviewer's reply on an unanswered card now counts as the answer. It is
    stored as the `comment` verdict with `via: "reply"`, so the page, the
    hook, `cards` and round `undecided_ids` all agree.
  - `addressed_by_agent` now means done, not "needs my review". A card the
    agent addressed or withdrew without a verdict drops its buttons and is not
    undecided anywhere. A reviewer reply reopens it.
  - Needs a page-server restart.
- **A retired or unpublished page no longer notifies every session.** Retiring
  moves a page's row out of `state/<project>.json` and leaves its bus in place.
  The hook then found a bus with no owner on record and announced its whole
  backlog to every session that had never read it: retiring 14 pages on
  2026-09-23 sent old verdicts from la-plastic-email-tactics and
  windmill-runbook into an unrelated session. A bus with no registry row is now
  skipped (`ANNOTATE_HOOK_ALL=1` still shows it).
- **Section comments work over the tailnet address.** A page opened at its
  `*.ts.net` URL had no reviewer identity, and the shell refuses to open the
  comment composer without one, so a reviewer on that URL could answer cards
  but could not comment on any section. Every reviewer event on
  windmill-cheerticketing-plan-20260922 had been recorded as `anonymous`. The
  server now accepts the `Tailscale-User-Login` / `Tailscale-User-Name` headers
  that `tailscale serve` sets. It does so only on a loopback peer with a
  `*.ts.net` Host, and never on a request carrying Cloudflare headers, because
  the tunnel connector is itself a tailnet node. `tailscale serve` replaces a
  client-forged header with the real login, which was checked live. Cloudflare
  Access identity still wins when both are present. Needs a page-server restart.
- **A carried card asked a new question goes back to the reviewer.** When
  `ask` changes the question on a card that was carried into a newer version
  after it was answered, the old verdict moves to `decision_history`. The card
  reopens, gets a `reposed_at` stamp, and shows under "Needs my review" again.
  Before this, an Answer-in-words that asked "which session is that?" kept the
  re-asked card under "Waiting on agent", where the reviewer would never look.
  Re-running `ask` with the same question, or rewording a card inside the
  version where it was answered, still keeps the verdict. Needs a page-server
  restart.
- **Review rounds are one ordered, cumulative plan instead of another chat
  transcript.** Later-version sources now declare `full_plan: true` and
  `other_files_required`; the page renders that scope and warns when most prior
  sections disappear. Every response card has one stable integer `number`,
  lives in the final `Questions for Chang` section, and links back to plan
  evidence; rail, body, pin and CLI use the same `#N` order. Free-text
  **Answer in words** now counts as answered and waits on the agent, while a
  plain reply remains a remark. Generating vN no longer selects it before the
  publication/carry-over gate passes. Generated skills and Chang's global
  instruction make the page replace chat walls of text: chat carries only
  changed/needed/URL.
- **Earlier-round comments cannot remain in limbo.** `publish-version` now
  fails before changing `current.html` when any prior `open` or
  `addressed_by_agent` item lacks an explicit disposition. `annotate resolve`
  records the exact version and anchor where the answer landed; the item stays
  in origin-version history but no longer follows the reviewer as outstanding.
  `annotate carry` moves genuinely open work to a real anchor in the new
  version while preserving origin and carry history. Reviewer replies reopen a
  resolved item. Resolved cards are excluded from CLI/hook card totals, round
  submission and `undecided_ids`. `addressed` can no longer demote
  `user_confirmed` cards.
- **A reviewer can comment on a decision card, and long options fit** (D3).
  Three items from a reviewer's round-1 note on a live page, all in the
  decision surfaces:
  - **`comment` is the free-text answer verdict beside "Request changes".**
    The current UI calls it **💬 Answer in words**; it collapses the card,
    waits on the agent, and is not `undecided`. Plain thread replies remain
    available for remarks that do not answer the question.
  - **Option labels wrap.** A label longer than the rail used to widen the
    flex line to its own min-content width, pushing the button *and* its
    consequence line off the right edge of the screen. Buttons now wrap in the
    rail card and in the body strip, at every width.
  - **Clicking into a card's box goes to its location.** Focus landing in a
    reply, verdict note, "Request changes" or "Comment" box scrolls the
    document to that card's anchor, exactly as clicking the card does, without
    disturbing what is being typed. Every one of those boxes now also survives
    a re-render with its text, its open state and the caret intact.
  - **A custom option id posts the new `select` verdict** (`☑ Selected:
    <label>`) instead of `comment`, since picking one of the card's own
    options is a choice, not a remark. It answers the card and leaves it open.
    Against a server that predates `select`, the chrome posts the pre-D3
    `comment` text.
- **`annotate new <slug-dir> --from page.md` — a page costs one write** (D9).
  A small dependency-free markdown parser turns front matter, `##`/`###`
  headings, paragraphs, bullet and numbered lists, pipe tables, `kpi:` lines,
  fenced code and a ` ```cards ` block into `versions/<vN>.html` from the
  packaged `template.html`, with a `data-anchor-id` on every element and a
  matching `ANCHOR_REGISTRY` (`name`, `grp`, `parent`, `kind`). One run also
  writes `cards.json`, the `current.html` symlink, an idempotent
  `current.meta.json` history entry, `comments.json` and a copy of the source
  at `source/<vN>.md`, then prints the anchor count and the next commands.
  `--publish` and `--ask` run the real `publish` / `ask` code paths, so the
  markdown file to a published page with a posed round is two tool calls
  against a baseline of 6 minutes and 31, a bespoke `build.py` per page (one
  slug had fifteen) and a hand-written `cards.json`.
  - Anchor grammar is generated, not remembered: `s:<section>`,
    `s:<section>:<sub>`, `s:<section>:p<n>` / `li<n>` / `code<n>`,
    `tbl:<section>` with `:col:<header>` and `:row:<first-cell>`,
    `kpi:<label>`, `d:<n>`. Repeated keys dedupe with `-2`, `-3`.
  - A ` ```cards ` entry is rendered as a visible `.card` in the body — title,
    context, one line per option, a "Recommended" badge, impact and blocking
    chips — as well as written to `cards.json`. An entry that names an anchor
    the prose already mints is pinned to that element instead of duplicating
    the id, in either document order.
  - The run fails and writes nothing on duplicate anchor ids, zero anchors, or
    text between `</style>` and the first element — the CSS-outside-`<style>`
    mistake that shipped in nine published versions.
  - `annotate new --example > page.md` prints a document exercising every
    construct (32 anchors, 3 cards). Format reference:
    `references/building-pages.md` §1.
- **`install-skill --provider claude|codex --dest <dir>`** writes a skill
  directory from the package's own skill text, which now ships as package
  data under `src/agent_annotate/skills/`: `SKILL.md` with the invocation
  section rewritten to `annotate <cmd>` plus the `python3 -m
  agent_annotate.cli` fallback, the one set of `references/`, a
  `hooks/check-comment-bus.sh` shim that execs the packaged hook, and the
  Codex agent manifest. Atomic, idempotent, never deletes. The skills-org
  checkout that `~/.claude/skills/annotate` links to becomes a deployment
  regenerated by this command; it no longer holds runtime code.
- **projects.toml options reach the transport.** Every key in a project's
  section other than `transport`, `hostname`, `port_base` and `path_prefix`
  is passed to the transport on publish and unpublish, so a
  `cloudflare_tailscale` section can carry `env_file` and `tunnel_id` where
  the live transport used to hard-code them.

## v2.19.0 The live v2.19 skill as a package (2026-09-18)

Everything the skill-directory install shipped through v2.19 now lives in
`src/agent_annotate/`, alongside what only the repo had: `paths.py`, the MCP
server, the Codex app-server provider and the `doctor`, `sessions`,
`connect`, `disconnect`, `send`, `hook-check` and `mcp` commands.

- **Locations come from `paths.py` and default to the live roots.** The
  registry, cursors, leases, locks and logs sit under
  `~/.claude/annotate-state/state`, buses under `~/.claude/annotate-bus`, the
  hook goes into `~/.claude/settings.json` and the launcher into
  `~/.local/bin/annotate` — exactly where the 18 live slugs are. Override with
  `ANNOTATE_STATE_DIR` (alias `ANNOTATE_STATE_ROOT`), `ANNOTATE_BUS_ROOT`,
  `ANNOTATE_CONFIG_DIR`, `ANNOTATE_DATA_DIR`, `ANNOTATE_PROJECTS_TOML`,
  `ANNOTATE_CLAUDE_SETTINGS`, `ANNOTATE_SHIM_PATH`,
  `ANNOTATE_BUS_ARCHIVE_ROOT` and `ANNOTATE_TRANSCRIPT_GLOB`. `projects.toml`
  is read from `ANNOTATE_CONFIG_DIR` and, until it is moved, from the live
  skill's symlink. Relocating state to platform directories is a future
  migration command, never an install side effect.
- **Invocation.** `annotate` is the package entry point. Every printed
  invocation is `annotate …` only when the name on PATH runs this package (a
  `uv tool install` entry point, or the shim `install-shim` writes), and
  `<python> -m agent_annotate.cli …` otherwise. `publish` writes the shim only
  when the path is empty or holds a stale shim of ours; `install-shim` repoints
  a shim of ours, `--force` overwrites a foreign file, and an entry point is
  never touched. The hook registers as the packaged
  `hooks/check-comment-bus.sh` and recognises an existing registration of the
  skill-directory copy, so it never fires twice per prompt.
- **`--project` names the project.** The live CLI assigned it to the slug.
- **`monitor --provider codex-app-server --session-id <thread>`** delivers
  each `session_push` (now a round) into a Codex thread before advancing the
  monitor cursor, so a failed turn is retried from the bus. `connect` and
  `disconnect` wrap it; both take `<project>/<slug>`.
- **`prune-bus`** wraps the live archive script. **`eval`** takes
  `--state-dir`, `--bus-dir` and `--transcript-glob` so it can run over a
  fixture or a copied estate.
- **`doctor`** reports the invocation, what `annotate` on PATH resolves to,
  every root, the hook script and whether it is registered, and the session
  id, alongside `node`, `lsof` and `codex`.
- **Cloudflare transport** keeps the repo's configuration-free `_auth`
  (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
  `ANNOTATE_CLOUDFLARE_TUNNEL_ID`, `ANNOTATE_CLOUDFLARE_HOSTNAME`, or
  `ANNOTATE_CLOUDFLARE_ENV_FILE`), accepts the older env-file spellings as
  fallbacks, and preserves an explicit non-loopback origin across re-publishes
  as the live transport did.
- **Skills.** `skills/claude/annotate/SKILL.md` is the live v2.19 text with
  the packaged invocation; its `references/` hold the live references plus the
  one `interaction-contract.md`. The Codex skill and plugin say the same thing
  in Codex wording and point at those references.
- **Tests.** 147 unit tests, up from 94: the decision API, batch idempotency,
  rounds, per-session hook cursors, compact inbox, `ask`, publish-version
  history, shim install, hook registration, eval over a fixture, and the
  monitor lease lifecycle. `tests/conftest.py` sandboxes every root so the
  suite cannot touch a live estate.

## v2.19 Decision rounds, targeted notices, invocation that works (2026-09-17)

Eight failures were measured across the live estate before this release: 903
bus events, 93 `session_push` since 2026-08-04 across 9 slugs of which **100%
were queued**, 8 monitor leases all pointing at dead pids, 315 hook notices,
and 22 of 22 observed `inbox --unread` calls answering "(no new events)". The
labels S1-S8 below are that audit's.

### Runtime (`sync_server.py`)

- **`decision_request` is a real schema, and oversize is an error** (S5). The
  request now carries `context`, `recommendation`, `options` as objects
  `{id, label, consequence, style}`, a `consequences` shortcut, `evidence`
  `[{label, anchor}]`, `impact`, `blocking` and a server-set `requested_at`.
  `prompt` is required. The cap rose from 2048 to 8192 bytes and is enforced as
  **HTTP 413** with a JSON error. The old code stored any dict under 2048 bytes
  and silently dropped anything larger while still answering 200, so agents
  believed cards had been posed that never existed, and every extra field they
  sent was persisted and never rendered.
- **`POST /api/comments` accepts `decision_request`** (S6). Creating a card was
  two round trips — a create whose `decision_request` was dropped by a fixed
  field list, then a mandatory `PUT` — and emitted two events per card.
- **`POST /api/comments/batch`** (S6). `{items, idempotency}`, up to 200 items
  under one store lock. With `idempotency: "anchor"` an existing non-archived
  card by the same author on the same anchor is updated instead of duplicated,
  so a round can be re-posed in place. One bad or oversize item rejects the
  whole batch with nothing written. Emits per-item events plus one
  `comments_seeded`. Before this the only multi-write path was the legacy
  whole-store overwrite, and agents hand-rolled `curl` loops.
- **Review rounds** (S4). `POST /api/comments/<id>/decision {defer_push: true}`
  records the verdict, sets `decision.round_pending`, marks `comment_updated`
  `deferred: true` and emits **no** push. `POST /api/rounds/submit {note}`
  clears every pending flag and emits one `round_submitted` plus exactly one
  `session_push {round: true, comment_ids, verdict_counts, undecided_ids}`.
  `POST /api/rounds/discard` clears the flags and pushes nothing. Previously
  each click emitted its own push, so a session reacted to the first verdict of
  a ten-card round and then waited on the rest.
- **`GET /api/capabilities`** → `{version, batch, rounds, decision_schema,
  decision_request_cap}`. A 404 is how new chrome detects an old server and
  drops to legacy behavior.
- **`latency_s` on every verdict** (S7), from `requested_at` to the decision,
  on both the comment and the `comment_updated` event. Cards posed before this
  release carry no `requested_at` and therefore no latency.
- **`X-Annotate-Session: <id>`** — when present, every event the request emits
  carries `session_id`. Nothing on the bus could previously be attributed to
  the session that caused it.
- New events: `decision_requested`, `comments_seeded`, `round_submitted`,
  `round_discarded` (S7). Every pre-existing endpoint, event and field is
  unchanged in both directions: new chrome against an old server behaves
  exactly as before, and a new server reads old stored data.

### Chrome (`shell.js`, `adapter.js`, `shell.css`, `shell.html`)

- **Cards render what they are asking** (S5). Both the rail card and the inline
  body strip now show context, a "Recommended" badge, each option's
  consequence under its own button, impact and blocking chips, and evidence
  links that scroll to an anchor and flash it. Long context sits behind a
  WAI-ARIA disclosure that opens inline on mobile. Previously only `prompt` and
  `options` were read, so a reviewer saw a bare question with no stakes and no
  recommendation. Cards that recommend are answered 74% of the time against 34%
  for cards that only ask.
- **Round bar** (S4). "Finish review (N)" with "D of M decided", sticky at the
  bottom on mobile and above the rail footer on desktop. Its confirm dialog
  takes a note and offers "Submit review" and "Discard pending". Each pending
  card keeps a "Send now" link that pushes that one card immediately. Round
  mode activates only when capabilities report `rounds`.
- **Owner chip** in the desktop header, read once from `current.meta.json`
  (label, claimed-at, full session id in the tooltip). No liveness polling.
- **"+ Add a note"** under Accept/Reject attaches text to that verdict without
  forcing a `comment` verdict.
- Object options with a custom id post verdict `comment` with text
  `Selected: <label>`, so the verdict enum is unchanged.

### CLI (`cli.py`)

- **`~/.local/bin/annotate` shim** (S1). `publish` writes it before printing
  anything, and `install-shim [--force]` writes it on demand; both refuse to
  clobber a file this skill did not write. Every printed invocation is the shim
  only when `command -v annotate` really resolves to it, and the absolute
  `python3 …/cli.py` form otherwise. On this machine the bare name resolves to
  libgd's image tool in `/opt/homebrew/bin`, and five sessions lost a turn to
  `Usage: annotate imagein.jpg`.
- **Correct session id** (S2). `CLAUDE_CODE_SESSION_ID`, then
  `CODEX_THREAD_ID`, then `CLAUDE_SESSION_ID`. The old code read
  `CLAUDE_SESSION_ID`, which is empty under Claude Code, which is why every
  lease was labelled `interactive-ppid-<n>` and no page could be attributed to
  a session.
- **Ownership at publish** (S3). `publish` stamps `owner_session`,
  `owner_agent`, `owner_label` and `owner_claimed_at` into the registry **and**
  an `owner` object into `current.meta.json`. New `claim <slug>` re-stamps both
  for the current session, for a handoff or a page published before ownership
  existed.
- **Session-keyed inbox cursors** (S3).
  `state/bus-offsets/<session>/<project>/<slug>.offset`, with the old shared
  path kept only for a session with no discoverable id. **Expect one replay:**
  the first notice and the first `inbox --unread` per session after this lands
  re-read that slug's whole history, because no session-keyed cursor exists
  yet. The alternative was seeding every session from another session's cursor.
- **Compact `inbox`** (S3). One line per event with comment id, anchor, author
  and verdict, plus a decisions/undecided summary. Bookkeeping events are
  hidden unless `--all-events`; `--json` keeps the raw shape. It also emits
  `inbox_read`.
- **`ask <slug> --from cards.json`** (S6) poses a whole round in one batch
  call, falling back to per-card `POST`+`PUT` on a server without the route.
  **`cards <slug>`** (alias `open-cards`) lists cards and verdicts straight
  from `comments.json`, with no cursor and no side effects.
- **Monitor hygiene** (S2). `SIGTERM`/`SIGHUP` now raise so the `finally` block
  releases the lease and emits `monitor_exited`; every lease found on this
  machine had been left behind by a SIGTERM, and each one made the UI report a
  listener that was not there. The lease is labelled with the real session id,
  and `monitor_armed` is emitted on arming.
- **The monitor heartbeat is off by default** (S2). It existed only to stop
  Claude Code's Monitor tool reaping a quiet stream, which no longer happens —
  verified 2026-09-17 against a 150-second silent stream — and it cost a wakeup
  every 30 seconds, roughly 120 conversation turns an hour of nothing. Set
  `ANNOTATE_MONITOR_HEARTBEAT_INTERVAL` to a positive number to opt back in
  under a supervisor that needs liveness output. Arm with `timeout_ms: 1800000`
  and re-arm on expiry.
- **The monitor prints only rounds and pushes** (S4). `round_submitted` and
  `round_discarded` joined the advertised event set, but stdout now carries
  only `session_push` and `round_submitted`. Every printed line costs the
  reading agent a turn, and after this release the actionable unit is the round
  rather than the individual click.
- **`publish-version` no longer duplicates history** (S7). History is a set
  keyed on version, updated in place, written under the server's meta lock —
  the unconditional append plus an unlocked read-modify-write had listed every
  version of every observed page twice. Emits `version_published`.
- **The publish gate distinguishes "broken" from "cannot check"** (S8). A
  public stage that meets a Cloudflare Access login page is `UNVERIFIED …
  (Access login)` and exits 0, with the local and tailscale stages' PASS stated
  alongside. Only a genuinely failing hop prints `NOT PUBLISHED`. The old
  behavior called five healthy pages dead and cost 5-10 recovery calls each.
- **`eval`** (S7) runs the new `eval.py` over every bus, every comment store
  and the Claude transcripts, and writes `eval-baseline.{md,json}` into
  `state/logs`. It is exec'd as a subprocess rather than imported so a
  measurement can never run through `inbox` and advance the cursor it is
  measuring. Seven sections: per-slug shape, round shape, verdict-to-reaction
  and unanswered cards, `comment` verdict taxonomy, prompt quality against
  outcome, the transcript trace join, and whether each hook notice reached the
  page's owner or a bystander. It classifies `session_push` and `seen_updated`
  as machinery, which moved 116 in-window events and took the measured agent
  share from 72.1% to 89.6% — a baseline taken before this release is not
  comparable to one taken after.
- New events `page_published`, `page_publish_failed`, `page_claimed`,
  `inbox_read`, `monitor_armed`, `monitor_exited` (S7).

### Hook (`hooks/check-comment-bus.py`)

- **The hook stops eating the inbox's delta** (S3). It keeps its own cursors
  under `state/hook-offsets/<session>/…` and only reads the inbox cursor,
  starting its scan at the later of the two. Sharing one cursor per slug meant
  the first session prompted consumed everybody's delta.
- **Notices go to the page's owner** (S3). A slug owned by another session is
  skipped unless `ANNOTATE_HOOK_ALL=1`; a slug with no owner recorded still
  notifies everyone. 8 of 32 deliveries used to land in a session that did not
  own the page, and in 13 of 25 busy slugs the notices were split across
  unrelated sessions. A page published before this release has no owner
  recorded and therefore still notifies everyone until it is re-published or
  `claim`ed.
- **Reviewer-only counts, with verdicts** (S3). Bookkeeping events and
  agent-authored writes no longer count, which removes roughly 2x of inflation.
  The notice now reads:
  `[annotate] <project>/<slug>: N reviewer event(s) since your last read — verdicts: <id> accept, <id> comment("…"); undecided: N of M cards. Read: python3 <skill>/cli.py inbox <slug> --unread`
  A `round_submitted` prefixes it with `ROUND SUBMITTED:`. When cards are still
  undecided and the newest reviewer event is under three minutes old, it
  appends a warning not to act mid-round.
- Emits `notice_emitted {session_id, slug, count, offset_from, offset_to}`,
  keeps a per-session single-flight lock, and still always exits 0.
  `ANNOTATE_HOOK_DRY_RUN=1` prints what it would say and writes nothing at all,
  and `ANNOTATE_HOOK_ALL=1` ignores owner targeting. Both are for tests, as are
  `ANNOTATE_BUS_ROOT` and `ANNOTATE_STATE_ROOT`.

### Docs

- **SKILL.md rewritten to ≤6 KB.** It now opens with the real invocation, and
  every bare `annotate …` claim that resolved to libgd is gone or qualified.
  The contradiction is gone too: the old file said a session **MUST** arm a
  Monitor immediately after publish and then, forty lines later, said armed
  monitors are for unattended reaction only. There is now one policy — the hook
  when a human is reviewing and turns are coming, `monitor` only when no user
  turn is coming — plus the exact hook string, the rule never to act on a
  partial round, and the rule to verify rendered content in the authenticated
  browser rather than a status code.
- **New `references/decision-cards.md`** (schema, limits, 413, field-by-field
  rendering, round mode, custom option ids, events),
  **`references/building-pages.md`** (placeholders, CANVAS sentinels, the
  `build.py` pattern, the `node --check` lint caveat, Orca browser
  verification, the 6-minute/31-call cost baseline) and
  **`references/telemetry-and-eval.md`** (every event with its fields and emit
  point, `annotate eval`'s seven sections, five regression thresholds:
  unanswered cards past 7 days above 30%, verdict-to-reaction p90 above an
  hour, and any single queued push with an owner recorded, false
  `NOT PUBLISHED`, or notice to a non-owner).
- **`references/cli-reference.md` and `references/architecture.md` rewritten**
  for the shim, session identity, session-keyed cursors, the owner stamp, the
  verification gate, capabilities, batch and rounds.
  `references/durable-tool-architecture.md` was folded into `architecture.md`
  and deleted.
- Known and unfixed (S8): the live skill dir and the `agent-annotate` repo have
  diverged in both directions and neither is a deployment of the other. The
  merge plan is not part of this release.

## v2.18.1 Heartbeat env override + attended-review guidance (2026-07-25)

Follow-up to the v2.18 monitor heartbeat, based on live-test feedback: the
heartbeat lands as a main-thread turn per line under Claude Code's Monitor
tool (~120 turns/hour of noise). Since the reaper kills at ~60s of silence,
the interval can't simply be raised.

- **`ANNOTATE_MONITOR_HEARTBEAT_INTERVAL` env var** (`cli.py`). Overrides the
  default 30.0s. Set to a value `<= 0` to disable heartbeat entirely — only
  safe when the monitor is launched OUTSIDE the persistent Monitor tool (plain
  shell, `Bash --run_in_background`, process supervisor). Invalid values print
  a stderr warning and fall back to 30.0.
- **SKILL.md § 6** now documents that armed monitors are for unattended
  reaction and the silent `check-comment-bus.sh` hook is the strictly-better
  default for pages under active human review.
- Deferred: routing the heartbeat to stderr instead of stdout as a possible
  low-noise liveness signal — hypothesis, untested against Claude Code's
  Monitor reaper. Do not ship without a real before/after under the tool.

## v2.18 Concurrency hardening (2026-07-25)

Root-caused by the 2026-07-25 skill-audit incident: a peer session republished
a different slug from another worktree while launchd was mid-restart on an
unrelated port, and Chang saw BAD GATEWAY on the tunnel URL. `cli.py` had no
coordination across worktrees/sessions for the two files every `publish`/
`unpublish` mutates.

- **Port-liveness check** (`_port_listen_pid`, `cli.py`). Before trusting a
  candidate port as free, `_find_free_port_after` now also asks `lsof` who is
  actually LISTENing there. If a foreign PID holds it, that PID is alive, and
  this slug's own last-known PID is dead, the candidate is skipped — a stale
  state-file registration can no longer cause `publish` to claim a port a
  launchd-restarted or peer-session process already owns. Falls back to the
  existing OS bind-test only (with a stderr warning) if `lsof` is unavailable;
  never hard-fails the publish over this check. Exhausting the port range
  raises an error naming the conflicting PID(s).
- **Advisory locks on shared read-modify-write files** (`_flock`, `cli.py`).
  `state/<project>.json` (publish/unpublish) and the remote Cloudflare tunnel
  config (GET-mutate-PUT, via the `cloudflare` transport) are now serialized
  end-to-end with `fcntl.LOCK_EX` lock files under `state/locks/`. Without
  this, two concurrent sessions publishing into the same project could each
  load the state dict, mutate their own slug, and write the whole dict back —
  silently dropping the other's entry. Non-blocking first, then a 30s
  poll-and-retry, then a clear error naming the stuck lock rather than
  blocking forever on a crashed peer.
- **Monitor heartbeat** (`cmd_monitor`, `cli.py`). Emits
  `ANNOTATE_MONITOR_HEARTBEAT` every 30s of bus quiet so Claude Code's
  persistent Monitor tool doesn't reap the stream and SIGTERM the process
  (observed: exit 143 at ~60s on a quiet bus). See SKILL.md § 6.

## v2.17 Chrome is served, never baked (2026-07-25)

User-reported: "can we have it so that these types of updates occur across the
board without having to rewrite/update them? as agent-annotate is about keeping
the UI aspects deterministic ... while the skills aspect instructs that agent on
how to use it."

v2.16 had to hand-patch each baked page to fix the `<select>` hijack, because
legacy slugs froze a copy of the chrome into every published version. Shell
slugs got the same fix for free. That asymmetry is now gone.

- **Request-time content extraction** (`extract.py`). `template.html` brackets
  its canvas with `<!-- CANVAS CONTENT -->` sentinels, which survive baking
  verbatim — verified across all 11 published version files spanning three
  template generations. The server recovers the author's content by string
  slice (no HTML parsing), re-encodes `ANCHOR_REGISTRY` into the
  `anchor-registry-data` JSON `adapter.js` reads (tolerating the older JS
  object-literal form: single quotes, bare keys, trailing commas), and serves
  it through the universal shell.
  - Happens on every request and writes **nothing** to disk. That is what makes
    it universal: a page picks up the current chrome on its next request, with
    no migration to run and no duplicate to go stale.
  - An explicit `content/<version>.html` still wins, so hand-tuned extractions
    (the `schema` slug) are untouched.
  - A document without sentinels keeps the old direct-serve behavior.
  - Measured: 2.3 ms for a 100 KB page, 23 ms for the 344 KB / 958-entry one.

- **Anchor preservation verified, not assumed.** Every `anchor_id` in every
  `comments.json`, matched against the version its comments were filed on,
  resolves in the extracted document. The two apparent misses were confirmed
  pre-existing: one orphan absent from the original baked file, and 900
  `lead-universe-probe-review` rows built at runtime from `data/*.json` that
  were never in the static HTML either. `comments.json` is never touched.

- **`cmd_migrate` no longer copies the baked page into `content/`.** That was
  worse than leaving it absent: the artifact's chrome script has no iframe
  guard, so it kept running beside `adapter.js` — two click handlers, two
  comment paths — and the older baked handler went on swallowing clicks on
  native controls. The byte-copy would not have fixed the `<select>` bug.

- **`openPopover()` shim in `adapter.js`.** In-canvas affordances ("comment on
  this row") call the global the old chrome defined; they are guarded by
  `typeof`, so without the shim they fail silently. Routed through the normal
  pin-click path.

- **Versions rail collapse** in the legacy template, mirroring the feedback
  rail with the Lucide `panel-left-*` family (a left panel reverses the
  direction: collapse points left, expand right). One `wireRail()` serves both;
  they collapse independently and persist separately.

- Interaction contract gains item 15: chrome is served, never baked.
  SKILL.md §7 now states the chrome is the server's job — do not hand-patch a
  published page's chrome, because the server does not serve it.

All 9 running page servers restarted onto the new runtime and verified: every
one now serves the universal shell, including the 5 that were baked.

## v2.16 Interactive controls act natively; conventional rail toggle (2026-07-24)

User-reported: "for the lead-universe-probe-review page, i cannot select from
the dropdown fields because a comment box appears instead." Click-to-comment is
registered in the CAPTURE phase and calls `stopPropagation()`, so anything its
bail-out list fails to name never receives its own click at all — a native
`<select>` never opened its dropdown.

The two front-ends had drifted. `adapter.js` (universal shell) excluded
`a[href], button, input, textarea, select, .col-resize-handle, th.sortable`;
`template.html` (legacy single-file artifact) excluded
`.col-resize-handle, .title-collapse-toggle, .alink, a[href], button, th.sortable`
— **no `input`, no `select`, no `textarea`**. Every legacy artifact therefore
swallowed clicks on every text field, checkbox and dropdown, while the shell
swallowed `<summary>`, `<label>`, `<option>` and all ARIA widgets.

- **Shared `INTERACTIVE_SEL`** — one list, byte-identical in `template.html`
  and `adapter.js`: native form controls, links, `option`/`optgroup`, `label`,
  `summary`, media with `controls`, the ARIA widget roles (`button`, `link`,
  `checkbox`, `radio`, `combobox`, `listbox`, `option`, `menu`, `menuitem`,
  `menuitemcheckbox`, `menuitemradio`, `slider`, `spinbutton`, `switch`, `tab`,
  `textbox`, `searchbox`), `[contenteditable]`, `[tabindex]:not([tabindex="-1"])`,
  and the artifact chrome classes. Everything else stays annotatable, so
  click-anywhere-to-comment is unchanged.
  - `[data-annotate-interactive]` — author opt-in to exclude a custom widget.
  - **Alt/Option-click** — forces a comment on an excluded element, so
    controls do not become permanently un-commentable.

- **Feedback rail collapse/expand** — the legacy `template.html` gained the
  collapse affordance the universal shell already had. Single toggle following
  the WAI-ARIA APG disclosure pattern: `aria-expanded` on the *button* (never
  the panel), `aria-controls="panel-body"`, and an accessible name that flips
  with state (`Collapse`/`Expand feedback panel`) because it doubles as the
  tooltip on an icon-only control. State persists in
  `localStorage['annotate:panelCollapsed']`. Collapsed leaves a 44px rail that
  still carries the toggle and the comment count; `display:none` on the rest
  also takes it out of the tab order. Collapsing resizes the canvas, so
  `renderBadges()` re-runs on every toggle.
  - The comment badge now renders the number and the word as separate spans
    (`.cnt-n` / `.cnt-w`) so the collapsed rail shows just the count without
    the label overflowing; an `aria-label` keeps the full phrase in both states.

- **Conventional rail iconography** — replaced the `»`/`«` guillemets in
  `shell.html` (versions rail *and* feedback drawer) and the legacy template
  with **Lucide `panel-left-*` / `panel-right-*`** (ISC License, © Lucide Icons
  and Contributors) inline SVG. The panel-pictogram-plus-chevron form is
  unanimous across Material Symbols, Primer Octicons, Lucide, Fluent and
  Carbon; the collapse chevron points *toward* the rail's own edge and the
  expand chevron away from it, and the glyph flips with state. Guillemets were
  rejected deliberately: they are quotation marks, carry no panel semantics,
  and the Dingbats chevrons (U+276E/U+276F) are subject to emoji-font
  substitution that CSS `color` cannot override. Targets are ≥24px per
  WCAG 2.2 SC 2.5.8.

- **Tests** — `tests/browser/test_interactive_controls.py` (shell path) and
  `tests/browser/test_legacy_template.py` (legacy path, which had *no*
  coverage of any kind — this is how the drift went unnoticed). Both verified
  to fail against the pre-fix code before being kept. The legacy suite renders
  `template.html`'s placeholders directly, since nothing in the repo renders it.

## v2.15 Mobile-optimized reviewer shell (2026-07-19)

User-reported: "the page doesn't seem to be mobile optimized at all" — shell.css
had zero `@media` queries, so a phone got the desktop three-column layout
(180px rail + flexible content + fixed 380px drawer) crushed into ~390px.
Every rule below lives inside `@media (max-width: 768px), (max-height: 480px)`
(the height branch catches a landscape phone, e.g. 844×390, which is wide
enough to read as "desktop" by width alone) — desktop above the query is
byte-for-byte unchanged, verified by comparing computed layout dimensions at
1440×900 and 1024×768 before and after (header 52px, rail 180px, drawer
380px, drawer `position:static` — identical).

- **Bottom-sheet drawer** — the comment drawer becomes a `position:fixed`
  sheet (85vh, rounded top corners, drag-handle bar), toggled by
  `body.is-mobile-sheet-open` (`shell.js` `setMobileSheetOpen`/
  `isMobileSheetOpen`) rather than the desktop `.collapsed` rail mechanism —
  the two never apply to the same element at once (`wireRailCollapse`
  branches on `isMobileLayout()`, and a stale `annotate:drawerCollapsed`
  localStorage flag from a prior desktop session is no longer replayed on a
  phone). A floating action button (bottom-right, safe-area-aware) shows the
  total comment count and an unread badge and opens the sheet; it hides
  itself while the sheet is open. Sheet open/scroll state lives in module
  state / a body class, so the 8s poll's routine re-render never yanks the
  sheet shut or the list back to the top — `renderDrawer()` now saves and
  restores `#drawer-body.scrollTop` around its innerHTML swap (skipped only
  when a reply textarea just reclaimed focus, so that existing behavior
  isn't fought).
  - `focusSidebarCard()` (pin → card reverse lookup) and
    `goToCommentLocation()` (card → content "go to location") each drive the
    sheet in the direction that makes the result visible: focusing a card
    opens the sheet if it was closed; navigating to content closes it if it
    was open, since content sits entirely behind the sheet on a phone.
- **Version rail → header `<select>`** — the desktop rail (`.vrail`) is
  hidden outright; a native `<select>` takes the `#hdr-sub` "Version vN"
  slot in the header, rebuilt by `renderMobileVersionSelect()` every time
  `renderVersionRail()` runs so the two can never drift apart. Each option
  carries the same "needs my review" count the rail's red badge shows, as a
  `(N)` suffix, so that signal isn't lost in the mobile layout.
- **Create-comment and pin popovers → bottom sheets** — `positionPopover()`
  and `positionPinPopover()` skip their dynamic click-anchored left/top math
  under `isMobileLayout()` and let shell.css's `left:0;right:0;bottom:0`
  rule fully own placement instead — an x/y-anchored popover is exactly the
  "renders off-screen on a 390px phone" failure mode this avoids. A shared
  `#mobile-dialog-backdrop` dims the content behind whichever one is open
  (tap it to dismiss). Comment/decision textareas are 16px on mobile (was
  11–13px) so iOS doesn't zoom the page in on focus.
- **Touch tap targets ≥44px** — chips, toggle buttons, rail-card action
  links (Accept/Reopen/Archive/Re-pin/Change verdict), go-to-location and
  reply-submit buttons, the body-inline decision strip's Accept/Reject/
  Comment/Change buttons, and the FAB are all ≥44px on mobile. Pins stay
  visually compact (`PIN_SIZE_MOBILE = 26`, up from the desktop 18px — "scale
  up on touch devices" without blanketing a dense diagram at a literal 44px
  dot) but gain an invisible 44px tap box via a `::before` pseudo-element
  inset -9px on each side — pseudo-elements share their host's hit box, so
  this widens the tappable area without moving the rendered dot.
  `clampPinLeft`/`pinPoint`/`PIN_SPACING` all read pin size through a new
  `PIN_SIZE()` function (was a `const`) so the clamp math is correct at
  either size; re-verified at 390px width (pins land 8px from the edge, the
  same inset the desktop clamp always used).
- **Touch equivalent of hover-linking** — hovering a pin/anchor/strip has no
  touch analogue, so tapping a pin now lights up its anchor row
  (`annotate-anchor-hl`, the same class `wireHoverLinking` uses) for 1.5s
  synchronously with opening the popover/card, confirming the pin↔row
  pairing the way a mouse user's hover already does. Strips sit in-row
  already and need no equivalent.
- iOS specifics: `viewport-fit=cover` added to the viewport meta tag, FAB
  and sheet bottom padding read `env(safe-area-inset-bottom)`, interactive
  elements get `touch-action: manipulation` (no 300ms delay / accidental
  text selection on a fast tap).
- The header's Push-to-session button collapses to icon + counter on
  mobile (`.push-session-label{display:none}`); the transient "✅ Sent…" /
  "⏳ Queued…" status text it shows for 3s after a push still renders in
  full (a plain-text `textContent` write, unchanged), and the reset callback
  was changed from `textContent` to `innerHTML` so it restores the
  icon/label span structure afterward instead of flattening it permanently
  on the first push of the session.

QA: Playwright viewport-resize passes at 390×844 (portrait), 844×390
(landscape — confirms the height-based branch of the media query), 768×1024
(tablet boundary), plus 1440×900/1024×768 desktop regression, against an
isolated scratch copy of a real slug's data (never the live 8799–8810
servers). Verified end-to-end: decision accept/reject with server-side
persistence (`decision_history` append), comment creation with server-side
persistence, cross-anchor pin popover rendering as a bottom sheet, version
switching, and zero horizontal overflow at 390px in both the shell and the
content iframe.

## v2.14 Verdict reversal + pin/row visual tying (2026-07-19)

Two UX fixes driven by a real incident: the user clicked Reject on decision
D8 by mistake with no way to reverse it, and separately mis-attributed pin
"#13" to the wrong table row ("pin on adjacent row looked like it was for
decision 7").

- **Change verdict** — a resolved decision block (rail card AND body strip)
  now shows a "↺ Change verdict" / "↺ Change" link next to its chip whenever
  `c.decision_request` is still present (i.e. hasn't been explicitly
  withdrawn). Clicking it re-renders the Accept/Reject/Comment buttons for
  that one card/strip, with a "Changing verdict — currently X" note and a
  Cancel link that restores the chip without submitting anything. Open state
  is tracked in a module-level map (`decisionChanging` in `shell.js`,
  `stripChanging` in `adapter.js`) keyed by comment id, so the 8s poll's
  routine re-render never silently snaps a mid-correction card back to its
  chip. Submitting a new verdict (or Cancel) clears the flag.
  - `sync_server.py`'s `_v2_post_decision` already overwrote `c["decision"]`
    unconditionally on every call — re-posting a verdict against a server
    running this build worked with no server change required. It now ALSO
    detects that overwrite: when `c["decision"]` already exists, the prior
    decision is appended to `c["decision_history"]` (oldest first) before
    being replaced, and both bus events it emits (`comment_updated` and
    `session_push`) carry `revised: true, prior_verdict: <old verdict>` so a
    monitoring agent sees an explicit correction rather than an ordinary
    first vote. A comment's first-ever decision is completely unaffected by
    this branch — byte-identical to v2.13 behavior.
  - The reply text makes the reversal explicit too: an accept/reject revision
    reads "↺ Changed to ✓ Accepted (was ✗ Rejected)"; a comment-verdict
    revision appends a "(revised verdict; was <prior label>)" line after the
    new comment text.
  - `shell.js`'s pins payload (`sendCommentCountsToFrame`) now sends
    `decisionRequest` whenever `c.decision_request` exists — resolved or not
    — instead of only for an unresolved one; `decisionVerdict` and the
    boolean `decision` (pin-emphasis) flag keep their existing meaning
    unchanged. `adapter.js` reads "`decisionRequest` + `decisionVerdict` both
    present" as resolved-but-changeable and renders the strip's "Change"
    button accordingly. An adapter predating this fix simply ignores the
    extra field and shows a plain chip against a new shell — graceful
    degradation, not an error; equally, a new adapter served by an old shell
    (which never sends `decisionRequest` once resolved) just never shows the
    button.
- **Pin/row visual tying** — kills the adjacent-row ambiguity from two
  angles:
  - Vertical centering: `adapter.js`'s `pinPoint()` legacy (non-granular)
    corner placement put the pin at the anchor's top-right corner, which for
    a table row sits exactly on the shared boundary with the row above —
    readable as belonging to either one. Fixed a follow-up bug from the
    first pass at this: real decision-table rows run 73-165px tall, well
    past the original `rect.height <= 60px` guess, so that predicate never
    actually fired for the rows the incident happened on. Centering now
    keys off the placement element's own tag (any real `<tr>`, whatever its
    height) OR the `<=60px` height check, so it also covers a short
    non-table-row anchor. Centered anchors get their pin vertically centered
    inside their own row band instead (`renderBadges` renders this case
    without the corner path's `translate(0,-100%)` bottom-anchor shift, so
    the returned `top` IS the
    pin's rendered center). Non-`<tr>` elements over 60px, granular
    (click-offset) pins, and the existing collision-nudge logic are all
    unchanged.
  - Hover linking, both directions, for every pin/anchor/strip pairing:
    hovering a pin outlines its anchor element (`annotate-anchor-hl`:
    2px indigo outline + faint tint); hovering an anchor — or a body-inline
    decision strip sitting at/beside it — scales up and rings its pin(s)
    (`bpin-hl`). One pair of delegated `mouseover`/`mouseout` listeners
    (`wireHoverLinking`, `adapter.js`), no per-element wiring needed as new
    pins/strips render.
  - Strip anchor label: a body-inline decision strip's header now shows the
    anchored row's own registry name (e.g. "D7: Scoring weights") as a small
    muted line above the prompt, sourced from `adapter.js`'s existing
    `ANCHOR_REGISTRY`/`anchorName()` — no new payload field needed since
    artifact anchor names already carry this identifying text.

## v2.13 Body-inline decision strips (2026-07-18)

- **Body-inline decision strips** — v2.12 rendered a decision_request's
  Accept/Reject/Comment controls only on the rail card. User-reported: "i
  don't see the ability to quickly accept/reject/comment on any of the
  decision points in the body area (not the right comment rail)." `adapter.js`
  now injects the same affordance directly at the anchored element inside the
  content iframe, in addition to (not instead of) the rail card:
  - `tr` anchors (the real case: decision-table rows) get a sibling `<tr>`
    with a single `colspan` `<td>` holding the strip — real document flow,
    nothing overlaps.
  - Other block/flow anchors get an `insertAdjacentElement('afterend', …)`
    block.
  - Anchors where DOM-flow injection can't apply or throws (inside `<svg>`,
    a `try/catch` failure) fall back to an absolute-positioned overlay strip
    in a new `#annotate-strip-layer`, clamped into the viewport the same way
    `clampPinLeft` clamps pins.
  - Strip content is built with `textContent` only, never `innerHTML`, since
    `decision_request.prompt` is store/agent-controlled data.
  - Clicking Accept/Reject posts immediately; Comment reveals an inline
    textarea (Ctrl/Cmd+Enter submits, matching every other composer in the
    tool). Buttons disable in flight; on response the strip swaps in place to
    a compact verdict chip (`✓ Accepted` / `✗ Rejected` / `✓ Commented`
    styling), and a new `annotate:decision-posted {commentId}` postMessage
    tells the shell to `refreshStore()` immediately — the rail card and the
    strip both reflect the resolution without waiting on the 8s poll.
  - Both surfaces call the identical `POST /api/comments/<id>/decision`
    endpoint and the identical old-server (pre-`/decision`, 404/405)
    composite fallback (`reply` + status `PUT` + `push`).
  - `shell.js`'s pins payload (`sendCommentCountsToFrame`) now carries
    `decisionRequest: {prompt, options}` for an unresolved decision and
    `decisionVerdict` for a resolved one, alongside the existing boolean
    `decision` flag used for pin emphasis.
  - Strips rebuild only on an actual `annotate:comment-counts` message (data
    changed), never on the resize/scroll-driven badge-refresh cadence that
    also repositions pins — this keeps the strip-injection DOM mutations from
    ever feeding back into the badge `MutationObserver` and looping. Ordering
    within that handler matters: strips are (re)built BEFORE `renderBadges()`
    runs, so pins measure their anchors' post-shift positions, not
    pre-shift ones.
  - Clicks landing on non-button parts of a strip (prompt text, padding) are
    explicitly excluded from click-to-CREATE and from the granular-target
    text-quote scan (`[data-annotate-strip]`), so a strip can never be
    misread as a click on its underlying anchor or as a match for another
    comment's captured quote.

## v2.12 One-click decision buttons (2026-07-18)

- **T19 · One-click decision buttons** — an agent poses an accept/reject/
  comment question on a specific card via `PUT .../comments/<id>
  {"decision_request": {"prompt": ..., "options": [...]}}`. The card renders
  a pulsing, high-emphasis decision block with large Accept/Reject/Comment
  buttons above its normal actions. A click on Accept/Reject submits
  immediately; Comment reveals an inline textarea. Every path goes straight
  to `POST /api/comments/<id>/decision`, which sets `c.decision`, appends a
  matching thread reply, transitions status (`accept` → `user_confirmed`,
  `reject`/`comment` → `open`), and performs the same monitor-lease push as
  the existing per-comment push button — there is no separate "Push to
  session" step. `sync_server.py` gained a shared `_compute_delivery()`
  helper so the bulk-push, single-push, and decision routes stop duplicating
  the monitor-lease lookup. Old servers predating `/decision` (404/405) fall
  back client-side to reply + status PUT + push; `c.decision` is never set
  server-side in that path, so the buttons stay live after a refresh —
  accepted degraded behavior on an un-upgraded server, not a bug.
- **Emphasized decision pins** — content-doc pins for a comment with an
  unresolved `decision_request` render in a distinct pulsing indigo
  (`adapter.js` `.bpin-decision`), separate from the existing unread/cluster
  pin styling.
- **Ctrl/Cmd+Enter everywhere** — reply boxes and the new decision-comment
  box now submit on Ctrl/Cmd+Enter, matching the create-comment popover's
  existing behavior.
- **Pin overflow fix** — a pin placed at the corner of a wide/overflowing
  element (e.g. a table row wider than its own scroll container) could
  render past the visible viewport edge and inflate the document's
  horizontal `scrollWidth`, forcing an unwanted scrollbar at ~1024px
  viewport widths. `adapter.js`'s `renderBadges()` now clamps a pin's final
  horizontal position into the visible viewport (8px inset) before
  rendering; vertical position is untouched since normal page scroll is
  expected. Verified with a scratch document containing `table.tbl{min-width
  :460px}` at 1024px width: `document.documentElement.scrollWidth` no longer
  exceeds `clientWidth`.

## v2.11 Granular pins + exclusive monitor ownership (2026-07-14)

- **T16 · One-click pin reverse lookup** — clicking an individually numbered
  pin now expands the feedback rail and focuses that exact numbered comment
  card. Only aggregate pins open the intermediate chooser.
- **T17 · Click-position pin placement** — the shell now sends each comment's
  stored inner target and click offset to the universal adapter. New comments
  render their number at the applicable point inside the larger anchor box;
  legacy comments without target data stay at the anchor corner. The same
  overlay geometry works for HTML and SVG and refreshes with nested scrolling.
- **T18 · Exclusive per-page monitor ownership** — one live owner lease is
  allowed per project/slug. `--owner` records the managing interactive session;
  `--takeover` performs an explicit handoff by stopping the old monitor process
  while leaving the persistent web server, bus, and queued-delivery cursor
  intact. The monitor status API exposes sanitized owner metadata.

## v2.10 Deterministic scrolling + diagram jumps + truthful session delivery (2026-07-14)

- **T12 · Deterministic content scrolling** — replaced the timing-sensitive
  `body{height:100vh;overflow:hidden}` heuristic with an explicit extracted-doc
  contract in `adapter.js`. The iframe viewport always owns vertical scrolling,
  legacy `.canvas-area` boxes grow with the active tab, and responsive rules can
  no longer stack every `.tab-panel` merely because shell rails narrow the
  iframe. Diagram widgets retain their own two-axis overflow and fullscreen.
- **T13 · Universal diagram-cluster jumps** — `adapter.js` now owns
  `.er-cluster-jump` controls for both baked SVGs and Plot-backed diagrams. It
  finds semantic node kinds and centers them in `#er-container`, replacing the
  stripped v4.6 handler and avoiding diagram-specific pixel coordinates.
- **T14 · Live session monitor transport** — new `annotate monitor <slug>`
  command creates a live PID/bus lease and tails every actionable event,
  including `session_push`. Push endpoints now return `active_monitor` vs
  `queued`, a monitor count, and a delivery id. The button says "Sent to active
  session" only with a verified lease; otherwise it says "Queued — no monitor
  armed." A separate delivery cursor replays events queued while no monitor was
  active. The UserPromptSubmit hook remains the fallback, not the real-time
  transport.
- **T15 · Exact push scope** — bulk push now sends only open comments with
  user activity newer than their previous push. The server and toolbar badge
  share the same rule, so managing sessions do not receive older open feedback
  again and the reported delivery count matches the button counter.

## v2 (initial v2 release)

The v2 redesign adds:

- Per-anchor comment threads (open → addressed_by_agent → user_confirmed → archived)
- In-artifact version pivot (`?v=vN` hard reload, Figma-style)
- Multi-author identity via Cloudflare Access SSO header
- Transport-agnostic publishing (Cloudflare Tunnel today; Tailscale stub for tomorrow)
- NDJSON event bus so a hook can wake Claude when new comments land
- Directory-based slugs (not single-file artifacts)

## v2.1 UI features (2026-06-28)

- **F1 · Push-to-session button** — sticky header button "Push to session
  (N)" with live counter. Click flags every open comment. Per-comment
  "Send" link does the same for one comment. Backed by `POST
  /api/push-session` (all open) and `POST /api/comments/<id>/push`
  (single).
- **F2 · Mermaid diagrams** — `mermaid@10.9.1` loaded via CDN with SRI.
  Any `<pre class="mermaid">` block renders as interactive SVG; each node
  and edge gets a `data-anchor-id="mmd:<diagram-id>:node:<key>"` (or
  `:edge:<n>`) so users can click individual diagram parts to comment.
  Rendering is lazy: only blocks whose tab is currently active render, so
  blocks inside hidden tabs render on first tab-switch.
- **F3 · Collapsible title block** — `.doc-title-block` collapses to a
  thin breadcrumb bar on every tab except `panel-overview`. Manual toggle
  button included.
- **F4 · Tab-level fallback anchor** — every `.tab-panel` gets
  `data-anchor-id="tab:<name>"` at init so users can comment on an entire
  tab when no specific section is the right target.
- **F5 · Code-as-table** — emit a `<table class="dict-table">` instead of
  a `<pre>` block when the source is a dict-shaped Python/SQL constant;
  gives the user real columns + per-row anchors.
- **F6 · Sort + resize on every `table.tbl`** — vanilla JS
  `enhanceAllTables()` adds: click-to-sort with up/down indicators,
  drag-to-resize handles on every column edge (except the last), column
  separator lines, row hover highlight.

## v2.2 Review-UX rework (2026-07-13)

Research-grounded (R1/R2/R3 reports, 2026-07-12) rework of the universal
shell's commenting loop:

- **Card-click navigation (T1)** — clicking anywhere on a sidebar card
  (not just the "→ Go to location" button, which stays) switches version
  if needed, scrolls to the anchor, and pulse-highlights it. `general:*`
  cards no-op gracefully (they have no location by design).
- **Shared numbering (T1b)** — every comment gets a stable per-version
  number (creation order, archived included so accepting never renumbers
  neighbors). The number renders on the sidebar card (`#7`) and on the
  page pin (`7`) — the shared key that disambiguates two comments on the
  same section (Markup.io pattern).
- **Pin → comment reverse lookup (T2)** — pins are now clickable:
  clicking one opens a popover listing that pin's comment(s) (text,
  status, agent response) and focuses the matching sidebar card. Anchors
  with ≤3 comments get individual numbered pins side by side; 4+ collapse
  into a cluster pin whose click lists all. Clicking the anchor's own
  text still opens the CREATE popover (pin clicks take precedence via
  capture-phase routing in adapter.js).
- **Per-comment read model (T3)** — new `read-state.json` sidecar +
  `GET/POST /api/read-state` (per-author, like seen.json). A comment is
  read on engagement (card click, goto, pin popover, acting on it) —
  never on page load. Agent activity (response/status/reply) shifts the
  comment's activity sig, re-marking it unread with a "↑ NEW reply" chip
  (vs "Unread" for never-engaged). Drawer header shows an unread count
  badge; "Unread first" ordering toggle; "Mark all read" button.
- **Version visibility (T4)** — drawer defaults to the viewed version's
  comments; persistent "All versions" toggle (localStorage) shows every
  version's; every card carries a version chip. No version tags are ever
  rewritten (Frame.io/W3C immutable-birth-version model).
- **Live-sync polish** — the 8s poll now skips re-render when nothing
  changed, and renderDrawer preserves in-progress reply drafts and focus
  across re-renders (previously a half-typed reply was silently wiped).
- Popover coordinates from the iframe are now translated by the frame's
  offset (create popover used to open ~180px left of the click).

## v2.3 Granular anchors (2026-07-13, same-day follow-up on user feedback)

- **Granular target capture** — every new comment records the innermost
  element the user actually clicked, W3C-multi-selector style (R2 report):
  inner data-anchor id / DOM id, CSS path relative to the registered
  anchor, normalized text quote (160 chars), fractional click offset.
  Stored on the comment (`target`) AND emitted in the bus
  `comment_created` event. Server caps the payload at 4KB.
- **Granular goto resolution** — verify-then-degrade order: inner anchor
  id → DOM id → relative CSS path (quote-verified) → tightest
  quote-containing element → section anchor → explicit "location
  unavailable". Pulse lands on the exact inner element; never a
  wrong-but-plausible one.
- **Box-pin subtree aggregation** — clicking a pin on an outer box lists
  ALL comments anchored within that box's DOM subtree (its own + nested
  registered anchors), grouped by anchor; each entry click jumps to its
  exact location and focuses the sidebar card.
- **Re-pin** — per-card "Re-pin" action arms a one-shot mode (banner in
  the frame area): the next click in the content doc becomes the
  comment's new location, saved via PUT as `target` +
  `reanchor:{strategy:"manual-repin"}` provenance; PUT also supports
  anchor_id moves (record relocates between store keys). Creation
  records are never rewritten.
- **Retroactive re-anchor** — comment records/bus events carry NO
  sub-section payload historically, so retro-fitting is generally
  impossible (forward-only). Exception applied: the 5
  ontology-2026-07-12 comments were mapped ordinally to the 5 decision
  cards (user-confirmed mapping; confidence 0.9/0.9/0.9/0.6 + 1
  section-overall), as additive `target`+`reanchor` fields plus
  `comment_reanchored` bus events.

## v2.4 Review-loop fixes (2026-07-13, user-reported T6/T7/T8)

- **T6 · Push badge clears after push** — the counter now counts open
  comments with user-side activity NEWER than their last push
  (flagged_at), instead of all open comments; a successful push zeroes
  and disables the button, a new user reply re-arms it. (Was: "1
  remaining" forever after pushing, because pushing flags but never
  closes.)
- **T7 · Collapsible rails** — both the version rail and the comment
  drawer collapse to 30px strips (« / » buttons; strip click restores;
  state persists in localStorage; drawer auto-expands on pin/card
  focus; collapsed drawer strip shows the unread count). Fixes the
  expanded-ER-diagram squeeze: the diagram's fullscreen is
  position:fixed INSIDE the iframe, so its 100vw ends where the drawer
  begins — collapsing both rails reclaims ~530px (measured 1040→1540px
  at 1600px viewport).
- **T8 · Reply box clears on post** — successful replies clear the
  textarea before the re-render (the v2.2 draft-preservation would
  otherwise re-inject the posted text forever); failed posts keep the
  text; unposted drafts in other cards still survive re-renders.

## v2.5 Edge-cache bypass (2026-07-13, urgent — stale shell behind Cloudflare)

Users behind the Cloudflare tunnel kept receiving the OLD shell after
deploys: the pre-v2.5 server sent no cache headers, Cloudflare edge-cached
.js/.css by extension, and the shell referenced its assets with bare
unversioned URLs — so hard refresh re-fetched the same stale edge keys.
Two-layer fix in sync_server.py (universal; v1/legacy slugs unaffected):

- **mtime-stamped asset URLs** — `_v2_serve_root` rewrites the served
  shell.html's `shell.css`/`shell.js` refs to `?v=<int st_mtime>`;
  `_v2_serve_content` stamps the injected `adapter.js` ref and the
  rewritten slug-local `diagram-plot.js` ref. A changed file mints a NEW
  edge cache key instantly — no purge needed.
- **`Cache-Control: no-store, max-age=0, must-revalidate`** on every
  .js/.css response (skill assets + static fallthrough) and on the served
  shell.html, so the edge never caches shell chrome again. Other
  responses keep `no-cache`.

## v2.6 Reply auto-reopen + scroll-lock release (2026-07-13, user-reported T9/T10)

- **T9 · User reply auto-reopens** — a reply by a non-agent author on an
  `addressed_by_agent` comment flips it back to `open` server-side
  (records reopened_at/reopened_by; bus `comment_reply` event carries
  `auto_reopened` + old/new status). Agent (`agent:*`) replies never
  auto-reopen. The user no longer needs a separate Reopen click after
  replying.
- **T10 · Viewport scroll-lock release (adapter)** — extracted content
  docs carried their pre-extraction app-shell CSS
  (`body{height:100vh;overflow:hidden}`) whose inner scroller the chrome
  removal left height-unconstrained: JS scrolling (goto) worked but
  wheel/trackpad/keyboard scrolling was dead on EVERY tab — body
  overflow:hidden propagates to the viewport and blocks user-input
  scroll. `fixViewportScrollLock()` in adapter.js releases the lock at
  init, only when demonstrably broken (document taller than viewport AND
  no functional inner scroller) — intentional app-shell layouts are left
  alone. Verified: wheel scrolls v4-6 (all 12 tabs), v4-2, and
  ontology-2026-07-12; diagram fullscreen enter/exit unaffected.

## v2.7 P0 scroll regression + auto-collapse + draft persistence (2026-07-13)

- **P0 · Scroll-lock back-off fixed** — v2.6's release heuristic backed off
  whenever ANY ≥50%-viewport-height overflow-auto element existed; at
  narrow windows (rails open at a ≤1290px window → iframe ≤720px) the
  scrollable ER diagram WIDGET (#er-container) satisfied it and the whole
  page stayed locked (wheelY=0 at 1280×800, reproduced). Back-off now
  requires a genuine FULL-PAGE inner scroller (≥90% viewport height AND
  ≥70% width), and the check re-runs on resize (content media queries
  restructure below 720px — tab panels stack). Verified: wheel scrolls
  v4-6/v4-2/ontology at 1600×1000, 1440×900 AND 1280×800.
- **P1 · Fullscreen auto-collapse** — adapter detects any large fixed
  overlay (diagram ⛶) via the existing mutation cadence and notifies the
  shell ('annotate:content-fullscreen'); the shell auto-collapses both
  rails for the duration and restores prior states on exit (never
  persisted). The user never sees rail occlusion without acting.
- **T11 · Draft persistence** — reply drafts (per comment id) and
  general-feedback drafts (per version) live in a localStorage-backed
  store: they survive re-renders, VERSION SWITCHES, and reloads; cleared
  on successful post. Live input capture, 400ms debounced save.
- **Process** — REGRESSION-CHECKLIST.md (R1-R18) added to the report dir;
  regression_full.js runs the complete list (throwaway server for write
  paths, live read-only) and appends results to the checklist run log.
  22/22 green on this change.

## v2.8 PATH-based asset versioning (2026-07-13, third stale-delivery fix)

?v= query stamps + no-store proved insufficient at the edge: the user's
browser still received old shell.js/shell.css through Cloudflare while
HTML/API stayed fresh — consistent with a zone config that strips query
strings from cache keys and/or a Cache Rule overriding origin headers
(no CF API creds available to inspect/purge). PATH-based versioning
defeats any such config: a new URL path is always a new cache key.

- New route `/assets/<stamp>/<name>` for shell.js / shell.css /
  adapter.js / diagram-plot.js — the stamp segment is a cache key only,
  ignored for resolution. diagram-plot.js prefers the slug-local copy
  (the fork live content renders with), falling back to the skill dir.
  Legacy bare routes (/shell.js …) kept for compatibility.
- _v2_serve_root rewrites shell.css/shell.js refs to
  `<public_base_path>/assets/<mtime>/…`; _v2_serve_content injects
  adapter.js and rewrites diagram-plot.js the same way. no-store
  retained on all .js/.css responses.
- Verified at origin (production-mirroring instance): refs present,
  versioned paths serve byte-identical current files with no-store,
  legacy routes intact; Playwright smoke green via /schema prefix AND
  bare root; full regression suite 22/22.

## v2.9 ER-diagram geometry repair (2026-07-13, user: "schema tab not scrollable" + "right side cut off")

Both complaints were ONE geometry bug in the extracted content docs, not
staleness (delivery was edge-verified good by then). v4-2's own
`body.er-tab-wide .canvas-wrapper{max-width:none}` was designed for the
pre-extraction app shell where #canvas-area was a viewport-sized
overflow:auto box the user could h-scroll. Post-extraction the wrapper
chain (flex child of body, min-width:auto) stretches to the ER SVG's
fixed 2440px, NOTHING in the chain h-scrolls, and body overflow-x:hidden
clips the right ~1500px with no user-input path to reach it (measured:
#er-container clientW==scrollW==2440, horizontal wheel scrollLeft stayed
0, doc scrollWidth 2684 vs 880 window).

- adapter.js `ensureGeometryFixStyle()`: clamps .canvas-wrapper /
  .canvas-area / .er-container back to their parents (max-width 100% /
  100vw, min-width 0) so the containers' own overflow:auto engages.
  After: #er-container clientW 636 / scrollW 2440 → real horizontal
  scrollbar, wheel scrolls both axes (scrollLeft 800 measured), page
  overflow eliminated (docScrollW == window). Docs without these
  classes: no-op.
- Exhaustive per-tab wheel sweep: 48/48 OK (12 tabs × v4-2+v4-6 ×
  1440×900+1280×800). Full regression 23/23 incl. new R19 (ER container
  scrollable both axes, right side reachable).
