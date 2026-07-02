"""Verify StudyRoute home cards and national hub navigation."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


OUTPUT = config.OUTPUT_DIR
REPORT = config.ROOT_DIR / "navigation_report.md"
NATIONAL_HUBS = [
    "수학과외",
    "영어과외",
    "초등과외",
    "중등과외",
    "고등과외",
    "초등수학과외",
    "중등수학과외",
    "고등수학과외",
    "초등영어과외",
    "중등영어과외",
    "고등영어과외",
    "학습전략가이드",
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {key: value or "" for key, value in attrs}
        href = attr_map.get("href")
        if href:
            self.links.append(href)


def page_exists(slug: str) -> bool:
    return (OUTPUT / slug / "index.html").exists()


def local_href_exists(page_file: Path, href: str) -> bool:
    if href.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return True
    path = urlparse(href).path
    resolved = (page_file.parent / unquote(path)).resolve()
    if resolved.is_dir():
        resolved = resolved / "index.html"
    try:
        resolved.relative_to(OUTPUT.resolve())
    except ValueError:
        return False
    return resolved.exists()


def collect_links(page_file: Path) -> list[str]:
    parser = LinkParser()
    parser.feed(page_file.read_text(encoding="utf-8"))
    return parser.links


def main() -> None:
    pages = sorted(OUTPUT.glob("*/index.html"))
    home = OUTPUT / "index.html"
    home_html = home.read_text(encoding="utf-8")
    home_links = collect_links(home)

    missing_hubs = [hub for hub in NATIONAL_HUBS if not page_exists(hub)]
    missing_home_cards = [hub for hub in NATIONAL_HUBS if slug_to_encoded(hub) not in home_html and f'href="{hub}/"' not in home_html]
    broken_links: list[str] = []
    for page_file in [home, *pages]:
        for href in collect_links(page_file):
            if not local_href_exists(page_file, href):
                broken_links.append(f"{page_file.relative_to(OUTPUT)} -> {href}")

    chain_checks = {
        "수학과외 -> 대전수학과외": "대전수학과외" in (OUTPUT / "수학과외" / "index.html").read_text(encoding="utf-8"),
        "대전수학과외 -> 유성구수학과외": "유성구수학과외" in (OUTPUT / "대전수학과외" / "index.html").read_text(encoding="utf-8"),
        "유성구수학과외 -> 관평동수학과외": "관평동수학과외" in (OUTPUT / "유성구수학과외" / "index.html").read_text(encoding="utf-8"),
        "영어과외 -> 대구영어과외": "대구영어과외" in (OUTPUT / "영어과외" / "index.html").read_text(encoding="utf-8"),
        "대구영어과외 -> 달서구영어과외": "달서구영어과외" in (OUTPUT / "대구영어과외" / "index.html").read_text(encoding="utf-8"),
        "학습전략가이드 -> 대전학습전략가이드": "대전학습전략가이드" in (OUTPUT / "학습전략가이드" / "index.html").read_text(encoding="utf-8"),
        "대전학습전략가이드 -> 유성구학습전략가이드": "유성구학습전략가이드" in (OUTPUT / "대전학습전략가이드" / "index.html").read_text(encoding="utf-8"),
    }

    generated_count = len([path for path in pages if path.parent.name != "assets"])
    report = [
        "# StudyRoute Navigation Report",
        "",
        "## 요약",
        "",
        f"- 생성 콘텐츠 페이지 수: {generated_count}",
        f"- 전국 허브 생성: {len(NATIONAL_HUBS) - len(missing_hubs)}/{len(NATIONAL_HUBS)}",
        f"- 홈 카테고리 카드 연결: {len(NATIONAL_HUBS) - len(missing_home_cards)}/{len(NATIONAL_HUBS)}",
        f"- 전체 내부 링크 404: {len(broken_links)}",
        "",
        "## 전국 허브",
        "",
        *[f"- {'통과' if hub not in missing_hubs else '누락'}: /{hub}/" for hub in NATIONAL_HUBS],
        "",
        "## 대표 계층 연결",
        "",
        *[f"- {'통과' if ok else '실패'}: {name}" for name, ok in chain_checks.items()],
        "",
        "## 홈 카드 누락",
        "",
        "없음" if not missing_home_cards else "\n".join(f"- {hub}" for hub in missing_home_cards),
        "",
        "## 깨진 링크",
        "",
        "없음" if not broken_links else "\n".join(f"- {item}" for item in broken_links[:200]),
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    print(f"pages={generated_count} national_hubs={len(NATIONAL_HUBS) - len(missing_hubs)}/{len(NATIONAL_HUBS)} broken_links={len(broken_links)}")


def slug_to_encoded(slug: str) -> str:
    from urllib.parse import quote

    return f'href="{quote(slug)}/"'


if __name__ == "__main__":
    main()
