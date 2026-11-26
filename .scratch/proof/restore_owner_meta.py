"""Re-stamp the claimed owner into the sandbox page meta (I overwrote it while fixing the draft meta)."""
import json
from pathlib import Path

from agent_annotate import cli, paths

record = json.loads((paths.STATE_DIR / "proof.json").read_text())["slugs"]["proof-page"]
print(cli._write_owner_meta(Path(record["slug_dir"]), record))
print(json.loads((Path(record["slug_dir"]) / "current.meta.json").read_text())["owner"]["target"]["handle"])
