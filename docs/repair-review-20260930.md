# Review reliability and security repair evidence

This candidate repairs user-visible review failures and the concrete security findings from the September 30 audit. It is prepared for source review; no live page, runtime, route, owner, installed skill or native settings rollout is included.

## Behavior and evidence

| Area | Result | Verification |
| --- | --- | --- |
| Titles and tables | Visible document title follows the selected version; normal words stay whole and wide tables scroll | Desktop and 390px browser checks |
| Decision numbering | Explicit labels persist across rounds; archived labels reserve numbers through the actual CLI loader | Two completed rounds, carry/repose/history, real temp-file CLI |
| Frame messaging | Exact origin and WindowProxy checks; exact-target sends; regular and nested srcdoc supported | Foreign navigation with the same WindowProxy is rejected |
| Request boundaries | Recorded Host, origin, loopback listener and mount checks; declared reviewer identity; no wildcard CORS | Real mounted HTTP plus CLI/MCP agent/human tests |
| File boundaries | Version/V1 containment, static private-file filtering, safe atomic writes and settings modes | Traversal, symlink, alias and temp-path regressions |
| Embedded metadata | Every '<' is Unicode-escaped in JSON embedded in script elements; decoded values remain unchanged | Script-end injection, legacy comment/script tokenizer cases, browser adapter canary |
| Cloudflare API | Authenticated requests refuse redirects; backups are private from creation and do not collide | Inert local cross-origin redirect and birth-mode/failure fixtures |
| Runtime precedence | MCP plugin uses installed CLI; package/plugin version agree; updates exclude user-managed skills | Package contract and updater tests |

The full local suite passed 773 checks before the last five script-tokenizer regressions were added. All 778 collected cases are included in the final CI run. The latest affected unit/browser group independently checks the final serializers. Ruff and whitespace checks pass. A wheel was built and installed in a fresh private environment; doctor, MCP 2.x startup, page publication and declared human feedback passed using isolated state. The wheel pattern scan found no JWT/provider-key matches; this is not a proof that every secret format is absent.

## Qlty audit

Qlty 0.649.0 ran read-only scans in isolated Git snapshots. Both snapshots used the same generated plugin configuration; the actual repository has no Qlty policy and none was installed. TruffleHog was disabled to avoid outbound credential validation. Python, JavaScript, shell, workflow checks, smells and source metrics were inspected.

Comparable returned findings: 2,148 baseline versus 2,277 candidate; non-test source findings: 418 versus 409. The increase in total findings is dominated by additional test assertions (Bandit B101: 1,771 in the candidate). The scan exits 1 and is not advertised as clean. Sixteen message-origin findings, unsafe archive extraction fallback and persisted checkout credentials are corrected. The fleet TLS warning is a false positive: its actual context uses certificate and hostname verification. The three conditional JS warnings have correctly braced outer guards. Subprocess calls use argv lists and shell=False; fixed/configured executables remain a local installation trust boundary. The string PASS='pass' is a verdict constant, not a password.

Remaining maintenance findings include 108 Python/JS cognitive-complexity warnings, 36 duplicated Python literals, optional chaining/readability suggestions, and subprocess/URL audit annotations. These remain visible; no blanket suppression or broad state-machine refactor was applied. Qlty smells also identifies large CLI, shell, server and adapter modules. Future simplification should preserve the feedback/ownership contracts under the existing tests.

## Performance sample

On one Mac, headless Chrome loaded an ephemeral loopback page with 175 anchors and 13 cards. Each viewport used one cold load and four warm reloads. At 1440px, UI readiness was 169.2ms cold and 97.8ms warm median; at 390px it was 172.6ms cold and 96.7ms warm median. One idle polling interval made four requests and zero feedback-list DOM mutations; no JavaScript errors occurred. This is a small local diagnostic, not a remote latency or device-wide service-level guarantee.

Existing metrics/report commands count completed rounds, delivery attempts/acceptance/acknowledgment, publish failures and decision quality without copying reviewer text into fleet results. They do not infer implementation completion or collect browser timing/resource opens. The owned weekly schedule and stable-update enrollment remain disabled during repair review.

## Promotion boundary

An explicitly trusted Access edge must validate JWTs and overwrite identity headers; the application itself does not cryptographically validate the assertion. Source fixtures do not prove actual edge Host preservation, route protection, or remote reviewer activation. Before fleet activation, validate an owned canary through its real local/tailnet/public paths, then compare owners, ports, routes, history and submitted-round delivery. Preserve the current runtime until that operator-reviewed promotion completes.

Installed skills and instruction files remain user-managed. The plugin's bundled reference files are incomplete and remain unchanged; canonical references live in the package source. Unregistered prototype forks require explicit owner migration. Neither GitHub pushes nor runtime staging implicitly rewrites those resources.
