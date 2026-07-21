# StudyHub Deployment Checks

## Folder Structure

- `pre_deploy_check.py`: local pre-deploy gate. Exits `1` when any P0 issue exists.
- `post_deploy_check.py`: live site audit after deployment. Checks `https://studyhub.co.kr` over HTTP.
- `deploy_guard.py`: upload gate. Runs `pre_deploy_check.py`; exits before upload when P0 exists.
- `cloudflare_build.py`: Cloudflare Pages build entrypoint. Runs `generator.py`, then `deploy_guard.py`.
- `seo_audit/core.py`: shared audit engine.
- `verification/`: generated audit reports.

## Local Usage

```powershell
python generator.py
python pre_deploy_check.py
```

If Python is not on PATH:

```powershell
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' generator.py
& 'C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe' pre_deploy_check.py
```

`pre_deploy_check.py` writes:

- `verification/host_audit.xlsx`
- `verification/redirect_audit.xlsx`
- `verification/canonical_errors.xlsx`
- `verification/robots_errors.xlsx`
- `verification/sitemap_audit.xlsx`
- `verification/http_status_errors.xlsx`
- `verification/broken_internal_links.xlsx`
- `verification/orphan_pages.xlsx`
- `verification/duplicate_titles.xlsx`
- `verification/duplicate_descriptions.xlsx`
- `verification/duplicate_content.xlsx`
- `verification/placeholder_pages.xlsx`
- `verification/summary.md`

## Deployment Gate

P0 blocks deployment and exits with code `1`.

P0 includes:

- representative URL conflict
- www/non-www mixed live host
- canonical error
- robots error
- sitemap error
- HTTP 404/500/timeout in live mode
- broken internal links
- output missing from sitemap
- sitemap URL missing from output

P1 is warning-only:

- orphan pages
- placeholder text
- duplicate title
- duplicate description
- duplicate or highly similar content

## Console Output

The scripts print one line per section:

```text
PASS 대표 URL
PASS sitemap
FAIL canonical
...
====================
P0 : 0
P1 : 5
P2 : 12
====================
READY FOR DEPLOY
```

If P0 is greater than zero, the last line is:

```text
DEPLOY BLOCKED
```

## Cloudflare Pages Setup

Set Cloudflare Pages build command to:

```bash
python cloudflare_build.py
```

Set output directory to:

```text
output
```

This makes Cloudflare run:

1. `generator.py`
2. `deploy_guard.py`
3. `pre_deploy_check.py`
4. upload `output` only if P0 is zero

Redirect status codes `301`, `302`, `307`, and `308` are all accepted. The representative URL check only requires:

- final URL is the configured representative URL
- final HTTP status is 200
- final host matches the representative host

## Optional Full Live HTTP Before Deploy

By default, pre-deploy checks local output for URL existence and only uses live HTTP for representative host convergence.

To force full live HTTP before deployment:

```powershell
$env:STUDYHUB_PRE_DEPLOY_LIVE_HTTP="1"
python pre_deploy_check.py
```

This is slower and checks the currently deployed site, so it is usually more useful after deployment.

## Post-Deploy Check

Run after Cloudflare deployment:

```powershell
python post_deploy_check.py
```

This performs live HTTP checks against `https://studyhub.co.kr` and fails if the deployed response differs from the local expectations.
