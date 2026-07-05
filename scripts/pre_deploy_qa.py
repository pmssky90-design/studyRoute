"""Pre-deploy QA for the generated StudyRoute static site."""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


OUTPUT = config.OUTPUT_DIR
BASE_URL = config.BASE_URL.rstrip("/")
REPORT_JSON = ROOT / "reports" / "pre_deploy_qa_results.json"
REPORT_MD = ROOT / "pre_deploy_report.md"


@dataclass
class Issue:
    severity: str
    category: str
    path: str
    message: str
    detail: str = ""


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[tuple[str, str], str] = {}
        self.links: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.h1s: list[str] = []
        self.json_ld: list[str] = []
        self.body_text: list[str] = []
        self.classes: set[str] = set()
        self.ids: set[str] = set()
        self.in_title = False
        self.in_h1 = False
        self.in_json_ld = False
        self.in_body = False
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: v or "" for k, v in attrs_list}
        if attrs.get("class"):
            self.classes.update(attrs["class"].split())
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "title":
            self.in_title = True
            self.title_parts = []
        elif tag == "body":
            self.in_body = True
        elif tag == "h1":
            self.in_h1 = True
            self.h1_parts = []
        elif tag == "meta":
            if "name" in attrs:
                self.meta[("name", attrs["name"])] = attrs.get("content", "")
            if "property" in attrs:
                self.meta[("property", attrs["property"])] = attrs.get("content", "")
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "a":
            self.anchors.append(attrs)
        elif tag == "img":
            self.images.append(attrs)
        elif tag == "script":
            self.scripts.append(attrs)
            if attrs.get("type") == "application/ld+json":
                self.in_json_ld = True
                self.json_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            self.title = normalize("".join(self.title_parts))
        elif tag == "body":
            self.in_body = False
        elif tag == "h1":
            self.in_h1 = False
            self.h1s.append(normalize("".join(self.h1_parts)))
        elif tag == "script" and self.in_json_ld:
            self.in_json_ld = False
            self.json_ld.append("".join(self.json_parts).strip())

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_h1:
            self.h1_parts.append(data)
        if self.in_json_ld:
            self.json_parts.append(data)
        if self.in_body:
            text = normalize(data)
            if text:
                self.body_text.append(text)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def rel(path: Path | str) -> str:
    if isinstance(path, Path):
        try:
            return path.relative_to(OUTPUT).as_posix()
        except ValueError:
            try:
                return path.relative_to(ROOT).as_posix()
            except ValueError:
                return str(path)
    return path


def add(issues: list[Issue], severity: str, category: str, path: Path | str, message: str, detail: str = "") -> None:
    issues.append(Issue(severity, category, rel(path), message, detail))


def page_url(page: Path) -> str:
    if page == OUTPUT / "index.html":
        return f"{BASE_URL}/"
    return f"{BASE_URL}/{quote(page.parent.name)}/"


def local_target(base_file: Path, href: str) -> Path | None:
    href = (href or "").split("#", 1)[0]
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        if f"{parsed.scheme}://{parsed.netloc}".rstrip("/") != BASE_URL:
            return None
        href = parsed.path
    else:
        href = parsed.path
    if href.startswith("/"):
        target = OUTPUT / unquote(href).lstrip("/")
    else:
        target = (base_file.parent / unquote(href)).resolve()
    try:
        target.relative_to(OUTPUT.resolve())
    except ValueError:
        return target
    if target.suffix:
        return target
    return target / "index.html"


def asset_exists(base_file: Path, url: str) -> bool:
    target = local_target(base_file, url)
    return target is None or target.exists()


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser


def expected_title(path: Path, title: str) -> bool:
    if path == OUTPUT / "index.html":
        return bool(title)
    slug = path.parent.name
    return title.startswith(f"{slug} | ") and title.endswith(f" | {config.PROJECT_NAME}")


