"""Check generated article text lengths."""

from __future__ import annotations

import re
from pathlib import Path


BODY_RE = re.compile(r'<div class="article-body">(.*?)</div>\s*</div>\s*</article>', re.S)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def text_len(path: Path) -> int:
    html = path.read_text(encoding="utf-8", errors="replace")
    match = BODY_RE.search(html)
    body = match.group(1) if match else ""
    text = TAG_RE.sub(" ", body)
    return len(SPACE_RE.sub(" ", text).strip())


def main() -> None:
    modified = [
        "동성로초등과외",
        "산격동과외",
        "신서동초등과외",
        "이시아폴리스과외",
        "봉명동초등수학과외",
        "태전동초등수학과외",
        "테크노폴리스초등수학과외",
        "대덕구초등영어과외",
    ]
    print("MODIFIED_LENGTHS")
    for slug in modified:
        print(slug, text_len(Path("output") / slug / "index.html"))

    rows = []
    for path in Path("output").glob("*/index.html"):
        length = text_len(path)
        if length < 1500:
            rows.append((path.parent.name, length))

    print("UNDER_1500")
    for slug, length in sorted(rows, key=lambda item: item[1]):
        print(slug, length)
    print("TOTAL_UNDER_1500", len(rows))


if __name__ == "__main__":
    main()
