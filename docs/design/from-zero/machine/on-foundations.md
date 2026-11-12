# Build the review surface on the existing foundations

12 November 2026. Keep Beads as the work record, Orca as the agent runtime, Windmill as the clock and check runner, and Claude Code/Codex as makers or separate checkers; extend the review surface where those pieces stop.
This is a working surface, with no assistant persona and no resident agent watching other agents.
Target: at most three human review passes per piece of work, and no manual checking that work continues; neither outcome is demonstrated by this research.

Started from [the installed-capability inventory](../research/x-what-exists.md), then rechecked commands, deployed definitions and existing results on this Mac.
**High** below means a fresh record or installed contract supports the stated narrow claim; **medium** means the integration is documented but its end-to-end behavior was not exercised; **unknown** means there is no supporting live test.
No new worker, session, flow or bead was started; no review page was changed.

## What each foundation already supplies

| Need | Foundation | How today, with evidence and confidence | Gap the review surface must cover |
|---|---|---|---|
| 1. Work record and cold pickup | Beads | **High:** `bd schema` includes description, design, acceptance criteria, notes, metadata, external reference, dependencies and comments; `bd show ID --include-comments --json`, `bd comments ID --json`, `bd history ID --events --json` and `bd show ID --as-of COMMIT` expose content and history [B]. | A bead can carry showing/feedback text itself, not merely links; it is not an artifact viewer or a defined pass ledger, and issue closure does not establish Chang's acceptance. |
| 1. Every showing, feedback and acceptance | Existing agent-annotate + Beads | **High:** the review store/history already holds versions, anchored decisions/comments and submitted feedback rounds; Beads holds the durable work identity [A,B]. Claude/Codex have resumable local conversations [C]. | Bind each showing, check, feedback submission and explicit acceptance to a root work ID and exact artifact version; page versions and Send rounds alone cannot count passes per work item. |
| 2. Checks without the maker | Windmill test lanes | **High:** deployed `f/test/run` dispatches then collects; `f/test/full` calls `f/test/change`; Project B UAT and Project C UAT also have existing run records [W]. An agent-annotate receipt reports 2,487 passed, 2 skipped on M5 Max, with logs/JUnit and a receipt digest [W1]. | Attach the source/build identity, actual verdict, skipped/blocked coverage and proof to the showing; historical receipts were read, not independently rerun or cryptographically revalidated here. |
| 2. Separate judgement | Orca + Claude Code/Codex + Windmill | **High** for installed capability: Orca `worker-start --agent claude` or `--agent codex`; Claude `-p`, Codex `exec`/`review`; deployed `f/build/item` separates test-author, builder, verification and intent review [O,C,W]. **Medium** for real use: its one returned historic run used `stub` for all three roles [W3]. | No proof here of a routine non-maker intent checker before every showing; enforce different maker/checker identity, exact result binding and no self-issued acceptance at the review boundary. |
| 3. A clock without an agent | Windmill | **High:** `wmill schedule list --json`, `schedule get PATH --json`, `job list/get` expose schedules and execution; the existing five-minute `f/test/trial_watch` observes pushed revisions and starts the test lane [W]. There are 17 schedules, 11 enabled. | Watching pushed commits is not watching all work: add due checkpoints, parked/human waits, result deadlines and meaningful progress observations; a configured interval is not a detection guarantee. |
| 3. Observe three Macs honestly | Orca + Windmill | **High:** `orca status --json` and `worktree ps --agent-wait --json`, repeated with `--environment M5Max` / `M1Max16`, answer now on all three; worker-list separates task outcome, liveness and terminal accounting [O]. Beads status/heartbeat is a reported claim [B]. | Combine per-host coverage and observation time; live terminal/working label is not progress, silence is not exit, and omitted/unreachable hosts mean unknown; Windmill only knows external work through its bridge. |
| 4. Feedback to a running helper | Orca | **High** for contract: `reference find`, `orchestration send --to dispatch:ID`; an existing remote agent uses `send --on SERVER --to HANDLE`; ordinary terminals use `terminal send --environment SERVER --terminal HANDLE --text TEXT --enter --wait-submit 10` [O]. Existing annotate delivery already journals owner-bound sends [A]. | Persist work/pass plus execution host, dispatch/session and process incarnation; distinguish saved, input accepted, turn started and acted on, and reconcile the answer with a new showing. |
| 4. Finished or missing helper | Orca + Claude Code/Codex | **High** for contract: sending to a settled local dispatch reopens it; the guide says a finished paired-server worker refuses send and needs a new dispatch [O]. `claude --resume ID`, `codex resume ID PROMPT` restore saved sessions; `codex queue --thread ID --message TEXT --resume` may succeed even when resuming fails [C]. | Keep feedback pending until receipt; resume only the exact saved owner where available, otherwise pass the work packet to a replacement; a vanished transcript cannot be restored from a terminal handle. No resumption or replacement was attempted. |
| 5. Orca plug-in/panel | Orca plug-in API | **High:** actual `plugin` commands exist; HTML/TSX sidebar panels, custom editors, commands, Node workers, storage and workspace/agent events are documented by this binary [P]. Only bundled theme plug-ins are installed here. | Medium extra build cost: packaging, grants and support on each Mac; a panel delegates terminal actions to a worker; sidebar width limits grouped review. iPad/phone panel parity is **unknown**; external-open/save dialogs/status-bar APIs are explicitly desktop-only. |
| 5. Page in Orca's browser | Orca browser + review web page | **High:** `tab create --url URL --split right` supports a browser pane beside the work; tabs are workspace-scoped; the browser guide distinguishes desktop-hosted and server-hosted pages [O]. | Lowest desktop integration cost: open the same review URL rather than duplicate its UI; a desktop-hosted browser requires its desktop online. On iPad/phone use the same reachable web page; do not assume pane layout or local URLs carry over. |
| 5. M1-hosted web page | Existing review server + tailnet | **High** for existing architecture: agent-annotate already serves shared review pages and evidence [A]; the Windmill CLI currently reaches its M1-hosted workspace and lists a deployed inbox and Project B planner [W]. | Smallest shared UI build: adapt one web surface for wide grouped work, iPad, and narrow exceptions; authentication, exact links and unreachable-host states still matter. M1 sleep loses service; a phone's localhost is not a Mac's localhost. Actual device use is **unknown**. |
| 5. Native menu-bar item | macOS app; Orca status bar is different | **High:** Orca exposes `statusBar.update` inside Orca; its documented plug-in API has no macOS menu-bar contribution [P]. | Highest additional platform cost: a separate native wrapper/launch lifecycle, yet still a web destination for the review itself; no native iPad/phone equivalent. Add only if a later measured glance need justifies it. |
| 6. Show the thing itself | Orca + web artifacts + Windmill | **High:** `orca ports --json` discovers host-qualified dev servers; browser split panes show running web builds; Orca emulator lists/views iOS and Android devices; Windmill results include artifact/receipt references [O,W1,W2]. HTML can show images, diagrams, recordings and performance plots [A]. | Embed reachable web previews only when framing/auth permits; otherwise open beside the review. A native simulator is an Orca host view, not an ordinary iframe; export recordings/screenshots for iPad/phone until streaming is proved. Pin build/hash and test conditions beside each result. |

