"""Project-wide configuration for the StudyRoute static site generator."""

from __future__ import annotations

from pathlib import Path


PROJECT_NAME = "StudyRoute"
BASE_URL = "https://studyroute.co.kr"
LANGUAGE = "ko"
TIMEZONE = "Asia/Seoul"

ROOT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT_DIR / "templates"
ASSET_DIR = ROOT_DIR / "assets"
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
SOURCE_WORKBOOK = DATA_DIR / "대전_대구_12개메인허브.xlsx"

DEFAULT_TITLE = "StudyRoute | 대전 대구 과외 학습 경로"
DEFAULT_DESCRIPTION = "StudyRoute는 대전과 대구 지역의 과외 학습 정보를 정적 HTML로 제공하는 사이트입니다."
DEFAULT_IMAGE = "assets/images/og-default.svg"
FAVICON_PATH = "assets/images/favicon.svg"
BODY_IMAGE_PATH = "assets/images/body-common.webp"
BODY_IMAGE_WIDTH = 800
BODY_IMAGE_HEIGHT = 8000
OG_THUMBNAILS = tuple(f"assets/images/og-thumbs/thumb{index:02d}.svg" for index in range(1, 13))
EXTRA_NATIONAL_HUB_SUFFIXES = ("학습전략가이드",)

ROBOTS_ALLOW_ALL = True

NAVIGATION_ITEMS = [
    {"label": "홈", "url": "./"},
    {"label": "대전과외", "url": "대전과외/"},
    {"label": "대구과외", "url": "대구과외/"},
]

CITY_NAMES = ["대전", "대구"]
HOME_CITY_ORDER = ["대전", "대구"]

# Explicit parent-child region structure for the current workbook. Links are
# still emitted only when the corresponding A-column keyword exists.
REGION_CHILDREN = {
    "대전": ["대전동구", "대전중구", "대전서구", "유성구", "대덕구"],
    "대구": ["대구동구", "대구중구", "대구서구", "대구북구", "대구남구", "수성구", "달서구", "달성군"],
    "대전동구": ["가양동", "대동", "대전삼성동", "성남동", "신흥동", "천동"],
    "대전중구": ["대사동", "대전대흥동", "문화동", "중촌동", "태평동", "대전은행동", "선화동"],
    "대전서구": [
        "가수원동",
        "가장동",
        "갈마동",
        "관저동",
        "괴정동",
        "내동",
        "도마동",
        "도안동",
        "둔산동",
        "만년동",
        "변동",
        "복수동",
        "월평동",
        "둔산신도시",
        "도안신도시",
    ],
    "유성구": [
        "관평동",
        "노은동",
        "궁동",
        "덕명동",
        "반석동",
        "봉명동",
        "상대동",
        "송강동",
        "원내동",
        "원신흥동",
        "장대동",
        "전민동",
        "죽동",
        "지족동",
        "하기동",
        "노은지구",
        "테크노벨리",
    ],
    "대덕구": ["비래동", "신탄진동", "석봉동", "송촌동"],
    "대구동구": [
        "각산동",
        "괴전동",
        "대구불로동",
        "대구대림동",
        "봉무동",
        "사복동",
        "신서동",
        "신기동",
        "신천동",
        "신암동",
        "율암동",
        "율하동",
        "지묘동",
        "효목동",
        "동호동",
        "대구혁신도시",
        "안심",
        "팔공산",
        "이시아폴리스",
    ],
    "대구중구": ["남산동", "대봉동", "동성로", "동인동", "봉산동", "삼덕동", "수창동", "반월당"],
    "대구서구": ["대구비산동", "평리동", "원대동"],
    "대구북구": [
        "검단동",
        "고성동",
        "구암동",
        "국우동",
        "대현동",
        "동천동",
        "매천동",
        "복현동",
        "산격동",
        "읍내동",
        "칠성동",
        "침산동",
        "태전동",
    ],
    "대구남구": ["대명동", "봉덕동", "이천동"],
    "수성구": [
        "가천동",
        "고모동",
        "노변동",
        "두산동",
        "만촌동",
        "범물동",
        "범어동",
        "매호동",
        "사월동",
        "대구상동",
        "수성동",
        "시지동",
        "신매동",
        "대구중동",
        "지산동",
        "파동",
        "황금동",
        "알파시티",
        "연호지구",
    ],
    "달서구": [
        "감삼동",
        "대곡동",
        "도원동",
        "두류동",
        "본동",
        "본리동",
        "상인동",
        "성당동",
        "송현동",
        "신당동",
        "용산동",
        "대구월성동",
        "유천동",
        "이곡동",
        "대구장기동",
        "대구죽전동",
        "진천동",
    ],
    "달성군": ["화원읍", "다사읍", "테크노폴리스", "논공", "구지"],
}


def _build_region_order() -> list[str]:
    order = ["대전과외", "대구과외"]
    for parent, children in REGION_CHILDREN.items():
        parent_slug = f"{parent}과외"
        if parent_slug not in order:
            order.append(parent_slug)
        for child in children:
            child_slug = f"{child}과외"
            if child_slug not in order:
                order.append(child_slug)
    return order


REGION_ORDER = _build_region_order()

SOCIAL_PROFILES: list[str] = []
