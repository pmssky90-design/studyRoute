import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from datetime import datetime
from html import unescape
from pathlib import Path

import requests
from openpyxl import Workbook


PROJECT = Path(r"C:\Projects\studyhub")
OUTPUT = PROJECT / "output"
VERIFY = PROJECT / "verification"
EXPECTED_HOST = "studyhub.co.kr"
EXPECTED_BASE = "https://studyhub.co.kr"
ALT_BASE = "https://www.studyhub.co.kr"
EDUGUIDE = "https://www.eduguide.kr"
HTTP_DELAY = 0.25
HTTP_TIMEOUT = 5

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


def safe_text(value):
    if value is None:
        return ""
    value = str(value)
    return "".join(ch if ch >= " " or ch in "\r\n\t" else " " for ch in value)


def normalize_site_url(url):
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or EXPECTED_HOST
    path = urllib.parse.unquote(parsed.path or "/")
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    if not path.endswith("/") and "." not in Path(path).name:
        path += "/"
    encoded_path = urllib.parse.quote(path, safe="/%")
    return urllib.parse.urlunparse((scheme, netloc.lower(), encoded_path, "", "", ""))


def write_xlsx(path, rows, columns=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or ISSUE_COLUMNS
    wb = Workbook()
    ws = wb.active
    ws.title = "audit"
    ws.append(columns)
    for row in rows:
        ws.append([safe_text(row.get(col, "")) for col in columns])
    ws.freeze_panes = "A2"
    widths = {col: min(max(len(col), 12), 70) for col in columns}
    for row in rows[:1000]:
        for col in columns:
            widths[col] = min(max(widths[col], len(safe_text(row.get(col, ""))) + 2), 70)
    for idx, col in enumerate(columns, 1):
        ws.column_dimensions[ws.cell(1, idx).column_letter].width = widths[col]
    wb.save(path)


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: safe_text(row.get(col, "")) for col in columns})