## The smallest new parts

- **Work/pass links:** extend the existing review store with root Beads ID, showing ID, artifact version/digest, check references, feedback ID and explicit accepted-showing ID, because neither board history nor page history currently joins those facts per piece of work.
- **Checked showing and flexible viewing:** build on the existing web server and evidence files, with side-by-side/grouped review on the desk, focused review on iPad and a narrow exception view on phone, because Orca panes and Windmill job pages do not prepare the actual material and its decisions together.
- **Check admission and progress watch:** add deterministic Windmill steps that read native receipts, require independent checks where judgement is needed, compare promised checkpoints with observations, and expire stale coverage in the client, because scheduler success and terminal liveness alone cannot certify usable or continuing work.
- **Feedback delivery adapter:** extend the existing owner journal with host/session/dispatch routing, retry IDs, receipts and replacement pickup packets, because Orca delivers messages but does not decide which exact showing they answer or reconstruct absent project context.

No second issue board, model launcher, scheduler, general conversation archive or always-running helper is needed.
Use the root bead for purpose, done conditions, owner/status and review links; use review records for showing-specific feedback/acceptance; use Windmill for job evidence and Orca for dispatch/session observations.
Keep large proof in existing evidence files with content marks and durable references; do not copy screenshots into bead comments or duplicate the entire feedback conversation there.
Count one pass when a checked candidate for that root work item is shown for Chang's judgement; repeated opening/Send retries do not add passes, while a revised candidate after feedback does.
Republishing an unchanged candidate keeps its showing identity; new subtasks retain the parent work identity; historical page versions without this binding remain uncountable rather than guessed.

## A piece of work moves through the foundations

```text
asked       [Beads: root work ID + request + done conditions]
  -> made   [Orca: Claude Code/Codex makes the artifact]
  -> checked[Windmill: tests + separate Orca checker]
  -> shown  [Review web surface: exact artifact + proof + omissions]
  -> feedback [Review record: located answer -> Orca delivery]
  -> next pass [Same Beads ID: Orca maker -> Windmill -> new showing]
  -> accepted [Review record: explicit acceptance -> Beads closure]
```

Feedback can return through further made/checked/shown passes; acceptance can also follow the first showing, and a passing machine check alone is never acceptance.
Every new helper reads the root request/done conditions, latest showing/checks, unresolved feedback and next action from records, not a predecessor's conversation.

## Retire the earlier record service, keep its unmet guarantees explicit

