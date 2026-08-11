"""Audit the Excel expansion candidate against the verified 2,207-page baseline."""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path


BASE_URL = "https://studyroute.co.kr"
PUBLIC_TEXT_SUFFIXES = {".html", ".xml", ".json", ".js", ".css"}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", html.unescape(value))).strip()


def normalized_url(value: str, current: str) -> str:
    absolute = urllib.parse.urljoin(current, html.unescape(value))
    parsed = urllib.parse.urlsplit(absolute)
    path = unicodedata.normalize("NFC", urllib.parse.unquote(parsed.path))
    path = urllib.parse.quote(path, safe="/%:@")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), (parsed.hostname or "").lower(), path, parsed.query, ""))


def sitemap_urls(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    return [html.unescape(value) for value in re.findall(r"<loc>(.*?)</loc>", content, flags=re.I | re.S)]


def file_for_url(root: Path, url: str) -> Path:
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).strip("/")
    if not path:
        return root / "index.html"
    return root.joinpath(*path.split("/"), "index.html")


def url_for_file(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative == "index.html":
        return BASE_URL + "/"
    slug = relative.removesuffix("/index.html")
    return BASE_URL + "/" + urllib.parse.quote(slug, safe="/") + "/"


class SnapshotParser(HTMLParser):
    def __init__(self, current_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.current_url = current_url
        self.in_title = False
        self.main_depth = 0
        self.title: list[str] = []
        self.main: list[str] = []
        self.canonical = ""
        self.description = ""
        self.og_image = ""
        self.anchors: list[str] = []
        self.images: list[str] = []
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self.in_title = True
        if tag == "main":
            self.main_depth += 1
        elif self.main_depth:
            self.main_depth += 1
        if tag == "link" and data.get("rel", "").lower() == "canonical":
            self.canonical = normalized_url(data.get("href", ""), self.current_url)
        if tag == "meta" and data.get("name", "").lower() == "description":
            self.description = normalize_text(data.get("content", ""))
        if tag == "meta" and data.get("property", "").lower() == "og:image":
            self.og_image = normalized_url(data.get("content", ""), self.current_url)
        if tag == "a" and data.get("href"):
            self.anchors.append(normalized_url(data["href"], self.current_url))
        if tag == "img" and data.get("src"):
            value = normalized_url(data["src"], self.current_url)
            self.images.append(value)
            self.assets.append(value)
        if tag == "script" and data.get("src"):
            self.assets.append(normalized_url(data["src"], self.current_url))
        if tag == "link" and data.get("href") and data.get("rel", "").lower() != "canonical":
            self.assets.append(normalized_url(data["href"], self.current_url))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        if self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title.append(data)
        if self.main_depth:
            self.main.append(data)

    def snapshot(self) -> dict[str, object]:
        return {
            "title": normalize_text("".join(self.title)),
            "description": self.description,
            "canonical": self.canonical,
            "og_image": self.og_image,
            "main_text": normalize_text(" ".join(self.main)),
            "anchors": self.anchors,
            "images": self.images,
            "assets": self.assets,
        }


def snapshot(path: Path, url: str) -> dict[str, object]:
    parser = SnapshotParser(url)
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.snapshot()


def article_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(r'(?is)<div class="article-body">(.*?)</div>\s*(?:<section class="related-section"|</div>)', content)
    return normalize_text(match.group(1)) if match else ""


def same_site_page(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.hostname == "studyroute.co.kr" and not Path(parsed.path).suffix


def public_files(root: Path) -> list[Path]:
    result = list(root.rglob("*.html"))
    for relative in ("sitemap.xml", "robots.txt", "search-index.json"):
        result.append(root / relative)
    result.extend(path for path in (root / "assets").rglob("*") if path.is_file())
    favicon = root / "favicon.ico"
    if favicon.is_file():
        result.append(favicon)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    baseline = args.baseline.resolve()
    plan_report = json.loads((candidate / "url_plan.json").read_text(encoding="utf-8"))
    plan = plan_report["items"]
    included = [item for item in plan if item["included"]]
    excluded = [item for item in plan if not item["included"]]
    included_by_slug = {item["slug"]: item for item in included}

    old_urls = sitemap_urls(baseline / "sitemap.xml")
    new_urls = sitemap_urls(candidate / "sitemap.xml")
    old_set = set(old_urls)
    new_set = set(new_urls)
    planned_urls = {item["url"] for item in included}
    excluded_urls = {item["url"] for item in excluded}
    html_files = sorted(candidate.rglob("*.html"))
    html_urls = {url_for_file(candidate, path) for path in html_files}

    parsed: dict[str, dict[str, object]] = {}
    for url in new_urls:
        path = file_for_url(candidate, url)
        if path.is_file():
            parsed[url] = snapshot(path, url)

    canonical_mismatches = [url for url, page in parsed.items() if page["canonical"] != normalized_url(url, url)]
    title_counter = Counter(str(page["title"]) for page in parsed.values())
    canonical_counter = Counter(str(page["canonical"]) for page in parsed.values())
    duplicate_titles = sorted(title for title, count in title_counter.items() if title and count > 1)
    duplicate_canonicals = sorted(url for url, count in canonical_counter.items() if url and count > 1)

    page_paths = {urllib.parse.urlsplit(url).path.rstrip("/") + "/" for url in new_urls}
    inbound: Counter[str] = Counter()
    broken_internal: list[dict[str, str]] = []
    missing_assets: list[dict[str, str]] = []
    for source_url, page in parsed.items():
        for target in page["anchors"]:
            parsed_target = urllib.parse.urlsplit(str(target))
            if parsed_target.hostname != "studyroute.co.kr":
                continue
            target_path = parsed_target.path.rstrip("/") + "/"
            if target_path in page_paths:
                inbound[BASE_URL + target_path] += 1
            elif parsed_target.fragment:
                continue
            else:
                broken_internal.append({"source": source_url, "target": str(target)})
        for asset in page["assets"]:
            parsed_asset = urllib.parse.urlsplit(str(asset))
            if parsed_asset.hostname != "studyroute.co.kr":
                continue
            relative = urllib.parse.unquote(parsed_asset.path).lstrip("/")
            if relative and not (candidate / relative).is_file():
                missing_assets.append({"source": source_url, "asset": str(asset)})

    orphan_new = sorted(url for url in planned_urls if inbound[url] == 0)

    hierarchy_parent_errors: list[str] = []
    hierarchy_child_errors: list[str] = []
    for item in included:
        url = item["url"]
        anchors = set(parsed[url]["anchors"])
        parent_url = flat_url = BASE_URL + "/" + urllib.parse.quote(item["parent_slug"]) + "/"
        if item["parent_slug"] and normalized_url(parent_url, url) not in anchors:
            hierarchy_parent_errors.append(item["slug"])
        for child_slug in item["child_slugs"]:
            child_url = BASE_URL + "/" + urllib.parse.quote(child_slug) + "/"
            if normalized_url(child_url, url) not in anchors:
                hierarchy_child_errors.append(f"{item['slug']} -> {child_slug}")

    existing_missing = sorted(set(old_urls) - new_set)
    existing_meta = Counter()
    existing_body_mismatches: list[str] = []
    existing_link_losses: list[str] = []
    intentional_link_changes: list[str] = []
    for url in old_urls:
        old_path = file_for_url(baseline, url)
        new_path = file_for_url(candidate, url)
        if not old_path.is_file() or not new_path.is_file():
            continue
        old = snapshot(old_path, url)
        new = parsed[url]
        for field in ("canonical", "title", "description", "og_image", "images"):
            if old[field] != new[field]:
                existing_meta[field] += 1
        old_body = article_body(old_path)
        new_body = article_body(new_path)
        if old_body != new_body:
            existing_body_mismatches.append(url)
        old_links = Counter(old["anchors"])
        new_links = Counter(new["anchors"])
        if old_links - new_links:
            existing_link_losses.append(url)
        if new_links - old_links:
            intentional_link_changes.append(url)

    search = json.loads((candidate / "search-index.json").read_text(encoding="utf-8"))
    search_urls = {normalized_url(record["url"], BASE_URL + "/") for record in search["pages"]}
    normalized_sitemap_urls = {normalized_url(url, url) for url in new_urls}

    school_marker_hits: list[str] = []
    for path in public_files(candidate):
        if path.suffix.lower() in PUBLIC_TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "(학교)" in text:
                school_marker_hits.append(path.relative_to(candidate).as_posix())

    slug_counts = Counter(item["slug"] for item in included)
    duplicate_slugs = sorted(slug for slug, count in slug_counts.items() if count > 1)
    formula_errors = sorted(
        item["slug"]
        for item in included
        if not item["generated_hub"]
        and item["slug"] != re.sub(r"\s+", "", item["entity_name"] + item["normalized_sheet_type"])
    )
    long_title_slug_errors = sorted(
        item["slug"]
        for item in included
        if len(item["slug"]) > len(re.sub(r"\s+", "", item["entity_name"] + item["normalized_sheet_type"]))
        and not item["generated_hub"]
    )

    robots_same = (
        (candidate / "robots.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        == (baseline / "robots.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    )

    report = {
        "counts": {
            "baseline_html": len(list(baseline.rglob("*.html"))),
            "candidate_html": len(html_files),
            "baseline_sitemap": len(old_urls),
            "candidate_sitemap": len(new_urls),
            "planned_new": len(included),
            "excluded": len(excluded),
        },
        "url_integrity": {
            "existing_missing": existing_missing,
            "unexpected_additional": sorted((new_set - set(old_urls)) - planned_urls),
            "planned_missing": sorted(planned_urls - new_set),
            "excluded_in_sitemap": sorted(excluded_urls & new_set),
            "html_without_sitemap": sorted(html_urls - new_set),
            "sitemap_without_html": sorted(new_set - html_urls),
        },
        "existing_protection": {
            "meta_mismatch_counts": dict(existing_meta),
            "body_mismatches": existing_body_mismatches,
            "internal_link_losses": existing_link_losses,
            "intentional_link_addition_pages": len(intentional_link_changes),
        },
        "new_pages": {
            "canonical_mismatches": canonical_mismatches,
            "duplicate_slugs": duplicate_slugs,
            "formula_errors": formula_errors,
            "long_title_slug_errors": long_title_slug_errors,
            "parent_link_errors": hierarchy_parent_errors,
            "child_link_errors": hierarchy_child_errors,
            "orphan_pages": orphan_new,
        },
        "site": {
            "broken_internal_links": broken_internal,
            "missing_assets": missing_assets,
            "duplicate_titles": duplicate_titles,
            "duplicate_canonicals": duplicate_canonicals,
            "robots_match": robots_same,
            "search_index_count": search.get("count"),
            "search_index_missing_urls": sorted(normalized_sitemap_urls - search_urls),
            "search_index_additional_urls": sorted(search_urls - normalized_sitemap_urls),
            "school_marker_hits": school_marker_hits,
        },
    }
    blockers = []
    for section in ("url_integrity", "new_pages"):
        blockers.extend(key for key, value in report[section].items() if value)
    blockers.extend(
        key
        for key, value in report["existing_protection"].items()
        if key != "intentional_link_addition_pages" and value
    )
    blockers.extend(
        key
        for key, value in report["site"].items()
        if key not in {"robots_match", "search_index_count"} and value
    )
    if not robots_same:
        blockers.append("robots_match")
    if search.get("count") != len(new_urls):
        blockers.append("search_index_count")
    report["blockers"] = blockers
    target = candidate / "expansion_validation_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    compact_report = {
        "counts": report["counts"],
        "existing_meta_mismatches": report["existing_protection"]["meta_mismatch_counts"],
        "existing_body_mismatches": len(existing_body_mismatches),
        "existing_link_losses": len(existing_link_losses),
        "intentional_link_addition_pages": len(intentional_link_changes),
        "broken_internal_links": len(broken_internal),
        "missing_assets": len(missing_assets),
        "orphan_pages": len(orphan_new),
        "school_marker_hits": len(school_marker_hits),
        "blockers": blockers,
    }
    print(json.dumps(compact_report, ensure_ascii=False, indent=2))
    print(f"report={target}")
    if blockers:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