def audit() -> tuple[list[Issue], dict[str, object]]:
    issues: list[Issue] = []
    pages = sorted(OUTPUT.glob("**/index.html"))
    parsed = {page: parse_page(page) for page in pages}
    titles = Counter(p.title for p in parsed.values() if p.title)
    descriptions = Counter(p.meta.get(("name", "description"), "") for p in parsed.values())
    canonicals = Counter(
        next((l.get("href", "") for l in p.links if l.get("rel") == "canonical"), "") for p in parsed.values()
    )
    all_classes = set().union(*(p.classes for p in parsed.values())) if parsed else set()

    required_icons = {
        "favicon.ico": "assets/images/favicon.ico",
        "favicon-32x32.png": "assets/images/favicon-32x32.png",
        "apple-touch-icon.png": "assets/images/apple-touch-icon.png",
    }
    for label, path in required_icons.items():
        if not (OUTPUT / path).exists():
            add(issues, "High", "Favicon", path, f"{label} missing")

    for page, p in parsed.items():
        expected = page_url(page)
        canonical = next((l.get("href", "") for l in p.links if l.get("rel") == "canonical"), "")
        if canonical != expected:
            add(issues, "High", "Canonical", page, "canonical does not match current URL", f"{canonical} != {expected}")

        icon_hrefs = [l.get("href", "") for l in p.links if "icon" in l.get("rel", "")]
        apple_hrefs = [l.get("href", "") for l in p.links if l.get("rel") == "apple-touch-icon"]
        for icon in required_icons.values():
            if not any(urlparse(href).path.lstrip("/").endswith(icon) for href in icon_hrefs + apple_hrefs):
                add(issues, "Medium", "Favicon", page, "favicon link missing", icon)
        for href in icon_hrefs + apple_hrefs:
            if not asset_exists(page, href):
                add(issues, "High", "Favicon", page, "favicon link resolves to 404", href)

        if not p.title:
            add(issues, "Critical", "Title", page, "title missing")
        elif not expected_title(page, p.title):
            add(issues, "High", "Title", page, "title format mismatch", p.title)
        if len(p.title) > 75:
            add(issues, "Low", "Title", page, "title is long", str(len(p.title)))

        desc = p.meta.get(("name", "description"), "")
        if not desc:
            add(issues, "High", "Meta description", page, "meta description missing")
        elif len(desc) < 35:
            add(issues, "Medium", "Meta description", page, "meta description too short", str(len(desc)))

        if len(p.h1s) != 1:
            add(issues, "High", "H1", page, "H1 count is not one", str(len(p.h1s)))
        elif page != OUTPUT / "index.html" and p.h1s[0] != page.parent.name:
            add(issues, "High", "H1", page, "H1 does not match page keyword", p.h1s[0])

        body_text = normalize(" ".join(p.body_text))
        if len(body_text) < (250 if page == OUTPUT / "index.html" else 700):
            add(issues, "Medium", "Page", page, "body appears too short", str(len(body_text)))

        for key in ["og:title", "og:description", "og:image", "og:url"]:
            if not p.meta.get(("property", key)):
                add(issues, "High", "Open Graph", page, f"{key} missing")
        if p.meta.get(("property", "og:url")) != expected:
            add(issues, "High", "Open Graph", page, "og:url mismatch", p.meta.get(("property", "og:url"), ""))
        for key in ["twitter:title", "twitter:description", "twitter:image"]:
            if not p.meta.get(("name", key)):
                add(issues, "High", "Twitter Card", page, f"{key} missing")
        for key in [("property", "og:image"), ("name", "twitter:image")]:
            image_url = p.meta.get(key, "")
            if image_url and not asset_exists(page, image_url):
                add(issues, "High", "Social image", page, f"{key[1]} resolves to 404", image_url)

        for raw in p.json_ld:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                add(issues, "High", "JSON-LD", page, "JSON-LD syntax error", str(exc))
                continue
            nodes = data if isinstance(data, list) else data.get("@graph", []) if isinstance(data, dict) else []
            types = {node.get("@type") for node in nodes if isinstance(node, dict)}
            if "Organization" not in types:
                add(issues, "Medium", "JSON-LD", page, "Organization missing")
            if "WebSite" not in types:
                add(issues, "Medium", "JSON-LD", page, "WebSite missing")
            webpage = next((node for node in nodes if isinstance(node, dict) and node.get("@type") == "WebPage"), None)
            if not webpage:
                add(issues, "Medium", "JSON-LD", page, "WebPage missing")
            else:
                if webpage.get("@id") != expected or webpage.get("url") != expected:
                    add(issues, "Medium", "JSON-LD", page, "WebPage @id/url mismatch")
                if "publisher" not in webpage:
                    add(issues, "Medium", "JSON-LD", page, "publisher missing")

        for anchor in p.anchors:
            href = anchor.get("href", "")
            target = local_target(page, href)
            if target is not None and not target.exists():
                add(issues, "High", "Internal link", page, "internal link resolves to 404", href)
        for img in p.images:
            src = img.get("src", "")
            if src and not asset_exists(page, src):
                add(issues, "High", "Image", page, "image resolves to 404", src)
            for attr in ["alt", "width", "height"]:
                if not img.get(attr):
                    add(issues, "Medium", "Image", page, f"image {attr} missing", src)
            if page != OUTPUT / "index.html" and img.get("loading") != "lazy":
                add(issues, "Low", "Image", page, "non-home image should declare lazy loading", src)
        for link in p.links:
            if "stylesheet" in link.get("rel", ""):
                href = link.get("href", "")
                if href and not asset_exists(page, href):
                    add(issues, "High", "CSS", page, "stylesheet resolves to 404", href)
        for script in p.scripts:
            src = script.get("src", "")
            if src and not asset_exists(page, src):
                add(issues, "High", "JavaScript", page, "script resolves to 404", src)

    for title, count in titles.items():
        if count > 1:
            add(issues, "Low", "Title", "", "duplicate title", f"{count}: {title}")
    for desc, count in descriptions.items():
        if desc and count > 1:
            add(issues, "Low", "Meta description", "", "duplicate meta description", f"{count} pages")
    for canonical, count in canonicals.items():
        if canonical and count > 1:
            add(issues, "Critical", "Canonical", "", "duplicate canonical", f"{count}: {canonical}")

    robots = OUTPUT / "robots.txt"
    if not robots.exists():
        add(issues, "High", "Robots", robots, "robots.txt missing")
    else:
        text = robots.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"(?im)^User-agent:\s*\*", text):
            add(issues, "High", "Robots", robots, "User-agent missing")
        if f"Sitemap: {BASE_URL}/sitemap.xml" not in text:
            add(issues, "High", "Robots", robots, "Sitemap path missing or wrong")
        if re.search(r"(?im)^Disallow:\s*/\s*$", text):
            add(issues, "Critical", "Robots", robots, "site-wide disallow found")

    sitemap = OUTPUT / "sitemap.xml"
    sitemap_urls: list[str] = []
    if not sitemap.exists():
        add(issues, "Critical", "Sitemap", sitemap, "sitemap.xml missing")
    else:
        try:
            root = ET.parse(sitemap).getroot()
            sitemap_urls = [node.text or "" for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        except Exception as exc:
            add(issues, "Critical", "Sitemap", sitemap, "sitemap XML syntax error", repr(exc))
        expected_urls = {page_url(page) for page in pages}
        for url in sorted(expected_urls - set(sitemap_urls)):
            add(issues, "High", "Sitemap", sitemap, "URL missing from sitemap", url)
        for url in sorted(set(sitemap_urls) - expected_urls):
            add(issues, "High", "Sitemap", sitemap, "sitemap URL has no HTML page", url)
        for url, count in Counter(sitemap_urls).items():
            if count > 1:
                add(issues, "High", "Sitemap", sitemap, "duplicate sitemap URL", f"{count}: {url}")

    css_files = sorted((OUTPUT / "assets" / "css").glob("*.css"))
    for css_file in css_files:
        css = css_file.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"url\(([^)]+)\)", css):
            href = match.group(1).strip("\"'")
            target = local_target(css_file, href)
            if target is not None and not target.exists():
                add(issues, "High", "CSS", css_file, "CSS asset resolves to 404", href)
        unused = sorted(set(re.findall(r"\.([a-zA-Z][\w-]*)", css)) - all_classes)
        if unused:
            add(issues, "Low", "CSS", css_file, "possible unused CSS classes", ", ".join(unused[:30]))

    sample_pages = random.Random(20260702).sample(pages, min(100, len(pages)))
    sample_issues = []
    for page in sample_pages:
        p = parsed[page]
        if not p.title or not p.h1s or not normalize(" ".join(p.body_text)) or not p.images:
            sample_issues.append(rel(page))
    if sample_issues:
        add(issues, "High", "Random sample", "", "sample page structural failures", ", ".join(sample_issues[:20]))

    stats = {
        "pages": len(pages),
        "sitemap_urls": len(sitemap_urls),
        "sample_pages": [rel(page) for page in sample_pages],
        "issues_by_severity": dict(Counter(issue.severity for issue in issues)),
        "issues_by_category": dict(Counter(issue.category for issue in issues)),
    }
    return issues, stats


