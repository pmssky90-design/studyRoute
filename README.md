# StudyRoute

Python Static Site Generator for <https://studyroute.co.kr>

StudyRoute는 Python 기반 정적 사이트 생성기입니다. `generator.py`를 실행하면 `data/` 폴더의 엑셀 파일을 읽어 `output/`에 배포 가능한 HTML 정적 사이트를 생성합니다.

## 기본 정보

- 브랜드: StudyRoute
- 도메인: <https://studyroute.co.kr>
- 런타임: Python 3.14
- 외부 라이브러리: 없음
- 입력 데이터: `data/대전_대구_12개메인허브.xlsx`
- 배포 폴더: `output/`

## 실행 방법

Windows PowerShell 기준:

```powershell
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' generator.py
```

Python 실행기가 PATH에 잡혀 있다면 다음처럼 실행할 수도 있습니다.

```powershell
python generator.py
```

## 엑셀 입력 규칙

각 시트는 하나의 허브 그룹입니다.

- A열: 키워드
- B열: HTML 본문

생성기는 A열 키워드를 페이지 생성 기준으로 사용합니다. B열 HTML 본문은 수정하지 않고 페이지 본문에 삽입합니다.

## URL, Title, H1 규칙

예를 들어 A열 키워드가 `대전수학과외`이고 시트명이 `수학과외 가이드`라면 다음처럼 생성됩니다.

- URL: `/대전수학과외/`
- title: `대전수학과외 | 수학과외 가이드 | StudyRoute`
- H1: `대전수학과외`

시트명은 title에만 사용하고 URL과 H1에는 사용하지 않습니다.

## 자동 생성 항목

- HTML 페이지
- 공통 Header
- 공통 Footer
- 공통 Navigation
- Breadcrumb
- canonical
- Open Graph
- Twitter Card
- favicon
- JSON-LD
- `robots.txt`
- `sitemap.xml`

## 프로젝트 구조

```text
StudyRoute/
  generator.py
  config.py
  requirements.txt
  README.md
  templates/
    base.html
    pages/
      index.html
      content.html
    partials/
      breadcrumb.html
      footer.html
      header.html
  assets/
    css/
      main.css
    js/
      main.js
    images/
      favicon.svg
      og-default.svg
  data/
    대전_대구_12개메인허브.xlsx
  output/
  scripts/
```

## 배포

GitHub Pages 또는 Cloudflare Pages에서 빌드 명령은 `generator.py` 실행으로 지정하고, 배포 폴더는 `output`으로 지정합니다.
