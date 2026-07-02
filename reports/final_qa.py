from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
ASSETS = OUTPUT / "assets"
BASE_URL = "https://studyroute.co.kr"


@dataclass
class Issue:
    severity: str
    category: str
    message: str
    path: str = ""
    detail: str = ""


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[tuple[str, str], str] = {}
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.headings: list[tuple[int, str]] = []
        self.json_ld: list[str] = []
        self.body_text: list[str] = []
        self.in_title = False
        self.in_json_ld = False
        self.in_article_body = False
        self.article_depth = 0
        self.current_heading: int | None = None
        self.heading_text: list[str] = []
        self.current_script: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: v or "" for k, v in attrs_list}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            if "name" in attrs:
                self.meta[("name", attrs["name"])] = attrs.get("content", "")
            if "property" in attrs:
                self.meta[("property", attrs["property"])] = attrs.get("content", "")
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "a":
            self.links.append({"tag": "a", **attrs})
        elif tag == "img":
            self.images.append(attrs)
        elif tag == "script":
            self.scripts.append(attrs)
            self.current_script = attrs
            if attrs.get("type") == "application/ld+json":
                self.in_json_ld = True
        elif tag == "button":
            self.buttons.append(attrs)
        elif re.fullmatch(r"h[1-6]", tag):
            self.current_heading = int(tag[1])
            self.heading_text = []
        if tag == "div" and "article-body" in attrs.get("class", "").split():
            self.in_article_body = True
            self.article_depth = 1
        elif self.in_article_body:
            self.article_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "script":
            self.in_json_ld = False
            self.current_script = None
        elif re.fullmatch(r"h[1-6]", tag) and self.current_heading is not None:
            text = " ".join("".join(self.heading_text).split())
            self.headings.append((self.current_heading, text))
            self.current_heading = None
            self.heading_text = []
        if self.in_article_body:
            self.article_depth -= 1
            if self.article_depth <= 0:
                self.in_article_body = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.in_json_ld:
            self.json_ld.append(data)
        if self.current_heading is not None:
            self.heading_text.append(data)
        if self.in_article_body:
            self.body_text.append(data)


def rel(path: Path) -> str:
    return path.relative_to(OUTPUT).as_posix()


def add(issues: list[Issue], severity: str, category: str, message: str, path: Path | str = "", detail: str = "") -> None:
    issues.append(Issue(severity, category, message, rel(path) if isinstance(path, Path) and path.is_relative_to(OUTPUT) else str(path), detail))


def page_url(page: Path) -> str:
    if page == OUTPUT / "index.html":
        return BASE_URL + "/"
    return BASE_URL + "/" + quote(page.parent.name) + "/"


def target_exists(base: Path, href: str) -> bool:
    href = href.split("#", 1)[0]
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return True
    if href.startswith(("http://", "https://")):
        return href.startswith(BASE_URL)
    target = (base / unquote(href)).resolve()
    try:
        target.relative_to(OUTPUT.resolve())
    except ValueError:
        return False
    if href.endswith("/"):
        return (target / "index.html").exists()
    return target.exists() or (target / "index.html").exists()


