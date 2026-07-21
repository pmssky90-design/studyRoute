"""Build the school-enabled preview without replacing the production output."""

from __future__ import annotations

import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

import config
import generator


CANDIDATE_OUTPUT = config.ROOT_DIR / "candidate_output"
SCHOOL_WORKBOOK = config.DATA_DIR / "대전_대구_고등학교_영어과외_작성완료.xlsx"
SCHOOL_HUB_SLUG = "고등학교"
SUBJECTS = ("수학과외", "영어과외")
INITIALS = tuple("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")


@dataclass(frozen=True)
class School:
    display_name: str
    official_name: str
    slug: str
    mapped_region: str
    city: str
    district: str
    body_by_subject: dict[str, str]


def read_workbook_table(sheet_name: str) -> list[dict[str, str]]:
    """Read one OOXML worksheet into dictionaries using the standard library."""

    with zipfile.ZipFile(SCHOOL_WORKBOOK) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        shared = generator.read_shared_strings(archive)
        for sheet in workbook_xml.find("a:sheets", generator.SPREADSHEET_NS):
            if sheet.attrib["name"].strip() != sheet_name:
                continue
            target = rel_map[sheet.attrib[generator.RELATIONSHIP_ID]].lstrip("/")
            path = "xl/" + target if not target.startswith("xl/") else target
            root = ET.fromstring(archive.read(path))
            rows: list[dict[str, str]] = []
            headers: dict[str, str] = {}
            for row_index, row in enumerate(root.findall(".//a:sheetData/a:row", generator.SPREADSHEET_NS)):
                values: dict[str, str] = {}
                for cell in row.findall("a:c", generator.SPREADSHEET_NS):
                    column = re.sub(r"\d+", "", cell.attrib.get("r", ""))
                    values[column] = generator.read_cell_value(cell, shared).strip()
                if row_index == 0:
                    headers = {column: value for column, value in values.items() if value}
                    continue
                record = {header: values.get(column, "") for column, header in headers.items()}
                if any(record.values()):
                    rows.append(record)
            return rows
    raise ValueError(f"학교 엑셀에 {sheet_name!r} 시트가 없습니다.")


def clean_school_name(value: str) -> str:
    return re.sub(r"\s*\(학교\)\s*$", "", value).strip()


def region_tree() -> tuple[dict[str, str], dict[str, str]]:
    parent: dict[str, str] = {}
    city_for: dict[str, str] = {}
    for city in config.CITY_NAMES:
        city_for[city] = city
    for parent_region, children in config.REGION_CHILDREN.items():
        for child in children:
            parent[child] = parent_region
    for region in set(parent) | set(config.REGION_CHILDREN):
        cursor = region
        while cursor not in config.CITY_NAMES and cursor in parent:
            cursor = parent[cursor]
        if cursor in config.CITY_NAMES:
            city_for[region] = cursor
    return parent, city_for


def load_schools() -> list[School]:
    mappings = read_workbook_table("학교_매핑")
    sources = read_workbook_table("자료출처")
    subject_rows = {subject: read_workbook_table(subject) for subject in SUBJECTS}
    source_by_name = {row["표기 학교명"]: row for row in sources}
    body_by_subject = {
        subject: {row.get("학교", ""): row.get(f"{subject} 글", "") for row in rows}
        for subject, rows in subject_rows.items()
    }
    parent, city_for = region_tree()
    schools: list[School] = []
    seen_slugs: set[str] = set()
    for row in mappings:
        raw_name = row["학교"]
        display_name = clean_school_name(raw_name)
        slug = re.sub(r"\s+", "", display_name)
        if slug in seen_slugs:
            raise ValueError(f"학교 슬러그 중복: {slug}")
        mapped_region = row["매핑지역"]
        city = city_for.get(mapped_region, "")
        if not city:
            raise ValueError(f"도시를 찾을 수 없는 학교 지역: {display_name} / {mapped_region}")
        cursor = mapped_region
        while parent.get(cursor) and parent[cursor] not in config.CITY_NAMES:
            cursor = parent[cursor]
        district = cursor if parent.get(cursor) in config.CITY_NAMES else ""
        subject_bodies = {
            subject: body_by_subject[subject].get(raw_name, "")
            for subject in SUBJECTS
        }
        missing = [subject for subject, body in subject_bodies.items() if not body]
        if missing:
            raise ValueError(f"학교 본문 누락: {display_name} / {', '.join(missing)}")
        source = source_by_name.get(raw_name, {})
        schools.append(
            School(
                display_name=display_name,
                official_name=source.get("공식 학교명", display_name),
                slug=slug,
                mapped_region=mapped_region,
                city=city,
                district=district,
                body_by_subject=subject_bodies,
            )
        )
        seen_slugs.add(slug)
    return sorted(schools, key=lambda school: school.display_name)


