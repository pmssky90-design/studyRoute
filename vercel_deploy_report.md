# StudyRoute Vercel Deploy Report

## Summary

- Vercel account: `pmssky90-7645`
- Vercel project: `studyroute`
- GitHub repository connected: `https://github.com/pmssky90-design/studyRoute.git`
- Deploy ID: `dpl_DCxeKR4tXtqUQTQ7uT7Bg3gLii9u`
- Build success: Yes
- Deploy success: Yes
- Deployment status: Ready
- Final deploy URL: `https://studyroute-theta.vercel.app`

## Build Settings

- Framework Preset: Other / Static
- Install Command: empty
- Build Command: `python3 generator.py`
- Output Directory: `output`

These settings match the project structure: `generator.py` builds static HTML into `output/`, and `requirements.txt` declares no external Python dependencies.

## Deployment Result

- Production deployment URL: `https://studyroute-9glshbgl8-pmssky90-7645s-projects.vercel.app`
- Production aliases:
  - `https://studyroute-theta.vercel.app`
  - `https://studyroute-pmssky90-7645s-projects.vercel.app`
  - `https://studyroute-pmssky90-7645-pmssky90-7645s-projects.vercel.app`
- Requested alias `studyroute.vercel.app`: unavailable because Vercel reported it is already in use.

## URL Checks

- Main `/`: 200
- `대전과외/`: 200
- `대구과외/`: 200
- `수학과외/`: 200
- Random detail `가양동과외/`: 200
- `robots.txt`: 200
- `sitemap.xml`: 200
- `favicon.ico`: 200
- Missing page `/this-page-should-404/`: 404

## Metadata Checks

Checked pages: main, `대전과외`, `대구과외`, `수학과외`, `가양동과외`.

- title: OK
- description: OK
- canonical: present
- JSON-LD: OK, includes `Organization`, `WebSite`, `WebPage`
- Open Graph: OK
- Twitter Card: OK

Note: canonical and social URLs currently point to `https://studyroute.co.kr`, as defined in `config.BASE_URL`. No custom domain was connected in this task.

## Responsive Checks

Chrome headless screenshots were generated successfully:

- Desktop: `reports/vercel-desktop.png`
- Tablet: `reports/vercel-tablet.png`
- Mobile: `reports/vercel-mobile.png`

All three rendered non-empty pages with the main StudyRoute UI visible.

## Verification Artifacts

- JSON verification result: `reports/vercel_verify_results.json`
- Verification script: `scripts/vercel_verify.py`

## Excluded Work

The following were not performed:

- Custom domain connection
- Gabia DNS
- Search Console
- Naver registration
- Cloudflare configuration

## Conclusion

Vercel 배포 완료
