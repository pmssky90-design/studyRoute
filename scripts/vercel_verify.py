"""Verify the deployed Vercel StudyRoute site."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://studyroute-theta.vercel.app"
REPORT = Path("reports/vercel_verify_results.json")


class HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.in_json_ld = False
        self.json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if tag == "title":
            self.in_title = True
            self.title_parts = []
        elif tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key:
                self.meta[key] = attrs.get("content", "")
        elif tag == "link":
            rel = attrs.get("rel", "")
            if rel:
                self.links[rel] = attrs.get("href", "")
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            self.in_json_ld = True
            self.json_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            self.title = " ".join("".join(self.title_parts).split())
        elif tag == "script" and self.in_json_ld:
            self.in_json_ld = False
            self.json_ld.append("".join(self.json_parts).strip())

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_json_ld:
            self.json_parts.append(data)


def fetch(path: str) -> tuple[int, str]:
    url = BASE_URL + path
    request = Request(url, headers={"User-Agent": "StudyRoute-Vercel-QA/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        status = getattr(getattr(exc, "fp", None), "status", 0) or getattr(exc, "code", 0)
        return int(status), str(exc)


def page_path(slug: str) -> str:
    return f"/{quote(slug)}/"


def main() -> int:
    paths = {
        "home": "/",
        "daejeon": page_path("대전과외"),
        "daegu": page_path("대구과외"),
        "math": page_path("수학과외"),
        "random_detail": page_path("가양동과외"),
        "robots": "/robots.txt",
        "sitemap": "/sitemap.xml",
        "favicon": "/assets/images/favicon.ico",
        "not_found": "/this-page-should-404/",
    }
    results: dict[str, object] = {"base_url": BASE_URL, "paths": {}, "meta": {}}
    ok = True
    for name, path in paths.items():
        status, body = fetch(path)
        expected = 404 if name == "not_found" else 200
        results["paths"][name] = {"path": path, "status": status, "expected": expected}
        if status != expected:
            ok = False
        if name in {"home", "daejeon", "daegu", "math", "random_detail"} and status == 200:
            parser = HeadParser()
            parser.feed(body)
            json_ok = False
            json_types: list[str] = []
            for raw in parser.json_ld:
                data = json.loads(raw)
                nodes = data if isinstance(data, list) else [data]
                json_types.extend(str(node.get("@type")) for node in nodes if isinstance(node, dict))
                json_ok = True
            required_meta = [
                "description",
                "og:title",
                "og:description",
                "og:image",
                "og:url",
                "twitter:title",
                "twitter:description",
                "twitter:image",
            ]
            missing = [key for key in required_meta if not parser.meta.get(key)]
            results["meta"][name] = {
                "title": bool(parser.title),
                "description": bool(parser.meta.get("description")),
                "canonical": parser.links.get("canonical", ""),
                "json_ld": json_ok,
                "json_ld_types": json_types,
                "missing_meta": missing,
            }
            if not parser.title or missing or not json_ok:
                ok = False
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
