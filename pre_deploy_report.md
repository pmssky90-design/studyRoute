# StudyRoute Pre-Deploy QA Report

## 검사 기준

- 검사 대상: `generator.py` 재실행 후 생성된 `output` 배포 HTML
- 검사 페이지: 1,976개 `index.html`
- sitemap URL: 1,976개
- 랜덤 샘플: 100페이지
- 검사 결과 원본: `reports/pre_deploy_qa_results.json`
- HTTP 스모크 체크: `robots.txt`, `sitemap.xml`, favicon 3종, OG/Twitter 이미지 샘플 모두 200

## 수정 내용

- `favicon.ico`, `favicon-32x32.png`, `apple-touch-icon.png`를 기존 StudyRoute favicon SVG와 같은 형태로 생성했습니다.
- 모든 페이지 head에 `.ico`, 32x32 PNG, SVG, Apple touch icon 링크가 함께 출력되도록 보강했습니다.
- JSON-LD에 `Organization`, `WebSite @id`, `publisher`, `WebPage isPartOf` 연결을 추가했습니다.
- 수정 후 `generator.py`를 재실행하여 `output` 전체를 재빌드했습니다.
- 재빌드 후 전체 QA를 다시 실행했습니다.

## 수정 파일

- `templates/base.html`
- `generator.py`
- `assets/images/favicon.ico`
- `assets/images/favicon-32x32.png`
- `assets/images/apple-touch-icon.png`
- `scripts/create_favicons.py`
- `scripts/pre_deploy_qa.py`
- `scripts/http_smoke_check.py`
- `output/**`

## 재검사 결과

- Favicon: OK
- Open Graph image / Twitter image 존재 여부: OK
- Open Graph image / Twitter image HTTP 200: OK
- robots.txt: OK
- robots.txt HTTP 200: OK
- sitemap.xml XML 문법 / URL 수 / 중복 / 누락: OK
- sitemap.xml HTTP 200: OK
- canonical 현재 URL 일치: OK
- JSON-LD 문법 / `@id` / `url` / `publisher` / `Organization` / `WebSite` / `WebPage`: OK
- Open Graph 필수 태그: OK
- Twitter Card 필수 태그: OK
- title 누락 / 중복 / 형식: OK
- meta description 누락 / 너무 짧음 / 중복: OK
- H1 누락 / 중복 / keyword 불일치: OK
- 내부 링크 404: OK
- 이미지 404 / alt / width / height / lazy loading: OK
- CSS 404: OK
- JavaScript 404: OK
- 빈 페이지 / 본문 누락 / 본문 너무 짧음: OK
- 랜덤 100페이지 샘플 HTML / title / H1 / 본문 / 이미지 / 링크: OK

## Severity Summary

- Critical: 0
- High: 0
- Medium: 0
- Low: 1

## 남은 이슈

- Low 1건: `assets/css/main.css`에서 미사용 가능성이 있는 CSS class 후보가 감지되었습니다.
- 해당 항목은 404, 렌더링 실패, SEO 오류, 배포 차단 오류가 아니라 정리 후보입니다.
- 디자인 변경 금지 조건 때문에 CSS 삭제나 시각 영향 가능성이 있는 정리는 수행하지 않았습니다.

## 배포 가능 여부

현재 바로 배포 가능한 상태입니다.

Critical, High, Medium 이슈는 0건이며, 남은 Low 1건은 배포를 막지 않는 CSS 정리 후보입니다.
