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
[cli-reference.md](skills/claude/annotate/references/cli-reference.md).

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
[decision-cards.md](skills/claude/annotate/references/decision-cards.md).

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
card. Both rails collapse; below 1160px the page becomes a phone layout with
a bottom-sheet drawer. The chrome is served from the package on every
request, so a fix reaches every published page at once.

## Repository layout

- `src/agent_annotate/` — CLI, page server, `paths.py`, verify/extract/eval,
  hooks, providers, transports, web assets
- `skills/claude/annotate/` — the Claude Code skill and the one set of references
- `skills/codex/annotate/`, `plugins/codex/` — the same skill in Codex wording
- `tests/` — unit suite (sandboxed roots) and browser suite
- `docs/` — architecture map, contract map, handoffs, incidents

## Transports

| Name | Public origin |
|---|---|
| `local` | none; `http://localhost:<port>/` |
| `tailscale` | `tailscale serve` HTTPS endpoint on the tailnet |
| `cloudflare` | Cloudflare Tunnel ingress rule; origin defaults to loopback, override with `service=` |
| `cloudflare_tailscale` | Cloudflare Tunnel whose origin is the tailnet endpoint |

Prefer `cloudflare_tailscale` for a tunnel whose connector cannot dial
loopback. The transport is configured per project in `projects.toml`
(`transport`, `hostname`, `port_base`, `path_prefix`). Cloudflare credentials
come from `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`ANNOTATE_CLOUDFLARE_TUNNEL_ID` and `ANNOTATE_CLOUDFLARE_HOSTNAME`, or from a
private env file named by `ANNOTATE_CLOUDFLARE_ENV_FILE`; nothing is embedded.

## Publish verification

`annotate publish` prints a URL only after it has loaded the page and found
rendered anchors at the local origin, the tailnet hop and the public URL,
naming the hop that broke. A Cloudflare Access login page is reported as
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
