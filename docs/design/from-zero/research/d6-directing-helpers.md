# D6 — Directing software helpers: patterns and attention costs

**18 active products/projects × 9 questions = 162 coverage cells; 50 public report threads; 10 recurring complaint categories; 1 historical comparator.** Snapshot: 12 November 2026. No product is recommended.
Counts describe this purposive, English-language sample, not market prevalence, independent users, or current bug rates. Threads may share authors; categories overlap. Full evidence, quotes, caveats and question-by-question notes: `DATA/outside-d6/notes.md`, `products.json`, `complaints.json` and saved public sources.

## Patterns, rather than products

| Pattern | What the person sees / attention cost | Where it fits | Reported failure | Examples |
|---|---|---|---|---|
| Plan before execution | Read/edit a plan once, then approve; work has already been spent researching | Ambiguous or expensive changes | Plan approved without reading, ignored later, or timed out while being corrected | Claude Code, Cline, Antigravity, Factory, CodeRabbit; historical Jules |
| Issue or task queue → PR | Issue text goes in; draft PR/diff comes back; effort shifts to scoping and review | Bounded changes with runnable checks | Incomplete review cleanup, false readiness, PR queue exceeds human throughput | Copilot, Devin, Codex, Linear, Replit |
| Many isolated workspaces | One overview, many task/branch/diff drill-downs; less launch friction but more context to rebuild | Independent tasks with few shared changes | More finished work than can be validated; stale status; shared code still conflicts | Conductor, Vibe Kanban, Kilo, OpenHands, Amp |
| One parent delegates | Parent conversation plus child runs; hierarchy hides routine detail | Work that decomposes and can be recombined | Parent success can conceal unfinished/failed children; child completion fails to wake parent | Warp/Oz, Factory, Kilo, Claude Code |
| Review on the result | Preview, diff, recording or inline artifact comments; cheaper correction than restating intent | Visible behavior and localized defects | Plausible demo or green CI misses acceptance criteria; review agents add noise | Replit, Cursor, Linear, Antigravity, CodeRabbit |
| Exception notifications / inbox | Needs-input/error/complete alerts, or a mailbox; reduces polling only if delivery and status are trustworthy | Long jobs and work away from desk | Missing pushes, duplicates, action already auto-approved still pings; inbox adds another place | Happy, Warp, Cursor, Codex, Linear |
| Rules and memory | Stored instructions or learned preferences reduce retyping; person must inspect/correct stale rules | Repeated conventions and recurring workflows | Compaction loses intent; memory conflicts; no measured decline in human questions | Devin Memory, Claude auto-memory, CodeRabbit Learnings, Warp Memory preview, Antigravity /learn |
| Voice or remote chat | Speak/answer from phone; typing and location cost fall | Short direction and occasional decisions away from desk | Approval transport breaks; easier tapping does not improve judgment or review capacity | Happy, Cursor mobile, Claude Remote Control, Amp Huddle, Warp |

These are documented workflow fits, not measured comparative wins. Product mechanisms overlap; adding a new front end often moves the attention cost rather than removing it.

## Product coverage: intent, running work, questions and result

A plan mode is an option unless stated otherwise. For the active set, a universal question contract carrying a recommendation, deadline and fallback was **not established**; Warp documents recommended options and explicit skip behavior. Blank evidence is called unknown, not absent functionality.