def school_url(school: School, subject: str, prefix: str = "") -> str:
    return f"{prefix}{quote(school.slug)}/{quote(subject)}/"


def region_page_for_school(school: School, region_slugs: set[str]) -> str:
    candidates = [school.mapped_region, school.district, school.city]
    for region in candidates:
        slug = f"{region}{generator.REGION_SUFFIX}"
        if region and slug in region_slugs:
            return slug
    raise ValueError(f"연결 가능한 지역 페이지가 없습니다: {school.display_name}")


def chose_schools_for_region(region: str, schools: list[School]) -> list[School]:
    exact = [school for school in schools if school.mapped_region == region]
    if exact:
        return exact
    district = [school for school in schools if school.district == region]
    if district:
        return district
    city = [school for school in schools if school.city == region]
    return city


def page_region_name(page: generator.Page) -> str:
    names = set(config.CITY_NAMES) | set(config.REGION_CHILDREN)
    for children in config.REGION_CHILDREN.values():
        names.update(children)
    matches = [name for name in names if page.keyword.startswith(name)]
    return max(matches, key=len) if matches else ""


def add_school_links_to_region_pages(
    pages: list[generator.Page], schools: list[School]
) -> list[generator.Page]:
    updated: list[generator.Page] = []
    for page in pages:
        region = page_region_name(page)
        if not region or page.output_path == "index.html":
            updated.append(page)
            continue
        nearby = chose_schools_for_region(region, schools)
        links = tuple(
            generator.LinkItem(
                f"{school.display_name} {subject}",
                school_url(school, subject, "../"),
            )
            for school in nearby
            for subject in SUBJECTS
        )
        if links:
            page = replace(
                page,
                link_sections=page.link_sections + (generator.LinkSection("인근 고등학교", links),),
            )
        updated.append(page)
    return updated


