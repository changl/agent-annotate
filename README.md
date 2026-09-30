# Agent Annotate

Agent Annotate turns an HTML document, schema, diagram, plan or mockup into a
versioned review page. A reviewer pins comments to exact elements, answers the
agent's decision cards in one click, and submits a round; the coding-agent
session that published the page reads the round back and acts on it.

The page server and the feedback history outlive any single agent session.
Claude Code, Codex and future providers attach to the same runtime.

## Install

```sh
uv tool install "agent-annotate[mcp] @ git+https://github.com/changl/agent-annotate.git"
annotate doctor
```

For development:

```sh
uv venv
uv pip install -e '.[dev]'
annotate doctor
```

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
[building-pages.md](skills/claude/annotate/references/building-pages.md) §1;
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
[telemetry-and-eval.md](skills/claude/annotate/references/telemetry-and-eval.md).

In Claude Code the `UserPromptSubmit` hook (installed by `publish`) announces
new reviewer activity on the next turn, to the session that owns the page
only, without consuming the inbox. `annotate monitor` is for a session with
no user turn coming. A Codex session reads with `annotate inbox`; `annotate
connect` can relay each submitted round into an idle Codex thread through
the local app-server, but nothing interrupts a running Codex prompt.

## Reviewing a page

Click any element to pin a comment to it. Interactive elements keep their
native behavior; mark a custom widget `data-annotate-interactive` for the
same treatment, and Alt/Option-click to comment on an excluded element
anyway. Decision cards show their prompt, context, recommendation and
consequences on the rail and inline next to the anchored element. In round
mode a verdict is parked until "Finish review"; "Send now" pushes a single
card. Accept, Reject and Request changes answer a card; the last one requires
a note, and that note is what the agent acts on. A standing **Comment** button
sits beside them for saying something *without* answering — the card keeps its
options, stays in "Needs my review" and the round still reports it undecided,
but the remark travels as a verdict instead of an easily-missed reply. Long
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
A version bump pushed to main runs CI, builds one wheel, and publishes an immutable stable release with SHA256SUMS and a build ID. Tag-triggered releases use the same checks.

```bash
annotate update --check
annotate update --apply
annotate update --enable
annotate revive --install
```

Daily checks are opt-in per machine through the existing revive watchdog.
Updates stage a separate environment, verify the wheel checksum, reconcile every
registered server and listener, preserve owners/ports/routes/state, and roll back
failed restarts. Generated skill deployments refresh from their manifests;
custom edits remain untouched and are reported. Running agents must reload
instructions they already read. Prototype forks and unregistered servers need
explicit migration; an updater never kills them by guessing.

```bash
annotate report /path/to/reviews/annotate-weekly --publish
annotate report /path/to/reviews/annotate-weekly --install
```

The weekly page uses existing local events and transcripts without a model run
or inbox-cursor changes. It tracks submitted rounds, delivery states/latencies,
owner acknowledgment, publishing failures, choice-card quality and agent cost.
It does not infer completed implementation from a prompt receipt. Remote hosts
are separate estates; browser timing and resource opens are not yet measured.

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
