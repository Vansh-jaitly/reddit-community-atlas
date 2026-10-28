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
    ("01_discover", "#/discover"),
    ("02_atlas_raw", "#/atlas?view=raw"),
    ("03_atlas_adjusted", "#/atlas"),
    ("04_atlas_selected", "#/atlas?sel={personalfinance}"),
    ("05_story_popularity_raw", "#/stories/popularity"),
    ("06_story_popularity_example", "#/stories/popularity?step=2"),
    ("07_story_neighbours", "#/stories/neighbours"),
    ("08_story_connectors", "#/stories/connectors"),
    ("09_story_crowds_timeline", "#/stories/crowds"),
    ("10_story_crowds_peak", "#/stories/crowds?step=1"),
    ("11_story_crowds_after", "#/stories/crowds?step=2"),
    ("12_story_marvel", "#/stories/crowds?step=3"),
    ("13_explore_profile", "#/explore/personalfinance"),
    ("14_compare_pair", "#/compare?a=CanadaPolitics&b=PersonalFinanceCanada"),
    ("15_compare_periods", "#/compare?mode=periods&p1=2017Q4&p2=2018Q3"),
    ("16_methods", "#/methods"),
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


def main():
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/screenshots"))
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    ids = {n["name"]: n["id"] for n in json.loads((WEB / "data/nodes.json").read_text())}

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    browser = find_browser()
    profile = tempfile.mkdtemp(prefix="atlas-shots-")
    for name, frag in VIEWS:
        url = base + frag.format(**ids)
        subprocess.run([browser, "--headless=new", f"--user-data-dir={profile}", "--use-angle=swiftshader",
                        "--enable-unsafe-swiftshader", "--hide-scrollbars", f"--window-size={args.width},{args.height}",
                        "--virtual-time-budget=12000", f"--screenshot={out / (name + '.png')}", url],
                       capture_output=True, timeout=120)
        print(("ok   " if (out / f"{name}.png").exists() else "FAIL ") + name)
    srv.shutdown()
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
