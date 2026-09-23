# Interaction contract

These behaviors are release gates, not visual preferences. The one copy of
this file lives here; the Codex skill and plugin point at it.

## Reviewing

1. Exactly one content tab is visible, and every long tab can be scrolled to its bottom.
2. Diagram navigation controls move to the requested diagram target and visibly identify it.
3. Clicking a numbered pin opens the feedback rail and focuses that exact numbered thread.
4. New pins retain an inner target and click offset so they render at the applicable point inside a larger box. Table-row anchors and anchors up to 60px tall are centered in their own band rather than cornered.
5. Older comments without granular target data fall back to their stable parent anchor.
6. Hovering a pin outlines its anchor; hovering an anchor or its body strip rings its pins.
7. Click-to-comment never suppresses a native control's own behavior. Links, form controls, ARIA widget roles, contenteditable regions, focusable elements, and artifact chrome act natively on click. Authors opt a custom widget out with `data-annotate-interactive`; Alt/Option-click forces a comment on any excluded element.
8. Both rails can be collapsed and expanded independently, that state persists across reloads, and the collapsed feedback rail still reports its outstanding comment count.
9. Below the compact breakpoint (`max-width: 1160px`, or `max-height: 480px`) the version rail becomes a `<select>`, the drawer a bottom sheet behind a floating action button, and popovers become sheets, with 44px tap targets. Desktop above the breakpoint is untouched.
10. Reviewer chrome is served, never baked. A fix to the chrome reaches every published page on its next request, with nothing regenerated and no per-page edit. A page whose content the server cannot recover is the only exception, and it serves its own baked chrome unchanged.

## Comments and decisions

11. Comment states follow `open -> addressed_by_agent -> user_confirmed -> archived` within a round. `addressed_by_agent` can never demote `user_confirmed`.
11a. Before vN publishes, every earlier `open` or `addressed_by_agent` item is either `resolved_in_version` with a real vN-or-earlier anchor pointer, or carried onto a real vN anchor as open work. Publication fails closed otherwise.
11b. `resolved_in_version` stays visible as history on its origin version, is not outstanding on later versions, and a reviewer reply reopens it without erasing resolution provenance. It is excluded from `cards`, inbox/hook card totals, round submission, and every `undecided_ids` calculation.
11c. Carry-forward preserves origin version/anchor and a carry history while moving the live card to the target version/anchor.
12. An agent response must not silently confirm or archive a user's comment.
13. Version changes retain comments and preserve explicit version association.
14. A decision card renders its prompt, context, recommendation, each option's consequence, impact and blocking chips, and evidence links on both the rail card and the inline body strip. A card the server would not store (malformed, or over the 8192-byte cap) is refused with HTTP 400/413, never silently dropped.
15. A verdict can be changed; the prior verdict is kept in `decision_history` and both bus events mark the reversal.
15a. The third verdict is "Request changes" (`changes`) wherever the server advertises it in `GET /api/capabilities` `verdicts`, and it submits only with a non-empty note. A server that does not advertise it still shows the pre-D2 "Comment" button, and the server accepts that verdict from such a page indefinitely.
15b. Every unanswered card carries **Answer in words**. Its `comment` verdict requires text, writes `💬 Answer in words:`, collapses the options, moves the card to "Waiting on agent", and counts as answered. Plain thread replies are non-answer remarks.
15c. An option label of any length wraps inside the rail and the body strip; nothing in a decision card renders outside the rail's width.
15d. Focus landing in any of a card's boxes — reply, verdict note, "Request changes", "Comment" — takes the document to that card's location, exactly as clicking the card does, without disturbing what is being typed.
16. In round mode (server capabilities report `rounds`) a verdict click is parked with `round_pending` and emits no push. "Submit review" clears every pending flag and emits exactly one `round_submitted` and one `session_push {round: true}`; "Discard pending" emits `round_discarded` and no push; "Send now" pushes that one card. Against a server without capabilities the chrome behaves exactly as v2.18.
17. `ask` is idempotent by anchor: re-posing a round updates existing cards by the same author on the same anchor instead of duplicating them.

## Delivery and ownership

18. Push-to-session reports `Sent` only when the page has a verified live owner lease; otherwise it reports `Queued`. A deferred verdict reports `deferred` and emits nothing.
19. Ownership takeover stops only the previous monitor. It never stops the page server or discards feedback.
20. Feedback activity is append-audited before delivery and can be replayed after a provider outage.
21. The UserPromptSubmit hook notifies only the session that published or claimed the slug (a slug with no owner recorded notifies everyone), counts only reviewer events, keeps one cursor per session, and never advances the `inbox --unread` cursor.
22. A session never acts on a partial round: it waits for `round_submitted` or for every card to carry a verdict.
23. The monitor releases its lease on SIGTERM and SIGHUP and records `monitor_exited`; a lease pointing at a dead pid is never reported as a listener.

## Publishing

24. A published URL is printed only after the page has been read back and found to contain commentable anchors, at every hop the transport adds. A Cloudflare Access login page is `UNVERIFIED`, not a failure; a 502, 404 or zero anchors on a reachable hop is `NOT PUBLISHED`.
25. Public-delivery acceptance is tested through the actual edge path; localhost success alone is insufficient.
26. `publish-version` registers a version once; re-running it updates the entry in place, under the same lock the server takes on `current.meta.json`.
27. The carry-over gate runs before `current.html` or version history changes, so a rejected publication leaves the prior version selected.
28. Every later-version source declares `full_plan: true` and `other_files_required`; the rendered page says whether any other file must be read. Generating vN writes its files but does not select it until `publish-version` passes.
29. Every later-version response item has one stable positive integer `number`, is placed in the single final `## Questions for Chang` section in ascending order, uses `d:q<number>`, and links back to plan evidence. Rail, body card, and pin show the same `#<number>` and sort by it.
30. The annotate page contains plan and review substance. Chat handoff contains only what changed, what Chang must answer, and the URL; it never repeats the page as a wall of text.

All browser releases must test long and short tabs at supported desktop
viewports with the feedback rail both open and collapsed, and the compact
layout at phone width. Collapsed rail state persists across reloads, so pin
placement must be re-verified after the canvas resizes in each direction.
Monitor tests must cover claim conflict, explicit takeover, queued push, round
submit, replay, SIGTERM release, and provider failure.
