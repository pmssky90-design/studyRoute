# StudyRoute Responsive Report

## 캡처 결과

- PC: `reports/home-pc.png`
- Tablet: `reports/home-tablet.png`
- Mobile: `reports/home-mobile.png`

## PC

- 기준 화면: 1536 x 900
- Hero는 좌우 배치입니다.
- 학습 카테고리는 4열 grid로 배치됩니다.
- 지역 카드는 2열로 배치됩니다.
- Header는 한 줄 레이아웃입니다.

## Tablet

- 기준 화면: 834 x 1112
- Hero는 세로 배치입니다.
- 학습 카테고리는 2열 grid로 배치됩니다.
- CTA 버튼은 터치 가능한 크기를 유지합니다.
- 지역 카드는 2열로 유지됩니다.

## Mobile

- 기준 화면: 390 x 844
- Mobile First CSS 기준으로 설계했습니다.
- 표시 순서: Hero, 지역 버튼, 12개 학습 카테고리, SEO 영역, 지역 찾기입니다.
- 학습 카테고리는 2열 grid입니다.
- CTA 및 지역 버튼은 최소 44px 이상 터치 영역을 유지합니다.
- Hero 이미지는 `width`, `height`, `loading="lazy"`, `decoding="async"`를 포함합니다.

## 확인 사항

- 모바일에서 헤더 메뉴는 4칸 grid로 고정되어 검색 아이콘까지 화면 안에 들어옵니다.
- 카드 hover transition, shadow, border radius를 적용했습니다.
- 긴 버튼/문장으로 인한 치명적 레이아웃 깨짐은 확인되지 않았습니다.

## 남은 차이

- 원본 첨부 이미지의 hero 일러스트는 고해상도 그림체이지만, 현재는 경량 SVG 재현입니다.
- 모바일 첫 화면에서는 hero 영역이 우선 표시되므로 12개 카테고리는 스크롤 후 확인됩니다.
