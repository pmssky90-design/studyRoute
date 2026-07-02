"""Serve output locally and verify key deploy URLs return HTTP 200."""

from __future__ import annotations

import functools
import http.server
import json
import re
import socketserver
import threading
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def main() -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUTPUT))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    html = (OUTPUT / "index.html").read_text(encoding="utf-8")
    social_images = re.findall(
        r'<meta (?:property="og:image"|name="twitter:image") content="https://studyroute.co.kr/([^"]+)"',
        html,
    )
    paths = [
        "/robots.txt",
        "/sitemap.xml",
        "/assets/images/favicon.ico",
        "/assets/images/favicon-32x32.png",
        "/assets/images/apple-touch-icon.png",
    ]
    paths.extend(f"/{path}" for path in social_images[:2])
    results = {}
    try:
        for path in paths:
            with urllib.request.urlopen(base + path, timeout=10) as response:
                results[path] = response.status
    finally:
        httpd.shutdown()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
