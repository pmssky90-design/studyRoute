"""Audit the generated StudyRoute static output.

This script reads the workbook and the generated output directory, then writes
audit_report.md. It does not modify generated pages or source templates.
"""

from __future__ import annotations

import json
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import sys
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config

OUTPUT = ROOT / "output"
REPORT = ROOT / "audit_report.md"
BASE_URL = config.BASE_URL.rstrip("/")
SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELATIONSHIP_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass
class WorkbookPage:
    sheet: str
    keyword: str
    body_html: str


@dataclass
class PageHtml:
    path: Path
    slug: str
    title: str = ""
    descriptions: list[str] = field(default_factory=list)
    canonical: str = ""
    h1s: list[str] = field(default_factory=list)
    breadcrumbs: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    stylesheets: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    json_ld: list[str] = field(default_factory=list)
    html_tag_attrs: dict[str, str] = field(default_factory=dict)
    meta_charset: str = ""
    viewport: str = ""
    article_html: str = ""
    article_text: str = ""
    classes: set[str] = field(default_factory=set)
    ids: set[str] = field(default_factory=set)
    tag_errors: list[str] = field(default_factory=list)


class SiteHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = PageHtml(path=Path(), slug="")
        self.stack: list[str] = []
        self.in_head = False
        self.capture_title = False
        self.capture_h1 = False
        self.capture_json = False
        self.capture_breadcrumb = False
        self.capture_article = False
        self.capture_article_depth = 0
        self.current_script_type = ""
        self.text_buffer: list[str] = []
        self.article_parts: list[str] = []
        self.article_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if tag not in VOID_TAGS:
            self.stack.append(tag)

        class_value = attrs.get("class", "")
        if class_value:
            self.page.classes.update(class_value.split())
        if attrs.get("id"):
            self.page.ids.add(attrs["id"])

        if tag == "head":
            self.in_head = True
        elif tag == "html":
            self.page.html_tag_attrs = attrs
        elif tag == "title" and self.in_head:
            self.capture_title = True
            self.text_buffer = []
        elif tag == "h1":
            self.capture_h1 = True
            self.text_buffer = []
        elif tag == "meta":
            if attrs.get("name") == "description":
                self.page.descriptions.append(attrs.get("content", ""))
            if attrs.get("charset"):
                self.page.meta_charset = attrs.get("charset", "")
            if attrs.get("name") == "viewport":
                self.page.viewport = attrs.get("content", "")
            if attrs.get("property", "").startswith("og:"):
                self.page.og[attrs["property"]] = attrs.get("content", "")
            if attrs.get("name", "").startswith("twitter:"):
                self.page.twitter[attrs["name"]] = attrs.get("content", "")
        elif tag == "link":
            rel = attrs.get("rel", "")
            if rel == "canonical":
                self.page.canonical = attrs.get("href", "")
            if "stylesheet" in rel:
                self.page.stylesheets.append(attrs.get("href", ""))
        elif tag == "script":
            self.current_script_type = attrs.get("type", "")
            if self.current_script_type == "application/ld+json":
                self.capture_json = True
                self.text_buffer = []
            elif attrs.get("src"):
                self.page.scripts.append(attrs["src"])
        elif tag == "a" and attrs.get("href"):
            self.page.anchors.append(attrs["href"])
        elif tag == "img":
            self.page.images.append(attrs)
        elif tag == "nav" and "breadcrumb" in class_value.split():
            self.capture_breadcrumb = True
        elif tag == "div" and "article-body" in class_value.split():
            self.capture_article = True
            self.capture_article_depth = 1
            self.article_parts = []
            self.article_text_parts = []
        elif self.capture_article and tag == "div":
            self.capture_article_depth += 1

        if self.capture_article and tag != "div":
            self.article_parts.append(self.get_starttag_text() or "")
        elif self.capture_article and tag == "div" and self.capture_article_depth > 1:
            self.article_parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if self.capture_title and tag == "title":
            self.page.title = "".join(self.text_buffer).strip()
            self.capture_title = False
        elif self.capture_h1 and tag == "h1":
            self.page.h1s.append("".join(self.text_buffer).strip())
            self.capture_h1 = False
        elif self.capture_json and tag == "script":
            self.page.json_ld.append("".join(self.text_buffer).strip())
            self.capture_json = False
        elif self.capture_breadcrumb and tag == "nav":
            self.capture_breadcrumb = False
        elif self.capture_article:
            if tag == "div":
                self.capture_article_depth -= 1
                if self.capture_article_depth == 0:
                    self.page.article_html = "".join(self.article_parts).strip()
                    self.page.article_text = normalize_text(" ".join(self.article_text_parts))
                    self.capture_article = False
            else:
                self.article_parts.append(f"</{tag}>")

        if tag == "head":
            self.in_head = False

        if tag not in VOID_TAGS:
            if not self.stack:
                self.page.tag_errors.append(f"unexpected closing tag </{tag}>")
            else:
                open_tag = self.stack.pop()
                if open_tag != tag:
                    self.page.tag_errors.append(f"mismatched tag <{open_tag}> closed by </{tag}>")

    def handle_startendtag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if tag == "img":
            self.page.images.append(attrs)

    def handle_data(self, data: str) -> None:
        if self.capture_title or self.capture_h1 or self.capture_json:
            self.text_buffer.append(data)
        if self.capture_breadcrumb:
            text = normalize_text(data)
            if text and text != "/":
                self.page.breadcrumbs.append(text)
        if self.capture_article:
            self.article_parts.append(data)
            self.article_text_parts.append(data)

    def close(self) -> None:
        super().close()
        if self.stack:
            self.page.tag_errors.append(f"unclosed tags: {', '.join(self.stack)}")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_workbook() -> tuple[list[str], dict[str, WorkbookPage], list[str]]:
    workbook = config.SOURCE_WORKBOOK
    if not workbook.exists():
        workbook = sorted(config.DATA_DIR.glob("*.xlsx"))[0]

    sheet_names: list[str] = []
    pages: dict[str, WorkbookPage] = {}
    with zipfile.ZipFile(workbook) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        shared = read_shared_strings(archive)

        for sheet in workbook_xml.find("a:sheets", SPREADSHEET_NS):
            sheet_name = sheet.attrib["name"].strip()
            sheet_names.append(sheet_name)
            target = rel_map[sheet.attrib[RELATIONSHIP_ID]].lstrip("/")
            sheet_path = "xl/" + target if not target.startswith("xl/") else target
            sheet_xml = ET.fromstring(archive.read(sheet_path))
            for keyword, body_html in read_sheet_rows(sheet_xml, shared):
                if keyword == "키워드":
                    continue
                pages[keyword] = WorkbookPage(sheet=sheet_name, keyword=keyword, body_html=body_html)
    return sheet_names, pages, infer_hub_suffixes(sheet_names, pages)


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.findall(".//a:t", SPREADSHEET_NS)) for item in xml_root.findall("a:si", SPREADSHEET_NS)]


