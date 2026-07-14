# Agent Annotate

Agent Annotate is a local-first review surface for coding agents. It turns an
HTML document, schema, diagram, plan, or mockup into a versioned page where a
reviewer can pin comments to exact elements and push selected feedback to the
coding-agent session responsible for that page.

The web server and feedback history persist across agent handoffs. Claude Code,
Codex, and future providers connect through replaceable session adapters.

> Status: alpha extraction of the working v2.11 annotation runtime. The
> standalone interaction and packaging suites pass; existing production pages
> should remain on their current installation until a per-page migration check
> confirms parity.

## Target installation

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

## Core workflow

```sh
annotate migrate ./review.html --copy --slug review
annotate publish ./review --transport local
annotate sessions --cwd "$PWD"
annotate connect review --thread <codex-thread-id>
```

The server remains running when ownership changes. Use `annotate connect ...
--takeover` for an explicit handoff and `annotate disconnect <slug>` to release
the monitor without stopping the page.

## Repository layout

- `src/agent_annotate/` — provider-neutral CLI, server, state, web assets, and transports
- `src/agent_annotate/providers/` — coding-agent session delivery adapters
- `skills/` — thin Claude and Codex workflow skills
- `plugins/codex/` — installable Codex plugin wrapper
- `tests/` — interaction, monitor, and packaging conformance suites
- `docs/` — architecture and public contributor documentation

Runtime configuration, data, and state use operating-system standard
directories. `ANNOTATE_CONFIG_DIR`, `ANNOTATE_DATA_DIR`, and
`ANNOTATE_STATE_DIR` provide explicit overrides for tests and portable
deployments.

Cloudflare publishing has no embedded account or project defaults. Set
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`ANNOTATE_CLOUDFLARE_TUNNEL_ID`, and `ANNOTATE_CLOUDFLARE_HOSTNAME`, or point
`ANNOTATE_CLOUDFLARE_ENV_FILE` at a private env file containing those values.

## Safety defaults

- Local transport binds to the local machine by default.
- A page reports feedback as delivered only when a live owner lease exists.
- Feedback is append-audited and is never silently archived during publishing.
- Public ingress and identity are explicit transport concerns, not core-runtime assumptions.

See [docs/architecture.md](docs/architecture.md) and
[docs/interaction-contract.md](docs/interaction-contract.md).

## License

MIT. See [LICENSE](LICENSE).
