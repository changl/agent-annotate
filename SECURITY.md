# Security

Report vulnerabilities privately to the repository owner. Do not post reviewer content, credentials, or private review links in public issues.

The runtime binds loopback. Recorded Host/origin and mount checks guard proxy requests. Tailscale Funnel supplies TLS; page-scoped share keys and signed Secure/HttpOnly/SameSite cookies grant external review access. Possession of the private link grants access to its page. Tailnet visitors retain their Tailscale identity.

Do not expose raw local API ports or reset unrelated routes. Reviewer confirmation and history remain reviewer-owned. Legacy Cloudflare identity requires an explicitly trusted, JWT-validating edge.