def read_sheet_rows(sheet_xml: ET.Element, shared: list[str]) -> list[tuple[str, str]]:
    rows = []
    for row in sheet_xml.findall(".//a:sheetData/a:row", SPREADSHEET_NS):
        cells = {}
        for cell in row.findall("a:c", SPREADSHEET_NS):
            column = re.sub(r"\d+", "", cell.attrib.get("r", ""))
            if column in {"A", "B"}:
                cells[column] = read_cell(cell, shared)
        keyword = cells.get("A", "").strip()
        if keyword:
            rows.append((keyword, cells.get("B", "")))
    return rows


def read_cell(cell: ET.Element, shared: list[str]) -> str:
    inline = cell.find("a:is", SPREADSHEET_NS)
    if inline is not None:
        return "".join(node.text or "" for node in inline.findall(".//a:t", SPREADSHEET_NS))
    value = cell.find("a:v", SPREADSHEET_NS)
    if value is None:
        return ""
    text = value.text or ""
    return shared[int(text)] if cell.attrib.get("t") == "s" else text


def infer_hub_suffixes(sheet_names: list[str], pages: dict[str, WorkbookPage]) -> list[str]:
    suffixes: list[str] = []
    by_sheet: dict[str, list[str]] = defaultdict(list)
    for page in pages.values():
        by_sheet[page.sheet].append(page.keyword)

    for sheet in sheet_names:
        suffix = ""
        for city in config.HOME_CITY_ORDER:
            city_prefixes = [keyword for keyword in by_sheet[sheet] if keyword.startswith(city)]
            city_exact_candidates = sorted(city_prefixes, key=len)
            if city_exact_candidates:
                suffix = city_exact_candidates[0].removeprefix(city)
                break
        if suffix:
            suffixes.append(suffix)
    return suffixes


