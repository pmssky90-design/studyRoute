import csv
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from openpyxl import Workbook


VERIFY = Path(r"C:\Projects\studyhub\verification")
URLS_FILE = VERIFY / "http_urls_to_check.txt"
OUT_CSV = VERIFY / "full_url_audit.csv"
ERR_XLSX = VERIFY / "http_status_errors.xlsx"
DELAY = 0.25
TIMEOUT = 5


CSV_COLUMNS = [
    "original_url",
    "final_url",
    "status_code",
    "redirect_count",
    "redirect_chain",
    "error",
    "content_type",
    "content_length",
    "method",
    "x_robots_tag",
    "server",
]

ISSUE_COLUMNS = [
    "issue_type",
    "local_file",
    "original_url",
    "final_url",
    "status_code",
    "detected_host",
    "expected_host",
    "source_page",
    "detail",
    "severity",
    "recommended_fix",
]


def response_to_row(url, resp, method):
    chain = [f"{r.status_code} {r.url}" for r in resp.history] + [f"{resp.status_code} {resp.url}"]
    return {
        "original_url": url,
        "final_url": resp.url,
        "status_code": resp.status_code,
        "redirect_count": len(resp.history),
        "redirect_chain": " -> ".join(chain),
        "error": "",
        "content_type": resp.headers.get("content-type", ""),
        "content_length": resp.headers.get("content-length", ""),
        "method": method,
        "x_robots_tag": resp.headers.get("x-robots-tag", ""),
        "server": resp.headers.get("server", ""),
    }


def request(session, url):
    result = {col: "" for col in CSV_COLUMNS}
    result["original_url"] = url
    for attempt in range(2):
        try:
            resp = session.head(url, allow_redirects=True, timeout=TIMEOUT)
            method = "HEAD"
            if resp.status_code in (403, 405) or resp.status_code >= 500:
                time.sleep(DELAY)
                resp = session.get(url, allow_redirects=True, timeout=TIMEOUT)
                method = "GET"
            return response_to_row(url, resp, method)
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                time.sleep(0.5)
    return result


def append_csv(rows, reset=False):
    mode = "w" if reset else "a"
    exists = OUT_CSV.exists() and not reset
    with OUT_CSV.open(mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def existing_urls():
    if not OUT_CSV.exists():
        return set()
    with OUT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return {row.get("original_url", "") for row in csv.DictReader(f)}


def write_errors_from_csv():
    rows = []
    with OUT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            status_text = row.get("status_code", "")
            try:
                status = int(status_text)
            except Exception:
                status = 0
            if row.get("error") or status < 200 or status >= 400:
                parsed = urllib.parse.urlparse(row.get("final_url") or "")
                rows.append(
                    {
                        "issue_type": "http_status_error",
                        "local_file": "",
                        "original_url": row.get("original_url", ""),
                        "final_url": row.get("final_url", ""),
                        "status_code": row.get("status_code", ""),
                        "detected_host": parsed.netloc,
                        "expected_host": "studyhub.co.kr",
                        "source_page": "",
                        "detail": row.get("error") or row.get("redirect_chain", ""),
                        "severity": "P1",
                        "recommended_fix": "최종 상태가 200~399가 되도록 경로, 배포 파일, 리다이렉션을 확인하세요.",
                    }
                )
    wb = Workbook()
    ws = wb.active
    ws.title = "audit"
    ws.append(ISSUE_COLUMNS)
    for row in rows:
        ws.append([row.get(col, "") for col in ISSUE_COLUMNS])
    ws.freeze_panes = "A2"
    wb.save(ERR_XLSX)
    return len(rows)


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
    reset = "--reset" in sys.argv
    urls = [line.strip() for line in URLS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = set() if reset else existing_urls()
    chunk = [u for u in urls[start : start + limit] if u not in done]
    session = requests.Session()
    session.headers.update({"User-Agent": "StudyHubAudit/1.0 (+https://studyhub.co.kr)"})
    if reset and OUT_CSV.exists():
        OUT_CSV.unlink()
    total = len(chunk)
    for idx, url in enumerate(chunk, 1):
        time.sleep(DELAY)
        append_csv([request(session, url)], reset=False)
        if idx % 50 == 0:
            print(f"checked {start + idx}/{len(urls)}")
    err_count = write_errors_from_csv()
    print(f"chunk_done start={start} count={total} total_urls={len(urls)} errors={err_count}")


if __name__ == "__main__":
    main()
