# StudyRoute 메인 디자인 업데이트 보고서

작성일: 2026-07-02

## 작업 범위

- 기존 메인 HTML/CSS 구조를 유지한 상태에서 첨부 시안에 맞게 Hero와 학습 카테고리 영역을 보정했습니다.
- `generator.py`, 페이지 생성 구조, SEO 메타, breadcrumb, canonical, JSON-LD, robots, sitemap, 내부 링크는 수정하지 않았습니다.
- 수정 파일:
  - `templates/pages/index.html`
  - `assets/css/main.css`
  - `assets/images/home-hero-books-skyline-crop.png`

## Hero 수정 내용

- Hero 문구를 시안 톤에 맞게 변경했습니다.
  - `대전과 대구에서`
  - `맞춤 학습을 시작하세요`
- 오른쪽 일러스트를 책, 노트, 연필, 스카이라인이 중심이 되도록 교체했습니다.
- 데스크톱에서는 좌우 레이아웃을 유지하면서 제목이 자연스러운 두 줄로 보이도록 폭과 글자 크기를 보정했습니다.
- 태블릿과 모바일에서는 Hero 이미지가 아래로 배치되고 잘리지 않도록 보정했습니다.
- 첫 화면 핵심 이미지이므로 `loading="eager"`와 `fetchpriority="high"`를 적용했습니다.

## 카테고리 카드 수정 내용

- 기존 12개 카테고리 카드 구조와 링크는 유지했습니다.
- 아이콘 배경 크기와 내부 SVG 표시 크기를 통일했습니다.
- 카드 Hover 시 떠오름, 살짝 확대, 아이콘 확대 효과를 유지하면서 그림자를 조금 더 정돈했습니다.
- PC 4열, Tablet 2열, Mobile 2열 Grid 구조를 유지했습니다.

## 반응형 검증

- PC 캡처: `reports/design-update-pc.png`
- Tablet 캡처: `reports/design-update-tablet.png`
- Mobile 캡처: `reports/design-update-mobile.png`

검증 결과:

- PC: Hero 좌우 배치, 제목 두 줄, 오른쪽 일러스트, 4열 카테고리 카드 정상 표시
- Tablet: Hero 세로 배치, 버튼 2열, 이미지 하단 배치, 2열 카테고리 카드 정상 표시
- Mobile: 제목, 설명, 버튼, 이미지 순서 유지, 카테고리 2열 유지

## 산출 HTML 검증

- `output/index.html`에 새 Hero 문구 반영 확인
- `output/index.html`에 `home-hero-books-skyline-crop.png` 반영 확인
- Hero 이미지 크기값 `width="1100" height="538"` 반영 확인
- 카테고리 SVG 아이콘 12개 output 복사 확인
- `py generator.py` 재빌드 완료

## 시안과의 차이

- 첨부 시안은 Hero 이미지가 넓은 배경처럼 보이는 구성이고, 현재 구현은 기존 구조를 유지하기 위해 오른쪽 일러스트 영역 안에서 이미지를 표시합니다.
- 모바일에서는 화면 폭이 좁아 Hero 일러스트의 오른쪽 요소가 일부 우선적으로 보이도록 배치했습니다.
- SEO와 생성 구조를 보존해야 하므로 메인 외 페이지 구조와 전역 생성 로직은 변경하지 않았습니다.
