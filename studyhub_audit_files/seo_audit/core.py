from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook


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

HTTP_COLUMNS = [
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

PLACEHOLDER_PATTERNS = [
    "제목을 입력해주세요",
    "제목을 입력",
    "TODO",
    "Coming Soon",
    "Sample",
    "Placeholder",
    "Lorem ipsum",
    "준비중",
    "샘플",
]


@dataclass
class AuditConfig:
    root_dir: Path
    output_dir: Path
    verification_dir: Path
    site_url: str
    site_domain: str
    live_http: bool = False
    mode: str = "pre"
    http_timeout: int = 5
    http_delay: float = 0.25

    @property
    def expected_base(self) -> str:
        return self.site_url.rstrip("/")

    @property
    def alt_base(self) -> str:
        parsed = urllib.parse.urlparse(self.expected_base)
        host = parsed.netloc
        alt_host = host[4:] if host.startswith("www.") else f"www.{host}"
        return urllib.parse.urlunparse((parsed.scheme, alt_host, "", "", "", "")).rstrip("/")


def load_config(root_dir: Path, mode: str = "pre", live_http: bool = False) -> AuditConfig:
    import importlib.util

    config_path = root_dir / "config.py"
    spec = importlib.util.spec_from_file_location("studyhub_config_for_audit", config_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {config_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    site_url = str(getattr(module, "SITE_URL"))
    site_domain = urllib.parse.urlparse(site_url).netloc
    output_dir = Path(getattr(module, "OUTPUT_DIR", root_dir / "output"))
    return AuditConfig(
        root_dir=root_dir,
        output_dir=output_dir,
        verification_dir=root_dir / "verification",
        site_url=site_url,
        site_domain=site_domain,
        live_http=live_http,
        mode=mode,
    )


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return "".join(ch if ch >= " " or ch in "\r\n\t" else " " for ch in text)


def write_xlsx(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    columns = columns or ISSUE_COLUMNS
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "audit"
    ws.append(columns)
    for row in rows:
        ws.append([safe_text(row.get(col, "")) for col in columns])
    ws.freeze_panes = "A2"
    for idx, col in enumerate(columns, 1):
        width = min(max(len(col) + 2, 12), 70)
        ws.column_dimensions[ws.cell(1, idx).column_letter].width = width
    wb.save(path)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows({col: safe_text(row.get(col, "")) for col in columns} for row in rows)


def issue(issue_type: str, severity: str, detail: str, cfg: AuditConfig, **kwargs: Any) -> dict[str, Any]:
    row = {col: "" for col in ISSUE_COLUMNS}
    row.update(
        {
            "issue_type": issue_type,
            "severity": severity,
            "detail": detail,
            "expected_host": cfg.site_domain,
        }
    )
    row.update(kwargs)
    return row


def normalize_site_url(url: str, cfg: AuditConfig) -> str:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = (parsed.netloc or cfg.site_domain).lower()
    path = urllib.parse.unquote(parsed.path or "/")
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    if not path.endswith("/") and "." not in Path(path).name:
        path += "/"
    encoded_path = urllib.parse.quote(path, safe="/%")
    return urllib.parse.urlunparse((scheme, netloc, encoded_path, "", "", ""))


def file_to_url(path: Path, cfg: AuditConfig) -> str:
    rel = path.relative_to(cfg.output_dir).as_posix()
    if rel == "index.html":
        return cfg.expected_base + "/"
    if rel.endswith("/index.html"):
        rel_path = "/" + rel[: -len("index.html")]
    else:
        rel_path = "/" + rel
    return cfg.expected_base + urllib.parse.quote(rel_path, safe="/%")


def parse_attrs(tag: str) -> dict[str, str]:
    attrs = {}
    for match in re.finditer(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", tag, flags=re.S):
        attrs[match.group(1).lower()] = unescape(match.group(3).strip())
    return attrs


def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


def collect_jsonld_urls(obj: Any, out: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"url", "@id", "item", "contentUrl", "thumbnailUrl", "image", "primaryImageOfPage"}:
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, str) and item.startswith(("http://", "https://")):
                        out.append(item)
                    else:
                        collect_jsonld_urls(item, out)
            else:
                collect_jsonld_urls(value, out)
    elif isinstance(obj, list):
        for item in obj:
            collect_jsonld_urls(item, out)


def parse_html(path: Path, cfg: AuditConfig) -> dict[str, Any]:
    raw = path.read_bytes()
    html = raw.decode("utf-8", errors="replace")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = strip_tags(title_match.group(1)) if title_match else ""
    metas = [parse_attrs(tag) for tag in re.findall(r"(?is)<meta\b[^>]*>", html)]
    link_tags = [parse_attrs(tag) for tag in re.findall(r"(?is)<link\b[^>]*>", html)]
    anchors = [parse_attrs(tag) for tag in re.findall(r"(?is)<a\b[^>]*>", html)]
    jsonld_raw = [
        m.group(2).strip()
        for m in re.finditer(r"(?is)<script\b([^>]*)>(.*?)</script>", html)
        if parse_attrs(m.group(1)).get("type", "").lower() == "application/ld+json"
    ]
    description = ""
    robots = ""
    og_url = ""
    og_image = ""
    for meta in metas:
        name = meta.get("name", "").lower()
        prop = meta.get("property", "").lower()
        if name == "description":
            description = meta.get("content", "")
        if name == "robots":
            robots = meta.get("content", "")
        if prop == "og:url":
            og_url = meta.get("content", "")
        if prop == "og:image":
            og_image = meta.get("content", "")
    canonical = [tag.get("href", "") for tag in link_tags if tag.get("rel", "").lower() == "canonical"]
    h1s = [strip_tags(x) for x in re.findall(r"(?is)<h1\b[^>]*>(.*?)</h1>", html)]
    text = strip_tags(html)
    jsonld_urls = []
    jsonld_errors = []
    jsonld_types = set()
    for raw_json in jsonld_raw:
        try:
            data = json.loads(raw_json)
            nodes = data.get("@graph", []) if isinstance(data, dict) else data
            if isinstance(nodes, dict):
                nodes = [nodes]
            if isinstance(nodes, list):
                for node in nodes:
                    if isinstance(node, dict):
                        jsonld_types.add(str(node.get("@type", "")))
            collect_jsonld_urls(data, jsonld_urls)
        except Exception as exc:
            jsonld_errors.append(str(exc))
    return {
        "local_file": str(path),
        "page_url": file_to_url(path, cfg),
        "is_404": path.name == "404.html" or path.as_posix().endswith("/404.html"),
        "title": title,
        "description": description,
        "robots": robots,
        "canonical": canonical,
        "og_url": og_url,
        "og_image": og_image,
        "h1s": h1s,
        "anchors": [a.get("href", "").strip() for a in anchors if a.get("href", "").strip()],
        "jsonld_urls": jsonld_urls,
        "jsonld_errors": jsonld_errors,
        "jsonld_types": jsonld_types,
        "text": text,
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "tokens": set(re.findall(r"[\w가-힣]{2,}", text.lower())),
        "word_count": len(re.findall(r"[\w가-힣]+", text)),
        "placeholder_hits": [p for p in PLACEHOLDER_PATTERNS if re.search(re.escape(p), html, re.I)],
    }


def internal_url(href: str, base_url: str, cfg: AuditConfig) -> str | None:
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    joined = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(joined)
    if parsed.netloc and parsed.netloc not in {cfg.site_domain, f"www.{cfg.site_domain}"}:
        return None
    return normalize_site_url(urllib.parse.urlunparse(("https", parsed.netloc or cfg.site_domain, parsed.path or "/", "", "", "")), cfg)


class HttpClient:
    def __init__(self, cfg: AuditConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "StudyHubPreDeployAudit/1.0"})
        self.last = 0.0

    def _wait(self) -> None:
        delta = time.time() - self.last
        if delta < self.cfg.http_delay:
            time.sleep(self.cfg.http_delay - delta)
        self.last = time.time()

    def request(self, url: str) -> dict[str, Any]:
        row = {col: "" for col in HTTP_COLUMNS}
        row["original_url"] = url
        for attempt in range(2):
            try:
                self._wait()
                resp = self.session.head(url, allow_redirects=True, timeout=self.cfg.http_timeout)
                method = "HEAD"
                if resp.status_code in {403, 405} or resp.status_code >= 500:
                    self._wait()
                    resp = self.session.get(url, allow_redirects=True, timeout=self.cfg.http_timeout)
                    method = "GET"
                chain = [f"{r.status_code} {r.url}" for r in resp.history] + [f"{resp.status_code} {resp.url}"]
                row.update(
                    {
                        "final_url": resp.url,
                        "status_code": resp.status_code,
                        "redirect_count": len(resp.history),
                        "redirect_chain": " -> ".join(chain),
                        "content_type": resp.headers.get("content-type", ""),
                        "content_length": resp.headers.get("content-length", ""),
                        "method": method,
                        "x_robots_tag": resp.headers.get("x-robots-tag", ""),
                        "server": resp.headers.get("server", ""),
                    }
                )
                return row
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    time.sleep(0.5)
        return row

    def get_text(self, url: str) -> tuple[dict[str, Any], str, bytes]:
        row = self.request(url)
        try:
            self._wait()
            resp = self.session.get(url, allow_redirects=True, timeout=self.cfg.http_timeout)
            chain = [f"{r.status_code} {r.url}" for r in resp.history] + [f"{resp.status_code} {resp.url}"]
            row.update(
                {
                    "final_url": resp.url,
                    "status_code": resp.status_code,
                    "redirect_count": len(resp.history),
                    "redirect_chain": " -> ".join(chain),
                    "content_type": resp.headers.get("content-type", ""),
                    "content_length": resp.headers.get("content-length", ""),
                    "method": "GET",
                }
            )
            return row, resp.text, resp.content
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            return row, "", b""


def parse_sitemap(text: str) -> tuple[list[str], list[str]]:
    try:
        root = ET.fromstring(text.encode("utf-8"))
        ns = root.tag.split("}", 1)[0] + "}" if root.tag.startswith("{") else ""
        return [loc.text.strip() for loc in root.findall(f".//{ns}loc") if loc.text], []
    except Exception as exc:
        return [], [str(exc)]


def read_local_sitemap(cfg: AuditConfig) -> tuple[list[str], list[str], bytes]:
    path = cfg.output_dir / "sitemap.xml"
    if not path.exists():
        return [], ["output/sitemap.xml missing"], b""
    raw = path.read_bytes()
    urls, errors = parse_sitemap(raw.decode("utf-8", errors="replace"))
    return urls, errors, raw


def similarity_rows(pages: list[dict[str, Any]], cfg: AuditConfig) -> list[dict[str, Any]]:
    max_rows = int(os.environ.get("STUDYHUB_MAX_SIMILARITY_ROWS", "500"))
    rows = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in pages:
        tokens = sorted(page["tokens"])
        fingerprint = " ".join(tokens[:80])
        key = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:8] if fingerprint else page["title"][:3]
        groups[key].append(page)
    for group in groups.values():
        group = sorted(group, key=lambda item: item["word_count"])
        for i, left in enumerate(group):
            candidates = group[i + 1 : i + 4]
            for right in candidates:
                if left["word_count"] and right["word_count"] > left["word_count"] * 1.15:
                    break
                a, b = left["tokens"], right["tokens"]
                if not a or not b:
                    continue
                ratio = len(a & b) / max(len(a), len(b))
                if ratio >= 0.90:
                    sev = "P1"
                    bucket = "90"
                    if ratio >= 0.99:
                        bucket = "99"
                    elif ratio >= 0.95:
                        bucket = "95"
                    rows.append(
                        issue(
                            f"duplicate_content_{bucket}",
                            sev,
                            f"similarity={ratio:.3f}; compare={right['page_url']}",
                            cfg,
                            local_file=left["local_file"],
                            original_url=left["page_url"],
                            final_url=right["page_url"],
                        )
                    )
                    if len(rows) >= max_rows:
                        return rows
    return rows


def run_audit(cfg: AuditConfig) -> tuple[int, dict[str, Any]]:
    gate_only = os.environ.get("STUDYHUB_GATE_ONLY", "0") == "1"
    cfg.verification_dir.mkdir(parents=True, exist_ok=True)
    pages = [parse_html(path, cfg) for path in sorted(cfg.output_dir.rglob("*.html"))]
    by_url = {page["page_url"]: page for page in pages}
    output_set = set(by_url)
    p0: list[dict[str, Any]] = []
    p1: list[dict[str, Any]] = []
    p2: list[dict[str, Any]] = []

    client = HttpClient(cfg)
    redirect_rows = []
    host_rows = []
    for url in [
        f"http://{cfg.site_domain}",
        f"http://www.{cfg.site_domain}",
        f"https://{cfg.site_domain}",
        f"https://www.{cfg.site_domain}",
    ]:
        row = client.request(url)
        redirect_rows.append(row)
        final = urllib.parse.urlparse(row.get("final_url") or "")
        chain = str(row.get("redirect_chain", ""))
        expected_final = cfg.expected_base + "/"
        actual_final = normalize_site_url(row.get("final_url") or "", cfg)
        ok = row.get("status_code") == 200 and actual_final == expected_final
        host_issue = issue(
            "host_canonicalization",
            "INFO" if ok else "P0",
            f"status={row.get('status_code')}; final={row.get('final_url')}; expected={expected_final}; redirects={row.get('redirect_count')}; chain={chain}; error={row.get('error')}",
            cfg,
            original_url=url,
            final_url=row.get("final_url", ""),
            status_code=row.get("status_code", ""),
            detected_host=final.netloc,
            recommended_fix="모든 http/www 변형의 최종 URL이 대표 URL이고 최종 HTTP가 200이 되도록 수렴시키세요. 중간 redirect 코드는 301/302/307/308 모두 허용됩니다.",
        )
        host_rows.append(host_issue)
        if host_issue["severity"] == "P0":
            p0.append(host_issue)

    sitemap_urls, sitemap_errors, sitemap_raw = read_local_sitemap(cfg)
    sitemap_set = {normalize_site_url(url, cfg) for url in sitemap_urls}
    sitemap_rows = []
    sitemap_hosts = Counter(urllib.parse.urlparse(url).netloc for url in sitemap_urls)
    sitemap_dupes = [url for url, count in Counter(sitemap_urls).items() if count > 1]
    sitemap_ok = sitemap_urls and not sitemap_errors and set(sitemap_hosts) <= {cfg.site_domain} and not sitemap_dupes
    sitemap_rows.append(
        issue(
            "sitemap_check",
            "INFO" if sitemap_ok else "P0",
            f"count={len(sitemap_urls)}; errors={sitemap_errors}; hosts={dict(sitemap_hosts)}; dupes={len(sitemap_dupes)}; utf8=True; bom={sitemap_raw.startswith(b'\xef\xbb\xbf') if sitemap_raw else False}",
            cfg,
            local_file=str(cfg.output_dir / "sitemap.xml"),
        )
    )
    if not sitemap_ok:
        p0.append(sitemap_rows[-1])
    if cfg.live_http:
        remote_row, remote_text, remote_raw = client.get_text(cfg.expected_base + "/sitemap.xml")
        remote_urls, remote_errors = parse_sitemap(remote_text)
        remote_set = {normalize_site_url(url, cfg) for url in remote_urls}
        remote_hosts = Counter(urllib.parse.urlparse(url).netloc for url in remote_urls)
        remote_ok = (
            remote_row.get("status_code") == 200
            and not remote_errors
            and remote_set == sitemap_set
            and set(remote_hosts) <= {cfg.site_domain}
            and not remote_raw.startswith(b"\xef\xbb\xbf")
        )
        row = issue(
            "live_sitemap_compare",
            "INFO" if remote_ok else "P0",
            f"status={remote_row.get('status_code')}; local_count={len(sitemap_set)}; live_count={len(remote_set)}; errors={remote_errors}; hosts={dict(remote_hosts)}; missing_live={len(sitemap_set - remote_set)}; extra_live={len(remote_set - sitemap_set)}",
            cfg,
            original_url=cfg.expected_base + "/sitemap.xml",
            final_url=remote_row.get("final_url", ""),
            status_code=remote_row.get("status_code", ""),
        )
        sitemap_rows.append(row)
        if row["severity"] == "P0":
            p0.append(row)
    for url in sorted(sitemap_set - output_set):
        row = issue("sitemap_output_missing", "P0", "sitemap URL has no matching output HTML", cfg, original_url=url)
        sitemap_rows.append(row)
        p0.append(row)
    for url in sorted(output_set - sitemap_set):
        if not by_url[url]["is_404"]:
            row = issue("output_missing_from_sitemap", "P0", "output HTML is missing from sitemap", cfg, local_file=by_url[url]["local_file"], original_url=url)
            sitemap_rows.append(row)
            p0.append(row)

    canonical_rows = []
    og_rows = []
    jsonld_rows = []
    robots_meta_rows = []
    placeholder_rows = []
    title_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    desc_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    graph: dict[str, set[str]] = defaultdict(set)
    broken_rows = []

    for page in pages:
        title_groups[page["title"]].append(page)
        desc_groups[page["description"]].append(page)
        hash_groups[page["text_hash"]].append(page)
        if page["is_404"]:
            if "noindex" not in page["robots"].lower():
                row = issue("404_missing_noindex", "P1", "404.html should include noindex", cfg, local_file=page["local_file"], original_url=page["page_url"])
                if not gate_only:
                    p1.append(row)
            continue
        if "noindex" in page["robots"].lower():
            row = issue("unexpected_noindex", "P0", page["robots"], cfg, local_file=page["local_file"], original_url=page["page_url"])
            robots_meta_rows.append(row)
            p0.append(row)
        if len(page["canonical"]) != 1:
            row = issue("canonical_count", "P0", f"canonical_count={len(page['canonical'])}", cfg, local_file=page["local_file"], original_url=page["page_url"])
            canonical_rows.append(row)
            p0.append(row)
        else:
            canonical = page["canonical"][0]
            parsed = urllib.parse.urlparse(canonical)
            if parsed.scheme != "https" or parsed.netloc != cfg.site_domain or normalize_site_url(canonical, cfg) != page["page_url"]:
                row = issue("canonical_mismatch", "P0", f"canonical={canonical}; expected={page['page_url']}", cfg, local_file=page["local_file"], original_url=page["page_url"], final_url=canonical, detected_host=parsed.netloc)
                canonical_rows.append(row)
                p0.append(row)
        if not page["og_url"] or normalize_site_url(page["og_url"], cfg) != page["page_url"]:
            row = issue("og_url_mismatch", "P1", f"og:url={page['og_url']}; expected={page['page_url']}", cfg, local_file=page["local_file"], original_url=page["page_url"], final_url=page["og_url"])
            og_rows.append(row)
            p1.append(row)
        for url in [page["og_image"], *page["jsonld_urls"]]:
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc and parsed.netloc != cfg.site_domain:
                target = jsonld_rows if url in page["jsonld_urls"] else og_rows
                row = issue("metadata_host_mismatch", "P0", url, cfg, local_file=page["local_file"], original_url=page["page_url"], final_url=url, detected_host=parsed.netloc)
                target.append(row)
                p0.append(row)
        if page["jsonld_errors"]:
            row = issue("jsonld_parse_error", "P0", "; ".join(page["jsonld_errors"]), cfg, local_file=page["local_file"], original_url=page["page_url"])
            jsonld_rows.append(row)
            p0.append(row)
        required = {"WebPage", "BreadcrumbList"}
        if page["page_url"] == cfg.expected_base + "/":
            required.add("WebSite")
        missing = sorted(required - set(page["jsonld_types"]))
        if missing and not gate_only:
            row = issue("jsonld_required_type_missing", "P1", f"missing={missing}", cfg, local_file=page["local_file"], original_url=page["page_url"])
            jsonld_rows.append(row)
            p1.append(row)
        if page["placeholder_hits"] and not gate_only:
            row = issue("placeholder_text", "P1", ", ".join(page["placeholder_hits"]), cfg, local_file=page["local_file"], original_url=page["page_url"])
            placeholder_rows.append(row)
            p1.append(row)
        for href in page["anchors"]:
            target = internal_url(href, page["page_url"], cfg)
            if not target:
                continue
            graph[page["page_url"]].add(target)
            parsed = urllib.parse.urlparse(target)
            if parsed.netloc != cfg.site_domain:
                row = issue("internal_link_host_mixed", "P0", href, cfg, local_file=page["local_file"], source_page=page["page_url"], original_url=href, final_url=target, detected_host=parsed.netloc)
                broken_rows.append(row)
                p0.append(row)
            elif target not in output_set:
                row = issue("broken_internal_link", "P0", href, cfg, local_file=page["local_file"], source_page=page["page_url"], original_url=href, final_url=target)
                broken_rows.append(row)
                p0.append(row)

    robots_rows = audit_robots(cfg, client)
    for row in robots_rows:
        if row["severity"] == "P0":
            p0.append(row)

    http_rows = []
    http_error_rows = []
    if cfg.live_http:
        for url in sorted(sitemap_set | {cfg.expected_base + "/robots.txt", cfg.expected_base + "/sitemap.xml"}):
            row = client.request(url)
            http_rows.append(row)
            status = int(row.get("status_code") or 0)
            if row.get("error") or status < 200 or status >= 400:
                err = issue("http_status_error", "P0", row.get("error") or row.get("redirect_chain", ""), cfg, original_url=url, final_url=row.get("final_url", ""), status_code=row.get("status_code", ""))
                http_error_rows.append(err)
                p0.append(err)
    else:
        for url in sorted(sitemap_set):
            if url not in output_set:
                err = issue("local_http_equivalent_missing", "P0", "URL is not present in output", cfg, original_url=url)
                http_error_rows.append(err)
                p0.append(err)

    reachable = set()
    start = cfg.expected_base + "/"
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        for next_url in graph.get(current, set()):
            if next_url in output_set and next_url not in reachable:
                queue.append(next_url)
    if gate_only:
        orphan_rows = []
        duplicate_title_rows = []
        duplicate_desc_rows = []
        content_similarity_rows = []
    else:
        orphan_rows = [
            issue("orphan_page", "P1", "page is not reachable from home through internal links", cfg, local_file=by_url[url]["local_file"], original_url=url)
            for url in sorted(output_set - reachable)
            if not by_url[url]["is_404"]
        ]
        p1.extend(orphan_rows)

        duplicate_title_rows = duplicate_rows(title_groups, "duplicate_title", cfg)
        duplicate_desc_rows = duplicate_rows(desc_groups, "duplicate_description", cfg)
        duplicate_hash_rows = duplicate_rows(hash_groups, "duplicate_content_exact", cfg)
        content_similarity_rows = duplicate_hash_rows + similarity_rows(pages, cfg)
        p1.extend(duplicate_title_rows + duplicate_desc_rows + content_similarity_rows)

    write_xlsx(cfg.verification_dir / "host_audit.xlsx", host_rows)
    write_xlsx(cfg.verification_dir / "redirect_audit.xlsx", [http_to_issue(row, cfg) for row in redirect_rows])
    write_xlsx(cfg.verification_dir / "canonical_errors.xlsx", canonical_rows)
    write_xlsx(cfg.verification_dir / "robots_errors.xlsx", robots_rows + robots_meta_rows)
    write_xlsx(cfg.verification_dir / "sitemap_audit.xlsx", sitemap_rows)
    write_xlsx(cfg.verification_dir / "jsonld_host_errors.xlsx", jsonld_rows)
    write_xlsx(cfg.verification_dir / "og_url_errors.xlsx", og_rows)
    write_xlsx(cfg.verification_dir / "http_status_errors.xlsx", http_error_rows)
    write_xlsx(cfg.verification_dir / "broken_internal_links.xlsx", broken_rows)
    write_xlsx(cfg.verification_dir / "orphan_pages.xlsx", orphan_rows)
    write_xlsx(cfg.verification_dir / "duplicate_titles.xlsx", duplicate_title_rows)
    write_xlsx(cfg.verification_dir / "duplicate_descriptions.xlsx", duplicate_desc_rows)
    write_xlsx(cfg.verification_dir / "duplicate_content.xlsx", content_similarity_rows)
    write_xlsx(cfg.verification_dir / "placeholder_pages.xlsx", placeholder_rows)
    if http_rows:
        write_csv(cfg.verification_dir / "full_url_audit.csv", http_rows, HTTP_COLUMNS)

    sections = {
        "대표 URL": host_rows,
        "canonical": canonical_rows,
        "robots": robots_rows + robots_meta_rows,
        "sitemap": sitemap_rows,
        "JSON-LD": jsonld_rows,
        "OG": og_rows,
        "HTTP": http_error_rows,
        "내부링크": broken_rows,
        "고아페이지": orphan_rows,
        "placeholder": placeholder_rows,
        "title 중복": duplicate_title_rows,
        "description 중복": duplicate_desc_rows,
        "본문 유사도": content_similarity_rows,
    }
    p0_count = len(p0)
    p1_count = len(p1)
    p2_count = len(p2)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": cfg.mode,
        "live_http": cfg.live_http,
        "gate_only": gate_only,
        "pages": len(pages),
        "sitemap_urls": len(sitemap_set),
        "P0": p0_count,
        "P1": p1_count,
        "P2": p2_count,
        "ready": p0_count == 0,
        "sections": {name: count_by_severity(rows) for name, rows in sections.items()},
    }
    write_summary_md(cfg, summary, sections)
    print_console(summary, sections)
    return (1 if p0_count else 0), summary


def duplicate_rows(groups: dict[str, list[dict[str, Any]]], issue_type: str, cfg: AuditConfig) -> list[dict[str, Any]]:
    rows = []
    for value, pages in groups.items():
        if value and len(pages) > 1:
            for page in pages:
                rows.append(issue(issue_type, "P1", f"count={len(pages)} value={value[:200]}", cfg, local_file=page["local_file"], original_url=page["page_url"]))
    return rows


def audit_robots(cfg: AuditConfig, client: HttpClient) -> list[dict[str, Any]]:
    rows = []
    path = cfg.output_dir / "robots.txt"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if cfg.live_http:
        http_row, text, _ = client.get_text(cfg.expected_base + "/robots.txt")
        status_ok = http_row.get("status_code") == 200
        final_url = http_row.get("final_url", "")
        status_code = http_row.get("status_code", "")
    else:
        status_ok = path.exists()
        final_url = str(path)
        status_code = "LOCAL"
    sitemap_hosts = [urllib.parse.urlparse(x).netloc for x in re.findall(r"(?im)^\s*sitemap\s*:\s*(\S+)", text)]
    blocked_all = bool(re.search(r"(?im)^\s*disallow\s*:\s*/\s*$", text))
    naver_blocked = bool(re.search(r"(?is)user-agent\s*:\s*(yeti|naverbot).*?disallow\s*:\s*/", text))
    ok = status_ok and sitemap_hosts == [cfg.site_domain] and not blocked_all and not naver_blocked
    rows.append(
        issue(
            "robots_check",
            "INFO" if ok else "P0",
            f"status={status_code}; sitemap_hosts={sitemap_hosts}; blocked_all={blocked_all}; naver_blocked={naver_blocked}",
            cfg,
            local_file=str(path),
            original_url=cfg.expected_base + "/robots.txt",
            final_url=final_url,
            status_code=status_code,
        )
    )
    return rows


def http_to_issue(row: dict[str, Any], cfg: AuditConfig) -> dict[str, Any]:
    return issue(
        "redirect_check",
        "INFO",
        f"redirect_count={row.get('redirect_count')}; chain={row.get('redirect_chain')}; error={row.get('error')}",
        cfg,
        original_url=row.get("original_url", ""),
        final_url=row.get("final_url", ""),
        status_code=row.get("status_code", ""),
        detected_host=urllib.parse.urlparse(row.get("final_url") or "").netloc,
    )


def count_by_severity(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(row.get("severity", "INFO") for row in rows)
    return {key: counts.get(key, 0) for key in ["P0", "P1", "P2", "INFO"]}


def section_failed(rows: list[dict[str, Any]]) -> bool:
    return any(row.get("severity") == "P0" for row in rows)


def p0_cause_label(row: dict[str, Any]) -> str:
    labels = {
        "host_canonicalization": "대표 URL 충돌 또는 www/non-www 미수렴",
        "canonical_count": "canonical 누락 또는 중복",
        "canonical_mismatch": "canonical host/path 불일치",
        "robots_check": "robots 오류",
        "sitemap_check": "sitemap 오류",
        "live_sitemap_compare": "배포 sitemap과 로컬 sitemap 불일치",
        "sitemap_output_missing": "sitemap URL의 output 누락",
        "output_missing_from_sitemap": "output 페이지의 sitemap 누락",
        "http_status_error": "HTTP 404/500/timeout",
        "broken_internal_link": "내부링크 오류",
        "internal_link_host_mixed": "내부링크 host 혼재",
        "metadata_host_mismatch": "메타데이터 host 불일치",
        "jsonld_parse_error": "JSON-LD 파싱 오류",
        "unexpected_noindex": "예상 밖 noindex",
    }
    return labels.get(str(row.get("issue_type", "")), str(row.get("issue_type", "P0 issue")))


def collect_p0_rows(sections: dict[str, list[dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    rows = []
    for section, items in sections.items():
        for row in items:
            if row.get("severity") == "P0":
                rows.append((section, row))
    return rows


def print_console(summary: dict[str, Any], sections: dict[str, list[dict[str, Any]]]) -> None:
    for name, rows in sections.items():
        counts = count_by_severity(rows)
        label = "FAIL" if counts["P0"] else ("WARN" if counts["P1"] or counts["P2"] else "PASS")
        print(f"{label} {name}")
    print("====================")
    print(f"P0 : {summary['P0']}")
    print(f"P1 : {summary['P1']}")
    print(f"P2 : {summary['P2']}")
    print("====================")
    print("READY FOR DEPLOY" if summary["ready"] else "DEPLOY BLOCKED")


def write_summary_md(cfg: AuditConfig, summary: dict[str, Any], sections: dict[str, list[dict[str, Any]]]) -> None:
    lines = [
        "# StudyHub Pre/Post Deploy SEO Check",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Mode: {summary['mode']}",
        f"- Live HTTP: {summary['live_http']}",
        f"- Gate only: {summary.get('gate_only', False)}",
        f"- Pages: {summary['pages']}",
        f"- Sitemap URLs: {summary['sitemap_urls']}",
        "",
        "| Check | Result | P0 | P1 | P2 | Info |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, rows in sections.items():
        counts = count_by_severity(rows)
        result = "FAIL" if counts["P0"] else ("WARN" if counts["P1"] or counts["P2"] else "PASS")
        lines.append(f"| {name} | {result} | {counts['P0']} | {counts['P1']} | {counts['P2']} | {counts['INFO']} |")
    p0_rows = collect_p0_rows(sections)
    lines += [
        "",
        "## P0 Causes",
        "",
    ]
    if p0_rows:
        for section, row in p0_rows[:200]:
            original = row.get("original_url", "")
            final = row.get("final_url", "")
            detail = row.get("detail", "")
            lines.append(f"- {section}: {p0_cause_label(row)}")
            if original or final:
                lines.append(f"  - URL: `{original}` -> `{final}`")
            if detail:
                lines.append(f"  - Detail: {detail}")
        if len(p0_rows) > 200:
            lines.append(f"- ... {len(p0_rows) - 200} more P0 rows in xlsx reports")
    else:
        lines.append("- None")
    lines += [
        "",
        "```",
        f"P0 : {summary['P0']}",
        f"P1 : {summary['P1']}",
        f"P2 : {summary['P2']}",
        "```",
        "",
        "READY FOR DEPLOY" if summary["ready"] else "DEPLOY BLOCKED",
        "",
        "P0 blocks deployment. P1 is warning-only.",
    ]
    (cfg.verification_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8-sig")
