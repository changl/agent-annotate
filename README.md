# Agent Annotate

Agent Annotate turns an HTML document, schema, diagram, plan or mockup into a
versioned review page. A reviewer pins comments to exact elements, answers the
agent's decision cards in one click, and submits a round; the coding-agent
session that published the page reads the round back and acts on it.

The page server and the feedback history outlive any single agent session.
Claude Code, Codex and future providers attach to the same runtime.

## Install

Requires Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), and
Python 3.11 or newer (uv can provision Python). Runtime ownership locks require
POSIX (macOS/Linux); browser reviewers can use other platforms. Install a tested release tag;
installing Git main is a development checkout and can differ from the stable
runtime on another machine.

```sh
uv tool install "agent-annotate[mcp] @ git+https://github.com/changl/agent-annotate.git@v2.20.4"
uv tool update-shell
annotate doctor
```

Open a new terminal after updating PATH. If `annotate doctor` runs another tool,
use the absolute `annotate` executable in the directory printed by
`uv tool dir --bin`. The `python -m` fallback works only in an environment where
this package is installed; system Python does not inherit uv's tool environment.
`doctor` reports the package version, resolved invocation, roots and dependencies.
Run it on each machine rather than assuming a GitHub push updated either one.

For development:

```sh
uv venv
uv pip install -e '.[dev]'
uv run annotate doctor
```

The local page server works without a provider plugin. Claude Code and Codex
can use the same CLI and stdio MCP server (`annotate mcp`). Existing skills are
user-managed: package installation and runtime updates do not install, replace,
or refresh them. A running agent must reload instructions it has already read.
The Codex plugin uses the installed CLI on its PATH; verify that invocation in
the provider's environment and restart its MCP process after a runtime change.
Its bundled skill references are incomplete; the canonical references below
remain in the package source. Plugin discovery is separate from runtime health.

Tailscale and Cloudflare transports require their corresponding CLI/account
configuration. Orca completed-round routing requires a live Orca owner session.
Automatic revive/report scheduling uses macOS launchd; on other systems run the
commands explicitly. Browser tests require Playwright and Chromium; normal
local page serving does not.