def write_outputs(issues: list[Issue], stats: dict[str, object]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps({"stats": stats, "issues": [asdict(issue) for issue in issues]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = Counter(issue.severity for issue in issues)
    lines = [
        "# StudyRoute Pre-Deploy QA Report",
        "",
        "## Summary",
        f"- Pages checked: {stats['pages']}",
        f"- Sitemap URLs checked: {stats['sitemap_urls']}",
        f"- Random sample checked: {len(stats['sample_pages'])}",
        f"- Critical: {counts['Critical']}",
        f"- High: {counts['High']}",
        f"- Medium: {counts['Medium']}",
        f"- Low: {counts['Low']}",
        "",
        "## Findings",
    ]
    if issues:
        for issue in issues[:300]:
            place = f" `{issue.path}`" if issue.path else ""
            detail = f" - {issue.detail}" if issue.detail else ""
            lines.append(f"- **{issue.severity}** [{issue.category}]{place}: {issue.message}{detail}")
        if len(issues) > 300:
            lines.append(f"- ... {len(issues) - 300} additional findings are in `{rel(REPORT_JSON)}`.")
    else:
        lines.append("- OK")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    issues, stats = audit()
    write_outputs(issues, stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 1 if any(issue.severity in {"Critical", "High", "Medium"} for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