def choseong(value: str) -> str:
    first = value[0]
    if "가" <= first <= "힣":
        return INITIALS[(ord(first) - ord("가")) // 588]
    return "기타"


def render_school_cards(schools: list[School], prefix: str = "../") -> str:
    cards = []
    for school in schools:
        links = " ".join(
            f'<a href="{generator.html_attr(school_url(school, subject, prefix))}">{subject}</a>'
            for subject in SUBJECTS
        )
        cards.append(
            '<article class="school-card">'
            f'<h3>{generator.html_attr(school.display_name)}</h3>'
            f'<p>{generator.html_attr(school.city)} · {generator.html_attr(school.district or school.mapped_region)} · {generator.html_attr(school.mapped_region)}</p>'
            f'<div class="school-card-links">{links}</div>'
            "</article>"
        )
    return "\n".join(cards)


def build_school_hub(schools: list[School]) -> generator.Page:
    by_initial: dict[str, list[School]] = defaultdict(list)
    by_region: dict[str, list[School]] = defaultdict(list)
    for school in schools:
        by_initial[choseong(school.display_name)].append(school)
        by_region[f"{school.city} {school.district or school.mapped_region}"].append(school)
    initial_nav = "\n".join(
        f'            <a href="#initial-{quote(initial)}">{initial}</a>'
        for initial in INITIALS
        if initial in by_initial
    )
    alphabetical = "\n".join(
        f'<section class="school-group" id="initial-{quote(initial)}"><h3>{initial}</h3>'
        f'<div class="school-grid">{render_school_cards(by_initial[initial])}</div></section>'
        for initial in INITIALS
        if initial in by_initial
    )
    regional = "\n".join(
        f'<section class="school-group"><h3>{generator.html_attr(region)}</h3>'
        f'<div class="school-grid">{render_school_cards(by_region[region])}</div></section>'
        for region in sorted(by_region)
    )
    return generator.Page(
        output_path=f"{SCHOOL_HUB_SLUG}/index.html",
        template="pages/school-hub.html",
        title=f"대전 대구 고등학교 찾기 | {config.PROJECT_NAME}",
        description="대전과 대구의 고등학교를 가나다순과 지역별로 찾고 학교별 수학과외·영어과외 정보를 확인하세요.",
        keyword=SCHOOL_HUB_SLUG,
        breadcrumbs=(
            generator.BreadcrumbItem("홈", "../"),
            generator.BreadcrumbItem("고등학교", "./"),
        ),
        body_class="school-hub-page",
        canonical_path=f"/{quote(SCHOOL_HUB_SLUG)}/",
        extra_context={
            "school_initial_navigation": initial_nav,
            "school_alphabetical_groups": alphabetical,
            "school_region_groups": regional,
        },
    )


def build_school_pages(schools: list[School], region_slugs: set[str]) -> list[generator.Page]:
    pages: list[generator.Page] = []
    for school in schools:
        region_slug = region_page_for_school(school, region_slugs)
        for subject in SUBJECTS:
            keyword = f"{school.display_name} {subject}"
            sibling = SUBJECTS[1] if subject == SUBJECTS[0] else SUBJECTS[0]
            links = (
                generator.LinkSection(
                    "이 학교가 있는 지역",
                    (generator.LinkItem(region_slug, f"../../{generator.slug_to_relative_url(region_slug)}"),),
                ),
                generator.LinkSection(
                    "같은 학교의 학습 정보",
                    (generator.LinkItem(f"{school.display_name} {sibling}", f"../{quote(sibling)}/"),),
                ),
            )
            output_path = f"{school.slug}/{subject}/index.html"
            body = generator.normalize_html_fragment(
                generator.extract_body_fragment(school.body_by_subject[subject])
            )
            pages.append(
                generator.Page(
                    output_path=output_path,
                    template="pages/content.html",
                    title=f"{school.display_name} {subject} | 내신 학습 정보 | {config.PROJECT_NAME}",
                    description=f"{school.official_name} {subject} 학습 정보를 확인하세요. {school.mapped_region} 학교 내신 준비와 과목별 학습 계획을 안내합니다.",
                    keyword=keyword,
                    body_html=body,
                    breadcrumbs=(
                        generator.BreadcrumbItem("홈", "../../"),
                        generator.BreadcrumbItem("고등학교", f"../../{quote(SCHOOL_HUB_SLUG)}/"),
                        generator.BreadcrumbItem(keyword, "./"),
                    ),
                    link_sections=links,
                    body_class="content-page school-page",
                    canonical_path=f"/{quote(school.slug)}/{quote(subject)}/",
                    extra_context={
                        "page_heading": f"<h1>{generator.html_attr(keyword)}</h1>",
                        "body_image_html": generator.render_body_image(
                            keyword, generator.output_relative_prefix(output_path)
                        ),
                    },
                )
            )
    return pages


def build_candidate_site() -> None:
    if not SCHOOL_WORKBOOK.exists():
        raise FileNotFoundError(f"학교 엑셀을 찾을 수 없습니다: {SCHOOL_WORKBOOK}")
    config.OUTPUT_DIR = CANDIDATE_OUTPUT
    generator.clean_output()
    renderer = generator.TemplateRenderer(config.TEMPLATE_DIR)
    schools = load_schools()
    region_pages = generator.build_pages()
    region_slugs = {page.keyword for page in region_pages if page.keyword}
    pages = add_school_links_to_region_pages(region_pages, schools)
    pages.append(build_school_hub(schools))
    pages.extend(build_school_pages(schools, region_slugs))
    for page in pages:
        generator.render_page(page, renderer)
    generator.copy_assets()
    generator.write_search_index(pages)
    generator.write_robots()
    generator.write_sitemap(pages)
    print(
        f"Candidate build complete: {CANDIDATE_OUTPUT} | "
        f"schools={len(schools)} school_pages={len(schools) * len(SUBJECTS)} total_pages={len(pages)}"
    )


if __name__ == "__main__":
    build_candidate_site()
