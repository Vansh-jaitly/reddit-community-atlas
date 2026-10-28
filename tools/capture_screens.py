"""
Capture 1440x900 screenshots of Atlas views with a headless Chrome/Edge, for the
report, slides and demo video. Every view is addressable by URL, so no clicking
is scripted.

Usage:  python tools/capture_screens.py [--out docs/screenshots]
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "atlas/web"

VIEWS = [
    ("01_start", "#/start"),
    ("02_start_raw", "#/atlas?view=raw"),
    ("03_atlas_adjusted", "#/atlas"),
    ("04_atlas_selected", "#/atlas?sel={personalfinance}"),
    ("05_atlas_surprise", "#/atlas?view=surprise"),
    ("06_tour_surprise", "#/atlas?view=surprise&tour=3"),
    ("07_story_neighbours", "#/stories/neighbours"),
    ("08_story_connectors", "#/stories/connectors"),
    ("09_story_crowds_timeline", "#/stories/crowds"),
    ("10_story_crowds_peak", "#/stories/crowds?step=1"),
    ("11_story_crowds_after", "#/stories/crowds?step=2"),
    ("12_story_takeaway", "#/stories/popularity?step=5"),
    ("13_explore_profile", "#/explore/personalfinance"),
    ("14_compare_pair", "#/compare?a=CanadaPolitics&b=PersonalFinanceCanada"),
    ("15_compare_periods", "#/compare?mode=periods&p1=2017Q4&p2=2018Q3"),
    ("16_pipeline_expected", "#/pipeline?stage=expected"),
    ("17_pipeline_validated", "#/pipeline?stage=validated"),
    ("18_about", "#/about"),   # headless Chrome does not paint a scrolled viewport, so the page top stands in for the section
    ("19_start_mobile", "#/start", 390, 844),
    ("20_atlas_mobile", "#/atlas?sel={Bitcoin}", 390, 844),
    ("21_story_crowds_starwars", "#/stories/crowds?step=3"),
    ("22_story_crowds_marvel", "#/stories/crowds?step=4"),
]
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "google-chrome", "chromium", "msedge",
]


def find_browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("No Chrome/Edge found for headless screenshots.")


def capture_with_devtools(browser: str, profile: str, url: str, width: int, height: int, png: Path) -> None:
    """Open one headless Chrome with remote debugging, emulate a width x height device, load the view and screenshot it."""
    import asyncio
    import base64
    import json
    import socket
    import time
    import urllib.request
    from tornado.websocket import websocket_connect   # Tornado ships with Streamlit, already a dependency

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    proc = subprocess.Popen([browser, "--headless=new", f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
                             "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                             "--window-size=600,1000", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(100):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2).read())
                ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t.get("type") == "page")
                break
            except Exception:   # noqa: BLE001 - the browser is still starting
                time.sleep(0.2)
        if not ws_url:
            raise RuntimeError("DevTools endpoint did not come up")

        async def run():
            conn = await websocket_connect(ws_url, max_message_size=64 * 1024 * 1024)
            counter = {"id": 0}

            async def send(method, params=None):
                counter["id"] += 1
                await conn.write_message(json.dumps({"id": counter["id"], "method": method, "params": params or {}}))
                while True:   # events (no id) are skipped until the reply arrives
                    msg = await conn.read_message()
                    if msg is None:
                        raise RuntimeError("DevTools connection closed")
                    m = json.loads(msg)
                    if m.get("id") == counter["id"]:
                        if "error" in m:
                            raise RuntimeError(m["error"])
                        return m.get("result", {})

            await send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": True})
            await send("Page.enable")
            await send("Page.navigate", {"url": url})
            ready = ("!!document.querySelector('#view') && !document.querySelector('#view .loading') "
                     "&& document.querySelector('#view').innerText.length > 50")
            for _ in range(80):
                await asyncio.sleep(0.25)
                r = await send("Runtime.evaluate", {"expression": ready, "returnByValue": True})
                if r.get("result", {}).get("value"):
                    break
            await asyncio.sleep(3.0)   # let the map render and animations settle
            shot = await send("Page.captureScreenshot", {"format": "png"})
            png.write_bytes(base64.b64decode(shot["data"]))
            conn.close()

        asyncio.run(asyncio.wait_for(run(), timeout=90))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:   # noqa: BLE001
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def main():
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/screenshots"))
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--only", default=None, help="capture only views whose name contains this text")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    ids = {n["name"]: n["id"] for n in json.loads((WEB / "data/nodes.json").read_text())}

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):   # keep the request log out of the capture output
            pass
    handler = functools.partial(QuietHandler, directory=str(WEB))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    browser = find_browser()
    profile = tempfile.mkdtemp(prefix="atlas-shots-")
    for name, frag, *size in VIEWS:
        if args.only and args.only not in name:
            continue
        url = base + "?shot=1" + frag.format(**ids)   # ?shot=1: pages skip scrolling, which headless Chrome does not paint
        png = out / f"{name}.png"
        if size:
            # headless Chrome will not open a window narrower than about 500 px, so narrow views are captured through
            # the DevTools protocol with a device-metrics override (a real 390 px viewport, media queries included)
            try:
                capture_with_devtools(browser, profile + "-cdp", url, size[0], size[1], png)
            except Exception as e:   # noqa: BLE001 - a failed narrow capture must not stop the run
                print(f"FAIL {name}: {e}")
                continue
        else:
            w, h = args.width, args.height
            subprocess.run([browser, "--headless=new", f"--user-data-dir={profile}", "--use-angle=swiftshader",
                            "--enable-unsafe-swiftshader", "--hide-scrollbars", f"--window-size={w},{h}",
                            "--virtual-time-budget=12000", f"--screenshot={png}", url],
                           capture_output=True, timeout=120)
        print(("ok   " if png.exists() else "FAIL ") + name)
    srv.shutdown()
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
