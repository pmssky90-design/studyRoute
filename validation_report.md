# StudyRoute Validation Report

## Validator

프로젝트 내 감사 도구 `scripts/audit_site.py`로 `output/` 전체를 재검사했다.

## 최종 요약

```text
Expected workbook pages: 1812
Generated content pages: 1812
Sitemap URLs: 1813
Critical: 0
High: 0
Medium: 4
Low: 6
```

## High 오류 결과

High 오류는 모두 해결됐다.

해결된 항목:

- 닫히지 않은 태그
- 잘못 중첩된 태그
- 잘못된 list 구조
- 잘못된 table 구조
- 잘못된 p/div 중첩으로 인한 outer document 파손
- 본문 내부 H1 중복으로 인한 H1 검사 오류

## 정상 확인 항목

- 페이지 개수
- 부모-자식 구조
- 12개 허브
- 내부 링크
- breadcrumb
- title
- H1
- canonical
- meta description
- Open Graph
- JSON-LD
- robots.txt
- sitemap.xml
- HTML 구조 High 오류

## 검증 명령

```powershell
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' generator.py
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' scripts\audit_site.py
```
