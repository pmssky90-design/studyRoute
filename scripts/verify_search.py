from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
REPORTS = ROOT / "reports"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
PORT = 8771
DEBUG_PORT = 9227


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class CDP:
    def __init__(self, url: str) -> None:
        self.sock = socket.create_connection((url.hostname, url.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = (url.path or "/") + (("?" + url.query) if url.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {url.hostname}:{url.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response:
            raise RuntimeError("WebSocket upgrade failed")
        self.next_id = 1

    def close(self) -> None:
        self.sock.close()

    def send(self, method: str, params: dict | None = None) -> dict:
        message_id = self.next_id
        self.next_id += 1
        payload = json.dumps({"id": message_id, "method": method, "params": params or {}}).encode("utf-8")
        self._send_frame(payload)
        while True:
            message = json.loads(self._recv_frame().decode("utf-8"))
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def _send_frame(self, payload: bytes) -> None:
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self) -> bytes:
        first = self._read_exact(2)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if first[1] & 0x80:
            mask = self._read_exact(4)
            data = self._read_exact(length)
            return bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        return self._read_exact(length)

    def _read_exact(self, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("Socket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def wait_for_debug_url() -> str:
    list_url = f"http://127.0.0.1:{DEBUG_PORT}/json/list"
    for _ in range(80):
        try:
            with urllib.request.urlopen(list_url, timeout=1) as response:
                pages = json.loads(response.read().decode("utf-8"))
            for page in pages:
                if page.get("type") == "page":
                    return page["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Edge remote debugging endpoint did not start")


def evaluate(cdp: CDP, expression: str) -> object:
    result = cdp.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
    )
    return result["result"].get("value")


def run_case(cdp: CDP, name: str, width: int, height: int, query: str) -> dict:
    cdp.send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768})
    cdp.send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html"})
    time.sleep(1.0)
    cdp.send("Runtime.evaluate", {"expression": "document.querySelector('.search-trigger').click()"})
    time.sleep(0.3)
    evaluate(cdp, f"document.querySelector('[data-search-input]').value = {json.dumps(query)}; document.querySelector('[data-search-input]').dispatchEvent(new Event('input', {{ bubbles: true }}));")
    time.sleep(0.8)
    open_state = evaluate(cdp, "document.querySelector('.site-nav').classList.contains('is-search-open')")
    result_count = evaluate(cdp, "document.querySelectorAll('.search-result').length")
    first_text = evaluate(cdp, "document.querySelector('.search-result strong')?.textContent || ''")
    panel_fixed = evaluate(cdp, "getComputedStyle(document.querySelector('[data-search-panel]')).position")
    first_href = evaluate(cdp, "document.querySelector('.search-result')?.getAttribute('href') || ''")
    shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    screenshot = REPORTS / f"search-{name}.png"
    screenshot.write_bytes(base64.b64decode(shot["data"]))
    cdp.send("Runtime.evaluate", {"expression": "document.querySelector('.search-result').click()"})
    time.sleep(0.8)
    navigated = evaluate(cdp, "location.pathname")
    cdp.send("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/index.html"})
    time.sleep(0.5)
    cdp.send("Runtime.evaluate", {"expression": "document.querySelector('.search-trigger').click()"})
    time.sleep(0.2)
    cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    time.sleep(0.2)
    esc_closed = not evaluate(cdp, "document.querySelector('.site-nav').classList.contains('is-search-open')")
    cdp.send("Runtime.evaluate", {"expression": "document.querySelector('.search-trigger').click()"})
    time.sleep(0.2)
    cdp.send("Runtime.evaluate", {"expression": "document.body.click()"})
    time.sleep(0.2)
    outside_closed = not evaluate(cdp, "document.querySelector('.site-nav').classList.contains('is-search-open')")
    return {
        "viewport": f"{width}x{height}",
        "query": query,
        "opened": bool(open_state),
        "results": int(result_count or 0),
        "first_result": first_text,
        "first_href": first_href,
        "navigated_path": navigated,
        "esc_closed": bool(esc_closed),
        "outside_click_closed": bool(outside_closed),
        "mobile_fullscreen": panel_fixed == "fixed" if width < 768 else True,
        "screenshot": str(screenshot.relative_to(ROOT)),
    }


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), QuietHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    os.chdir(OUTPUT)

    user_data = ROOT / ".edge-search-check"
    proc = subprocess.Popen(
        [
            str(EDGE),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={user_data}",
            f"http://127.0.0.1:{PORT}/index.html",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        from urllib.parse import urlparse

        cdp = CDP(urlparse(wait_for_debug_url()))
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cases = [
            run_case(cdp, "desktop", 1440, 1000, "대전"),
            run_case(cdp, "tablet", 820, 1100, "관평"),
            run_case(cdp, "mobile", 390, 844, "수학"),
        ]
        cdp.close()
    finally:
        proc.terminate()
        server.shutdown()

    index = json.loads((OUTPUT / "search-index.json").read_text(encoding="utf-8"))
    all_passed = all(
        case["opened"]
        and case["results"] > 0
        and case["first_href"]
        and case["navigated_path"] != "/index.html"
        and case["esc_closed"]
        and case["outside_click_closed"]
        and case["mobile_fullscreen"]
        for case in cases
    )
    payload = {"index_count": index["count"], "cases": cases, "passed": all_passed}
    (REPORTS / "search_verify_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
