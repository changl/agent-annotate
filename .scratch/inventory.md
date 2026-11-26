Inventory (M1Max, 02:55Z 11-24). Boot 07:01Z 11-23; Orca relaunched sessions in waves at ~19:19Z 11-23 and ~01:10Z 11-24, each with a NEW terminal handle.

Root cause already visible: delivery.refresh_session_owners skips a resumed owner whenever its recorded handle differs from the new one (`old["handle"] != target["handle"]`). Every resume got a new handle, so no page re-bound itself.

Page owners/orchestrators active 11-21..11-23 (project/page | session | alive now, current handle | owner record | queued Sends)
1. reviews: annotate-owner-takeover, -assessment, -conformity, -weekly | 3c3ae250 | alive pid 76084 term_3337e5b0 | re-bound only by manual claim 02:46:52Z | 1 Send 02:45:01Z sat pending on old handle term_7b8d553b, read 02:46:53 after the claim; none now
2. reviews: annotate-uiux-20261116 | 4e024ed8 | alive pid 4071 term_2bbe6cd6 | manual claim 02:50:46Z | none
3. reviews: fld-stack-round8 (FLD-B02) | 029a2e82 | alive pid 67782 term_f84f8e53 | re-bound by manual claim between 01:42 and 02:09Z | 1 Send 01:41:52Z queued on old term_105daa9f, read 01:42; none now
4. FLD usage audit: page | 42833a9a | alive pid 82254 term_18941829 | still old owner (pid 2094, term_cef9f5b0) = gone | none
5. cheerticketing: ui-revamp-2026-11 | 8e391e85 | alive pid 71799 term_5b205216 | still old (term_4281991a) = gone | none
6. leadory: wind-down-plan | 28ccd217 | alive pid 2887 term_10527dac | still old (term_89b3a596) = gone | none
7. multimac-orch: multimac-orch | fd956ed9 | alive pid 54484 term_a2e3f45b | still old (term_70a277cf) = gone | none
8. multimac-orch: storage | 5fc6435d | alive pid 54485 term_354f206e | still old (term_38712f84) = gone | none
9. rebex: rebex | 2c74e618 | owner pid 60552 alive term_f342268e (fresh claim 01:12Z) | ok | none
10. rebex: rebex-image-review | 68517770 | NOT running (no resumed process) | gone | none
11. fld-admin-meeting | owner_session "unknown", no Orca binding | n/a | none

Orchestrators with no page (resumed, alive, idle unless woken): Rebex orch d6df3500 pid 51274 term_2226d232; FLD orch ad54b05b pid 66167 term_b15041ce; review-surface lead f1ee23dd pid 56257 term_da4e4309; FLD workers 0c14c3db, 6dd250aa, 51f35d63, 52de52af, 738370e6, 9c0924fd, fd9dd4af, 6b705194, f3f77807; cheerticketing 01b7dcce, 2281890c.

Dead on purpose (Codex owners, not resumed, 20-60 days): ponytail/installation, windmill/workflow-plan, reviews/skills-consolidation, reviews/windmill-* (3, cheerticketing:28de/2758), agent-memory, codex-memory.

No Send is queued right now. Next: fix the handle check with tests, then sweep liveness + wake trigger.
