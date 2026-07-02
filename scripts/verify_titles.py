"""Verify generated titles against the current workbook sheet names."""

from __future__ import annotations

import html
import random
import re
import sys
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config


SPREADSHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELATIONSHIP_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
REPORT_PATH = ROOT / "title_validation_report.md"


@dataclass(frozen=True)
class ExpectedTitle:
    keyword: str
    sheet_name: str
    title: str


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


def read_workbook_expected_titles() -> dict[str, ExpectedTitle]:
    workbook = config.SOURCE_WORKBOOK
    expected: dict[str, ExpectedTitle] = {}

    with zipfile.ZipFile(workbook) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        shared_strings = read_shared_strings(archive)

        for sheet in workbook_xml.find("a:sheets", SPREADSHEET_NS):
            sheet_name = sheet.attrib["name"].strip()
            target = rel_map[sheet.attrib[RELATIONSHIP_ID]].lstrip("/")
            sheet_path = "xl/" + target if not target.startswith("xl/") else target
            sheet_xml = ET.fromstring(archive.read(sheet_path))

            for keyword in read_keywords(sheet_xml, shared_strings):
                if keyword == "키워드":
                    continue
                expected[keyword] = ExpectedTitle(
                    keyword=keyword,
                    sheet_name=sheet_name,
                    title=f"{keyword} | {sheet_name} | {config.PROJECT_NAME}",
                )

    return expected


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(node.text or "" for node in item.findall(".//a:t", SPREADSHEET_NS))
        for item in xml_root.findall("a:si", SPREADSHEET_NS)
    ]


def read_keywords(sheet_xml: ET.Element, shared_strings: list[str]) -> list[str]:
    keywords = []
    for row in sheet_xml.findall(".//a:sheetData/a:row", SPREADSHEET_NS):
        for cell in row.findall("a:c", SPREADSHEET_NS):
            column = re.sub(r"\d+", "", cell.attrib.get("r", ""))
            if column == "A":
                value = read_cell(cell, shared_strings).strip()
                if value:
                    keywords.append(value)
                break
    return keywords


def read_cell(cell: ET.Element, shared_strings: list[str]) -> str:
    inline = cell.find("a:is", SPREADSHEET_NS)
    if inline is not None:
        return "".join(node.text or "" for node in inline.findall(".//a:t", SPREADSHEET_NS))

    value = cell.find("a:v", SPREADSHEET_NS)
    if value is None:
        return ""

    text = value.text or ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(text)]
    return text


def read_generated_title(keyword: str) -> str:
    path = config.OUTPUT_DIR / keyword / "index.html"
    parser = HeadTitleParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()
    return html.unescape(parser.title)


def main() -> None:
    expected = read_workbook_expected_titles()
    mismatches = []
    missing = []

    for keyword, expected_title in expected.items():
        path = config.OUTPUT_DIR / keyword / "index.html"
        if not path.exists():
            missing.append(keyword)
            continue

        actual_title = read_generated_title(keyword)
        if actual_title != expected_title.title:
            mismatches.append((keyword, expected_title.sheet_name, expected_title.title, actual_title))

    sample_keywords = [
        "대전과외",
        "대전수학과외",
        "대전영어과외",
        "유성구초등과외",
        "유성구고등수학과외",
        "관평동영어과외",
        "대구과외",
        "대구고등영어과외",
    ]
    sample_keywords = [keyword for keyword in sample_keywords if keyword in expected]
    remaining = [keyword for keyword in expected if keyword not in sample_keywords]
    random.seed(20260702)
    sample_keywords.extend(random.sample(remaining, min(12, len(remaining))))

    lines = [
        "# StudyRoute Title Validation Report",
        "",
        "## Rule",
        "",
        "`A열 키워드 | 현재 시트명 | StudyRoute`",
        "",
        "## Summary",
        "",
        f"- Workbook pages checked: {len(expected)}",
        f"- Missing output pages: {len(missing)}",
        f"- Title mismatches: {len(mismatches)}",
        "",
        "## Sample Validation",
        "",
        "| Keyword | Workbook Sheet | Expected Title | Actual Title | Result |",
        "|---|---|---|---|---|",
    ]

    for keyword in sample_keywords:
        expected_title = expected[keyword]
        actual_title = read_generated_title(keyword)
        result = "OK" if actual_title == expected_title.title else "FAIL"
        lines.append(
            f"| {keyword} | {expected_title.sheet_name} | {expected_title.title} | {actual_title} | {result} |"
        )

    lines.extend(["", "## Missing Output Pages", ""])
    if missing:
        lines.extend(f"- {keyword}" for keyword in missing)
    else:
        lines.append("- OK")

    lines.extend(["", "## Title Mismatches", ""])
    if mismatches:
        for keyword, sheet_name, expected_title, actual_title in mismatches:
            lines.append(
                f"- {keyword}: sheet `{sheet_name}`, expected `{expected_title}`, actual `{actual_title}`"
            )
    else:
        lines.append("- OK")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Title validation complete: {REPORT_PATH}")
    print(f"checked={len(expected)} missing={len(missing)} mismatches={len(mismatches)}")


if __name__ == "__main__":
    main()
