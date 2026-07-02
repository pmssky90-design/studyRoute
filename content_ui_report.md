# StudyRoute 상세 본문 UI 개선 보고서

작성일: 2026-07-02

## 작업 범위

- 상세페이지의 본문 글 디자인 UI만 개선했습니다.
- 본문 내용, 문장, 단어, 키워드, 순서, SEO, title, slug, breadcrumb, canonical, JSON-LD, robots, sitemap, URL, 내부 링크 구조는 변경하지 않았습니다.
- JavaScript는 추가하지 않았습니다.
- 이번 작업에서 `generator.py`는 수정하지 않았습니다.

## 수정 파일

- `assets/css/main.css`

## 본문 폭과 타이포그래피

- 본문 최대폭을 `820px` 범위로 제한했습니다.
- 본문 기본 글자 크기와 줄간격을 개선했습니다.
  - 기본: `16.5px`, `line-height: 1.92`
  - Desktop: `17px`
  - Mobile: `16px`, `line-height: 1.86`
- 문단 간격을 확대하고 줄바꿈 안정성을 보강했습니다.
- `letter-spacing`은 0으로 유지했습니다.

## 제목 스타일

- H2는 더 크게, 굵게 표시되도록 조정했습니다.
- H2 상단에 StudyRoute 메인 컬러 기반의 짧은 포인트 라인을 추가했습니다.
- H3는 왼쪽 녹색 border를 적용해 본문 안의 소제목이 명확히 구분되도록 했습니다.

## 본문 요소 스타일

- `ul`, `ol`, `li`는 카드형 배경, 간격, marker 색상을 적용했습니다.
- `blockquote`는 카드형 인용문 스타일과 왼쪽 포인트 라인을 적용했습니다.
- `table`은 `table-layout: fixed`, 셀 줄바꿈, 헤더 배경, 경계선을 적용해 모바일에서도 읽기 쉽게 정리했습니다.
- `strong`은 StudyRoute 녹색 계열로 강조했습니다.
- `em`은 파란 계열 강조와 하이라이트 배경을 적용했습니다.
- `details`, `.faq`, `.faq-item`, `summary`는 FAQ 카드형 스타일로 정리했습니다.

## 본문 하단 연결

- 본문과 관련 링크 영역 사이 여백을 확보했습니다.
- 기존 링크 구조와 URL은 변경하지 않았습니다.
- 관련 링크 카드 스타일은 기존 개선 상태를 유지했습니다.

## 모바일 최적화

- 모바일 전용 미디어쿼리를 추가했습니다.
- 작은 화면에서 문단, H2/H3, 목록, 인용문, 표, FAQ, 관련 링크 간격을 별도로 조정했습니다.
- 링크는 터치하기 쉽도록 최소 높이와 여백을 유지했습니다.

## 검증 결과

- `py generator.py` 빌드 성공
- 샘플 20개 상세 페이지 본문 텍스트 해시 비교 완료
- 본문 내용 변경: 0건
- CSS 적용 확인:
  - H2 포인트 라인 적용
  - H3 왼쪽 border 적용
  - table 고정 레이아웃 적용
  - strong/em 강조 적용
  - 모바일 전용 본문 UI 적용

## 반응형 캡처

- Desktop: `reports/content-ui-pc.png`
- Tablet: `reports/content-ui-tablet.png`
- Mobile: `reports/content-ui-mobile.png`
- Desktop 본문 구간: `reports/content-ui-pc-body.png`
- Mobile 본문 구간: `reports/content-ui-mobile-body.png`

## 참고

- 공통 이미지는 원본 비율을 유지하므로 매우 긴 이미지가 먼저 표시됩니다.
- 이번 작업은 요청 범위에 따라 본문 글 디자인 CSS만 개선했습니다.
