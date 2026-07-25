# Interaction contract

These behaviors are release gates, not visual preferences.

1. Exactly one content tab is visible, and every long tab can be scrolled to its bottom.
2. Diagram navigation controls move to the requested diagram target and visibly identify it.
3. Clicking a numbered pin opens the feedback rail and focuses that exact numbered thread.
4. New pins retain an inner target and click offset so they render at the applicable point inside a larger box.
5. Older comments without granular target data fall back to their stable parent anchor.
6. Comment states follow `open -> addressed_by_agent -> user_confirmed -> archived`.
7. An agent response must not silently confirm or archive a user's comment.
8. Version changes retain comments and preserve explicit version association.
9. Push-to-session reports `Sent` only when the page has a verified live owner; otherwise it reports `Queued`.
10. Ownership takeover stops only the previous monitor. It never stops the page server or discards feedback.
11. Feedback activity is append-audited before delivery and can be replayed after a provider outage.
12. Public-delivery acceptance is tested through the actual edge path; localhost success alone is insufficient.
13. Click-to-comment never suppresses a native control's own behavior. Links, form
    controls, ARIA widget roles, contenteditable regions, focusable elements, and
    artifact chrome act natively on click. Authors opt a custom widget out with
    `data-annotate-interactive`; Alt/Option-click forces a comment on any excluded
    element.
14. Both rails can be collapsed and expanded independently, that state persists
    across reloads, and the collapsed feedback rail still reports its
    outstanding comment count.
15. Reviewer chrome is served, never baked. A fix to the chrome reaches every
    published page on its next request, with nothing regenerated and no
    per-page edit. A page whose content the server cannot recover is the only
    exception, and it serves its own baked chrome unchanged.

All browser releases must test long and short tabs at supported desktop
viewports with the feedback rail both open and collapsed. Collapsed rail state
persists across reloads, so pin placement must be re-verified after the canvas
resizes in each direction. Monitor tests must cover claim conflict, explicit
takeover, queued push, replay, and provider failure.

