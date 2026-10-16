"""Measure an isolated copy of a real page; writes only the test sandbox/output.

Run with this checkout on PYTHONPATH and dev/browser extras installed. The source
is copied before serving; no publish, registry, monitor, or transport is started.
"""

import argparse
import json
import shutil
import statistics
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # sandbox all state before package imports

root = conftest._SANDBOX

from playwright.sync_api import sync_playwright  # noqa: E402

from agent_annotate.paths import WEB_DIR  # noqa: E402
from agent_annotate.sync_server import ReviewHTTPServer, make_handler  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--browser", type=Path, required=True)
args = parser.parse_args()
source = args.source
page_dir = root / "page"
shutil.copytree(source, page_dir)
prefix = "/annotate/reviews/annotate-conformity-20260927"
server = ReviewHTTPServer(
    ("127.0.0.1", 0),
    make_handler(
        page_dir,
        public_base_path=prefix,
        slug="fixture",
        bus_dir=root / "bus",
        v2_mode=True,
        skill_dir=WEB_DIR,
        local_author="bench@example.test",
    ),
)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}{prefix}/"
results = []
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=str(args.browser))
        for mode in ("desktop", "slow4g"):
            for sample in range(3):
                context = browser.new_context(
                    viewport={
                        "width": 1440 if mode == "desktop" else 390,
                        "height": 960 if mode == "desktop" else 844,
                    }
                )
                page = context.new_page()
                page.set_default_timeout(120000)
                session = context.new_cdp_session(page)
                session.send("Network.enable")
                if mode == "slow4g":
                    session.send(
                        "Network.emulateNetworkConditions",
                        {
                            "offline": False,
                            "latency": 150,
                            "downloadThroughput": 1.6 * 1024 * 1024 / 8,
                            "uploadThroughput": 750 * 1024 / 8,
                        },
                    )
                    session.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                transfers = []
                responses = []
                session.on("Network.loadingFinished", lambda e: transfers.append(e["encodedDataLength"]))
                session.on(
                    "Network.responseReceived",
                    lambda e: responses.append(
                        {
                            "url": e["response"]["url"].split(prefix)[-1],
                            "status": e["response"]["status"],
                            "cached": e["response"].get("fromDiskCache", False),
                        }
                    ),
                )
                for load in ("cold", "warm"):
                    transfers.clear()
                    responses.clear()
                    page.goto(base + "#view=review", wait_until="commit") if load == "cold" else page.reload(
                        wait_until="commit"
                    )
                    page.locator(".citem").first.wait_for(state="attached")
                    card_ms = page.evaluate("performance.now()")
                    page.locator('body[data-ready="1"]').wait_for(state="attached")
                    frame = page.frame_locator("#content-frame")
                    frame.locator("body").wait_for()
                    # Load every real inline image, including images below the fold.
                    frame.locator("img").evaluate_all("imgs => imgs.forEach(i => i.loading = 'eager')")
                    frame.locator("body").evaluate(
                        "async () => { await Promise.all([...document.images].map(i => i.decode())); }"
                    )
                    page.wait_for_load_state("networkidle")
                    images = frame.locator("img").count()
                    results.append(
                        {
                            "mode": mode,
                            "sample": sample,
                            "load": load,
                            "bytes": sum(transfers),
                            "first_card_ms": round(card_ms, 1),
                            "images": images,
                            "responses": list(responses),
                        }
                    )
                    print(mode, sample, load, sum(transfers), round(card_ms, 1), images, flush=True)
                context.close()
        browser.close()
finally:
    server.shutdown()
    server.server_close()
Path(args.output).write_text(json.dumps(results, indent=2))
for mode in ("desktop", "slow4g"):
    for load in ("cold", "warm"):
        subset = [r for r in results if r["mode"] == mode and r["load"] == load]
        print(
            mode,
            load,
            statistics.median(r["bytes"] for r in subset),
            statistics.median(r["first_card_ms"] for r in subset),
        )
