# Interaction contract

1. One canonical project URL across sessions; Progress and Feedback tabs, plus short supplemental tabs. Existing independent worksheets remain resource links.
2. Publish supplies the URL; the agent shares it without being asked. The full Tailscale Funnel share link is canonical; explicit local setup is for development.
3. Updates are meaningful, batched, and concise. Identical project content changes neither timestamp nor unread count. Progress does not create feedback rounds.
4. Every decision can receive a text answer, an explanation with any choice, and a card comment, including after **Change verdict**. Native controls retain their behavior. Cmd/Ctrl+Enter submits text.
5. Feedback, decisions, drafts, numbers, and history survive refreshes, versions, and owner changes. An agent never confirms for a reviewer.
6. **Finish review** persists one round before waking its current owner. A missing owner queues feedback; ambiguous sends are not repeated automatically. The UI distinguishes saved feedback, accepted input, and agent acknowledgment.
7. Ownership shows available Orca group, project, worktree, and terminal names, with the terminal handle. Unknown names are omitted, never invented. Routing still validates terminal incarnation and provider process.
8. Dark is daisyUI `dark`; light is daisyUI `light`. The chosen theme persists and applies to generated content and feedback controls. Tabs, long content, tables, and text fields remain usable on mobile and keyboard.

For authoring use [page format](building-pages.md); for decisions use [cards](decision-cards.md). Legacy transport/provider adapters are compatibility paths, not extra steps in normal project work.
