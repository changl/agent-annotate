"""Sandbox page server on 127.0.0.1:18700 (run through ./aa py). Seeds the registry record once."""
import http.server
import json
import os
from pathlib import Path

from agent_annotate import paths
from agent_annotate.sync_server import make_handler

SBX = Path(os.environ["ANNOTATE_STATE_DIR"]).parent
assert "aa-resume-dlj/.scratch/proof/sbx" in str(paths.STATE_DIR), paths.STATE_DIR
slug_dir = SBX / "pages" / "proof-page"
bus_dir = paths.BUS_ROOT / "proof"
slug_dir.mkdir(parents=True, exist_ok=True)
bus_dir.mkdir(parents=True, exist_ok=True)
if not (slug_dir / "comments.json").exists():
    (slug_dir / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}))
    (slug_dir / "current.meta.json").write_text(json.dumps(
        {"name": "Restart proof", "current": "v1", "history": [{"version": "v1", "label": "initial"}]}))
state_file = paths.STATE_DIR / "proof.json"
if not state_file.exists():
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"project": "proof", "slugs": {"proof-page": {
        "slug_dir": str(slug_dir), "bus_file": str(bus_dir / "proof-page.ndjson"),
        "port": 18700, "title": "Restart proof"}}}))
handler = make_handler(artifact_dir=slug_dir, public_base_path="", slug="proof-page", bus_dir=bus_dir,
                       proxy_urls=("https://review.example.test",),
                       trusted_access_origins=("https://review.example.test",))
print("serving 127.0.0.1:18700", flush=True)
http.server.ThreadingHTTPServer(("127.0.0.1", 18700), handler).serve_forever()
