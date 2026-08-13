"""Build the Excel-driven StudyRoute expansion without touching production output."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET

import candidate_generator
import config
import generator


ROOT = config.ROOT_DIR
DEFAULT_WORKBOOK = config.DATA_DIR / "StudyRoute_페이지확장용_구조수정완료.xlsx"
FINAL_WORKBOOK = config.DATA_DIR / "StudyRoute_페이지확장용_최종.xlsx"
DEFAULT_OUTPUT = ROOT / "candidate_excel_expansion"
REFERENCE_SHEETS = {"전체_265", "지역_151", "학교_114", "ㅣ"}
REGION_SOURCE_TYPES = (
    "내신과외",
    "내신수학과외",
    "내신영어과외",
    "중1과외",
    "중1수학과외",
    "중1영어과외",
    "중2과외",
    "중2수학과외",
    "중2영어과외",
    "중3과외",
    "중3수학과외",
    "중3영어과외",
    "고1수학과외",
    "고1영어과외",
    "고2수학과외",
    "고2영어과외",
    "고3수학과외",
    "고3영어과외",
)
SCHOOL_SOURCE_TYPES = (
    "고1과외",
    "고2과외",
    "고3과외",
    "(학교)고1수학과외",
    "(학교)고1영어과외",
    "(학교)고2수학과외",
    "(학교)고2영어과외",
    "(학교)고3수학과외",
    "(학교)고3영어과외",
    "(학교)내신과외",
)


@dataclass(frozen=True)
class SourceRow:
    sheet: str
    row: int
    a: str
    b: str
    c: str


@dataclass
class PlanItem:
    source_sheet: str
    source_row: int
    entity_type: str
    entity_name: str
    normalized_sheet_type: str
    title: str
    content_exists: bool
    slug: str
    url: str
    parent_slug: str
    child_slugs: list[str] = field(default_factory=list)
    existing_child_links: list[tuple[str, str]] = field(default_factory=list)
    existing_url_collision: bool = False
    included: bool = True
    exclusion_reason: str = ""
    generated_hub: bool = False
    body_html: str = field(default="", repr=False)

    def public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("body_html", None)
        return value


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("(학교)", "")).strip()


def public_clean(value: str) -> str:
    return value.replace("(학교)", "").strip()


def normalized_type(sheet_name: str) -> str:
    return compact(sheet_name)


def flat_url(slug: str) -> str:
    return f"https://studyroute.co.kr/{quote(slug)}/"


def root_url(slug: str) -> str:
    return f"/{quote(slug)}/"


def read_workbook(path: Path) -> dict[str, list[SourceRow]]:
    sheets: dict[str, list[SourceRow]] = {}
    with zipfile.ZipFile(path) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        shared = generator.read_shared_strings(archive)
        for sheet in workbook_xml.find("a:sheets", generator.SPREADSHEET_NS):
            name = sheet.attrib["name"].strip()
            target = rel_map[sheet.attrib[generator.RELATIONSHIP_ID]].lstrip("/")
            sheet_path = "xl/" + target if not target.startswith("xl/") else target
            root = ET.fromstring(archive.read(sheet_path))
            rows: list[SourceRow] = []
            for row in root.findall(".//a:sheetData/a:row", generator.SPREADSHEET_NS):
                row_number = int(row.attrib.get("r", "0") or 0)
                if row_number <= 1:
                    continue
                values: dict[str, str] = {}
                for cell in row.findall("a:c", generator.SPREADSHEET_NS):
                    column = re.sub(r"\d+", "", cell.attrib.get("r", ""))
                    if column in {"A", "B", "C"}:
                        values[column] = generator.read_cell_value(cell, shared)
                if any(values.get(column, "").strip() for column in ("A", "B", "C")):
                    rows.append(
                        SourceRow(
                            sheet=name,
                            row=row_number,
                            a=values.get("A", "").strip(),
                            b=values.get("B", "").strip(),
                            c=values.get("C", ""),
                        )
                    )
            sheets[name] = rows
    return sheets


def reference_names(rows: list[SourceRow]) -> list[str]:
    return [public_clean(row.a) for row in rows if row.a.strip()]


def resolve_entity(raw_value: str, page_type: str, names: set[str]) -> str:
    raw = compact(raw_value)
    page_type = compact(page_type)
    by_compact = {compact(name): name for name in names}
    if raw in by_compact:
        return by_compact[raw]
    if raw.endswith(page_type):
        candidate = raw[: -len(page_type)]
        if candidate in by_compact:
            return by_compact[candidate]
    return ""


def resolve_row_entity(row: SourceRow, page_type: str, names: set[str]) -> str:
    """Resolve from A first, then validate against the B-title prefix.

    Some legacy sheets intentionally retain an incorrect A-column suffix, so
    the authoritative reference list and the cleaned B title are the fallback.
    """

    entity = resolve_entity(row.a, page_type, names)
    if entity:
        return entity
    compact_title = compact(row.b)
    compact_type = compact(page_type)
    for name in sorted(names, key=lambda value: len(compact(value)), reverse=True):
        if compact_title.startswith(compact(name) + compact_type):
            return name
    return ""


def plain_text(fragment: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def meta_description(title: str, body: str) -> str:
    text = plain_text(body)
    if not text:
        return f"{title} 관련 학습 페이지를 StudyRoute에서 확인하세요."
    excerpt = text[:155].rstrip()
    return excerpt + ("…" if len(text) > len(excerpt) else "")


def clean_body(body: str) -> str:
    body = public_clean(body)
    fragment = generator.extract_body_fragment(body)
    fragment = re.sub(r"(?is)<h1\b[^>]*>.*?</h1>", "", fragment)
    return generator.normalize_html_fragment(fragment).strip()


def existing_urls_from_sitemap(path: Path) -> set[str]:
    content = path.read_text(encoding="utf-8")
    return {html.unescape(value) for value in re.findall(r"<loc>(.*?)</loc>", content)}


def source_parent(entity_type: str, entity: str, page_type: str) -> str:
    if entity_type == "region":
        if page_type in {"내신수학과외", "내신영어과외"}:
            return compact(entity + "내신과외")
        match = re.fullmatch(r"(중[123]|고[123])(수학|영어)과외", page_type)
        if match:
            return compact(entity + match.group(1) + "과외")
        return compact(entity + "과외")
    if page_type == "내신과외":
        return compact(entity)
    match = re.fullmatch(r"(고[123])(수학|영어)과외", page_type)
    if match:
        return compact(entity + match.group(1) + "과외")
    return compact(entity)


def make_source_item(
    row: SourceRow,
    entity_type: str,
    entity: str,
    sheet_type: str,
    existing_urls: set[str],
) -> PlanItem:
    page_type = normalized_type(sheet_type)
    slug = compact(entity + page_type)
    title = public_clean(row.b)
    body = clean_body(row.c) if row.c.strip() else ""
    included = bool(body) and bool(title)
    reason = "" if included else ("empty_body" if not body else "empty_title")
    url = flat_url(slug)
    return PlanItem(
        source_sheet=row.sheet,
        source_row=row.row,
        entity_type=entity_type,
        entity_name=entity,
        normalized_sheet_type=page_type,
        title=title,
        content_exists=bool(body),
        slug=slug,
        url=url,
        parent_slug=source_parent(entity_type, entity, page_type),
        existing_url_collision=url in existing_urls,
        included=included,
        exclusion_reason=reason,
        body_html=body,
    )


def hub_body(title: str, child_items: list[PlanItem]) -> str:
    sections = [
        f"<p>{generator.html_attr(title)} 페이지는 아래 수학과외와 영어과외 자료를 연결하는 학습 안내 허브입니다.</p>",
        "<ul>",
    ]
    for child in child_items:
        summary = plain_text(child.body_html)[:180].rstrip()
        sections.append(
            f'<li><a href="{root_url(child.slug)}">{generator.html_attr(child.title)}</a>'
            + (f" — {generator.html_attr(summary)}" if summary else "")
            + "</li>"
        )
    sections.append("</ul>")
    return "\n".join(sections)


def build_plan(
    sheets: dict[str, list[SourceRow]], existing_urls: set[str]
) -> tuple[list[PlanItem], dict[str, object]]:
    regions = reference_names(sheets.get("지역_151", []))
    schools = reference_names(sheets.get("학교_114", []))
    region_set = set(regions)
    school_set = set(schools)
    items: list[PlanItem] = []
    classification_errors: list[dict[str, object]] = []

    for sheet_type in REGION_SOURCE_TYPES:
        for row in sheets.get(sheet_type, []):
            if not row.a:
                continue
            entity = resolve_row_entity(row, normalized_type(sheet_type), region_set)
            if not entity:
                # Mixed legacy rows that resolve to a known school are intentionally ignored.
                school_entity = resolve_row_entity(row, normalized_type(sheet_type), school_set)
                if not school_entity and sheet_type not in {"내신과외", "내신수학과외", "내신영어과외"}:
                    classification_errors.append({"sheet": sheet_type, "row": row.row, "value": row.a})
                continue
            items.append(make_source_item(row, "region", entity, sheet_type, existing_urls))

    for sheet_type in SCHOOL_SOURCE_TYPES:
        for row in sheets.get(sheet_type, []):
            if not row.a:
                continue
            entity = resolve_row_entity(row, normalized_type(sheet_type), school_set)
            if not entity:
                classification_errors.append({"sheet": sheet_type, "row": row.row, "value": row.a})
                continue
            items.append(make_source_item(row, "school", entity, sheet_type, existing_urls))

    included_by_slug = {item.slug: item for item in items if item.included}

    # Region high-school parent hubs are based only on their two real child pages.
    for region in regions:
        for grade in ("고1", "고2", "고3"):
            child_slugs = [compact(region + grade + subject + "과외") for subject in ("수학", "영어")]
            children = [included_by_slug[slug] for slug in child_slugs if slug in included_by_slug]
            if not children:
                continue
            slug = compact(region + grade + "과외")
            title = f"{region} {grade}과외 학습 안내"
            body = hub_body(title, children)
            hub = PlanItem(
                source_sheet="[generated-region-hub]",
                source_row=0,
                entity_type="region",
                entity_name=region,
                normalized_sheet_type=f"{grade}과외",
                title=title,
                content_exists=True,
                slug=slug,
                url=flat_url(slug),
                parent_slug=compact(region + "과외"),
                child_slugs=child_slugs,
                existing_url_collision=flat_url(slug) in existing_urls,
                included=True,
                generated_hub=True,
                body_html=body,
            )
            items.append(hub)
            included_by_slug[slug] = hub

    # Individual school hubs connect existing nested subject pages and all new school pages.
    for school in schools:
        school_children = [
            item for item in items if item.included and item.entity_type == "school" and item.entity_name == school
        ]
        if not school_children:
            continue
        slug = compact(school)
        existing_child_links = []
        for subject in candidate_generator.SUBJECTS:
            subject_slug = compact(subject)
            url = f"{config.BASE_URL}/{quote(slug)}/{quote(subject_slug)}/"
            if url in existing_urls:
                existing_child_links.append(
                    (f"{school} {subject_slug}", f"/{quote(slug)}/{quote(subject_slug)}/")
                )
        title = f"{school} 학습 정보 안내"
        body = hub_body(title, school_children)
        hub = PlanItem(
            source_sheet="[generated-school-hub]",
            source_row=0,
            entity_type="school",
            entity_name=school,
            normalized_sheet_type="학교허브",
            title=title,
            content_exists=True,
            slug=slug,
            url=flat_url(slug),
            parent_slug=candidate_generator.SCHOOL_HUB_SLUG,
            existing_child_links=existing_child_links,
            existing_url_collision=flat_url(slug) in existing_urls,
            included=True,
            generated_hub=True,
            body_html=body,
        )
        items.append(hub)
        included_by_slug[slug] = hub

    # Children are derived from validated parent assignments, not sheet order.
    children_for_parent: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if item.included:
            children_for_parent[item.parent_slug].append(item.slug)
    for item in items:
        if item.included:
            item.child_slugs = sorted(
                set(children_for_parent.get(item.slug, item.child_slugs)),
                key=lambda slug: (slug.endswith("중2수학과외"), slug),
            )

    slug_counts = Counter(item.slug for item in items if item.included)
    duplicate_slugs = sorted(slug for slug, count in slug_counts.items() if count > 1)
    collisions = sorted(item.slug for item in items if item.included and item.existing_url_collision)
    included_slugs = {item.slug for item in items if item.included}
    existing_path_slugs = {
        compact(unquote(urlsplit(url).path).strip("/"))
        for url in existing_urls
        if "/" not in unquote(urlsplit(url).path).strip("/")
    }
    parent_errors = sorted(
        item.slug
        for item in items
        if item.included and item.parent_slug not in included_slugs and item.parent_slug not in existing_path_slugs
    )
    long_title_slug_errors = sorted(
        item.slug
        for item in items
        if item.included and item.slug != compact(item.entity_name + item.normalized_sheet_type)
        and not item.generated_hub
    )
    school_marker_in_public_fields = sum(
        "(학교)" in (item.slug + item.url + item.title + item.body_html) for item in items if item.included
    )
    summary = {
        "sheet_count": len(sheets),
        "region_reference_count": len(regions),
        "school_reference_count": len(schools),
        "planned_count": len(items),
        "included_count": sum(item.included for item in items),
        "excluded_count": sum(not item.included for item in items),
        "empty_body_count": sum(item.exclusion_reason == "empty_body" for item in items),
        "duplicate_slugs": duplicate_slugs,
        "existing_url_collisions": collisions,
        "classification_errors": classification_errors,
        "parent_errors": parent_errors,
        "long_title_slug_errors": long_title_slug_errors,
        "school_marker_in_public_fields": school_marker_in_public_fields,
        "included_by_entity_type": dict(Counter(item.entity_type for item in items if item.included)),
        "included_by_sheet": dict(Counter(item.source_sheet for item in items if item.included)),
        "excluded_by_sheet": dict(Counter(item.source_sheet for item in items if not item.included)),
    }
    return items, summary


def write_plan(output: Path, workbook: Path, items: list[PlanItem], summary: dict[str, object]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "workbook": str(workbook.resolve()),
        "summary": summary,
        "items": [item.public_dict() for item in items],
    }
    (output / "url_plan.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )


def validate_plan(summary: dict[str, object]) -> None:
    blockers = {
        "duplicate_slugs": summary["duplicate_slugs"],
        "existing_url_collisions": summary["existing_url_collisions"],
        "classification_errors": summary["classification_errors"],
        "parent_errors": summary["parent_errors"],
        "long_title_slug_errors": summary["long_title_slug_errors"],
        "school_marker_in_public_fields": summary["school_marker_in_public_fields"],
    }
    if any(blockers.values()):
        raise ValueError("URL plan validation failed: " + json.dumps(blockers, ensure_ascii=False))


def build_existing_pages() -> tuple[list[generator.Page], list[candidate_generator.School]]:
    schools = candidate_generator.load_schools()
    region_pages = generator.build_pages()
    region_slugs = {page.keyword for page in region_pages if page.keyword}
    pages = candidate_generator.add_school_links_to_region_pages(region_pages, schools)
    pages.append(candidate_generator.build_school_hub(schools))
    pages.extend(candidate_generator.build_school_pages(schools, region_slugs))
    return pages, schools


def hierarchy_breadcrumbs(item: PlanItem, items_by_slug: dict[str, PlanItem]) -> tuple[generator.BreadcrumbItem, ...]:
    chain: list[str] = []
    cursor = item.parent_slug
    seen: set[str] = set()
    while cursor and cursor not in seen:
        seen.add(cursor)
        chain.append(cursor)
        parent_item = items_by_slug.get(cursor)
        if parent_item:
            cursor = parent_item.parent_slug
        else:
            break
    chain.reverse()
    crumbs = [generator.BreadcrumbItem("홈", "/")]
    crumbs.extend(generator.BreadcrumbItem(slug, root_url(slug)) for slug in chain)
    crumbs.append(generator.BreadcrumbItem(item.title, root_url(item.slug)))
    return tuple(crumbs)


def new_page(item: PlanItem, items_by_slug: dict[str, PlanItem]) -> generator.Page:
    parent_links = []
    if item.parent_slug:
        parent_links.append(generator.LinkItem(item.parent_slug, root_url(item.parent_slug)))
    ancestor = items_by_slug.get(item.parent_slug)
    if ancestor and ancestor.parent_slug:
        parent_links.append(generator.LinkItem(ancestor.parent_slug, root_url(ancestor.parent_slug)))
    child_links = [
        generator.LinkItem(items_by_slug[slug].title, root_url(slug))
        for slug in item.child_slugs
        if slug in items_by_slug
    ]
    child_links.extend(generator.LinkItem(title, url) for title, url in item.existing_child_links)
    child_links = tuple({link.url: link for link in child_links}.values())
    sections: list[generator.LinkSection] = []
    if parent_links:
        sections.append(generator.LinkSection("상위 학습 경로", tuple(parent_links)))
    if child_links:
        sections.append(generator.LinkSection("세부 학습 페이지", child_links))
    output_path = generator.slug_to_output_path(item.slug)
    return generator.Page(
        output_path=output_path,
        template="pages/content.html",
        title=item.title,
        description=meta_description(item.title, item.body_html),
        keyword=item.slug,
        body_html=item.body_html,
        breadcrumbs=hierarchy_breadcrumbs(item, items_by_slug),
        link_sections=tuple(sections),
        body_class=f"content-page expansion-page {item.entity_type}-expansion-page",
        canonical_path=generator.slug_to_canonical_path(item.slug),
        extra_context={
            "page_heading": f"<h1>{generator.html_attr(item.title)}</h1>",
            "body_image_html": generator.render_body_image(item.slug, generator.output_relative_prefix(output_path)),
        },
    )


def add_expansion_links_to_existing(
    pages: list[generator.Page], items: list[PlanItem], schools: list[candidate_generator.School]
) -> list[generator.Page]:
    items_by_slug = {item.slug: item for item in items if item.included}
    region_top_links: dict[str, tuple[generator.LinkItem, ...]] = {}
    for entity in sorted({item.entity_name for item in items if item.included and item.entity_type == "region"}):
        parent = compact(entity + "과외")
        child_slugs = sorted(item.slug for item in items if item.included and item.parent_slug == parent)
        region_top_links[parent] = tuple(
            generator.LinkItem(items_by_slug[slug].title, root_url(slug)) for slug in child_slugs
        )

    school_names = {school.slug: school.display_name for school in schools}
    updated: list[generator.Page] = []
    for page in pages:
        if page.keyword in region_top_links and region_top_links[page.keyword]:
            page = replace(
                page,
                link_sections=page.link_sections
                + (generator.LinkSection("학년·내신 세부 안내", region_top_links[page.keyword]),),
            )
        parts = Path(page.output_path).parts
        if (
            len(parts) == 3
            and parts[0] in school_names
            and parts[0] in items_by_slug
            and parts[-1] == "index.html"
        ):
            school_slug = parts[0]
            hub_link = generator.LinkSection(
                "학교 학습 허브",
                (generator.LinkItem(f"{school_names[school_slug]} 학습 정보", root_url(school_slug)),),
            )
            crumbs = list(page.breadcrumbs)
            if len(crumbs) >= 2:
                crumbs.insert(-1, generator.BreadcrumbItem(school_names[school_slug], root_url(school_slug)))
            page = replace(page, breadcrumbs=tuple(crumbs), link_sections=page.link_sections + (hub_link,))
        if page.keyword == candidate_generator.SCHOOL_HUB_SLUG:
            context = dict(page.extra_context)
            for key in ("school_alphabetical_groups", "school_region_groups"):
                value = context.get(key, "")
                for school in schools:
                    if school.slug not in items_by_slug:
                        continue
                    value = value.replace(
                        f"<h3>{generator.html_attr(school.display_name)}</h3>",
                        f'<h3><a href="{root_url(school.slug)}">{generator.html_attr(school.display_name)}</a></h3>',
                    )
                context[key] = value
            page = replace(page, extra_context=context)
        updated.append(page)
    return updated


def safe_clean_candidate(output: Path) -> None:
    resolved = output.resolve()
    expected = {
        (ROOT / "candidate_excel_expansion").resolve(),
        (ROOT / "candidate_clean_production_final").resolve(),
        (ROOT / "candidate_new_sitemap_verify").resolve(),
        (ROOT / "output").resolve(),
    }
    if resolved not in expected:
        raise ValueError(f"Refusing to clean unexpected output path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def write_new_pages_sitemap(pages: list[generator.Page]) -> None:
    """Write a standalone sitemap containing only Excel expansion pages."""

    today = date.today().isoformat()
    url_nodes = []
    for page in pages:
        loc = generator.xml_escape(generator.absolute_url(page.url_path))
        url_nodes.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            "    <changefreq>weekly</changefreq>\n"
            "    <priority>0.8</priority>\n"
            "  </url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(url_nodes)
        + "\n</urlset>\n"
    )
    (config.OUTPUT_DIR / "sitemap-new-pages.xml").write_text(
        sitemap, encoding="utf-8", newline="\n"
    )


def build_candidate(output: Path, workbook: Path, items: list[PlanItem], summary: dict[str, object]) -> None:
    safe_clean_candidate(output)
    config.OUTPUT_DIR = output
    existing_pages, schools = build_existing_pages()
    existing_pages = add_expansion_links_to_existing(existing_pages, items, schools)
    included = [item for item in items if item.included]
    items_by_slug = {item.slug: item for item in included}
    new_pages = [
        new_page(item, items_by_slug)
        for item in sorted(
            included,
            key=lambda x: (
                x.normalized_sheet_type == "중2수학과외",
                x.source_row if x.normalized_sheet_type == "중2수학과외" else x.slug,
            ),
        )
    ]
    pages = existing_pages + new_pages
    output_paths = [page.output_path for page in pages]
    if len(output_paths) != len(set(output_paths)):
        duplicates = sorted(path for path, count in Counter(output_paths).items() if count > 1)
        raise ValueError(f"Duplicate output paths: {duplicates[:20]}")
    renderer = generator.TemplateRenderer(config.TEMPLATE_DIR)
    for page in pages:
        generator.render_page(page, renderer)
    generator.copy_assets()
    generator.write_search_index(pages)
    generator.write_robots()
    generator.write_sitemap(pages)
    write_new_pages_sitemap(new_pages)
    write_plan(output, workbook, items, summary)
    build_summary = {
        "existing_pages": len(existing_pages),
        "new_pages": len(included),
        "total_pages": len(pages),
        "excluded_pages": sum(not item.included for item in items),
    }
    (output / "build_summary.json").write_text(
        json.dumps(build_summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps(build_summary, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    workbook = args.workbook.resolve()
    output = args.output.resolve()
    if not workbook.is_file():
        raise FileNotFoundError(workbook)
    existing_urls = existing_urls_from_sitemap(ROOT / "output" / "sitemap.xml")
    sheets = read_workbook(workbook)
    items, summary = build_plan(sheets, existing_urls)
    write_plan(output, workbook, items, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    validate_plan(summary)
    if not args.plan_only:
        build_candidate(output, workbook, items, summary)


if __name__ == "__main__":
    main()