| Product / primary source | Q1: state intent / correct before work | Q2: running visibility / push | Q3: question route | Q4: result / correction |
|---|---|---|---|---|
| [Cursor Cloud](https://cursor.com/docs/cloud-agent) | Prompt; optional plan | Agents Window/chat/desktop; question push | Chat/approval, phone/browser | PR/diff/demo/desktop; steer or comment |
| [Codex / ChatGPT Work](https://learn.chatgpt.com/codex/long-running-work) | Outcome/constraints/checks; /plan then /goal | Progress, Activity where available; configurable alerts | Chat/approval; surface-specific alerts | Diff/PR/artifacts; inline comments/revert |
| [Claude Code](https://code.claude.com/docs/en/remote-control) | Prompt; plan mode | Tool transcript/tasks; remote push toggles | Session or remote UI | Files/diff; follow-up/edit/review |
| [Copilot cloud agent](https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/manage-and-track-agents) | Issue/prompt; mandatory plan gate unproved | Agent panel/logs, usage and PR activity | Session/PR comments | Draft PR; review and mention agent |
| [Devin](https://docs.devin.ai/work-with-devin/devin-session-tools) | Prompt/issue/chat; plan confirmation can be requested | Session, IDE/browser/shell; exact current alert defaults unknown | Session/integration chat | PR/files/browser; comments or session tools |
| [Replit](https://docs.replit.com/references/agent/task-board) | Chat/Plan mode/draft plan; start task | Drafts/Active/Ready/Done; log/tests/preview | Project chat; timing policy unknown | Preview/diff; apply, ask fix or rollback |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Conversation/automation; universal plan gate unproved | Canvas/backends/conversations; push defaults unknown | Conversation/confirmation | Changes/PR; follow-up; mandatory demo unproved |
| [Cline](https://github.com/cline/cline/blob/main/docs/core-workflows/plan-and-act.mdx) | Plan→Act, prompt | Tools/diffs/context; alerts not established | Follow-up and approval UI | Diff/browser/checkpoint; edit/reject/restore |
| [Kilo](https://kilo.ai/docs/automate/agent-manager) | Prompt/profile/worktree; plan varies | Manager, chat, terminal/diff; remote sync | Local/cloud; noninteractive children cannot ask user directly | PR/diff/document comments; send to agent |
| [CodeRabbit](https://docs.coderabbit.ai/code/work-with-a-task) | Review/chat/task; versioned plan approval | Task activity/live diff; PR comments/checks | Task page raises question and waits | Finding/proposed patch/PR; inline reply or revise |
| [Linear Agent](https://linear.app/docs/coding-sessions) | Delegate issue; investigation does not authorize coding | Session states, Inbox and Reviews | Agent elicitation/comment | Draft PR/diff, optional recording; inline correction |
| [Conductor](https://www.conductor.build/docs/guides/review-and-merge) | Workspace prompt; provider plan mode | Workspace/chat/status/artifacts; notifications | Provider UI/chat | Diff/preview/PR; line comments/revert |
| [Vibe Kanban](https://vibekanban.com/docs/workspaces/chat-interface) | Issue→attempt; planning profile | Board/chat/execution state | Approval row/chat | Diff/preview/PR; comments/follow-up |
| [Happy](https://happy.engineering/docs/) | Typed/voice direction; underlying agent plans | Mobile/web sessions/live chat; pushes | Remote permission/question UI | Agent conversation/work; local review still needed |
| [Factory Missions](https://docs.factory.com/missions/overview) | Collaborative features/milestones/checks; approved plan | Mission Control; not fire-and-forget | Planning/dialogue/intervention | Code/milestones/validation; steer mission |
| [Amp](https://ampcode.com/docs/threads) | Thread prompt; ask for plan | Thread tools/files, remote queue/steering; alerts unknown | Thread/Huddle; timing policy unknown | Changes/PR/editable artifacts; follow-up |
| [Antigravity](https://antigravity.google/docs/artifact-review) | Planning/Fast; /plan waits for approval | Conversations/task artifacts; review notifications | Conversation/approval | Plan/diff/walkthrough; inline comments |
| [Warp / Oz](https://docs.warp.dev/platform/managing-cloud-agents/) | Prompt/profile/trigger; optional planning | Runs/list/mailbox/logs; inspect child states separately | Options/recommendation/skip; unattended input can end Blocked | Diff/PR/session evidence; follow-up/resume |

## Product coverage: checking, learning, trust and places to look

Q8 lists documented surfaces, not a measured mandatory click count. Self-tests, permission classifiers and a separate reviewer are different checks. None establishes correct user-visible behavior on every task.

| Product | Q5: before human review | Q6: preferences | Q7: widen/narrow trust | Q8: places to look | Q9: user evidence |
|---|---|---|---|---|---|
| Cursor | Agent tests/browser; optional dedicated review | Automation Memories | VM/tool/repo settings | Manager→task→PR/children | u01–u04: stalls, noise, scope drift |
| Codex / Work | Tests; dedicated /review/cloud review | Project instructions/context; adaptive loop unproved | Sandbox + approval/auto-review | Activity/projects→chat→PR; CLI differs | u05–u08: false done, context, cost |
| Claude Code | Agent tests; optional review; action-risk classifier | Auto-memory + CLAUDE.md | Manual/plan/auto/bypass and sandbox | Sessions/tasks→remote→diff/PR | u09–u12,u49: lost intent, fatigue |
| Copilot | Agent build/test + PR controls | Repo instructions; personal learning unproved | Runner/token/branch/human review | Global panel→session→repo PR | u13–u14: cleanup/check failures |
| Devin | Tests/browser; mandatory independent checker unproved | Automatic Memory + Dreaming | Security Profiles; task confidence is separate | Session/chat→IDE/browser→PR | u15: old firsthand 20-task trial |
| Replit | Browser App Testing; code self-review | Instructions/checkpoint context | Build/apply/rollback; mode ≠ trust earned | Project board→task/log→preview | u19–u21: false fixes, billed loops |
| OpenHands | Agent tests; action-risk analyzer | Exact personal policy not established | Confirmation/analyzer/backend | Canvas→conversation→PR/destination | u22–u24: loops, silent failure |
| Cline | Agent tools/tests; independent gate unproved | Explicit Rules; adaptive learning unproved | Per-tool auto-approve; CLI/IDE differ | Editor/CLI/background sessions→project | u25–u28: loops, context, hidden wait |
| Kilo | Runtime tests/browser, visible review context | Reusable instructions; adaptive learner unproved | Provider permissions/worktrees | Manager→project/worktree→PR/terminal | u29–u31: invisible blocks/cost |
| CodeRabbit | Review + pre-merge checks; separate plan approver | Learnings from review chat | Manual delivery vs Autofix/profile/checks | Task list + PR/IDE/Slack | u32–u34,u50: review noise/queue |
| Linear | Cloud tests/browser; GitHub requirements | Personal/workspace guidance | User permissions, admin/team controls | Inbox + issue/session + Reviews/PR | f53: first-party practitioner; independent gap |
| Conductor | Provider tests; requested Review | Configured agent/review preferences | Provider permissions; isolated branches | App→workspace/chat→diff/PR | u35: review overload; promotional conflict |
| Vibe Kanban | Provider tests; independent gate unproved | Profiles/provider context | Executor approval/skip settings | Board→workspace/attempt→diff/PR | u36–u37: stale running/review state |
| Happy | Inherits agent checks | Inherits agent memory | Remote→provider permission mapping | Session list→chat; code/PR elsewhere | u38–u40: missing/stuck/noisy prompts |
| Factory | Milestone validator workers + app QA; can disable | Reused instructions/skills; adaptive loop unproved | Off/Low/Medium/High; Missions require High | Mission Control→mission→code | u41: instruction-loading defect |
| Amp | Tests; read-only review subagent available | AGENTS.md/threads | Current default: tools run without approval; policy plugin | Projects→threads/runner→PR | u42: cost anxiety, older pricing |
| Antigravity | Agent tests/browser; independent gate unproved | Reviewed /learn rule/skill proposal | Review policy + permission presets | App/workspace→conversation→artifact | u43–u44: invisible gate, erased draft |
| Warp / Oz | Agent tests; parent success ≠ child success | Agent Memory research preview | Profiles; question permission distinct from command auto-approve | Manager/mailbox→parent→each child/PR | u45–u47: premature pings, skipped questions |

## Ten recurring complaints, ranked within the 50-thread sample

| Complaint, paraphrased | Threads | Two supporting original reports |
|---|---:|---|
| Babysitting: rescue loops, repeat corrections or complete leftover work | 22/50 | [OpenHands u22](https://github.com/OpenHands/OpenHands/issues/7960); [Cline u25](https://github.com/cline/cline/issues/11209) |
| Cannot tell the real activity/state; UI and execution disagree | 12/50 | [Codex u06](https://github.com/openai/codex/issues/42080); [Vibe u36](https://github.com/BloopAI/vibe-kanban/issues/3227) |
| Waiting silently; missing notification or invisible question | 12/50 | [Happy u38](https://github.com/slopus/happy/issues/1383); [Kilo u30](https://github.com/Kilo-Org/kilocode/issues/8658) |
| Context, standing instructions or a drafted correction disappears | 10/50 | [Claude u09](https://github.com/anthropics/claude-code/issues/23776); [Cline u26](https://github.com/cline/cline/issues/14328) |
| Cost grows unexpectedly or cannot be stopped/understood | 9/50 | [Replit u20](https://replit.discourse.group/t/ai-agent-continued-running-and-consuming-usage-even-after-closing-workspace/10161); [Kilo u31](https://github.com/Kilo-Org/kilocode/issues/3767) |
| Scope expands or authorization is lost | 8/50 | [Cursor u04](https://forum.cursor.com/t/disable-background-tasks/163448); [Claude u10](https://github.com/anthropics/claude-code/issues/61843) |
| Review becomes the backlog: too much code or low-value feedback | 7/50 | [CodeRabbit u32](https://www.reddit.com/r/codereview/comments/1vssbl8/coderabbit_noise_is_seriously_getting_out_of_hand/); [reviewer u34](https://www.reddit.com/r/ChatGPTCoding/comments/1wz72y2/im_tired_of_reviewing_code_nobody_actually_wrote/) |
| Approval fatigue: repeated consent leads to skimming/rubber-stamping | 6/50 | [Claude u12](https://github.com/anthropics/claude-code/issues/68249); [firsthand discussion u48](https://www.reddit.com/r/AI_Agents/comments/1uws7ct/anybody_else_struggling_with_constant_approvals/) |
| Finished/fixed claims are not supported by working results | 5/50 | [Replit u19](https://replit.discourse.group/t/agent-thinking-but-doing-nothing/7511); [Codex u06](https://github.com/openai/codex/issues/42080) |
| Notifications repeat, interrupt or request attention already handled | 4/50 | [Cursor u02](https://forum.cursor.com/t/chats-running-on-cloud-keeps-sending-notification-after-i-have-viewed-them-in-cursor/151713); [Warp u45](https://github.com/warpdotdev/warp/issues/15933) |

## What this corpus does not show anyone doing well

These are bounded evidence gaps and design openings, not universal absence claims: (1) reliably making silence mean every child is progressing or an exception will surface; (2) admitting new work at the rate the person can review it, rather than merely limiting concurrent compute; (3) preserving an inspectable intent/acceptance contract from plan through correction and independently checked outcome; (4) turning accepted/rejected results into reversible trust by work type, with measured fewer questions; (5) bringing a prepared decision, the actual artifact, its exact checked revision and a safe timed fallback into one doorway. Memory, plan approval, inboxes and validators cover parts; none of the sources establishes the whole loop.
Counterexamples matter: [Factory has milestone validator workers](https://docs.factory.com/missions/planning); [CodeRabbit versions plans and separates approval](https://docs.coderabbit.ai/code/work-with-a-task); [Warp has explicit question/skip controls](https://docs.warp.dev/agents/local-agents/interacting-with-agents/agent-questions/); [Devin automatically learns preferences](https://docs.devin.ai/product-guides/memory). The missing evidence is reliable integration and falling human load, not whether those features exist.

## Measured results and limits

[METR RCT, early 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/): 16 developers/246 tasks; AI access increased completion time 19% (reported CI +2% to +39%). Dated assistance study, not a current unattended-agent benchmark; [2026 update](https://metr.org/blog/2026-02-24-uplift-update/) explains follow-up measurement/selection problems.
[Answer.AI, January 2025](https://www.answer.ai/posts/2025-01-08-devin.html): Devin 3 successes, 14 failures, 3 inconclusive /20 tasks; informal old-version trial. [AIDev task-stratified study](https://arxiv.org/abs/2602.08915): 7,156 PRs, five agents; reported acceptance 82.1% documentation versus 66.1% features; observational, not correctness or saved review time.
[Anthropic, March 2026](https://www.anthropic.com/research/claude-code-auto-mode): users accept 93% of permission prompts; vendor classifier evaluation reports 0.4% benign-action false positives and 17% real-overeager-action misses. Acceptance is not proof prompts are unnecessary. [Older Devin disclosure](https://cognition.com/blog/devin-2-1): green confidence associated with twice the PR-merge likelihood of red; sample/causality not supplied.
No comparable current measures of human review minutes, intervention frequency, approval comprehension or memory-induced question reduction were found. Anonymous review-time claims and an inaccessible CHI full text are kept separate in notes, not promoted into measured findings.

## Provenance and reproduction

Reproduce counts/coverage: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/outside-d6/analyze.py`. It validates source receipts and regenerates `summary.json` and `notes.md`; coding choices are explicit in `complaints.json`. Published study numbers are reported, not recomputed from unavailable participant data.
Audit: 50 complaint rows inspected without replacement in seeded random order (20261112); one initial tag error, 1/50 = 2%, corrected: u36 was stale UI, not model context loss. Ten direct Reddit reads yielded empty article text despite HTTP 200 and were recovered through the public search connector; retrieval failures remain recorded. One coder; no bug reproduction or independent recoding.
Current-status exceptions: [Jules](https://jules.google/docs/changelog/2026-10-29) became read-only after November 11 and is historical only; its [timed plan auto-approval](https://jules.google/docs/review-plan/) is an instructive fallback that users reported firing while correcting the plan (u18). [Conductor](https://www.conductor.build/changelog) is active but winding down: cloud read-only November 13/shutdown November 20, local critical fixes into early 2027. Roo Code is excluded from the active count after its archive signal. Current Amp defaults, Cline surface differences and contradictory Cursor notification guidance are preserved in notes.
