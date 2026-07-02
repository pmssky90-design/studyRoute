# StudyRoute Design Report

## 구현 내용

- 첨부 메인 디자인을 기준으로 홈 화면을 카드형 서비스 메인으로 재구성했습니다.
- Header는 좌측 `StudyRoute`, 우측 `홈`, `대전과외`, `대구과외`, 검색 아이콘만 표시하도록 정리했습니다.
- Hero는 좌측 제목, 설명, 대전/대구 CTA 버튼과 우측 일러스트 영역으로 구성했습니다.
- 학습 카테고리는 생성기에서 내려주는 전국 허브 12개를 카드로 렌더링합니다.
- SEO 텍스트 예정 영역은 빈 입력 공간 형태로 유지했습니다.
- 지역 찾기는 대전/대구 카드와 각 하위 구 버튼을 자동 출력합니다.
- Footer는 `StudyRoute`와 copyright만 남겼습니다.

## 생성 구조

- `generator.py`에서 엑셀 기반 허브 suffix를 자동 추론합니다.
- 엑셀에 없는 `학습전략가이드`는 `config.EXTRA_NATIONAL_HUB_SUFFIXES` 확장 목록에서 추가합니다.
- 전국 허브 12개가 `/수학과외/` 같은 루트 slug로 생성됩니다.
- `학습전략가이드`는 모든 기존 지역 계층에 맞춰 지역별 허브 페이지도 자동 생성됩니다.

## 디자인 차이

- 첨부 이미지의 우측 hero 일러스트는 HTML/CSS와 SVG asset으로 재현했습니다. 실제 원본 bitmap과 완전히 동일한 세밀한 풍경, 책상 질감, 잎사귀 표현은 차이가 있습니다.
- 카테고리 아이콘은 외부 아이콘 라이브러리 없이 CSS/SVG/텍스트 기반으로 구현했습니다.
- 레이아웃, 카드 간격, 둥근 모서리, 연한 border, 초록/파랑 CTA, 그림자 톤은 첨부 이미지에 맞춰 최대한 근접시켰습니다.

## 변경 범위

- 수정: `templates/pages/index.html`
- 수정: `templates/partials/header.html`
- 수정: `templates/partials/footer.html`
- 수정: `assets/css/main.css`
- 추가: `assets/images/home-hero-studyroute.svg`
- 확장: `generator.py`, `config.py`

기존 엑셀 기반 페이지의 slug, 기존 URL, canonical, sitemap 생성 흐름은 유지했습니다.