def split_keyword(keyword: str, hub_suffixes: list[str]) -> tuple[str, str]:
    for suffix in sorted(hub_suffixes, key=len, reverse=True):
        if keyword.endswith(suffix):
            return keyword[: -len(suffix)], suffix
    return keyword.removesuffix("과외"), "과외"


def region_slug(region: str) -> str:
    return f"{region}과외"


def build_parent_map(expected_slugs: set[str]) -> dict[str, str]:
    parent_map: dict[str, str] = {}
    for city in config.CITY_NAMES:
        slug = region_slug(city)
        if slug in expected_slugs:
            parent_map[slug] = ""
    for parent, children in config.REGION_CHILDREN.items():
        parent_slug = region_slug(parent)
        if parent_slug not in expected_slugs:
            continue
        for child in children:
            child_slug = region_slug(child)
            if child_slug in expected_slugs:
                parent_map[child_slug] = parent_slug
    return parent_map


def expected_breadcrumb(keyword: str, hub_suffixes: list[str], parent_map: dict[str, str]) -> list[str]:
    region, suffix = split_keyword(keyword, hub_suffixes)
    chain = []
    cursor = region_slug(region)
    while cursor:
        chain.append(cursor)
        cursor = parent_map.get(cursor, "")
    chain.reverse()
    labels = ["홈", *chain]
    if suffix != "과외":
        labels.append(keyword)
    return labels


def parse_page(path: Path) -> PageHtml:
    parser = SiteHTMLParser()
    parser.page.path = path
    parser.page.slug = "" if path == OUTPUT / "index.html" else path.parent.name
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()
    return parser.page


