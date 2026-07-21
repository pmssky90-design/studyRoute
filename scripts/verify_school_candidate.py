"""Verify the candidate school hub and bidirectional school/region links."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.parse import quote
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "candidate_output"
SUBJECTS = ("수학과외", "영어과외")
EXPECTED_HOST = "studyroute.co.kr"
sys.path.insert(0, str(ROOT))

import candidate_generator
import generator


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.canonical = ""
        self.json_ld: list[str] = []
        self.breadcrumb = False
        self.in_json_ld = False
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        if tag == "a" and attrs.get("href"):
            self.hrefs.append(attrs["href"] or "")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href", "") or ""
        if tag == "nav" and "breadcrumb" in (attrs.get("class", "") or "").split():
            self.breadcrumb = True
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.in_json_ld = True
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_json_ld:
            self.json_ld.append("".join(self.buffer))
            self.in_json_ld = False


def parse(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def target_for(source: Path, href: str) -> Path | None:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc or href.startswith(('#', 'mailto:', 'tel:')):
        return None
    raw = unquote(parsed.path)
    target = (source.parent / raw).resolve()
    if raw.endswith("/") or not target.suffix:
        target /= "index.html"
    return target


def main() -> int:
    issues: list[str] = []
    html_files = list(OUTPUT.rglob("*.html"))
    school_files = []
    for path in html_files:
        parts = path.relative_to(OUTPUT).parts
        if len(parts) >= 3 and parts[-2] in SUBJECTS:
            school_files.append(path)
    subject_counts = Counter(path.relative_to(OUTPUT).parts[-2] for path in school_files)
    parsed = {path: parse(path) for path in html_files}
    schools = candidate_generator.load_schools()
    school_by_slug = {school.slug: school for school in schools}
    region_slugs = {
        path.parent.name
        for path in html_files
        if path.parent.name.endswith("과외") and len(path.relative_to(OUTPUT).parts) == 2
    }
    canonical_errors: list[str] = []
    json_ld_errors: list[str] = []
    breadcrumb_errors: list[str] = []
    subject_body_errors: list[str] = []
    school_to_region_errors: list[str] = []
    region_to_school_errors: list[str] = []
    host_errors: list[str] = []
    for path, page in parsed.items():
        rel_parts = path.relative_to(OUTPUT).parts
        expected_path = "/" if rel_parts == ("index.html",) else "/" + "/".join(quote(part) for part in rel_parts[:-1]) + "/"
        expected_canonical = f"https://{EXPECTED_HOST}{expected_path}"
        if page.canonical != expected_canonical:
            canonical_errors.append(f"{path.relative_to(OUTPUT)}: {page.canonical} != {expected_canonical}")
        if page.canonical and urlparse(page.canonical).hostname != EXPECTED_HOST:
            host_errors.append(f"canonical host: {path.relative_to(OUTPUT)} -> {page.canonical}")
        if not page.breadcrumb:
            breadcrumb_errors.append(str(path.relative_to(OUTPUT)))
        if not page.json_ld:
            json_ld_errors.append(f"누락: {path.relative_to(OUTPUT)}")
        else:
            try:
                [json.loads(value) for value in page.json_ld]
            except (ValueError, json.JSONDecodeError) as exc:
                json_ld_errors.append(f"문법: {path.relative_to(OUTPUT)} -> {exc}")
    for path in school_files:
        page = parsed[path]
        rel = path.relative_to(OUTPUT).as_posix()
        parts = path.relative_to(OUTPUT).parts
        school = school_by_slug.get(parts[0])
        subject = parts[1]
        if school is None:
            subject_body_errors.append(f"학교 데이터 없음: {rel}")
            continue
        expected_body = generator.normalize_html_fragment(
            generator.extract_body_fragment(school.body_by_subject[subject])
        )
        if expected_body not in path.read_text(encoding="utf-8"):
            subject_body_errors.append(f"{subject} 원문 불일치: {rel}")
        expected_region = candidate_generator.region_page_for_school(school, region_slugs)
        targets = [target_for(path, href) for href in page.hrefs]
        expected_region_path = OUTPUT / expected_region / "index.html"
        if expected_region_path not in targets:
            school_to_region_errors.append(f"{rel} -> {expected_region}")
    broken: list[str] = []
    reverse_links: set[Path] = set()
    graph: dict[Path, set[Path]] = {}
    for path, page in parsed.items():
        graph[path] = set()
        for href in page.hrefs:
            target = target_for(path, href)
            if target is None or OUTPUT not in target.parents:
                continue
            if not target.exists():
                broken.append(f"{path.relative_to(OUTPUT)} -> {href}")
            elif target.suffix == ".html":
                graph[path].add(target)
                if target in school_files and path not in school_files:
                    reverse_links.add(target)
    for path in school_files:
        if path not in reverse_links:
            issues.append(f"지역/허브→학교 링크 누락: {path.relative_to(OUTPUT)}")
        parts = path.relative_to(OUTPUT).parts
        school = school_by_slug.get(parts[0])
        if school:
            expected_region = candidate_generator.region_page_for_school(school, region_slugs)
            source = OUTPUT / expected_region / "index.html"
            if path not in graph.get(source, set()):
                region_to_school_errors.append(f"{expected_region} -> {path.relative_to(OUTPUT)}")
    home = OUTPUT / "index.html"
    reached = {home: 0}
    queue = deque([home])
    while queue:
        source = queue.popleft()
        for target in graph.get(source, set()):
            if target not in reached:
                reached[target] = reached[source] + 1
                queue.append(target)
    orphans = [path for path in school_files if path not in reached]
    over_three = [path for path in school_files if reached.get(path, 99) > 3]
    sitemap_root = ET.parse(OUTPUT / "sitemap.xml").getroot()
    sitemap_urls = {node.text or "" for node in sitemap_root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    for url in sitemap_urls:
        if urlparse(url).hostname != EXPECTED_HOST:
            host_errors.append(f"sitemap host: {url}")
    robots_text = (OUTPUT / "robots.txt").read_text(encoding="utf-8")
    if f"Sitemap: https://{EXPECTED_HOST}/sitemap.xml" not in robots_text:
        host_errors.append("robots.txt sitemap host 불일치")
    sitemap_missing = [path for path in school_files if parsed[path].canonical not in sitemap_urls]
    issues.extend(f"broken link: {item}" for item in broken)
    issues.extend(f"orphan page: {path.relative_to(OUTPUT)}" for path in orphans)
    issues.extend(f"3클릭 초과: {path.relative_to(OUTPUT)}" for path in over_three)
    issues.extend(f"sitemap 누락: {path.relative_to(OUTPUT)}" for path in sitemap_missing)
    issues.extend(f"canonical 오류: {item}" for item in canonical_errors)
    issues.extend(f"JSON-LD 오류: {item}" for item in json_ld_errors)
    issues.extend(f"breadcrumb 오류: {item}" for item in breadcrumb_errors)
    issues.extend(f"본문 뒤바뀜: {item}" for item in subject_body_errors)
    issues.extend(f"학교→지역 오류: {item}" for item in school_to_region_errors)
    issues.extend(f"지역→학교 오류: {item}" for item in region_to_school_errors)
    issues.extend(f"호스트 오류: {item}" for item in host_errors)
    report = {
        "status": "PASS" if not issues else "FAIL",
        "total_html_pages": len(html_files),
        "school_pages": len(school_files),
        "schools": len(schools),
        "math_pages": subject_counts["수학과외"],
        "english_pages": subject_counts["영어과외"],
        "sitemap_urls": len(sitemap_urls),
        "orphan_school_pages": len(orphans),
        "school_pages_over_three_clicks": len(over_three),
        "broken_links": len(broken),
        "canonical_errors": len(canonical_errors),
        "json_ld_errors": len(json_ld_errors),
        "breadcrumb_errors": len(breadcrumb_errors),
        "school_to_region_link_errors": len(school_to_region_errors),
        "region_to_school_link_errors": len(region_to_school_errors),
        "subject_body_mismatch_errors": len(subject_body_errors),
        "host_consistency_errors": len(host_errors),
        "issues": issues,
    }
    report_name = "school_output_qa.json" if OUTPUT.name == "output" else "school_candidate_qa.json"
    report_path = ROOT / "reports" / report_name
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