class HttpAuditor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "StudyHubAudit/1.0 (+https://studyhub.co.kr)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self.last = 0

    def wait(self):
        elapsed = time.time() - self.last
        if elapsed < HTTP_DELAY:
            time.sleep(HTTP_DELAY - elapsed)
        self.last = time.time()

    def request(self, url):
        self.wait()
        result = {
            "original_url": url,
            "final_url": "",
            "status_code": "",
            "redirect_count": "",
            "redirect_chain": "",
            "error": "",
            "content_type": "",
            "content_length": "",
            "method": "",
            "x_robots_tag": "",
            "server": "",
        }
        for attempt in range(2):
            try:
                resp = self.session.head(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
                method = "HEAD"
                if resp.status_code in (403, 405) or resp.status_code >= 500:
                    self.wait()
                    resp = self.session.get(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
                    method = "GET"
                result.update(response_to_row(resp, method))
                return result
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    time.sleep(0.5)
        return result

    def get_text(self, url):
        self.wait()
        result = self.request(url)
        text = ""
        try:
            self.wait()
            resp = self.session.get(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
            text = resp.text
            result.update(response_to_row(resp, "GET"))
            result["bytes"] = len(resp.content)
            result["bom"] = resp.content.startswith(b"\xef\xbb\xbf")
            result["utf8_ok"] = True
            try:
                resp.content.decode("utf-8")
            except UnicodeDecodeError:
                result["utf8_ok"] = False
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result, text


def response_to_row(resp, method):
    chain = [f"{r.status_code} {r.url}" for r in resp.history] + [f"{resp.status_code} {resp.url}"]
    return {
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


def parse_attrs(tag):
    attrs = {}
    for match in re.finditer(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", tag, flags=re.S):
        attrs[match.group(1).lower()] = unescape(match.group(3).strip())
    return attrs


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


def extract_html(path, rel_url):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        html = raw.decode("utf-8")
        utf8_ok = True
    except UnicodeDecodeError:
        html = raw.decode("utf-8", errors="replace")
        utf8_ok = False
    lower = html.lower()
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if m:
        title = strip_tags(m.group(1))
    metas = []
    links = []
    scripts = []
    for tag in re.findall(r"(?is)<meta\b[^>]*>", html):
        metas.append(parse_attrs(tag))
    for tag in re.findall(r"(?is)<link\b[^>]*>", html):
        links.append(parse_attrs(tag))
    for tag in re.findall(r"(?is)<a\b[^>]*>", html):
        links.append({"_tag": "a", **parse_attrs(tag)})
    for m in re.finditer(r"(?is)<script\b([^>]*)>(.*?)</script>", html):
        attrs = parse_attrs(m.group(1))
        if attrs.get("type", "").lower() == "application/ld+json":
            scripts.append(m.group(2).strip())
    h1s = [strip_tags(x) for x in re.findall(r"(?is)<h1\b[^>]*>(.*?)</h1>", html)]
    desc = ""
    robots = ""
    og_url = ""
    og_image = ""
    naver = ""
    for meta in metas:
        name = meta.get("name", "").lower()
        prop = meta.get("property", "").lower()
        if name == "description":
            desc = meta.get("content", "")
        if name == "robots":
            robots = meta.get("content", "")
        if prop == "og:url":
            og_url = meta.get("content", "")
        if prop == "og:image":
            og_image = meta.get("content", "")
        if name == "naver-site-verification":
            naver = meta.get("content", "")
    canonicals = [l.get("href", "") for l in links if l.get("rel", "").lower() == "canonical"]
    hreflangs = [l.get("href", "") for l in links if l.get("hreflang")]
    internal_links = []
    for link in links:
        if link.get("_tag") != "a":
            continue
        href = link.get("href", "").strip()
        if href:
            internal_links.append(href)
    body_text = strip_tags(html)
    jsonlds = []
    jsonld_hosts = []
    for script in scripts:
        try:
            data = json.loads(script)
            jsonlds.append(data)
            collect_jsonld_hosts(data, jsonld_hosts)
        except Exception:
            jsonlds.append({"_parse_error": script[:200]})
    return {
        "local_file": str(path),
        "rel_url": rel_url,
        "page_url": EXPECTED_BASE + rel_url,
        "bytes": len(raw),
        "bom": bom,
        "utf8_ok": utf8_ok,
        "title": title,
        "description": desc,
        "robots": robots,
        "h1s": h1s,
        "canonical": canonicals,
        "og_url": og_url,
        "og_image": og_image,
        "naver_verification": naver,
        "hreflang": hreflangs,
        "internal_links": internal_links,
        "jsonlds": jsonlds,
        "jsonld_hosts": jsonld_hosts,
        "text": body_text,
        "text_hash": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
        "word_count": len(re.findall(r"[\w가-힣]+", body_text)),
        "has_noindex": "noindex" in robots.lower(),
        "has_placeholder": bool(re.search(r"제목을 입력|lorem ipsum|placeholder|TODO|샘플|준비중", html, re.I)),
        "has_html": "<html" in lower,
    }


def collect_jsonld_hosts(obj, out):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("url", "@id", "item", "contentUrl", "thumbnailUrl", "image"):
                values = value if isinstance(value, list) else [value]
                for v in values:
                    if isinstance(v, str) and re.match(r"https?://", v):
                        out.append(v)
                    elif isinstance(v, dict):
                        collect_jsonld_hosts(v, out)
            collect_jsonld_hosts(value, out)
    elif isinstance(obj, list):
        for item in obj:
            collect_jsonld_hosts(item, out)


def file_to_url(path):
    rel = path.relative_to(OUTPUT).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return urllib.parse.quote("/" + rel[: -len("index.html")], safe="/%")
    return urllib.parse.quote("/" + rel, safe="/%")


def canonicalize_internal_url(href, base_url):
    if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    if href.startswith("#") or not href:
        return None
    joined = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(joined)
    if parsed.netloc not in ("studyhub.co.kr", "www.studyhub.co.kr", ""):
        return None
    path = urllib.parse.unquote(parsed.path or "/")
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    if not path.endswith("/") and "." not in Path(path).name:
        path += "/"
    return urllib.parse.urlunparse(("https", EXPECTED_HOST, urllib.parse.quote(path, safe="/%"), "", "", ""))


def parse_sitemap_xml(text):
    urls = []
    errors = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}", 1)[0] + "}"
        for loc in root.findall(f".//{ns}loc"):
            if loc.text:
                urls.append(loc.text.strip())
    except Exception as exc:
        errors.append(str(exc))
    return urls, errors


def local_sitemap_urls():
    path = OUTPUT / "sitemap.xml"
    if not path.exists():
        path = PROJECT / "sitemap.xml"
    if not path.exists():
        return [], ["local sitemap not found"], ""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    urls, errors = parse_sitemap_xml(text)
    return urls, errors, str(path)


def issue(issue_type, severity, detail, recommended_fix="", **kwargs):
    row = {col: "" for col in ISSUE_COLUMNS}
    row.update(
        {
            "issue_type": issue_type,
            "severity": severity,
            "detail": detail,
            "expected_host": EXPECTED_HOST,
            "recommended_fix": recommended_fix,
        }
    )
    row.update(kwargs)
    return row


def scan_deployment_files():
    names = {
        "vercel.json",
        "_redirects",
        "_headers",
        "wrangler.toml",
        "netlify.toml",
        "nginx.conf",
        "package.json",
        "generator.py",
        "render.py",
        "config.py",
    }
    rows = []
    targets = []
    for root, dirs, files in os.walk(PROJECT):
        parts = set(Path(root).relative_to(PROJECT).parts) if Path(root) != PROJECT else set()
        if parts & {".git", "output", "__pycache__", "verification"}:
            dirs[:] = []
            continue
        for fn in files:
            if fn in names or fn.endswith((".yml", ".yaml")):
                targets.append(Path(root) / fn)
    patterns = [
        "https://studyhub.co.kr",
        "https://www.studyhub.co.kr",
        "http://studyhub.co.kr",
        "http://www.studyhub.co.kr",
        "//studyhub.co.kr",
        "//www.studyhub.co.kr",
        "BASE_URL",
        "redirect",
        "rewrite",
        "sitemap",
        "canonical",
        "naver-site-verification",
    ]
    for path in sorted(targets):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            rows.append(issue("deployment_file_read_error", "P2", str(exc), local_file=str(path)))
            continue
        hits = []
        for pat in patterns:
            if pat.lower() in text.lower():
                hits.append(pat)
        rows.append(
            {
                **{col: "" for col in ISSUE_COLUMNS},
                "issue_type": "deployment_config_checked",
                "local_file": str(path),
                "detail": "hits: " + ", ".join(hits) if hits else "no requested host/config patterns found",
                "severity": "INFO",
                "expected_host": EXPECTED_HOST,
            }
        )
    return rows


def main():
    skip_http = "--skip-http" in sys.argv
    VERIFY.mkdir(parents=True, exist_ok=True)
    http = HttpAuditor()
    print(f"[{datetime.now()}] scanning local output")
    html_paths = sorted(OUTPUT.rglob("*.html"))
    pages = []
    for idx, path in enumerate(html_paths, 1):
        pages.append(extract_html(path, file_to_url(path)))
        if idx % 5000 == 0:
            print(f"  parsed {idx}/{len(html_paths)} html files")
    by_url = {p["page_url"]: p for p in pages}
    by_rel = {p["rel_url"]: p for p in pages}

    print(f"[{datetime.now()}] fetching redirects/robots/sitemaps")
    redirect_urls = [
        "http://studyhub.co.kr",
        "http://www.studyhub.co.kr",
        "https://studyhub.co.kr",
        "https://www.studyhub.co.kr",
    ]
    redirect_rows = [http.request(url) for url in redirect_urls]
    write_xlsx(
        VERIFY / "redirect_audit.xlsx",
        [
            {
                **{col: "" for col in ISSUE_COLUMNS},
                "issue_type": "redirect_check",
                "original_url": r["original_url"],
                "final_url": r["final_url"],
                "status_code": r["status_code"],
                "detected_host": urllib.parse.urlparse(r.get("final_url") or "").netloc,
                "expected_host": EXPECTED_HOST,
                "detail": f"redirect_count={r.get('redirect_count')} chain={r.get('redirect_chain')} error={r.get('error')}",
                "severity": "INFO" if r.get("status_code") == 200 else "P1",
            }
            for r in redirect_rows
        ],
    )

    host_rows = []
    for r in redirect_rows:
        final = urllib.parse.urlparse(r.get("final_url") or "")
        status = r.get("status_code")
        ok = status == 200 and final.scheme == "https" and final.netloc == EXPECTED_HOST
        host_rows.append(
            issue(
                "host_canonicalization",
                "INFO" if ok else "P0",
                f"status={status}, final={r.get('final_url')}, redirects={r.get('redirect_count')}",
                "4가지 URL이 모두 https://studyhub.co.kr 로 200 수렴해야 합니다.",
                original_url=r["original_url"],
                final_url=r.get("final_url", ""),
                status_code=status,
                detected_host=final.netloc,
            )
        )
    write_xlsx(VERIFY / "host_audit.xlsx", host_rows)

    robot_rows = []
    robots_texts = {}
    for base in (EXPECTED_BASE, ALT_BASE):
        url = base + "/robots.txt"
        row, text = http.get_text(url)
        robots_texts[base] = text
        parsed = urllib.parse.urlparse(row.get("final_url") or "")
        blocked_all = bool(re.search(r"(?im)^\s*disallow\s*:\s*/\s*$", text))
        y_block = bool(re.search(r"(?is)user-agent\s*:\s*(yeti|naverbot).*?disallow\s*:\s*/", text))
        sitemap_hosts = [urllib.parse.urlparse(m).netloc for m in re.findall(r"(?im)^\s*sitemap\s*:\s*(\S+)", text)]
        severity = "INFO"
        detail = f"final={row.get('final_url')}; sitemap_hosts={sitemap_hosts}; blocked_all={blocked_all}; naver_block={y_block}"
        if row.get("status_code") != 200 or blocked_all or y_block or any(h != EXPECTED_HOST for h in sitemap_hosts):
            severity = "P1"
        robot_rows.append(
            issue(
                "robots_check",
                severity,
                detail,
                "robots.txt는 200, Sitemap은 대표 도메인, Yeti/NaverBot 차단 없음 상태가 권장됩니다.",
                original_url=url,
                final_url=row.get("final_url", ""),
                status_code=row.get("status_code", ""),
                detected_host=parsed.netloc,
            )
        )
    write_xlsx(VERIFY / "robots_errors.xlsx", robot_rows)

    remote_sitemap_rows = []
    remote_sitemap_urls = {}
    for base in (EXPECTED_BASE, ALT_BASE):
        url = base + "/sitemap.xml"
        row, text = http.get_text(url)
        urls, errors = parse_sitemap_xml(text)
        remote_sitemap_urls[base] = urls
        hosts = Counter(urllib.parse.urlparse(u).netloc for u in urls)
        remote_sitemap_rows.append(
            issue(
                "remote_sitemap_check",
                "INFO" if row.get("status_code") == 200 and not errors and set(hosts) <= {EXPECTED_HOST} else "P1",
                f"count={len(urls)} errors={errors}; hosts={dict(hosts)}; content_type={row.get('content_type')}; utf8={row.get('utf8_ok')}; bom={row.get('bom')}; bytes={row.get('bytes')}",
                "sitemap.xml은 200 XML, 대표 도메인 URL만 포함하는 상태가 권장됩니다.",
                original_url=url,
                final_url=row.get("final_url", ""),
                status_code=row.get("status_code", ""),
                detected_host=urllib.parse.urlparse(row.get("final_url") or "").netloc,
            )
        )

    local_sm_urls, local_sm_errors, local_sm_path = local_sitemap_urls()
    sitemap_urls = remote_sitemap_urls.get(EXPECTED_BASE) or local_sm_urls
    sitemap_set = {normalize_site_url(u) for u in sitemap_urls}
    output_set = set(by_url)
    remote_sitemap_rows.append(
        issue(
            "local_sitemap_check",
            "INFO" if local_sm_urls and not local_sm_errors else "P1",
            f"path={local_sm_path}; count={len(local_sm_urls)}; errors={local_sm_errors}; hosts={dict(Counter(urllib.parse.urlparse(u).netloc for u in local_sm_urls))}",
            local_file=local_sm_path,
        )
    )
    dupes = [u for u, c in Counter(normalize_site_url(u) for u in sitemap_urls).items() if c > 1]
    for u in dupes[:10000]:
        remote_sitemap_rows.append(issue("duplicate_sitemap_url", "P1", "duplicate URL in sitemap", original_url=u))
    for u in sitemap_urls:
        parsed = urllib.parse.urlparse(u)
        if parsed.scheme != "https" or parsed.netloc != EXPECTED_HOST or "index.html" in parsed.path:
            remote_sitemap_rows.append(
                issue("sitemap_url_format", "P1", f"scheme={parsed.scheme} host={parsed.netloc} path={parsed.path}", original_url=u, detected_host=parsed.netloc)
            )
    write_xlsx(VERIFY / "sitemap_audit.xlsx", remote_sitemap_rows)

    sitemap_only = [
        issue("sitemap_only_url", "P2", "URL exists in sitemap but no matching local output HTML was found", original_url=u)
        for u in sorted(sitemap_set - output_set)
    ]
    output_only = [
        issue("output_only_page", "P2", "local output HTML exists but URL is missing from sitemap", local_file=by_url[u]["local_file"], original_url=u)
        for u in sorted(output_set - sitemap_set)
        if not u.endswith("/404.html")
    ]
    write_xlsx(VERIFY / "sitemap_only_urls.xlsx", sitemap_only)
    write_xlsx(VERIFY / "output_only_pages.xlsx", output_only)

    print(f"[{datetime.now()}] analyzing html metadata and links")
    canonical_rows = []
    jsonld_rows = []
    og_rows = []
    noindex_rows = []
    short_rows = []
    title_groups = defaultdict(list)
    desc_groups = defaultdict(list)
    content_groups = defaultdict(list)
    graph = defaultdict(set)
    all_internal_urls = set()
    broken_link_candidates = []

    for p in pages:
        page_url = p["page_url"]
        title_groups[p["title"]].append(p)
        desc_groups[p["description"]].append(p)
        content_groups[p["text_hash"]].append(p)
        is_404 = Path(p["local_file"]).name == "404.html" or p["rel_url"].endswith("/404.html")
        if p["has_noindex"] and not is_404:
            noindex_rows.append(issue("meta_robots_noindex", "P0", p["robots"], local_file=p["local_file"], original_url=page_url))
        if p["word_count"] < 80 or p["has_placeholder"] or not p["title"] or not p["h1s"]:
            short_rows.append(
                issue(
                    "thin_or_incomplete_page",
                    "P3",
                    f"words={p['word_count']}; title={bool(p['title'])}; h1_count={len(p['h1s'])}; placeholder={p['has_placeholder']}",
                    local_file=p["local_file"],
                    original_url=page_url,
                )
            )
        if is_404:
            pass
        elif len(p["canonical"]) != 1:
            canonical_rows.append(issue("canonical_count", "P1", f"canonical_count={len(p['canonical'])}", local_file=p["local_file"], original_url=page_url))
        else:
            can = p["canonical"][0]
            cp = urllib.parse.urlparse(can)
            if cp.scheme != "https" or cp.netloc != EXPECTED_HOST or normalize_site_url(can) != page_url:
                canonical_rows.append(
                    issue(
                        "canonical_mismatch",
                        "P1",
                        f"canonical={can}; expected={page_url}",
                        "canonical은 자기 자신의 대표 도메인 URL을 가리키도록 정리해야 합니다.",
                        local_file=p["local_file"],
                        original_url=page_url,
                        final_url=can,
                        detected_host=cp.netloc,
                    )
                )
        if is_404:
            pass
        elif p["og_url"]:
            op = urllib.parse.urlparse(p["og_url"])
            if op.scheme != "https" or op.netloc != EXPECTED_HOST or normalize_site_url(p["og_url"]) != page_url:
                og_rows.append(issue("og_url_mismatch", "P1", f"og:url={p['og_url']}; expected={page_url}", local_file=p["local_file"], original_url=page_url, final_url=p["og_url"], detected_host=op.netloc))
        else:
            og_rows.append(issue("og_url_missing", "P2", "missing og:url", local_file=p["local_file"], original_url=page_url))
        for u in [p["og_image"]] + p["hreflang"] + p["jsonld_hosts"]:
            if not u:
                continue
            up = urllib.parse.urlparse(u)
            if up.netloc and up.netloc not in (EXPECTED_HOST,):
                if u in p["jsonld_hosts"]:
                    jsonld_rows.append(issue("jsonld_host_mismatch", "P1", u, local_file=p["local_file"], original_url=page_url, final_url=u, detected_host=up.netloc))
                else:
                    og_rows.append(issue("metadata_host_mismatch", "P1", u, local_file=p["local_file"], original_url=page_url, final_url=u, detected_host=up.netloc))
        for href in p["internal_links"]:
            target = canonicalize_internal_url(href, page_url)
            if target:
                graph[page_url].add(target)
                all_internal_urls.add(target)
                tp = urllib.parse.urlparse(target)
                if tp.netloc != EXPECTED_HOST:
                    broken_link_candidates.append(issue("internal_link_wrong_host", "P1", href, local_file=p["local_file"], source_page=page_url, original_url=href, final_url=target, detected_host=tp.netloc))
                elif target not in output_set:
                    broken_link_candidates.append(issue("internal_link_no_local_output", "P2", href, local_file=p["local_file"], source_page=page_url, original_url=href, final_url=target))

    for rows, name in ((canonical_rows, "canonical_errors.xlsx"), (jsonld_rows, "jsonld_host_errors.xlsx"), (og_rows, "og_url_errors.xlsx"), (noindex_rows, "noindex_pages.xlsx"), (short_rows, "short_or_empty_pages.xlsx")):
        write_xlsx(VERIFY / name, rows)

    dup_title_rows = []
    for title, group in title_groups.items():
        if title and len(group) > 1:
            for p in group:
                dup_title_rows.append(issue("duplicate_title", "P2", f"count={len(group)} title={title}", local_file=p["local_file"], original_url=p["page_url"]))
    dup_desc_rows = []
    for desc, group in desc_groups.items():
        if desc and len(group) > 1:
            for p in group:
                dup_desc_rows.append(issue("duplicate_description", "P2", f"count={len(group)} description={desc[:200]}", local_file=p["local_file"], original_url=p["page_url"]))
    dup_content_rows = []
    for h, group in content_groups.items():
        if len(group) > 1:
            for p in group:
                dup_content_rows.append(issue("duplicate_content_exact", "P2", f"count={len(group)} hash={h}", local_file=p["local_file"], original_url=p["page_url"]))
    write_xlsx(VERIFY / "duplicate_titles.xlsx", dup_title_rows)
    write_xlsx(VERIFY / "duplicate_descriptions.xlsx", dup_desc_rows)
    write_xlsx(VERIFY / "duplicate_content.xlsx", dup_content_rows)

    reachable = set()
    start = EXPECTED_BASE + "/"
    dq = deque([start])
    while dq:
        cur = dq.popleft()
        if cur in reachable:
            continue
        reachable.add(cur)
        for nxt in graph.get(cur, set()):
            if nxt in output_set and nxt not in reachable:
                dq.append(nxt)
    orphan_rows = [
        issue("orphan_page", "P2", "local page is not reachable from home through parsed internal links", local_file=by_url[u]["local_file"], original_url=u)
        for u in sorted(output_set - reachable)
        if u != start
    ]
    write_xlsx(VERIFY / "orphan_pages.xlsx", orphan_rows)
    write_xlsx(VERIFY / "broken_internal_links.xlsx", broken_link_candidates)

    full_rows = []
    http_error_rows = []
    urls_to_check = sorted(sitemap_set | all_internal_urls | {EXPECTED_BASE + "/robots.txt", EXPECTED_BASE + "/sitemap.xml"})
    (VERIFY / "http_urls_to_check.txt").write_text("\n".join(urls_to_check), encoding="utf-8")
    if not skip_http:
        print(f"[{datetime.now()}] http-auditing sitemap and internal urls")
        for idx, url in enumerate(urls_to_check, 1):
            r = http.request(url)
            full_rows.append(r)
            status = r.get("status_code")
            if not isinstance(status, int) or status < 200 or status >= 400 or r.get("error"):
                http_error_rows.append(
                    issue(
                        "http_status_error",
                        "P1",
                        r.get("error") or f"status={status}; chain={r.get('redirect_chain')}",
                        original_url=url,
                        final_url=r.get("final_url", ""),
                        status_code=status,
                        detected_host=urllib.parse.urlparse(r.get("final_url") or "").netloc,
                    )
                )
            if idx % 50 == 0:
                print(f"  http checked {idx}/{len(urls_to_check)}")
        write_csv(
            VERIFY / "full_url_audit.csv",
            full_rows,
            ["original_url", "final_url", "status_code", "redirect_count", "redirect_chain", "error", "content_type", "content_length", "method", "x_robots_tag", "server"],
        )
        write_xlsx(VERIFY / "http_status_errors.xlsx", http_error_rows)

    deploy_rows = scan_deployment_files()
    write_xlsx(VERIFY / "deployment_config_audit.xlsx", deploy_rows)

    print(f"[{datetime.now()}] comparing eduguide")
    comparison_rows = []
    for base in (EDUGUIDE, EXPECTED_BASE, ALT_BASE):
        root_row, root_text = http.get_text(base)
        robots_row, robots_text = http.get_text(base.rstrip("/") + "/robots.txt")
        sm_row, sm_text = http.get_text(base.rstrip("/") + "/sitemap.xml")
        sm_urls, sm_errors = parse_sitemap_xml(sm_text)
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", root_text)
        if m:
            title = strip_tags(m.group(1))
        can = re.findall(r"(?is)<link\b[^>]*rel=['\"]canonical['\"][^>]*>", root_text)
        can_href = parse_attrs(can[0]).get("href", "") if can else ""
        comparison_rows.append(
            {
                "site": base,
                "root_status": root_row.get("status_code", ""),
                "root_final_url": root_row.get("final_url", ""),
                "root_redirects": root_row.get("redirect_count", ""),
                "canonical": can_href,
                "title": title,
                "robots_status": robots_row.get("status_code", ""),
                "robots_sitemap_lines": "\n".join(re.findall(r"(?im)^\s*sitemap\s*:\s*\S+", robots_text)),
                "sitemap_status": sm_row.get("status_code", ""),
                "sitemap_count": len(sm_urls),
                "sitemap_errors": "; ".join(sm_errors),
                "server": root_row.get("server", ""),
                "content_type": root_row.get("content_type", ""),
            }
        )
    write_xlsx(
        VERIFY / "studyhub_vs_eduguide_comparison.xlsx",
        comparison_rows,
        ["site", "root_status", "root_final_url", "root_redirects", "canonical", "title", "robots_status", "robots_sitemap_lines", "sitemap_status", "sitemap_count", "sitemap_errors", "server", "content_type"],
    )

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pages": len(pages),
        "sitemap_urls": len(sitemap_urls),
        "internal_urls": len(all_internal_urls),
        "redirect_rows": len(redirect_rows),
        "canonical_errors": len(canonical_rows),
        "jsonld_host_errors": len(jsonld_rows),
        "og_url_errors": len(og_rows),
        "broken_internal_link_candidates": len(broken_link_candidates),
        "orphans": len(orphan_rows),
        "noindex_pages": len(noindex_rows),
        "duplicate_title_rows": len(dup_title_rows),
        "duplicate_description_rows": len(dup_desc_rows),
        "duplicate_content_rows": len(dup_content_rows),
        "short_or_empty_rows": len(short_rows),
        "http_status_errors": len(http_error_rows),
        "host_expected": EXPECTED_BASE,
        "naver_registration_recommendation": EXPECTED_BASE,
    }
    (VERIFY / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
