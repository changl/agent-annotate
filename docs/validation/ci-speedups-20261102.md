# CI speed-ups: validation on 2026-11-02

The accepted full run passed **2,099 tests with two expected skips in 23m10s**, plus ruff and seven JS syntax checks. The serial baseline took 60m29s: **61.7% lower observed wall time (2.61x)**. [PR #93](https://github.com/changl/agent-annotate/pull/93) targets `changl/next-2.28.3` and includes PR #92 through rebase.

| Sample | Commit | Wall time | Pytest counts | Result |
|---|---|---:|---|---|
| Serial baseline | `0f361c8` | 60m29s | 2082 passed, 0 failed, 2 skipped | PASS |
| First parallel trial | `0f361c8` | 24m26s | 2077 passed, 5 failed, 2 skipped | FAIL (not accepted) |
| Isolation trial | `f2295eb` | 23m44s | 2097 passed, 1 failed, 2 skipped | FAIL (not accepted) |
| Accepted parallel run | `fadb849` | 23m10s | 2099 passed, 0 failed, 2 skipped | PASS |

The first two samples use the same SHA. That parallel sample failed and is not passing performance evidence. The accepted after sample includes PR #92 and test-infrastructure fixes, adding 17 cases and removing 0. The Mac was under substantial variable load: the serial sample's one-minute load moved 41.9 to 68.8, while the accepted sample moved 29.8 to 33.9. These are observed before/after timings, not an isolated estimate of parallelism's causal effect or a prediction for M1Max16.

Runtime tests now finish and clean up their detached test servers before three browser chunks run concurrently. Browser tests lease ports in 18700–18799 across processes, check the launched server's PID and page directory through loopback capabilities, and stop their owned children on failure. The shared test configuration selects port 18700 and rejects direct server launches in 8800–8899. Two existing browser checks now wait for the actual rendered Send count and use the existing timer-based popup pattern; all product assertions remain in place.

Local `--full --local` writes one summary line, merged JUnit, chunk XML and logs under `.ci-results/` by default. `--workers 1` runs the same chunks serially. The repository's Windmill full profile declares the merged XML and six chunk/check logs as required artifacts so cleanup retains useful failure evidence. Fixture errors preserve JUnit error counters. Missing or stale XML and subprocess failures cannot produce a passing receipt.

Validation: **39 focused infrastructure tests**, both Chrome/iPad checks for the rendered pending count, and the accepted full suite passed. Ruff and all seven JS checks passed. A three-process stress probe launched and identity-checked 90 real sandbox servers successfully. The exact two full-suite skip IDs, every failing ID from unaccepted samples, chunk durations, load observations and JUnit hashes are in [the machine-readable report](ci-speedups-20261102.json). Raw XML/logs remain in the `.ci-results/` sample directories named by the JSON commands.

GitHub checks passed at `fadb849` in 2m49s: [run](https://github.com/changl/agent-annotate/actions/runs/41538375183). The first uv run saved its cache; a subsequent run explicitly logged a cache hit and successful restore ([warm run](https://github.com/changl/agent-annotate/actions/runs/41534151925), 2m43s). Quick-job wall time remains test-dominated (about 2m32s of pytest); dependency setup reuses the frozen uv cache.

Only this M1's checkout-local dev/mcp/browser virtual environment was installed. Its existing Chrome and Playwright WebKit were used. This worker changed no M1Max16 or Windmill installation/configuration. The argv/deployment/version-guard fixes already exist in the base; no additional runtime cherry-pick or verified-install helper is needed for test execution.

The [Windmill activation plan](ci-windmill-plan.md) was answered through a blocking coordinator ask: approved for later activation, with optional Haiku triage deferred. Extra host installs, scoped credential renewal, remote dispatch/backup and status automation still need Chang's approval. Passing scheduled runs target **zero agent launches and zero AI tokens**. Test commands already used zero model tokens; the former agent coordination cost was not measured, so no numeric historical token saving is claimed. Remote activation and its same-SHA/backup/cleanup proofs remain open under `agent-annotate-va0`.