def audit() -> tuple[list[Issue], dict[str, object]]:
    issues: list[Issue] = []
    pages = sorted(OUTPUT.glob("**/index.html"))
    html_pages = sorted(OUTPUT.glob("**/*.html"))
    stats: dict[str, object] = {"html_pages": len(html_pages), "index_pages": len(pages)}
    title_counter: Counter[str] = Counter()
    desc_counter: Counter[str] = Counter()
    canonical_counter: Counter[str] = Counter()
    sitemap_urls: list[str] = []
    parsed_pages: dict[Path, PageParser] = {}

    for page in html_pages:
        parser = PageParser()
        try:
            html = page.read_text(encoding="utf-8")
            parser.feed(html)
        except Exception as exc:
            add(issues, "Critical", "HTML", "HTML 파싱 실패", page, repr(exc))
            continue
        parsed_pages[page] = parser
        title = " ".join(parser.title.split())
        desc = parser.meta.get(("name", "description"), "")
        canonical = next((l.get("href", "") for l in parser.links if l.get("rel") == "canonical"), "")
        title_counter[title] += 1
        desc_counter[desc] += 1
        canonical_counter[canonical] += 1

        if not title:
            add(issues, "Critical", "SEO", "title 누락", page)
        elif len(title) > 70:
            add(issues, "Low", "SEO", "title 길이 70자 초과", page, title)
        if not desc:
            add(issues, "High", "SEO", "meta description 누락", page)
        elif len(desc) < 35:
            add(issues, "Medium", "SEO", "meta description이 짧음", page, desc)
        h1 = [h for level, h in parser.headings if level == 1]
        if not h1:
            add(issues, "Critical", "Content", "H1 누락", page)
        elif len(h1) > 1:
            add(issues, "High", "Content", "H1 중복", page, " | ".join(h1[:5]))
        if canonical != page_url(page):
            add(issues, "High", "SEO", "canonical이 현재 URL과 불일치", page, f"{canonical} != {page_url(page)}")
        for key in [("property", "og:title"), ("property", "og:description"), ("property", "og:url"), ("property", "og:image"), ("name", "twitter:card"), ("name", "twitter:image")]:
            if not parser.meta.get(key):
                add(issues, "High", "SEO", f"{key[1]} 누락", page)
        if not parser.meta.get(("name", "viewport")):
            add(issues, "High", "Mobile", "viewport 누락", page)
        if not re.search(r"<html[^>]+lang=\"ko\"", html):
            add(issues, "High", "Accessibility", "html lang=ko 누락", page)
        if not parser.json_ld:
            add(issues, "High", "Schema", "JSON-LD 누락", page)
        else:
            for block in parser.json_ld:
                try:
                    data = json.loads(block)
                    if isinstance(data, dict) and data.get("@id", "").startswith("http://"):
                        add(issues, "Medium", "Schema", "JSON-LD @id가 http 사용", page)
                except Exception as exc:
                    add(issues, "High", "Schema", "JSON-LD 문법 오류", page, repr(exc))

        body_text = " ".join("".join(parser.body_text).split())
        if page != OUTPUT / "index.html":
            if not body_text:
                add(issues, "Critical", "Content", "본문 텍스트 없음", page)
            elif len(body_text) < 700:
                add(issues, "Medium", "Content", "본문 길이 700자 미만", page, str(len(body_text)))

        for img in parser.images:
            src = img.get("src", "")
            if not src:
                add(issues, "High", "Image", "src 없는 이미지", page)
                continue
            if not target_exists(page.parent, src):
                add(issues, "High", "Image", "이미지 경로 404", page, src)
            for attr in ["alt", "width", "height"]:
                if not img.get(attr):
                    add(issues, "Medium", "Image", f"이미지 {attr} 누락", page, src)
            if page != OUTPUT / "index.html" and not img.get("loading"):
                add(issues, "Low", "Image", "본문 이미지 lazy/eager 명시 없음", page, src)

        for link in parser.links:
            href = link.get("href")
            if not href:
                continue
            if link.get("tag") == "a":
                if not target_exists(page.parent, href):
                    add(issues, "High", "Link", "내부 링크 404 또는 루트 밖 링크", page, href)
                if link.get("target") == "_blank":
                    relv = link.get("rel", "")
                    if "noopener" not in relv or "noreferrer" not in relv:
                        add(issues, "Medium", "Security", "target=_blank rel 보안 속성 누락", page, href)

    for value, count in title_counter.items():
        if value and count > 1:
            add(issues, "Low", "SEO", "중복 title", "", f"{count} pages: {value}")
    for value, count in desc_counter.items():
        if value and count > 1:
            add(issues, "Low", "SEO", "중복 description", "", f"{count} pages")
    for value, count in canonical_counter.items():
        if value and count > 1:
            add(issues, "Critical", "SEO", "중복 canonical", "", f"{count} pages: {value}")

    sitemap = OUTPUT / "sitemap.xml"
    if not sitemap.exists():
        add(issues, "Critical", "Sitemap", "sitemap.xml 누락")
    else:
        try:
            root = ET.parse(sitemap).getroot()
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            sitemap_urls = [loc.text or "" for loc in root.findall(".//sm:loc", ns)]
            if len(sitemap_urls) != len(set(sitemap_urls)):
                add(issues, "High", "Sitemap", "sitemap URL 중복")
            expected_urls = {page_url(p) for p in html_pages}
            missing = expected_urls - set(sitemap_urls)
            extra = set(sitemap_urls) - expected_urls
            if missing:
                add(issues, "High", "Sitemap", "sitemap 누락 URL", "", str(len(missing)))
            if extra:
                add(issues, "High", "Sitemap", "sitemap에 없는 HTML URL", "", str(len(extra)))
        except Exception as exc:
            add(issues, "High", "Sitemap", "sitemap 파싱 오류", "", repr(exc))
    robots = OUTPUT / "robots.txt"
    if not robots.exists():
        add(issues, "High", "Robots", "robots.txt 누락")
    else:
        txt = robots.read_text(encoding="utf-8")
        if "Sitemap: https://studyroute.co.kr/sitemap.xml" not in txt:
            add(issues, "Medium", "Robots", "robots sitemap 경로 오류")
        if "Disallow: /" in txt:
            add(issues, "Critical", "Robots", "전체 차단 Disallow 발견")

    large_assets = []
    for f in ASSETS.glob("**/*"):
        if f.is_file() and f.stat().st_size > 1_000_000:
            large_assets.append((rel(f), f.stat().st_size))
            add(issues, "Medium", "Performance", "1MB 초과 asset", f, str(f.stat().st_size))
    stats["large_assets"] = large_assets
    stats["sitemap_urls"] = len(sitemap_urls)
    stats["issues_by_severity"] = dict(Counter(i.severity for i in issues))
    stats["issues_by_category"] = dict(Counter(i.category for i in issues))
    return issues, stats


def summarize(issues: list[Issue], stats: dict[str, object]) -> str:
    lines = [
        "# StudyRoute Final QA",
        "",
        "## Summary",
        f"- HTML files: {stats.get('html_pages')}",
        f"- Index pages: {stats.get('index_pages')}",
        f"- Sitemap URLs: {stats.get('sitemap_urls')}",
        f"- Issues by severity: {stats.get('issues_by_severity')}",
        f"- Issues by category: {stats.get('issues_by_category')}",
        "",
        "## Findings",
    ]
    for issue in issues[:500]:
        location = f" `{issue.path}`" if issue.path else ""
        detail = f" - {issue.detail}" if issue.detail else ""
        lines.append(f"- **{issue.severity}** [{issue.category}]{location}: {issue.message}{detail}")
    if len(issues) > 500:
        lines.append(f"- ... {len(issues) - 500} additional Low findings omitted from this summary.")
    return "\n".join(lines) + "\n"


def main() -> int:
    issues, stats = audit()
    Path("reports/final_qa_results.json").write_text(
        json.dumps({"stats": stats, "issues": [i.__dict__ for i in issues]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(summarize(issues, stats))
    return 1 if any(i.severity in {"Critical", "High", "Medium"} for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
