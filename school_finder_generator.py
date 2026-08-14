"""Build an additive school-finder preview without changing production output."""

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

import candidate_generator
import config
import generator

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate_child_backlink_fix"
OUTPUT = ROOT / "candidate_school_finder_preview"
ACTIVE_SOURCE = SOURCE
ACTIVE_OUTPUT = OUTPUT
SITEMAP_NAME = "sitemap-school-finder.xml"


@dataclass(frozen=True)
class Location:
    school: candidate_generator.School
    district: str
    neighborhood: str
    entry_url: str
    entry_kind: str


def url(*parts: str) -> str:
    suffix = "/".join(quote(part) for part in parts)
    return f"/schools/{suffix}/" if suffix else "/schools/"


def existing_hubs() -> dict[str, str]:
    items = json.loads((ACTIVE_SOURCE / "url_plan.json").read_text(encoding="utf-8"))["items"]
    return {
        item["slug"]: item["url"]
        for item in items
        if item.get("included") and item.get("source_sheet") == "[generated-school-hub]"
    }


def locations() -> tuple[list[Location], list[dict[str, str]]]:
    sitemap_urls = set(re.findall(r"<loc>(.*?)</loc>", (ACTIVE_SOURCE / "sitemap.xml").read_text(encoding="utf-8")))
    hubs = existing_hubs()
    result: list[Location] = []
    failures: list[dict[str, str]] = []
    for school in candidate_generator.load_schools():
        district = school.district.removeprefix(school.city)
        neighborhood = school.mapped_region if school.mapped_region != school.district else ""
        if not neighborhood:
            body = school.body_by_subject[candidate_generator.SUBJECTS[0]]
            matches = re.findall(r"\(([^()]{1,20}(?:동|읍|면|리))\)", body)
            neighborhood = matches[0].strip() if matches else ""
        fallback = f"{config.BASE_URL}/{quote(school.slug)}/{quote(candidate_generator.SUBJECTS[0])}/"
        if hubs.get(school.slug) in sitemap_urls:
            entry_url, entry_kind = hubs[school.slug], "school_hub"
        elif fallback in sitemap_urls:
            entry_url, entry_kind = fallback, "existing_subject_fallback"
        else:
            entry_url, entry_kind = "", ""
        missing = [name for name, value in (
            ("district", district), ("neighborhood", neighborhood), ("existing_entry_url", entry_url)
        ) if not value]
        if missing:
            failures.append({"school": school.display_name, "missing": ",".join(missing)})
        else:
            result.append(Location(school, district, neighborhood, entry_url, entry_kind))
    return result, failures


def cards(links: list[tuple[str, str, str]]) -> str:
    articles = "\n".join(
        '<article class="school-card">'
        f'<h3><a href="{generator.html_attr(href)}">{generator.html_attr(label)}</a></h3>'
        f'<p>{generator.html_attr(note)}</p></article>'
        for label, href, note in links
    )
    return f'<div class="school-grid">\n{articles}\n</div>'


def make_page(
    parts: tuple[str, ...], title: str, description: str, heading: str,
    intro: str, links: list[tuple[str, str, str]],
) -> generator.Page:
    crumbs = [generator.BreadcrumbItem("홈", "/"), generator.BreadcrumbItem("학교 찾기", url())]
    accumulated: list[str] = []
    for part in parts:
        accumulated.append(part)
        crumbs.append(generator.BreadcrumbItem(part, url(*accumulated)))
    return generator.Page(
        output_path="/".join(("schools", *parts, "index.html")),
        template="pages/content.html",
        title=title,
        description=description,
        keyword=heading,
        body_html=f"<p>{generator.html_attr(intro)}</p>{cards(links)}",
        breadcrumbs=tuple(crumbs),
        body_class="content-page school-finder-page",
        canonical_path=url(*parts),
        extra_context={"page_heading": f"<h1>{generator.html_attr(heading)}</h1>", "body_image_html": ""},
    )


