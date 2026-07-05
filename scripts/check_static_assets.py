from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
REPORTS_DIR = ROOT_DIR / "reports"
REPORT_PATH = REPORTS_DIR / "static_asset_report.txt"

EXPECTED_STYLESHEET = "/assets/css/main.css"
EXPECTED_SCRIPT = "/assets/js/search.js"

TAG_RE = re.compile(r"<(?P<tag>link|img|script)\b(?P<attrs>[^>]*)>", re.IGNORECASE)
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s"'=<>`]+))""",
    re.IGNORECASE,
)


def html_files() -> list[Path]:
    return sorted(OUTPUT_DIR.rglob("*.html"))


def tag_attrs(source: str) -> list[tuple[str, dict[str, str]]]:
    tags: list[tuple[str, dict[str, str]]] = []
    for match in TAG_RE.finditer(source):
        attrs = {
            attr.group("name").lower(): attr.group("double") or attr.group("single") or attr.group("bare") or ""
            for attr in ATTR_RE.finditer(match.group("attrs"))
        }
        tags.append((match.group("tag").lower(), attrs))
    return tags


def static_references(file_path: Path) -> tuple[list[str], list[str], list[str]]:
    stylesheets: list[str] = []
    images: list[str] = []
    scripts: list[str] = []
    source = file_path.read_text(encoding="utf-8")

    for tag, attrs in tag_attrs(source):
        if tag == "link" and attrs.get("rel", "").lower() == "stylesheet" and attrs.get("href"):
            stylesheets.append(attrs["href"])
        elif tag == "img" and attrs.get("src"):
            images.append(attrs["src"])
        elif tag == "script" and attrs.get("src"):
            scripts.append(attrs["src"])

    return stylesheets, images, scripts


def is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.scheme not in {"", "file"} and parsed.netloc)


def asset_path(url: str, source_file: Path) -> Path | None:
    if url.startswith(("data:", "mailto:", "tel:", "javascript:")) or is_external_url(url):
        return None

    parsed = urlparse(url)
    path = unquote(parsed.path)
    if not path:
        return None

    if path.startswith("/"):
        return OUTPUT_DIR / path.lstrip("/")

    return (source_file.parent / path).resolve()


def add_missing(missing: list[str], source_file: Path, asset_type: str, url: str, expected_path: Path) -> None:
    source = source_file.relative_to(OUTPUT_DIR).as_posix()
    try:
        target = expected_path.relative_to(OUTPUT_DIR).as_posix()
    except ValueError:
        target = str(expected_path)
    missing.append(f"{source}: {asset_type} {url} -> missing {target}")


def check_expected_paths(errors: list[str], source_file: Path, stylesheets: list[str], scripts: list[str]) -> None:
    source = source_file.relative_to(OUTPUT_DIR).as_posix()
    for href in stylesheets:
        if urlparse(href).path != EXPECTED_STYLESHEET:
            errors.append(f"{source}: stylesheet path must be {EXPECTED_STYLESHEET}, found {href}")
    for src in scripts:
        if urlparse(src).path != EXPECTED_SCRIPT:
            errors.append(f"{source}: script path must be {EXPECTED_SCRIPT}, found {src}")


def check_files(files: list[Path]) -> tuple[list[str], dict[str, int]]:
    missing_css: list[str] = []
    missing_images: list[str] = []
    missing_js: list[str] = []
    path_errors: list[str] = []
    counts = {"html": len(files), "stylesheets": 0, "images": 0, "scripts": 0}

    for file_path in files:
        stylesheets, images, scripts = static_references(file_path)
        counts["stylesheets"] += len(stylesheets)
        counts["images"] += len(images)
        counts["scripts"] += len(scripts)
        check_expected_paths(path_errors, file_path, stylesheets, scripts)

        for href in stylesheets:
            target = asset_path(href, file_path)
            if target is not None and not target.exists():
                add_missing(missing_css, file_path, "stylesheet", href, target)

        for src in images:
            target = asset_path(src, file_path)
            if target is not None and not target.exists():
                add_missing(missing_images, file_path, "image", src, target)

        for src in scripts:
            target = asset_path(src, file_path)
            if target is not None and not target.exists():
                add_missing(missing_js, file_path, "script", src, target)

    errors = path_errors + missing_css + missing_images + missing_js
    counts["css_missing"] = len(missing_css)
    counts["image_missing"] = len(missing_images)
    counts["js_missing"] = len(missing_js)
    counts["path_errors"] = len(path_errors)
    counts["errors"] = len(errors)
    return errors, counts


def write_report(errors: list[str], counts: dict[str, int]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Static Asset Report",
        "",
        f"HTML files: {counts['html']}",
        f"Stylesheet references: {counts['stylesheets']}",
        f"Image references: {counts['images']}",
        f"Script references: {counts['scripts']}",
        f"CSS missing: {counts['css_missing']}",
        f"Image missing: {counts['image_missing']}",
        f"JS missing: {counts['js_missing']}",
        f"Path errors: {counts['path_errors']}",
        f"Total errors: {counts['errors']}",
        "",
    ]
    if errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("No missing static assets.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    errors, counts = check_files(html_files())
    write_report(errors, counts)
    print("StudyRoute static asset check complete")
    print(f"- html_files: {counts['html']}")
    print(f"- css_missing: {counts['css_missing']}")
    print(f"- image_missing: {counts['image_missing']}")
    print(f"- js_missing: {counts['js_missing']}")
    print(f"- path_errors: {counts['path_errors']}")
    print(f"- errors: {counts['errors']}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