`annotate` is the package entry point. When that name on PATH is something
else (on one machine it is libgd's image tool) the CLI prints every
invocation as `python -m agent_annotate.cli …` instead, and `annotate
install-shim` writes a `~/.local/bin/annotate` launcher that runs this
package.

State is read from the same roots the pre-package skill directory used, so
an install sees the pages that already exist: `~/.claude/annotate-state/state`
for the registry, cursors, leases and logs, `~/.claude/annotate-bus` for the
event buses. `ANNOTATE_STATE_DIR`, `ANNOTATE_BUS_ROOT`, `ANNOTATE_CONFIG_DIR`
and friends relocate them; see the environment table in
[cli-reference.md](src/agent_annotate/skills/claude/references/cli-reference.md).

## A round

These commands are for the owning agent. Publishing from its Orca session
captures the owner automatically; after a handoff, the successor runs
`annotate claim review` from its own session before collecting another round.
Human runtime setup alone does not establish an orchestrator owner.

```sh
annotate new --example > page.md               # a worked markdown document
annotate new ./review --from page.md --publish --ask
# serve, claim, verify, print the URL — and pose the whole round
# ... the reviewer answers the cards and clicks "Finish review" ...
annotate inbox review --unread                 # compact, per-session, no double-reads
annotate cards review                          # verdicts only
annotate addressed review <comment-id> --response "fixed in v2"
annotate new ./review --from page.md --version v2 --label "round 2" --publish
```

`annotate new` is the whole page in one write: `---` front matter, `##`
sections, pipe tables, `kpi:` lines, fenced code and a ` ```cards ` block
become `versions/vN.html` with a `data-anchor-id` on every element, plus
`cards.json`, the `current.html` symlink and the version history. It refuses
to write a page with duplicate anchors, no anchors, or CSS outside its
`<style>` block. The format is in
[building-pages.md](src/agent_annotate/skills/claude/references/building-pages.md) §1;
`annotate publish ./review` and `annotate ask review --from cards.json` remain
separate commands for a page built by hand.

`cards.json` is a list of `{anchor_id, text, decision_request}`; each
`decision_request` carries the prompt, the context, a recommendation, what
each option costs, evidence anchors, impact and blocking. Cards that
recommend get answered; cards that only ask mostly do not. The schema is in
[decision-cards.md](src/agent_annotate/skills/claude/references/decision-cards.md).

## Keeping the estate readable

```sh
annotate status                                # health, owners, "(gone)" owners
annotate close review --older-than 30d --dry-run   # cards nobody ever answered
annotate retire --dead --dry-run               # registry rows whose server died
annotate revive --install                      # launchd: restart dead pages at login + every 60 s
annotate eval --since 2026-09-01               # read-only baseline, by hand
```

`close` archives unanswered decision cards past an age; it never touches a
card that has a verdict or an ordinary reviewer comment. `retire` moves dead
registry rows to `state/retired/`, keeping every field, and leaves the slug
directory, the bus and the transport config alone. Both take `--dry-run`, and
neither deletes anything. `revive` restarts every registered page whose server
died (reboot or crash) on its recorded port, re-runs its route and keeps its
owner; `--install` runs it from launchd at login and every 60 seconds.

`eval` is a **manual** step, not a scheduled one: run it once before an
improvement round and once after, and compare. Its thresholds are guidance for
reading the two reports against each other, not gates that fail anything.
Sections and thresholds:
[telemetry-and-eval.md](src/agent_annotate/skills/claude/references/telemetry-and-eval.md).

In Claude Code the `UserPromptSubmit` hook (installed by `publish`) announces
new reviewer activity on the next turn, to the session that owns the page
only, without consuming the inbox. `annotate monitor` is for a session with
no user turn coming outside automatic Orca delivery. A Codex session reads with `annotate inbox`; `annotate
connect` can relay each submitted round into an idle Codex thread through
the local app-server. Orca completed-round delivery below is the automatic
route when publishing from a supported Orca session.

## Reviewing a page

Click any element to pin a comment to it. Interactive elements keep their
native behavior; mark a custom widget `data-annotate-interactive` for the
same treatment, and Alt/Option-click to comment on an excluded element
anyway. Decision cards show their prompt, context, recommendation and
consequences on the rail and inline next to the anchored element. In round
mode a verdict is parked until "Finish review"; "Send now" pushes a single
card. Accept, Reject and Request changes answer a card; the last one requires
a note, and that note is what the agent acts on. **Answer in words** accepts
free-text feedback as the answer: the card waits for the agent and no longer
counts as undecided. Long
option labels wrap. Clicking into any of a card's boxes takes the document to
that card's location. Both rails collapse;
below 1160px the page becomes a phone layout with a bottom-sheet drawer. The chrome is served from the package on every
request, so a fix reaches every published page at once.

## Managed progress and review pages

The package owns the shell, content styles and decision controls. Standard pages
use `annotate new`; agents supply project information and decisions, not a copied
server or stylesheet. Shared `content.css` is applied at serve time to generated
pages, including earlier versions. Standalone HTML retains its fallback styles.

A `project` JSON fence persists links, progress and notes in `project.json`, outside
the versioned review. Modules use stable IDs and native disclosure controls; each
reviewer retains their collapse preferences. `annotate project SLUG --from FILE`
updates the workspace without publishing another feedback round. A `details`
fence contains a summary line followed by supporting Markdown. Choice options
must be structured; manual option-letter prompts produce actionable warnings.

Persistent information appears in one compact **Project summary** disclosure
inside the document. It starts collapsed, scrolls with the page and retains
section expansion preferences across review versions. There is no separate
header button or project-view navigation mode.

## Automatic completed-round delivery

Publishing or claiming a page from an Orca terminal captures that owner session,
terminal incarnation, worktree and provider-process start time. **Finish review**
commits one round to the durable bus before clearing pending answers. A server
worker sends a routing prompt through Orca and retries unavailable owners every
30 seconds. It does not send individual answers or rely on an agent's Monitor.

Delivery validates fresh ownership under the claim lock. Accepted input is never
resent; an interrupted or ambiguous send remains `uncertain` for inspection. The
page distinguishes accepted input, a started turn, owner acknowledgment through
`inbox --unread`, and project work completion. A successor must claim the page;
closed/replaced terminals are not reopened. `annotate deliver SLUG --dry-run`
inspects the journal. Outside Orca, delivery remains attended through the hook.

## Stable updates and weekly evidence

GitHub pushes do not update installed machines or already-loaded agent skills.
A version bump pushed to main runs CI, builds one wheel, and publishes a versioned stable release with SHA256SUMS and a build ID. Tag-triggered releases use the same checks. Checksums detect byte mismatches; they do not establish publisher provenance or GitHub release immutability.

```bash
annotate update --check
annotate update --apply
annotate update --enable
annotate revive --install
```

Daily checks are opt-in per machine through the existing revive watchdog.
Updates stage a separate environment, verify the wheel checksum, reconcile every
registered server and listener, preserve owners/ports/routes/state, and roll back
failed restarts. Skills remain user-managed and are excluded from runtime
updates. Running MCP processes must restart to load a changed runtime.
Prototype forks and unregistered servers need
explicit migration; an updater never kills them by guessing.

```bash
annotate report /path/to/reviews/annotate-weekly --publish
annotate report /path/to/reviews/annotate-weekly --install
```

The weekly page uses existing local events and transcripts without a model run
or inbox-cursor changes. It tracks submitted rounds, delivery states/latencies,
owner acknowledgment, publishing failures, choice-card quality and agent cost.
It does not infer completed implementation from a prompt receipt. Remote hosts
are separate estates unless explicitly enrolled below; browser timing and resource opens are not yet measured.

### Fleet coverage

`annotate fleet` collects runtime, capability, owner-presence and latest-delivery
observations from local registered pages. It never copies reviewer text or owner
session identifiers. Enroll explicit remote page URLs in the machine-local
`config_dir/fleet.json` shown by `annotate doctor`:

```json
{"schema_version":1,"targets":[{"machine":"remote-mac","project":"reviews","slug":"design","url":"https://remote-host.tailnet.ts.net:8445/design/"}]}
```

```bash
annotate fleet --snapshot /private/path/fleet.json
```

The existing weekly report includes enrolled coverage automatically. HTTPS uses
certificate verification; requests are bounded and do not follow redirects or
send credentials. Missing or legacy APIs remain unknown. Machine names are
inventory labels; owner metadata does not prove a live agent. Delivery counts
describe the latest observed row per target, not all submitted rounds. Use direct
machine-specific page URLs; a remote label cannot turn localhost into a remote
address. This inventory does not discover every remote page or change ownership.

## Repository layout

- `src/agent_annotate/` — CLI, page server, `paths.py`, verify/extract/eval,
  hooks, providers, transports, web assets
- `src/agent_annotate/skills/claude/` — the Claude Code skill and the one set of references, shipped as package data; `annotate install-skill` writes a skill directory from them
- `src/agent_annotate/skills/codex/`, `plugins/codex/` — the same skill in Codex wording
- `tests/` — unit suite (sandboxed roots) and browser suite
- `docs/` — architecture map, contract map, handoffs, incidents

## Transports

| Name | Public origin |
|---|---|
| `local` | none; `http://localhost:<port>/` |
| `tailscale` | `tailscale serve` HTTPS endpoint on the tailnet |
| `cloudflare` | Cloudflare Tunnel ingress rule; origin defaults to loopback, override with `service=` |
| `cloudflare_tailscale` | the tailnet endpoint; with `--public`, also a Cloudflare Tunnel route whose origin is that endpoint |

The tailnet URL is the page's one URL. `--public` on `publish` (or `new
--publish`) adds the Cloudflare route for a reviewer outside the tailnet and
prints it as `Public URL:`; a page that already had one keeps it. The transport is configured per project in `projects.toml`
(`transport`, `hostname`, `port_base`, `path_prefix`); every other key in a
project's section is passed to the transport as an option, so a section can
carry `env_file = "/path/.env.local"` and `tunnel_id = "…"`. Cloudflare
credentials otherwise come from `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`ANNOTATE_CLOUDFLARE_TUNNEL_ID` and `ANNOTATE_CLOUDFLARE_HOSTNAME`, or from a
private env file named by `ANNOTATE_CLOUDFLARE_ENV_FILE`; nothing is embedded.

### Reviewer identity and request boundaries

Local browser feedback needs an explicitly configured reviewer. Add a project
section to `projects.toml` in the config directory printed by `doctor` (the
section name is the project, such as `reviews`, not `projects.reviews`):

```toml
[reviews]
transport = "local"
local_author = "reviewer@example.com"
local_author_name = "Local reviewer"
```

These fields are passed when starting the server. They apply only to direct
loopback requests with the server's actual local Host and port. Agent CLI/MCP
requests are attributed separately and cannot establish human reviewer identity.
Requests from another browser origin, an unknown Host, or outside the published
mount are rejected. A mounted page URL without its final slash redirects to the
directory URL and preserves its query.

Tailnet reviewer identity requires Tailscale Serve identity headers on a recorded
tailnet endpoint. Public Access identity additionally requires its recorded
public URL and an explicit `trusted_access_origins = ["https://review.example.com"]`
in that project section. Only declare an edge that validates Access JWTs and
overwrites incoming identity headers: the application checks assertion presence
and trusts that configured edge; it does not cryptographically verify the JWT.
An arbitrary email header is insufficient. Validate the actual proxy Host,
headers and mount with a real authenticated reviewer before promoting a change.

Only intended assets and attachments are statically served. Internal project,
metrics, card and state JSON files and backup/hidden files are private. Published
attachments are public to whoever can access the page; review their contents
before attaching them.

## Removing an installation

Disable updates with `annotate update --disable`; remove a watchdog installed
by this package with `annotate revive --uninstall`. If a weekly report job was
installed, use `annotate report /path/to/its/page --uninstall`. These preserve
review history. Stop only the page servers and monitors you own, and remove
only their named transport routes; never reset unrelated Tailscale or tunnel
configuration.

Remove a package-managed shim only if it still points to this installation,
then use `uv tool uninstall agent-annotate`. Provider MCP registrations, skills
and hook registrations are separate resources: inspect ownership and remove
only this tool's entries, preserving unrelated settings and edits. Keep the
registry, page directories, buses and private backups unless you intentionally
choose to delete that history. No whole-settings restore is required.

Use `annotate unpublish PROJECT/SLUG` to stop an owned page and remove its named
route. Mutations and ownership changes require an exact project scope when a
slug appears in multiple projects. Cleanup verifies the current server's
directory, port and command before signaling it; unknown or reused process IDs
are refused. A failed or unproven teardown keeps its registry receipt for retry.
Other pages, review files and event history are retained.

## Publish verification

`annotate publish` prints a URL only after it has loaded the page and found
rendered anchors at the local origin and the tailnet hop (and the public URL,
with `--public`), naming the hop that broke. A Cloudflare Access login page is reported as
`UNVERIFIED … (Access login)` — live for an authenticated reviewer, unproven
from here — not as a failure. `--no-verify` skips the gate and says so.

## Safety defaults

- Local transport binds to the local machine by default.
- A URL is printed only after the page has been read back with anchors.
- A page reports feedback as sent only when a live owner lease exists.
- Feedback is append-audited and never silently archived or confirmed by an agent.
- A malformed or oversize decision card is refused (HTTP 400/413), never dropped.
- Public ingress and identity are transport concerns, not runtime assumptions.

See [docs/architecture.md](docs/architecture.md),
[docs/interaction-contract.md](docs/interaction-contract.md) and
[CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
