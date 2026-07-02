# StudyRoute SITE_URL 검증 보고서

작성일: 2026-07-02

## 기준 URL

모든 절대 URL 기준:

```text
https://studyroute.co.kr
```

## 검사 범위

- `config.py`
- `generator.py`
- `templates/`
- `assets/`
- `output/`
- canonical
- JSON-LD
- Open Graph
- Twitter Card
- `robots.txt`
- `sitemap.xml`
- RSS / feed 파일 존재 여부

## 재빌드

아래 명령으로 전체 사이트를 재빌드했습니다.

```powershell
py generator.py
```

빌드 결과:

```text
StudyRoute build complete: C:\Projects\StudyRoute\output
```

## 검증 결과

검증 파일:

```text
reports/site_url_check.json
```

검사 수량:

- HTML 파일: 1,976
- canonical: 1,976
- og:url: 1,976
- og:image: 1,976
- twitter:image: 1,976
- JSON-LD URL / @id: 5,928
- robots.txt Sitemap URL: 1
- sitemap.xml URL: 1,976
- RSS / feed 파일: 0

## 오류 결과

잘못된 절대 URL:

```text
0건
```

## 수정 사항

이번 검사에서 잘못된 URL은 발견되지 않았으므로 추가 수정은 필요하지 않았습니다.

현재 `config.py`의 기준값은 다음과 같습니다.

```python
BASE_URL = "https://studyroute.co.kr"
```

## 최종 결론

canonical, JSON-LD, Open Graph, Twitter Card, robots.txt, sitemap.xml의 모든 절대 URL은 `https://studyroute.co.kr` 기준으로 정상 생성되어 있습니다.

RSS 또는 feed 파일은 현재 프로젝트에 존재하지 않습니다.
