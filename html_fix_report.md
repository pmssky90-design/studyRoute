# StudyRoute HTML Fix Report

## 작업 범위

이번 작업은 HTML 구조만 수정했다.

수정하지 않은 항목:

- 문장
- 문체
- 지역명
- 학교명
- 키워드
- 본문 텍스트
- 본문 순서

## 수정 방식

`generator.py`에 HTML fragment normalizer를 추가했다. 엑셀 B열 본문을 출력하기 직전에 태그 구조만 정규화한다.

적용한 구조 보정:

- 닫히지 않은 태그 자동 닫기
- 잘못 중첩된 태그 정리
- `<p>` 내부에 block 요소가 시작될 때 `<p>`를 먼저 닫기
- 연속 `<li>` 구조 정리
- `<li>`가 리스트 밖에 있을 때 리스트 컨테이너 보정
- `<td>` 또는 `<th>`가 `<tr>` 밖에 있을 때 table row 보정
- `<tr>`이 table 밖에 있을 때 table 보정
- 완전한 HTML 문서가 본문에 들어온 경우 `<body>` 내부만 삽입
- 본문에 이미 같은 키워드의 `<h1>`이 있으면 외부 H1 중복 출력 방지

## 수정된 파일

- `generator.py`
- `templates/pages/content.html`
- `html_fix_report.md`
- `validation_report.md`

## 검증 결과

최종 재검사에서 High 오류가 0이 됐다.

```text
Critical: 0
High: 0
Medium: 4
Low: 6
```

## 남은 항목

Medium 4건은 본문 길이가 짧거나 현저히 짧다는 콘텐츠 품질 항목이다. 본문 내용을 수정하지 않는 작업 범위에 따라 수정하지 않았다.

Low 6건은 미사용 CSS 추정 항목이다. HTML 구조 오류가 아니므로 이번 작업 범위에서 제외했다.
