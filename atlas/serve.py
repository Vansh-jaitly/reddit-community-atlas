"""
Serve the Community Atlas locally and open it in the browser.

Usage:  python atlas/serve.py [--port 8000] [--no-browser]
(Browsers block fetch() from file:// pages, so index.html must be served over HTTP.)
"""

import argparse
import functools
import http.server
import threading
import webbrowser
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if not (WEB / "data" / "meta.json").exists():
        raise SystemExit("atlas/web/data is missing: run `python atlas/build_atlas.py` first.")
    class Handler(http.server.SimpleHTTPRequestHandler):
        # Windows registries sometimes map .js to text/plain, which browsers refuse for ES modules.
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".js": "text/javascript", ".json": "application/json", ".gexf": "application/xml"}

        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")   # always serve freshly rebuilt data
            super().end_headers()

        def log_message(self, *args):
            pass

    handler = functools.partial(Handler, directory=str(WEB))
    # Threaded: browsers open idle speculative connections that would block a single-threaded server.
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"Community Atlas running at {url}  (Ctrl+C to stop)")
        if not args.no_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
