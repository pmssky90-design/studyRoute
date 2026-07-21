from pathlib import Path


VERIFY = Path(r"C:\Projects\studyhub\verification")
REPORT = VERIFY / "final_report.md"

REPORT.write_text(
    """# StudyHub 배포/색인 감사 최종 보고

감사 일시: 2026-07-12 KST
대상: `C:\\Projects\\studyhub`, `https://studyhub.co.kr`, `https://www.studyhub.co.kr`
주의: 요청대로 로컬/배포 설정을 수정하지 않고 감사 산출물만 생성했습니다.

## 1. 대표 도메인 최종 판정

대표 도메인은 `https://studyhub.co.kr`로 판정합니다.

근거:
- `config.py`의 `SITE_DOMAIN = "studyhub.co.kr"`, `SITE_URL = "https://studyhub.co.kr"`
- sitemap 9,612개 URL host가 모두 `studyhub.co.kr`
- robots.txt의 Sitemap이 `https://studyhub.co.kr/sitemap.xml`
- canonical, og:url, JSON-LD host 불일치 0건
- `https://studyhub.co.kr` 실제 응답 200

## 2. 네이버에 등록해야 할 정확한 사이트 주소

네이버 서치어드바이저에는 `https://studyhub.co.kr` 하나를 대표 속성으로 등록하는 것을 권고합니다.

`https://www.studyhub.co.kr`도 200으로 열리지만 canonical/sitemap/robots가 모두 non-www를 가리키므로 대표 등록 주소로는 부적합합니다. 기존에 www 속성이 등록되어 있다면 소유 확인 상태와 제출 sitemap을 확인한 뒤 non-www 대표 속성으로 통합 관리하는 것이 좋습니다.

## 3. 현재 www/non-www 일관성 여부

불일치가 있습니다. `www`가 `non-www`로 리다이렉트되지 않고 별도 200 응답을 냅니다.

이 상태는 P0입니다. 같은 콘텐츠가 `https://studyhub.co.kr/`와 `https://www.studyhub.co.kr/` 두 host에서 동시에 200으로 열립니다. 다만 www 페이지의 canonical은 non-www를 가리키므로 검색엔진이 대표 URL을 추론할 여지는 있습니다.

## 4. 4개 URL 리다이렉션 결과

| 입력 URL | 최종 URL | 상태 | 리다이렉션 |
|---|---:|---:|---:|
| `http://studyhub.co.kr` | `https://studyhub.co.kr/` | 200 | 1 |
| `http://www.studyhub.co.kr` | `https://www.studyhub.co.kr/` | 200 | 1 |
| `https://studyhub.co.kr` | `https://studyhub.co.kr/` | 200 | 0 |
| `https://www.studyhub.co.kr` | `https://www.studyhub.co.kr/` | 200 | 0 |

문제: `www` 두 URL이 `https://studyhub.co.kr/`로 수렴하지 않습니다.

## 5. sitemap host 일치 여부

정상입니다.

- `https://studyhub.co.kr/sitemap.xml`: 200, XML, UTF-8 OK, BOM 없음, URL 9,612개
- `https://www.studyhub.co.kr/sitemap.xml`: 200, XML, 내부 URL host는 모두 `studyhub.co.kr`
- 중복 URL 0건
- sitemap only URL 0건
- output only page 0건
- sitemap URL 50,000개/50MB 제한 이내

## 6. canonical host 일치 여부

정상입니다.

- canonical 누락/중복/host mismatch: 0건
- 한글 URL percent-encoding까지 정규화해 비교했습니다.
- 404.html은 noindex 예외로 분리했습니다.

## 7. robots host 일치 여부

정상입니다.

- `https://studyhub.co.kr/robots.txt`: 200
- `https://www.studyhub.co.kr/robots.txt`: 200
- `Disallow: /` 없음
- Yeti/NaverBot 차단 없음
- Sitemap: `https://studyhub.co.kr/sitemap.xml`

## 8. JSON-LD host 일치 여부

정상입니다.

- JSON-LD host 오류: 0건

## 9. HTTP 404/500 수

전수 HTTP 검사 결과 오류 0건입니다.

- 검사 URL: 9,614개
- 상태 코드: 200 = 9,614개
- 최종 host: `studyhub.co.kr` = 9,614개

## 10. sitemap 누락 페이지 수

0건입니다.

## 11. 내부 링크 오류 수

0건입니다.

## 12. 고아 페이지 수

3,334건입니다.

HTTP로는 200이고 sitemap에도 존재하지만, 홈에서 내부 링크 그래프를 따라 도달되지 않는 페이지가 많습니다. 네이버 색인을 막는 치명 오류는 아니지만, 크롤링 우선순위와 발견성에는 불리할 수 있습니다.

## 13. noindex 페이지 수

0건입니다.

404.html의 `noindex,follow`는 정상 예외로 처리했습니다.

## 14. title 중복률

중복 title 행 2건입니다.

- `output/index.html`
- `output/전국과외/index.html`
- title: `전국과외`

## 15. description 중복률

중복 description 행 2건입니다.

- `output/index.html`
- `output/전국과외/index.html`
- description: `전국과외 | StudyHub`

## 16. 본문 유사도 90% 이상 페이지 수

전수 exact duplicate 기준 0건입니다.

이번 산출물은 exact hash 기준입니다. 80/90% fuzzy 유사도는 별도 대형 비교 작업이 필요하지만, 현재 exact duplicate는 발견되지 않았습니다.

## 17. 네이버 색인을 막을 수 있는 치명 오류

P0:
- `www.studyhub.co.kr`가 `studyhub.co.kr`로 301 리다이렉트되지 않고 200으로 열림

현재 sitemap/canonical/robots는 non-www로 정리되어 있으므로 색인 차단보다는 대표 URL 충돌/중복 관리 리스크입니다.

## 18. 네이버 색인에 노출될 수 있는 잔여 문제

P2/P3:
- 고아 페이지 3,334건
- 얇거나 placeholder 의심 페이지 52건
- 홈과 `/전국과외/`의 title/description 중복 2건씩

## 19. EduGuide와 다른 핵심 요소

EduGuide:
- `https://www.eduguide.kr/`는 200
- canonical은 `https://eduguide.kr/`
- sitemap 1,621개

StudyHub:
- `https://www.studyhub.co.kr/`는 200
- canonical은 `https://studyhub.co.kr/`
- sitemap 9,612개

두 사이트 모두 www에서 canonical은 non-www를 가리키지만, StudyHub는 URL 규모가 훨씬 커서 www/non-www 200 중복의 운영 리스크가 더 큽니다.

## 20. 수정 우선순위

P0:
- `www.studyhub.co.kr` 전체를 `https://studyhub.co.kr`로 301 리다이렉트

P1:
- Vercel 또는 DNS/도메인 설정에서 www/non-www canonical host 강제 규칙 추가
- 네이버 서치어드바이저 속성은 `https://studyhub.co.kr` 기준으로 sitemap 제출

P2:
- 고아 페이지 3,334건의 내부 링크 경로 보강
- `output/index.html`과 `output/전국과외/index.html` 중복 title/description 정리

P3:
- placeholder 의심/얇은 페이지 52건 콘텐츠 점검
- EduGuide처럼 대표 URL 정책을 문서화하고 배포 전 검증 스크립트에 host 수렴 검사를 고정

## 생성 산출물

`C:\\Projects\\studyhub\\verification`에 요청 산출물을 생성했습니다. 주요 파일:

- `host_audit.xlsx`
- `redirect_audit.xlsx`
- `sitemap_audit.xlsx`
- `canonical_errors.xlsx`
- `robots_errors.xlsx`
- `jsonld_host_errors.xlsx`
- `og_url_errors.xlsx`
- `broken_internal_links.xlsx`
- `orphan_pages.xlsx`
- `http_status_errors.xlsx`
- `full_url_audit.csv`
- `studyhub_vs_eduguide_comparison.xlsx`
- `summary.json`
""",
    encoding="utf-8",
)
print(REPORT)
