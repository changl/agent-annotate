# Required behaviors

- Exactly one tab panel is visible and every long tab reaches its bottom.
- Diagram navigation moves to and highlights the requested target.
- A numbered pin focuses its exact numbered feedback card.
- New comments retain an inner target and click offset; older comments fall back to their parent anchor.
- Native controls, ARIA widgets, contenteditable and focusable elements, and artifact chrome act natively on click; `data-annotate-interactive` opts a custom widget out and Alt/Option-click forces a comment anyway.
- Both rails collapse and expand independently, persist that state, and the feedback rail reports its comment count while collapsed.
- Reviewer chrome is served from the package, never baked into a published page; a chrome fix reaches every page on its next request with nothing regenerated.
- Lifecycle is `open -> addressed_by_agent -> user_confirmed -> archived`.
- Agent actions never silently confirm or archive user feedback.
- Version changes retain comments and explicit version association.
- Push reports sent only with a verified live owner; otherwise it queues durably.
- Explicit takeover stops only the old monitor, never the page server.
- Provider delivery failures replay from the append-only event history.
- Public delivery is verified through the actual edge path.