def resolve_local(page_path: Path, url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        if parsed.netloc != urlparse(BASE_URL).netloc:
            return None
        url = parsed.path
    else:
        url = parsed.path

    if not url or url.startswith("#") or url.startswith("mailto:") or url.startswith("tel:"):
        return None

    decoded = unquote(url)
    if decoded.startswith("/"):
        target = OUTPUT / decoded.lstrip("/")
    else:
        target = (page_path.parent / decoded).resolve()
        try:
            target.relative_to(OUTPUT.resolve())
        except ValueError:
            return target

    if target.suffix:
        return target
    return target / "index.html"


def canonical_for_slug(slug: str) -> str:
    if not slug:
        return f"{BASE_URL}/"
    return f"{BASE_URL}/{quote(slug)}/"


def write_report(sections: list[tuple[str, list[str]]], summary: dict[str, int | str]) -> None:
    lines = [
        "# StudyRoute Audit Report",
        "",
        f"- Generated at: {__import__('datetime').datetime.now().isoformat(timespec='seconds')}",
        f"- Output directory: `{OUTPUT}`",
        f"- Expected workbook pages: {summary['expected_pages']}",
        f"- Generated content pages: {summary['generated_content_pages']}",
        f"- Sitemap URLs: {summary['sitemap_urls']}",
        "",
        "## Severity Summary",
        "",
        f"- Critical: {summary['critical']}",
        f"- High: {summary['high']}",
        f"- Medium: {summary['medium']}",
        f"- Low: {summary['low']}",
        "",
    ]
    for title, items in sections:
        lines.append(f"## {title}")
        lines.append("")
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- OK")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    sheet_names, expected_pages, hub_suffixes = read_workbook()
    expected_slugs = set(expected_pages)
    parent_map = build_parent_map(expected_slugs)
    html_paths = sorted(OUTPUT.glob("**/index.html"))
    parsed_pages = {("" if path == OUTPUT / "index.html" else path.parent.name): parse_page(path) for path in html_paths}
    content_pages = {slug: page for slug, page in parsed_pages.items() if slug}

    sections: list[tuple[str, list[str]]] = []
    severity = Counter()

    missing_pages = sorted(expected_slugs - set(content_pages))
    extra_pages = sorted(set(content_pages) - expected_slugs)
    count_items = [
        f"홈: {'존재' if '' in parsed_pages else '누락'}",
        f"엑셀 기준 키워드 페이지: {len(expected_slugs)}",
        f"생성된 키워드 페이지: {len(content_pages)}",
        f"총 생성 index.html: {len(parsed_pages)}",
        f"메인 허브 suffix 수: {len(hub_suffixes)} ({', '.join(hub_suffixes)})",
    ]
    count_items += [f"누락 페이지: {slug}" for slug in missing_pages]
    count_items += [f"엑셀에 없는 생성 페이지: {slug}" for slug in extra_pages]
    if missing_pages or extra_pages:
        severity["critical"] += len(missing_pages) + len(extra_pages)
    sections.append(("1. 페이지 개수 검사", count_items))

    parent_issues = []
    for slug in expected_slugs:
        region, suffix = split_keyword(slug, hub_suffixes)
        base_region = region_slug(region)
        if base_region not in expected_slugs:
            parent_issues.append(f"{slug}: 기준 지역 페이지 없음 `{base_region}`")
        if base_region not in parent_map:
            parent_issues.append(f"{slug}: 부모 구조에 없는 지역 `{base_region}`")
        if suffix != "과외" and base_region not in expected_slugs:
            parent_issues.append(f"{slug}: 허브 부모 `{base_region}` 누락")
    severity["high"] += len(parent_issues)
    sections.append(("2. 부모-자식 구조 검사", parent_issues))

    hub_issues = []
    region_pages = [slug for slug in expected_slugs if split_keyword(slug, hub_suffixes)[1] == "과외"]
    for slug in sorted(region_pages):
        region, _ = split_keyword(slug, hub_suffixes)
        missing = [f"{region}{suffix}" for suffix in hub_suffixes if f"{region}{suffix}" not in expected_slugs]
        if missing:
            hub_issues.append(f"{slug}: 누락 허브 {', '.join(missing)}")
    severity["high"] += len(hub_issues)
    sections.append(("3. 12개 허브 검사", [f"검사 대상 지역/구/동 페이지: {len(region_pages)}", *hub_issues]))

    broken_links = []
    for slug, page in parsed_pages.items():
        urls = page.anchors + page.stylesheets + page.scripts + [img.get("src", "") for img in page.images]
        for url in urls:
            target = resolve_local(page.path, url)
            if target is not None and not target.exists():
                broken_links.append(f"{slug or '홈'}: `{url}` -> `{target}` 없음")
    severity["critical"] += len(broken_links)
    sections.append(("4. 내부링크 검사", broken_links))

    breadcrumb_issues = []
    for slug, page in content_pages.items():
        expected = expected_breadcrumb(slug, hub_suffixes, parent_map)
        if page.breadcrumbs != expected:
            breadcrumb_issues.append(f"{slug}: expected `{ ' > '.join(expected) }`, actual `{ ' > '.join(page.breadcrumbs) }`")
    severity["high"] += len(breadcrumb_issues)
    sections.append(("5. 브레드크럼 검사", breadcrumb_issues))

    title_issues = []
    titles = Counter(page.title for page in content_pages.values())
    for slug, page in content_pages.items():
        expected = f"{slug} | {expected_pages[slug].sheet} | {config.PROJECT_NAME}"
        if not page.title:
            title_issues.append(f"{slug}: title 누락")
        elif page.title != expected:
            title_issues.append(f"{slug}: expected `{expected}`, actual `{page.title}`")
    title_issues += [f"중복 title `{title}`: {count}회" for title, count in titles.items() if title and count > 1]
    severity["high"] += len(title_issues)
    sections.append(("6. Title 검사", title_issues))

    h1_issues = []
    h1_counter = Counter()
    for slug, page in content_pages.items():
        if not page.h1s:
            h1_issues.append(f"{slug}: H1 누락")
        elif len(page.h1s) > 1:
            h1_issues.append(f"{slug}: H1 복수 {page.h1s}")
        elif page.h1s[0] != slug:
            h1_issues.append(f"{slug}: expected `{slug}`, actual `{page.h1s[0]}`")
        if page.h1s:
            h1_counter[page.h1s[0]] += 1
    h1_issues += [f"중복 H1 `{h1}`: {count}회" for h1, count in h1_counter.items() if count > 1]
    severity["high"] += len(h1_issues)
    sections.append(("7. H1 검사", h1_issues))

    canonical_issues = []
    canonical_counter = Counter()
    for slug, page in parsed_pages.items():
        expected = canonical_for_slug(slug)
        canonical_counter[page.canonical] += 1
        if page.canonical != expected:
            canonical_issues.append(f"{slug or '홈'}: expected `{expected}`, actual `{page.canonical}`")
    canonical_issues += [f"중복 canonical `{url}`: {count}회" for url, count in canonical_counter.items() if url and count > 1]
    severity["high"] += len(canonical_issues)
    sections.append(("8. Canonical 검사", canonical_issues))

    desc_issues = []
    desc_counter = Counter()
    for slug, page in parsed_pages.items():
        if not page.descriptions:
            desc_issues.append(f"{slug or '홈'}: description 누락")
            continue
        desc = page.descriptions[0]
        desc_counter[desc] += 1
        if not desc.strip():
            desc_issues.append(f"{slug or '홈'}: description 비어 있음")
        if len(desc) < 50:
            desc_issues.append(f"{slug or '홈'}: description 짧음({len(desc)}자) `{desc}`")
        if len(page.descriptions) > 1:
            desc_issues.append(f"{slug or '홈'}: description 복수 {len(page.descriptions)}개")
    desc_issues += [f"중복 description `{desc}`: {count}회" for desc, count in desc_counter.items() if desc and count > 1]
    severity["medium"] += len(desc_issues)
    sections.append(("9. Meta Description 검사", desc_issues))

    og_issues = []
    required_og = ["og:title", "og:description", "og:url", "og:image"]
    for slug, page in parsed_pages.items():
        for key in required_og:
            if key not in page.og or not page.og[key]:
                og_issues.append(f"{slug or '홈'}: `{key}` 누락")
    severity["medium"] += len(og_issues)
    sections.append(("10. Open Graph 검사", og_issues))

    json_issues = []
    for slug, page in parsed_pages.items():
        if not page.json_ld:
            json_issues.append(f"{slug or '홈'}: JSON-LD 누락")
            continue
        for raw in page.json_ld:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                json_issues.append(f"{slug or '홈'}: JSON-LD 문법 오류 {exc}")
                continue
            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if isinstance(node, dict) and node.get("@type") == "WebPage":
                    if node.get("url") != canonical_for_slug(slug):
                        json_issues.append(f"{slug or '홈'}: JSON-LD url 불일치 `{node.get('url')}`")
                    if "@id" not in node:
                        json_issues.append(f"{slug or '홈'}: JSON-LD WebPage @id 누락")
    severity["medium"] += len(json_issues)
    sections.append(("11. JSON-LD 검사", json_issues))

    robots_issues = []
    robots = OUTPUT / "robots.txt"
    if not robots.exists():
        robots_issues.append("robots.txt 누락")
    else:
        robots_text = robots.read_text(encoding="utf-8")
        if "User-agent:" not in robots_text:
            robots_issues.append("User-agent 누락")
        if f"Sitemap: {BASE_URL}/sitemap.xml" not in robots_text:
            robots_issues.append("sitemap 경로 불일치")
    severity["high"] += len(robots_issues)
    sections.append(("12. robots.txt 검사", robots_issues))

    sitemap_issues = []
    sitemap_urls = []
    sitemap_path = OUTPUT / "sitemap.xml"
    if not sitemap_path.exists():
        sitemap_issues.append("sitemap.xml 누락")
    else:
        try:
            sitemap_xml = ET.fromstring(sitemap_path.read_text(encoding="utf-8"))
            sitemap_urls = [node.text or "" for node in sitemap_xml.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        except ET.ParseError as exc:
            sitemap_issues.append(f"sitemap XML 문법 오류: {exc}")
        expected_urls = {canonical_for_slug(slug) for slug in parsed_pages}
        sitemap_set = set(sitemap_urls)
        for url in sorted(expected_urls - sitemap_set):
            sitemap_issues.append(f"sitemap 누락 URL: {url}")
        for url in sorted(sitemap_set - expected_urls):
            sitemap_issues.append(f"sitemap extra URL: {url}")
        for url, count in Counter(sitemap_urls).items():
            if count > 1:
                sitemap_issues.append(f"sitemap 중복 URL: {url} ({count}회)")
    severity["critical"] += len(sitemap_issues)
    sections.append(("13. sitemap.xml 검사", sitemap_issues))

    html_issues = []
    for slug, page in parsed_pages.items():
        for error in page.tag_errors:
            html_issues.append(f"{slug or '홈'}: {error}")
    severity["high"] += len(html_issues)
    sections.append(("14. HTML 검사", html_issues))

    body_issues = []
    lengths = [len(page.article_text) for page in content_pages.values()]
    median_length = statistics.median(lengths) if lengths else 0
    short_threshold = max(200, int(median_length * 0.3))
    for slug, page in content_pages.items():
        text_len = len(page.article_text)
        if not page.article_html:
            body_issues.append(f"{slug}: 본문 HTML 없음")
        if not page.article_text:
            body_issues.append(f"{slug}: 본문 텍스트 없음")
        elif text_len < 200:
            body_issues.append(f"{slug}: 본문 매우 짧음({text_len}자)")
        elif text_len < short_threshold:
            body_issues.append(f"{slug}: 본문이 현저히 짧음({text_len}자, 기준 {short_threshold}자)")
    severity["medium"] += len(body_issues)
    sections.append(("15. 본문 검사", body_issues))

    image_issues = []
    for slug, page in parsed_pages.items():
        for img in page.images:
            src = img.get("src", "")
            target = resolve_local(page.path, src)
            if target is not None and not target.exists():
                image_issues.append(f"{slug or '홈'}: 이미지 404 `{src}`")
            if not img.get("alt"):
                image_issues.append(f"{slug or '홈'}: 이미지 alt 누락 `{src}`")
            if not img.get("width") or not img.get("height"):
                image_issues.append(f"{slug or '홈'}: 이미지 width/height 누락 `{src}`")
            if img.get("loading") != "lazy":
                image_issues.append(f"{slug or '홈'}: 이미지 lazy loading 누락 `{src}`")
    severity["medium"] += len(image_issues)
    sections.append(("16. 이미지 검사", image_issues))

    css_issues = []
    used_classes = set().union(*(page.classes for page in parsed_pages.values()))
    css_paths = set()
    for page in parsed_pages.values():
        css_paths.update(page.stylesheets)
        for href in page.stylesheets:
            target = resolve_local(page.path, href)
            if target is not None and not target.exists():
                css_issues.append(f"{page.slug or '홈'}: CSS 404 `{href}`")
    for css_url in sorted(css_paths):
        target = resolve_local(parsed_pages[""].path, css_url)
        if target and target.exists():
            css_text = target.read_text(encoding="utf-8", errors="replace")
            for class_name in sorted(set(re.findall(r"\.([a-zA-Z][\w-]*)", css_text)) - used_classes):
                css_issues.append(f"사용되지 않는 CSS class 추정: .{class_name}")
    severity["low"] += len(css_issues)
    sections.append(("17. CSS 검사", css_issues))

    js_issues = []
    for page in parsed_pages.values():
        for src in page.scripts:
            target = resolve_local(page.path, src)
            if target is not None and not target.exists():
                js_issues.append(f"{page.slug or '홈'}: JS 404 `{src}`")
            elif target and target.exists():
                text = target.read_text(encoding="utf-8", errors="replace")
                if "document." in text and "document.documentElement" not in text:
                    js_issues.append(f"{page.slug or '홈'}: DOM 접근 확인 필요 `{src}`")
    severity["medium"] += len(js_issues)
    sections.append(("18. JavaScript 검사", js_issues))

    seo_issues = []
    for slug, page in parsed_pages.items():
        if page.html_tag_attrs.get("lang") != "ko":
            seo_issues.append(f"{slug or '홈'}: html lang 불일치 `{page.html_tag_attrs.get('lang')}`")
        if page.meta_charset.lower() != "utf-8":
            seo_issues.append(f"{slug or '홈'}: charset 불일치 `{page.meta_charset}`")
        if "width=device-width" not in page.viewport:
            seo_issues.append(f"{slug or '홈'}: viewport 누락 또는 불완전")
        if page.title and len(page.title) > 65:
            seo_issues.append(f"{slug or '홈'}: title 김({len(page.title)}자)")
        if page.descriptions and len(page.descriptions[0]) > 160:
            seo_issues.append(f"{slug or '홈'}: description 김({len(page.descriptions[0])}자)")
    severity["low"] += len(seo_issues)
    sections.append(("19. 기술적 SEO 검사", seo_issues))

    summary = {
        "expected_pages": len(expected_slugs),
        "generated_content_pages": len(content_pages),
        "sitemap_urls": len(sitemap_urls),
        "critical": severity["critical"],
        "high": severity["high"],
        "medium": severity["medium"],
        "low": severity["low"],
    }
    write_report(sections, summary)
    print(f"Audit complete: {REPORT}")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
