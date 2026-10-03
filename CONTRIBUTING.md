# Contributing

Preserve the [interaction contract](src/agent_annotate/skills/claude/references/interaction-contract.md)
and existing feedback. Keep changes small; use synthetic fixtures.

Run `ruff check src tests` and relevant tests. Broad workflow/UI changes need
the full suite, browser interaction checks, and a real external Funnel reviewer check.

## Checks and releases

GitHub runs `python scripts/ci.py` once per PR: Ruff, bundled JavaScript syntax, and focused tests for
access, authoring, delivery, links, history, schemas, and provider parity.
Documentation wrappers skip Actions; skill instructions and references still
run checks. New commits cancel stale checks for the same PR. There are no
branch builds, browser downloads, scheduled matrices, or automatic live upgrades.

Run rigorous checks locally before requesting review:

```sh
python -m pip install -e '.[dev,browser,mcp]' build
python scripts/ci.py --full
```

Browser tests require Google Chrome at the fixture's documented path. Verify
that browser tests actually ran; skipped browser coverage is incomplete.
For bundled frontend changes, run `npm run build` in `ui/` locally and review
the resulting dark/light desktop/mobile screens.

Shipping requires matching version bumps in `pyproject.toml`, the package, and
the Codex manifest. A version change merged into `main` builds one wheel,
stamps its commit identity, imports the installed artifact, checks packaged
assets and schemas, then publishes `vX.Y.Z` with the wheel and `SHA256SUMS`.
An explicit matching version tag uses the same path. An existing release is
never overwritten; a tag at another commit fails with a version-bump request.
Full local verification remains the release evidence; GitHub's fast gate
does not replace visual or external reviewer testing.