[The earlier combined design](combined.md#3-the-record) introduced a general writing service, event ledger, read positions, claims, permissions and role enforcement.
Beads already supplies durable work identity, issue fields, dependencies, comments and database history; Orca supplies assignments, mail and sessions; Windmill supplies jobs, versions and flow state; review storage already supplies artifacts, questions, feedback and versions.
Their native stores replace a new universal record database and its duplicate work/job/session histories; the surface needs references and a small review-specific record extension.
They do **not** jointly provide an atomic transaction across acceptance, bead closure and dispatch; nor an immutable, role-protected approval ledger, guaranteed forever retention, one-use permission enforcement or budgets across all tools.
Use one authoritative acceptance record, unique receipt IDs and retryable reconciliation for its Beads/Orca mirrors; show pending/failed mirrors rather than pretending the multi-system write was atomic.
Beads comments/history can preserve evidence, but unrestricted board/file access is not the earlier service's protection against a maker rewriting a check; trusted-writer enforcement remains separate work if it is required.
Do not make this small surface responsible for policing every shell action: no verified foundation boundary here establishes that wider guarantee.

## Current proof that changes the design

- **[W1] agent-annotate tests:** job `0d2921c6-27e7-5e57-9b52-01183a3b6d7e` has a completed dispatch/collect flow; `wmill job result ID` returns a receipt with a digest, JUnit/log artifact names and the reported counts above, while `validation_required` remains true.
- **[W2] Project C UAT:** job `01a1c489-1bac-7c45-297d-3ebf6fbf3bfe` has `success: true`, but its nested result says `gate: VOID`, reviewer disabled, 385 blocked, zero passed and release not ready; display that verdict, never a generic green job badge.
- **[W3] Independent agent judgement:** `f/build/item` is genuinely deployed, but the historic job `01a151e4-54e8-8bf3-96ec-43ad180b3085` used stub makers/checkers; this proves the flow shape, not routine independent model review in projects.
- **Project B:** an existing `f/test/full` job reports `PASS` and no agent started, and UAT jobs exist; nightly/owner-review/coverage schedules are currently disabled, so their mere presence cannot support an always-on claim [W].
- **Fleet watch:** M1/M5/M1 Max 16 report Orca versions 1.4.256/1.4.256/1.4.257 and answer reads now; local and M1 Max 16 automation lists are empty, while M5's recorded monitoring automation is disabled and has no shell precheck [O].

## Risks and the check that would settle each

- **Pass counts can be gamed or split away:** replay mixed-work pages, revisions, duplicate Sends, reopened work and grouped showings against the root/showing rule; compare the resulting count with human-labelled examples before reporting improvement.
- **Old or incomplete proof can look current:** change one build after checking, omit one required test and feed a successful job with a blocked result; admission must reject or label each omission, including W2's real case.
- **Independent judgement may remain theoretical:** observe one real maker -> different checker -> repaired candidate -> showing cycle with source/result identities and proof; no launch was allowed here.
- **Sleep, queues and lost observation:** stop a helper, stall it while its terminal stays live, disconnect each Mac and suspend the Windmill host; verify due checkpoints become overdue/unknown and never imply exit or permission to duplicate work.
- **A watch cannot report its own total outage through itself:** the client must age the last observation locally; if alerts during M1 loss are required, prove a deterministic second-Mac probe and a separate delivery path before promising them.
- **Wrong or repeated recipient:** rehearse both agents on each host in working, finished, closed and missing-session states, plus a lost send receipt; verify one pending feedback ID reaches exactly the intended next pass or is visibly undeliverable.
- **M1 loss also removes board/review availability:** inspect and restore the actual Beads/review/Windmill backups and test cold pickup; this research did not establish a tested retention or failover policy.
- **Embedding/device access:** test the real iPad and phone over their normal network with tailnet/auth, restricted-frame pages, video, wide diagrams and an offline Mac; verify a usable open-link/recording fallback and stale state.
- **Plug-in parity and multi-screen behavior:** use a disposable panel to test current desktop/browser clients and all three Mac versions, including separate-window placement; installed API docs alone do not settle mobile rendering or desk ergonomics.

## Reproduce the evidence

Private evidence directory `E` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/v3/v5`.
Run `python3 E/verify.py` after replacing `E`; it performs individual read-only commands and writes `E/verified.json`, containing each exact command and selected results without prompts, logs, feedback bodies or credentials.
The completed collection has 62 receipts and no failed commands; live lists can change on a later run.
**[B]** receipts `board`, `board-context`, `bead`, `history` plus `bd` help/schema; the active server is M1-hosted Dolt, the sampled bead includes a real comment/revision, and audit events are readable.
**[O]** `orca` help/guides plus per-host `status`, `worktrees`, `automations` and `workers`; worktree/worker reads are bounded samples with explicit scope/truncation, not a complete fleet census.
**[P]** installed `orca-plugin-authoring` host-api, events and manifest references plus `plugin list`; no plug-in was loaded or installed.
**[C]** installed `claude --help`, `codex --help`, `codex resume --help` and `codex queue --help`; no inference/authentication/resumption test was made.
**[W]** `wmill --workspace chang` flow/job/schedule/app reads, including exact commands for [W1–W3] in the receipt file; these verify current deployed records, not new successful runs.
**[A]** local `src/agent_annotate/{store,review_history,delivery}.py`; reproduce focused reads with `rg -n 'append_round|round_submitted|versions|owner_target|turn_started|_target_ready'` followed by those three paths as separate arguments.
Skipped runtime/device/failure-injection tests under the read-only brief; the material risk is mistaking a useful set of existing mechanisms for a joined, proven review-and-watch system.
