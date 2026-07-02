"""Verify StudyRoute body images and social thumbnails in generated HTML."""

from __future__ import annotations

import hashlib
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


BODY_IMAGE_SRC = f"../{config.BODY_IMAGE_PATH}"
REPORT_PATH = config.ROOT_DIR / "image_report.md"


@dataclass
class ImageIssue:
    severity: str
    page: str
    message: str


def expected_thumb(keyword: str) -> str:
    digest = hashlib.sha256(keyword.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % len(config.OG_THUMBNAILS)
    return config.BASE_URL.rstrip("/") + "/" + config.OG_THUMBNAILS[index]


def meta_content(markup: str, attribute: str, value: str) -> str:
    pattern = (
        rf'<meta\s+[^>]*{attribute}=["\']{re.escape(value)}["\'][^>]*'
        r'content=["\']([^"\']+)["\'][^>]*>'
    )
    match = re.search(pattern, markup, re.IGNORECASE)
    if match:
        return html.unescape(match.group(1))

    pattern = (
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*'
        rf'{attribute}=["\']{re.escape(value)}["\'][^>]*>'
    )
    match = re.search(pattern, markup, re.IGNORECASE)
    return html.unescape(match.group(1)) if match else ""


def attrs_from_tag(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for name, _, value in re.findall(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(["\'])(.*?)\2', tag):
        attrs[name.lower()] = html.unescape(value)
    return attrs


def local_asset_exists(url_or_path: str, page_file: Path) -> bool:
    if url_or_path.startswith(config.BASE_URL):
        parsed = urlparse(url_or_path)
        local_path = config.OUTPUT_DIR / unquote(parsed.path.lstrip("/"))
        return local_path.exists()

    local_path = (page_file.parent / url_or_path).resolve()
    try:
        local_path.relative_to(config.OUTPUT_DIR.resolve())
    except ValueError:
        return False
    return local_path.exists()


def verify_page(page_file: Path) -> tuple[dict[str, int], list[ImageIssue]]:
    markup = page_file.read_text(encoding="utf-8")
    keyword = page_file.parent.name
    page_label = f"/{keyword}/"
    issues: list[ImageIssue] = []

    body_tags = re.findall(
        rf'<img\b[^>]*\bsrc=["\']{re.escape(BODY_IMAGE_SRC)}["\'][^>]*>',
        markup,
        re.IGNORECASE,
    )
    if len(body_tags) != 1:
        issues.append(ImageIssue("High", page_label, f"본문 공통 이미지 수가 {len(body_tags)}개입니다."))
    else:
        tag = body_tags[0]
        attrs = attrs_from_tag(tag)
        expected_alt = f"{keyword} 학습 정보"
        h1_match = re.search(r"<h1\b[^>]*>.*?</h1>", markup, re.IGNORECASE | re.DOTALL)
        image_pos = markup.find(tag)
        if not h1_match or h1_match.end() > image_pos:
            issues.append(ImageIssue("High", page_label, "본문 공통 이미지가 H1 바로 아래 순서에 있지 않습니다."))
        if attrs.get("alt") != expected_alt:
            issues.append(ImageIssue("High", page_label, "본문 공통 이미지 alt가 페이지 키워드 기반 값과 다릅니다."))
        if attrs.get("loading") != "lazy":
            issues.append(ImageIssue("High", page_label, "본문 공통 이미지에 loading=\"lazy\"가 없습니다."))
        if attrs.get("decoding") != "async":
            issues.append(ImageIssue("Medium", page_label, "본문 공통 이미지에 decoding=\"async\"가 없습니다."))
        if attrs.get("width") != str(config.BODY_IMAGE_WIDTH) or attrs.get("height") != str(config.BODY_IMAGE_HEIGHT):
            issues.append(ImageIssue("Medium", page_label, "본문 공통 이미지 width/height가 설정값과 다릅니다."))
        if not local_asset_exists(attrs.get("src", ""), page_file):
            issues.append(ImageIssue("High", page_label, "본문 공통 이미지 경로가 존재하지 않습니다."))

    og_image = meta_content(markup, "property", "og:image")
    twitter_image = meta_content(markup, "name", "twitter:image")
    expected_og = expected_thumb(keyword)

    if not og_image:
        issues.append(ImageIssue("High", page_label, "og:image가 없습니다."))
    elif og_image != expected_og:
        issues.append(ImageIssue("High", page_label, f"og:image가 결정론적 썸네일과 다릅니다: {og_image}"))
    elif not local_asset_exists(og_image, page_file):
        issues.append(ImageIssue("High", page_label, "og:image asset이 output에 없습니다."))

    if not twitter_image:
        issues.append(ImageIssue("High", page_label, "twitter:image가 없습니다."))
    elif twitter_image != expected_og:
        issues.append(ImageIssue("High", page_label, f"twitter:image가 og:image와 다릅니다: {twitter_image}"))
    elif not local_asset_exists(twitter_image, page_file):
        issues.append(ImageIssue("High", page_label, "twitter:image asset이 output에 없습니다."))

    if config.BODY_IMAGE_PATH in og_image or config.BODY_IMAGE_PATH in twitter_image:
        issues.append(ImageIssue("Critical", page_label, "본문 공통 이미지가 검색 썸네일로 사용되었습니다."))

    ok = {
        "body_image_one": 1 if len(body_tags) == 1 else 0,
        "og_image": 1 if og_image else 0,
        "twitter_image": 1 if twitter_image else 0,
        "separate_images": 1 if config.BODY_IMAGE_PATH not in og_image + twitter_image else 0,
        "path_exists": 1 if body_tags and local_asset_exists(attrs_from_tag(body_tags[0]).get("src", ""), page_file) and local_asset_exists(og_image, page_file) and local_asset_exists(twitter_image, page_file) else 0,
        "alt": 1 if body_tags and attrs_from_tag(body_tags[0]).get("alt") == f"{keyword} 학습 정보" else 0,
        "lazy": 1 if body_tags and attrs_from_tag(body_tags[0]).get("loading") == "lazy" else 0,
    }
    return ok, issues


def main() -> None:
    page_files = sorted(path for path in config.OUTPUT_DIR.glob("*/index.html") if path.parent.name != "assets")
    home_file = config.OUTPUT_DIR / "index.html"
    issues: list[ImageIssue] = []
    totals = {
        "body_image_one": 0,
        "og_image": 0,
        "twitter_image": 0,
        "separate_images": 0,
        "path_exists": 0,
        "alt": 0,
        "lazy": 0,
    }

    if home_file.exists() and config.BODY_IMAGE_PATH in home_file.read_text(encoding="utf-8"):
        issues.append(ImageIssue("High", "/", "메인 페이지에 본문 공통 이미지가 삽입되었습니다."))

    samples: list[str] = []
    for page_file in page_files:
        ok, page_issues = verify_page(page_file)
        for key, value in ok.items():
            totals[key] += value
        issues.extend(page_issues)
        if len(samples) < 12:
            keyword = page_file.parent.name
            samples.append(f"- /{keyword}/ -> {expected_thumb(keyword).rsplit('/', 1)[-1]}")

    counts_by_severity: dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for issue in issues:
        counts_by_severity[issue.severity] = counts_by_severity.get(issue.severity, 0) + 1

    issue_lines = ["문제 없음"] if not issues else [
        f"- {issue.severity}: {issue.page} - {issue.message}" for issue in issues[:200]
    ]
    if len(issues) > 200:
        issue_lines.append(f"- ... 추가 {len(issues) - 200}건 생략")

    report = f"""# StudyRoute Image Report

## 요약

- 검사 대상: 메인 제외 콘텐츠 페이지 {len(page_files)}개
- Critical: {counts_by_severity.get("Critical", 0)}
- High: {counts_by_severity.get("High", 0)}
- Medium: {counts_by_severity.get("Medium", 0)}
- Low: {counts_by_severity.get("Low", 0)}

## 검증 결과

- H1 아래 공통 본문 이미지 1장: {totals["body_image_one"]}/{len(page_files)}
- og:image 존재 및 결정론적 썸네일 적용: {totals["og_image"]}/{len(page_files)}
- twitter:image 존재 및 og:image와 동일 썸네일 적용: {totals["twitter_image"]}/{len(page_files)}
- 본문 이미지와 검색 썸네일 분리: {totals["separate_images"]}/{len(page_files)}
- 이미지 경로 존재: {totals["path_exists"]}/{len(page_files)}
- 본문 이미지 alt 존재 및 키워드 기반 값 일치: {totals["alt"]}/{len(page_files)}
- 본문 이미지 lazy loading 적용: {totals["lazy"]}/{len(page_files)}
- 메인 페이지 본문 공통 이미지 제외: {"통과" if not any(issue.page == "/" for issue in issues) else "실패"}

## 사용 이미지

- 본문 공통 이미지: `{config.BODY_IMAGE_PATH}`
- 검색 썸네일 풀: `{", ".join(config.OG_THUMBNAILS)}`

## 썸네일 샘플

{chr(10).join(samples)}

## 문제 목록

{chr(10).join(issue_lines)}
"""
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    print(f"checked={len(page_files)} critical={counts_by_severity.get('Critical', 0)} high={counts_by_severity.get('High', 0)} medium={counts_by_severity.get('Medium', 0)} low={counts_by_severity.get('Low', 0)}")


if __name__ == "__main__":
    main()