def build_pages(items: list[Location]) -> list[generator.Page]:
    tree: dict[str, dict[str, dict[str, list[Location]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for item in items:
        tree[item.school.city][item.district][item.neighborhood].append(item)
    cities = ("대전", "대구")
    pages = [make_page(
        (), f"대전·대구 고등학교 찾기 | {config.PROJECT_NAME}",
        "대전과 대구의 고등학교를 구·군과 동 순서로 찾아 기존 학교 학습 페이지로 이동하세요.",
        "학교 찾기", "도시를 선택한 뒤 구·군과 동을 차례로 확인하세요.",
        [(f"{city} 고등학교", url(city), f"{sum(len(s) for d in tree[city].values() for s in d.values())}개 학교")
         for city in cities],
    )]
    for city in cities:
        pages.append(make_page(
            (city,), f"{city} 고등학교 찾기 | {config.PROJECT_NAME}",
            f"{city} 고등학교를 구·군별로 찾아 기존 학교 학습 페이지를 확인하세요.",
            f"{city} 고등학교", "실제 학교 데이터에 연결된 구·군만 표시합니다.",
            [(district, url(city, district), f"{sum(len(v) for v in neighborhoods.values())}개 학교")
             for district, neighborhoods in sorted(tree[city].items())],
        ))
        for district, neighborhoods in sorted(tree[city].items()):
            pages.append(make_page(
                (city, district), f"{city} {district} 고등학교 찾기 | {config.PROJECT_NAME}",
                f"{city} {district}의 고등학교를 동별로 찾아 기존 학교 학습 페이지를 확인하세요.",
                f"{city} {district} 고등학교", "학교가 실제로 연결된 읍·면·동만 표시합니다.",
                [(neighborhood, url(city, district, neighborhood), f"{len(schools)}개 학교")
                 for neighborhood, schools in sorted(neighborhoods.items())],
            ))
            for neighborhood, schools in sorted(neighborhoods.items()):
                links = [
                    (item.school.display_name, item.entry_url.removeprefix(config.BASE_URL),
                     "기존 학교 대표 페이지" if item.entry_kind == "school_hub" else "기존 학교 수학과외 페이지")
                    for item in sorted(schools, key=lambda value: value.school.display_name)
                ]
                pages.append(make_page(
                    (city, district, neighborhood),
                    f"{city} {district} {neighborhood} 고등학교 | {config.PROJECT_NAME}",
                    f"{city} {district} {neighborhood}에 연결된 고등학교와 기존 학교 학습 페이지를 확인하세요.",
                    f"{neighborhood} 고등학교",
                    "학교명을 선택하면 새 콘텐츠가 아닌 기존 StudyRoute 학교 학습 페이지로 이동합니다.",
                    links,
                ))
    return pages


def inject_home(items: list[Location]) -> None:
    target = ACTIVE_OUTPUT / "index.html"
    html = target.read_text(encoding="utf-8")
    if "school-finder-home-section" in html:
        return
    marker = '      <section class="home-section home-region-section"'
    if marker not in html:
        raise ValueError("기존 지역 찾기 섹션 위치를 찾을 수 없습니다.")
    descriptions = {
        "대전": "39개 고등학교를 구·동별로 찾아보세요.",
        "대구": "76개 고등학교를 구·군·동별로 찾아보세요.",
    }
    articles = "\n".join(
        '            <article class="school-finder-card">'
        '<span class="school-finder-card-icon" aria-hidden="true">'
        '<svg viewBox="0 0 24 24"><path d="M3 10.5 12 5l9 5.5-9 5.5-9-5.5Z"/>'
        '<path d="M6.5 13v4.5c2.8 2 8.2 2 11 0V13M21 11v6"/></svg></span>'
        '<div class="school-finder-card-content">'
        f'<h3 class="school-finder-card-title">{city} 고등학교</h3>'
        f'<p class="school-finder-card-description">{descriptions[city]}</p>'
        f'<a class="school-finder-card-link" href="{url(city)}">{city} 고등학교 찾기'
        '<span aria-hidden="true">→</span></a></div></article>'
        for city in ("대전", "대구")
    )
    section = (
        '      <section class="home-section school-finder-home-section" aria-labelledby="school-finder-title">\n'
        '        <div class="container"><div class="center-heading region-heading">\n'
        '          <span class="heading-icon" aria-hidden="true">🏫</span>\n'
        '          <h2 id="school-finder-title">학교 찾기</h2></div>\n'
        f'          <div class="school-finder-grid">\n{articles}\n          </div>\n'
        '        </div>\n      </section>\n\n'
    )
    target.write_text(html.replace(marker, section + marker, 1), encoding="utf-8", newline="\n")


def write_incremental_sitemap(pages: list[generator.Page]) -> None:
    today = date.today().isoformat()
    nodes = []
    for page in pages:
        loc = generator.xml_escape(config.BASE_URL + page.canonical_path)
        nodes.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            "    <changefreq>weekly</changefreq>\n"
            "    <priority>0.7</priority>\n"
            "  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(nodes)
        + "\n</urlset>\n"
    )
    (ACTIVE_OUTPUT / SITEMAP_NAME).write_text(xml, encoding="utf-8", newline="\n")


def augment_output(output: Path, *, write_sitemap: bool = True) -> dict[str, object]:
    """Add school finder pages to an already-built production-equivalent output."""
    global ACTIVE_SOURCE, ACTIVE_OUTPUT
    ACTIVE_SOURCE = output.resolve()
    ACTIVE_OUTPUT = output.resolve()
    if not (ACTIVE_SOURCE / "sitemap.xml").is_file() or not (ACTIVE_SOURCE / "url_plan.json").is_file():
        raise ValueError("학교 찾기를 추가할 production-equivalent output이 아닙니다.")
    items, failures = locations()
    if failures:
        raise ValueError(f"학교 위치 매핑 실패: {failures}")
    config.OUTPUT_DIR = ACTIVE_OUTPUT
    renderer = generator.TemplateRenderer(config.TEMPLATE_DIR)
    pages = build_pages(items)
    for item in pages:
        generator.render_page(item, renderer)
    inject_home(items)
    if write_sitemap:
        write_incremental_sitemap(pages)
    return {
        "school_records": len(items),
        "new_hub_pages": len(pages),
        "school_links": len(items),
        "sitemap": SITEMAP_NAME if write_sitemap else None,
    }


def main() -> None:
    if OUTPUT.resolve() != (ROOT / "candidate_school_finder_preview").resolve():
        raise ValueError("지정된 preview 출력 경로만 허용합니다.")
    if not (SOURCE / "sitemap.xml").is_file():
        raise ValueError("원본 candidate가 없습니다.")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(SOURCE, OUTPUT)
    global ACTIVE_SOURCE, ACTIVE_OUTPUT
    ACTIVE_SOURCE, ACTIVE_OUTPUT = SOURCE, OUTPUT
    items, failures = locations()
    summary = augment_output(OUTPUT, write_sitemap=False)
    generator.copy_assets()
    pages = build_pages(items)
    report = {
        "source_pages": len(re.findall(r"<loc>", (SOURCE / "sitemap.xml").read_text(encoding="utf-8"))),
        "school_records": len(candidate_generator.load_schools()),
        "mapped_schools": len(items),
        "mapping_failures": failures,
        "representative_hubs": sum(x.entry_kind == "school_hub" for x in items),
        "subject_fallbacks": [x.school.display_name for x in items if x.entry_kind == "existing_subject_fallback"],
        "new_hub_pages": len(pages),
        "new_urls": [config.BASE_URL + item.canonical_path for item in pages],
        "build": summary,
    }
    (OUTPUT / "school_finder_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "new_urls"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
