"""annotate transports — pluggable publish/unpublish/status backends.

A transport exposes three functions:

    publish(slug: str, port: int, **opts) -> dict
        Register a public route from <transport>://<address>/<slug>/ to
        http://localhost:<port>/. Returns {"url": str, "details": dict}.

    unpublish(slug: str, **opts) -> dict
        Tear down the previously-registered route. Returns {"ok": bool}.

    status(slug: str | None = None, **opts) -> dict
        Health/visibility. If `slug` is None, returns a summary of all
        known routes. Otherwise returns the status for that slug only.

Load by name via `load(name)`. Transports live as sibling modules:

    cloudflare.py  — Cloudflare Tunnel ingress mutation
    tailscale.py   — Tailscale Funnel/serve (stubbed; raises NotImplementedError)
    local.py       — no-op; just returns http://localhost:<port>/
"""

import importlib
import importlib.util
from typing import Any


def load(name: str) -> Any:
    """Return the transport module for the given name.

    Raises KeyError if the transport is unknown.
    """
    name = (name or "").strip().lower()
    if not name:
        raise KeyError("transport name is empty")
    # File-based loading keeps optional transport dependencies isolated.
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent
    file = here / f"{name}.py"
    if not file.exists():
        raise KeyError(f"unknown transport: {name!r}")
    spec_name = f"annotate_transport_{name}"
    if spec_name in sys.modules:
        return sys.modules[spec_name]
    spec = importlib.util.spec_from_file_location(spec_name, file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec_name] = mod
    spec.loader.exec_module(mod)
    return mod
