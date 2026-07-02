from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
DEBUG_PORT = 9231
BASE_URL = "https://studyroute.co.kr"


class CDP:
    def __init__(self, websocket_url: str) -> None:
        parsed = urlparse(websocket_url)
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        self.sock.settimeout(0.5)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
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
        self.events: list[dict] = []

    def close(self) -> None:
        self.sock.close()

    def send(self, method: str, params: dict | None = None) -> dict:
        message_id = self.next_id
        self.next_id += 1
        payload = json.dumps({"id": message_id, "method": method, "params": params or {}}).encode("utf-8")
        self._send_frame(payload)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                message = json.loads(self._recv_frame().decode("utf-8"))
            except TimeoutError:
                continue
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})
            self.events.append(message)
        raise RuntimeError(f"CDP command timed out: {method}")

    def drain(self, seconds: float = 1.0) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                self.events.append(json.loads(self._recv_frame().decode("utf-8")))
            except TimeoutError:
                pass

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
        try:
            first = self._read_exact(2)
        except socket.timeout as exc:
            raise TimeoutError from exc
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
    result = cdp.send("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
    return result["result"].get("value")


def network_summary(cdp: CDP) -> dict:
    responses = {}
    failures = []
    for event in cdp.events:
        method = event.get("method")
        params = event.get("params", {})
        if method == "Network.responseReceived":
            response = params.get("response", {})
            url = response.get("url", "")
            if "search.js" in url or "search-index.json" in url or url.rstrip("/") == BASE_URL:
                responses[url] = {
                    "status": response.get("status"),
                    "mimeType": response.get("mimeType"),
                    "fromDiskCache": response.get("fromDiskCache"),
                    "fromPrefetchCache": response.get("fromPrefetchCache"),
                }
        elif method == "Network.loadingFailed":
            url = params.get("requestId")
            failures.append({"requestId": url, "errorText": params.get("errorText")})
    return {"responses": responses, "failures": failures}


def console_summary(cdp: CDP) -> list[dict]:
    logs = []
    for event in cdp.events:
        if event.get("method") == "Runtime.consoleAPICalled":
            params = event.get("params", {})
            logs.append({"type": params.get("type"), "args": [arg.get("value") for arg in params.get("args", [])]})
        elif event.get("method") == "Runtime.exceptionThrown":
            detail = event.get("params", {}).get("exceptionDetails", {})
            logs.append({"type": "exception", "text": detail.get("text"), "line": detail.get("lineNumber")})
    return logs


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    user_data = ROOT / ".edge-runtime-check"
    proc = subprocess.Popen(
        [
            str(EDGE),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={user_data}",
            BASE_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        cdp = CDP(wait_for_debug_url())
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        cdp.send("Page.navigate", {"url": BASE_URL})
        time.sleep(3)
        cdp.drain(1)

        initial = {
            "search_script_in_dom": evaluate(cdp, "Boolean(document.querySelector('script[src$=\"assets/js/search.js\"]'))"),
            "search_trigger_exists": evaluate(cdp, "Boolean(document.querySelector('.search-trigger'))"),
            "search_panel_exists": evaluate(cdp, "Boolean(document.querySelector('[data-search-panel]'))"),
            "search_input_exists": evaluate(cdp, "Boolean(document.querySelector('[data-search-input]'))"),
        }

        evaluate(cdp, "document.querySelector('.search-trigger').click()")
        time.sleep(1)
        cdp.drain(1)
        after_click = {
            "open_class": evaluate(cdp, "document.querySelector('.site-nav').classList.contains('is-search-open')"),
            "panel_opacity": evaluate(cdp, "getComputedStyle(document.querySelector('[data-search-panel]')).opacity"),
            "active_element": evaluate(cdp, "document.activeElement && document.activeElement.id"),
            "aria_expanded": evaluate(cdp, "document.querySelector('.search-trigger').getAttribute('aria-expanded')"),
        }

        evaluate(
            cdp,
            "document.querySelector('[data-search-input]').value='수학';"
            "document.querySelector('[data-search-input]').dispatchEvent(new Event('input', {bubbles:true}));",
        )
        time.sleep(2)
        cdp.drain(1)
        autocomplete = {
            "result_count": evaluate(cdp, "document.querySelectorAll('.search-result').length"),
            "first_result": evaluate(cdp, "document.querySelector('.search-result strong')?.textContent || ''"),
            "first_href": evaluate(cdp, "document.querySelector('.search-result')?.getAttribute('href') || ''"),
        }

        evaluate(cdp, "document.querySelector('.search-result').click()")
        time.sleep(1)
        cdp.drain(1)
        navigation = {"pathname": evaluate(cdp, "location.pathname")}

        shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        screenshot = REPORTS / "search-runtime-production.png"
        screenshot.write_bytes(base64.b64decode(shot["data"]))

        payload = {
            "base_url": BASE_URL,
            "initial": initial,
            "after_click": after_click,
            "autocomplete": autocomplete,
            "navigation": navigation,
            "network": network_summary(cdp),
            "console": console_summary(cdp),
            "screenshot": str(screenshot.relative_to(ROOT)),
        }
        payload["passed"] = (
            initial["search_script_in_dom"]
            and initial["search_trigger_exists"]
            and initial["search_panel_exists"]
            and after_click["open_class"]
            and after_click["aria_expanded"] == "true"
            and int(autocomplete["result_count"] or 0) > 0
            and navigation["pathname"] != "/"
            and not payload["console"]
        )
        (REPORTS / "search_runtime_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        cdp.close()
        if not payload["passed"]:
            raise SystemExit(1)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
