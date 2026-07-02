# Search Runtime Report

## 기준

- 운영 URL: `https://studyroute.co.kr`
- 확인 일시: 2026-07-02
- 확인 방식:
  - `curl.exe`로 운영 HTML/정적 자산 HTTP 상태 확인
  - Edge headless + Chrome DevTools Protocol로 운영 페이지 실제 클릭 검증

## 최초 운영 증상 확인

운영 사이트 초기 확인 결과, 검색 기능이 배포되지 않은 이전 HTML이 서비스되고 있었습니다.

- `https://studyroute.co.kr`: `200 OK`
- 운영 HTML 내 `.search-trigger`: 존재
- 운영 HTML 내 `assets/js/search.js`: 없음
- 운영 HTML 내 `.search-panel`: 없음
- 운영 HTML 내 `data-search-input`: 없음
- `https://studyroute.co.kr/assets/js/search.js`: `404 NOT_FOUND`
- `https://studyroute.co.kr/search-index.json`: `404 NOT_FOUND`

따라서 돋보기 버튼은 있었지만 검색 JavaScript와 검색 패널 DOM이 운영 배포본에 없어서 클릭 이벤트가 연결될 수 없는 상태였습니다.

## 수정 및 배포

- 커밋: `b60fffa Implement runtime search`
- GitHub Push: `main -> origin/main`
- Vercel 자동 재배포 후 운영 응답 갱신 확인

재배포 후 운영 HTTP 확인:

- `https://studyroute.co.kr`: `200 OK`
- 운영 HTML 내 `assets/js/search.js`: 포함됨
- 운영 HTML 내 `.search-trigger`: 존재
- 운영 HTML 내 `.search-panel`: 존재
- 운영 HTML 내 `data-search-input`: 존재
- `https://studyroute.co.kr/assets/js/search.js`: `200 OK`
- `https://studyroute.co.kr/search-index.json`: `200 OK`

## 운영 브라우저 검증

검증 명령:

```powershell
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' scripts\verify_search_runtime.py
```

검증 결과: 통과.

운영 DOM 확인:

- `script[src$="assets/js/search.js"]`: 존재
- `.search-trigger`: 존재
- `[data-search-panel]`: 존재
- `[data-search-input]`: 존재

운영 클릭 확인:

- 돋보기 클릭 후 `.site-nav.is-search-open`: `true`
- 검색 패널 opacity: `1`
- 버튼 `aria-expanded`: `true`
- 포커스된 요소: `site-search-input`

운영 자동완성 확인:

- 입력값: `수학`
- 자동완성 결과 수: `8`
- 첫 결과 URL: `/수학과외/`
- 결과 클릭 후 이동 path: `/수학과외/`

운영 Network 확인:

- `https://studyroute.co.kr/`: `200`
- `https://studyroute.co.kr/assets/js/search.js`: 브라우저 재검증에서 `304`, 직전 HTTP HEAD 확인에서 `200`
- `https://studyroute.co.kr/search-index.json`: `200`

운영 Console 확인:

- JavaScript exception: 없음
- Console error: 없음

검증 산출물:

- `reports/search_runtime_results.json`
- `reports/search-runtime-production.png`

## 결론

운영에서 검색이 동작하지 않은 원인은 검색 기능 구현 파일이 GitHub/Vercel 운영 배포에 반영되지 않아 `search.js`와 `search-index.json`이 404였기 때문입니다.

현재 운영 `https://studyroute.co.kr` 기준으로 돋보기 클릭 시 검색창이 열리고, 자동완성 결과가 표시되며, 결과 클릭 시 해당 페이지로 이동하는 것까지 확인했습니다.
