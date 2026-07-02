# Search Enter Fix Report

## 기준

- 운영 URL: `https://studyroute.co.kr`
- 범위: Enter 키 이동만 수정
- 유지 대상:
  - 자동완성 로직 유지
  - 화살표 선택 로직 변경 없음
  - 마우스 클릭 이동 변경 없음
  - 검색 인덱스/검색 스코어링 변경 없음

## 운영 증상 재현

수정 전 운영 사이트에서 `scripts/verify_search_runtime.py`를 Enter 방식으로 실행했습니다.

결과:

- 검색창 열림: 정상
- 자동완성 결과 표시: 정상
- Enter 이동: 실패

즉 운영 증상과 동일하게 Enter만 동작하지 않는 상태를 확인했습니다.

## 수정 내용

파일: `assets/js/search.js`

추가한 동작:

- 검색창이 열려 있고 Enter가 눌렸을 때만 처리
- 현재 선택된 결과가 있으면 해당 항목으로 이동
- 선택된 결과가 없으면 첫 번째 `.search-result`로 이동
- 결과가 없으면 아무 동작도 하지 않음
- 이동 전 `event.preventDefault()` 실행
- 이동은 `window.location.href = target.href`로 처리

선택 항목 판별은 기존 기능을 변경하지 않고 읽기만 합니다.

우선순위:

1. `.search-result[aria-selected="true"]`
2. `.search-result.is-active`
3. `.search-result.active`
4. `.search-result.selected`
5. 현재 포커스된 `.search-result`
6. 첫 번째 `.search-result`

## 배포

- 커밋: `e7915248370d6ea78df226dfc24d46b6f28b63b8`
- 메시지: `Fix search enter navigation`
- GitHub Push: 완료
- Vercel 자동 재배포: 완료

운영 자산 확인:

- `https://studyroute.co.kr/assets/js/search.js`: `200 OK`
- 응답 내 `selectedResult`: 존재
- 응답 내 `event.key !== "Enter"`: 존재
- 응답 내 `window.location.href = target.href`: 존재

## 운영 검증

검증 명령:

```powershell
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' scripts\verify_search_runtime.py
```

검증 결과: 통과.

운영 브라우저 확인:

- `script[src$="assets/js/search.js"]`: 존재
- `.search-trigger`: 존재
- `[data-search-panel]`: 존재
- `[data-search-input]`: 존재
- 돋보기 클릭 후 검색창 열림: 통과
- `수학` 입력 후 자동완성 결과 수: `8`
- Enter 입력 후 이동 방식: `Enter`
- Enter 입력 후 이동 경로: `/수학과외/`
- Console 오류: 없음
- Network 실패: 없음

검증 산출물:

- `reports/search_runtime_results.json`
- `reports/search-runtime-production.png`

## 결론

운영 사이트 기준으로 Enter 키 입력 시 선택된 검색 결과 또는 첫 번째 검색 결과로 이동하는 것을 확인했습니다.
