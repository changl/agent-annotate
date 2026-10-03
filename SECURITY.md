# Security

Report vulnerabilities privately to the repository owner. Do not post reviewer content, credentials, or private review links in public issues.

The runtime binds loopback. Recorded Host/origin and mount checks guard proxy requests. Tailscale Funnel supplies TLS; page-scoped share keys and signed Secure/HttpOnly/SameSite cookies grant external review access. Possession of the private link grants access to its page. Tailnet visitors retain their Tailscale identity.

Do not expose raw local API ports or reset unrelated routes. Reviewer confirmation and history remain reviewer-owned. Legacy Cloudflare identity requires an explicitly trusted, JWT-validating edge.

The bundled Quill 2.0.3 dependency has low advisory GHSA-v3m3-f69x-jf25 affecting HTML export of formula/video content. Copy accepts text-only Deltas, rejects embeds and unsafe links, disables those formats, and never calls HTML export or renders reviewer HTML. No fixed Quill 2 release is available; reassess when upstream publishes one.
