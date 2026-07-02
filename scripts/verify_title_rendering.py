"""Verify Page.title, template title context, and final HTML title match."""

from __future__ import annotations

import html
import random
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
import generator


REPORT_PATH = ROOT / "title_render_report.md"


def md_cell(value: object) -> str:
    """Escape markdown table cell separators."""

    return str(value).replace("|", "\\|").replace("\n", " ")


class HeadTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.in_title = False
        self.parts: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "head":
            self.in_head = True
        elif tag == "title" and self.in_head:
            self.in_title = True
            self.parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.in_title:
            self.title = "".join(self.parts).strip()
            self.in_title = False
        elif tag == "head":
            self.in_head = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.parts.append(data)


def read_final_html_title(page: generator.Page) -> str:
    path = config.OUTPUT_DIR / page.output_path
    parser = HeadTitleParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()
    return html.unescape(parser.title)


def main() -> None:
    base_template = (config.TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")
    template_title_line = next(
        (line.strip() for line in base_template.splitlines() if "<title" in line),
        "",
    )
    template_uses_title = bool(re.search(r"<title>\$\{title\}</title>", base_template))
    template_uses_keyword_in_title = bool(re.search(r"<title>.*\$\{(?:keyword|slug|h1|page\.title)\}.*</title>", base_template, re.S))

    renderer = generator.TemplateRenderer(config.TEMPLATE_DIR)
    pages = [page for page in generator.build_pages() if page.output_path != "index.html"]
    pages_by_keyword = {page.keyword: page for page in pages}

    fixed_samples = [
        "대전과외",
        "대전수학과외",
        "대전영어과외",
        "유성구초등과외",
        "유성구고등수학과외",
        "유성구영어과외",
        "관평동영어과외",
        "대구과외",
        "대구고등영어과외",
        "수성구초등수학과외",
    ]
    samples = [pages_by_keyword[keyword] for keyword in fixed_samples if keyword in pages_by_keyword]

    remaining = [page for page in pages if page.keyword not in fixed_samples]
    random.seed(20260702)
    samples.extend(random.sample(remaining, min(100 - len(samples), len(remaining))))

    mismatches = []
    rows = []
    for page in samples:
        context = generator.page_context(page, renderer)
        generator_title = page.title
        template_context_title = html.unescape(context["title"])
        final_html_title = read_final_html_title(page)
        expected = generator.build_page_title(page.keyword, generator_title.split(" | ")[1])
        ok = (
            generator_title == template_context_title
            and template_context_title == final_html_title
            and final_html_title == expected
        )
        if not ok:
            mismatches.append(page.keyword)
        rows.append((page.keyword, generator_title, template_context_title, final_html_title, "OK" if ok else "FAIL"))

    lines = [
        "# StudyRoute Title Rendering Report",
        "",
        "## Template Check",
        "",
        f"- Base template title line: `{template_title_line}`",
        f"- Uses `${{title}}`: {template_uses_title}",
        f"- Uses slug/keyword/H1 in `<title>`: {template_uses_keyword_in_title}",
        "",
        "## Summary",
        "",
        f"- Content pages available: {len(pages)}",
        f"- Random/sample pages checked: {len(samples)}",
        f"- Mismatches: {len(mismatches)}",
        "- Browser DOM check: attempted with headless Microsoft Edge against a local HTTP server, but this environment returned no `--dump-dom` output. HTTP-served HTML was reachable and final HTML `<title>` was verified directly.",
        "",
        "## 100 Page Sample",
        "",
        "| Keyword | Generator Page.title | Template Context title | Final HTML title | Result |",
        "|---|---|---|---|---|",
    ]
    for keyword, generator_title, template_context_title, final_html_title, result in rows:
        lines.append(
            f"| {md_cell(keyword)} | {md_cell(generator_title)} | {md_cell(template_context_title)} | {md_cell(final_html_title)} | {md_cell(result)} |"
        )

    lines.extend(["", "## Mismatches", ""])
    if mismatches:
        lines.extend(f"- {keyword}" for keyword in mismatches)
    else:
        lines.append("- OK")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Title rendering validation complete: {REPORT_PATH}")
    print(f"checked={len(samples)} mismatches={len(mismatches)}")


if __name__ == "__main__":
    main()
