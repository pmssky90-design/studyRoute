import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from seo_audit.core import HttpClient, load_config, normalize_site_url, run_audit, write_xlsx


ROOT = Path(__file__).resolve().parent
LABEL_REPRESENTATIVE_URL = "\ub300\ud45c URL"
CAUSE_HOST_CONFLICT = "\ub300\ud45c URL \ucda9\ub3cc \ub610\ub294 www/non-www \ubbf8\uc218\ub834"


def quick_host_gate(cfg) -> int:
    client = HttpClient(cfg)
    expected = cfg.expected_base + "/"
    rows = []
    p0_rows = []
    for url in [
        f"http://{cfg.site_domain}",
        f"http://www.{cfg.site_domain}",
        f"https://{cfg.site_domain}",
        f"https://www.{cfg.site_domain}",
    ]:
        result = client.request(url)
        final_url = result.get("final_url") or ""
        final = urlparse(final_url)
        ok = result.get("status_code") == 200 and normalize_site_url(final_url, cfg) == expected
        row = {
            "issue_type": "host_canonicalization",
            "local_file": "",
            "original_url": url,
            "final_url": final_url,
            "status_code": result.get("status_code", ""),
            "detected_host": final.netloc,
            "expected_host": cfg.site_domain,
            "source_page": "",
            "detail": f"status={result.get('status_code')}; final={final_url}; expected={expected}; redirects={result.get('redirect_count')}; chain={result.get('redirect_chain')}; error={result.get('error')}",
            "severity": "INFO" if ok else "P0",
            "recommended_fix": "Final URL must be the representative URL and final HTTP must be 200. Redirect codes 301/302/307/308 are accepted.",
        }
        rows.append(row)
        if not ok:
            p0_rows.append(row)
    write_xlsx(cfg.verification_dir / "host_audit.xlsx", rows)
    if not p0_rows:
        return 0

    lines = [
        "# StudyHub Deploy Guard",
        "",
        "- Mode: deploy_guard",
        "- Gate only: True",
        "",
        "| Check | Result | P0 |",
        "|---|---:|---:|",
        f"| {LABEL_REPRESENTATIVE_URL} | FAIL | {len(p0_rows)} |",
        "",
        "## P0 Causes",
        "",
    ]
    for row in p0_rows:
        lines.extend(
            [
                f"- {LABEL_REPRESENTATIVE_URL}: {CAUSE_HOST_CONFLICT}",
                f"  - URL: `{row['original_url']}` -> `{row['final_url']}`",
                f"  - Detail: {row['detail']}",
            ]
        )
    lines.extend(
        [
            "",
            "```",
            f"P0 : {len(p0_rows)}",
            "P1 : 0",
            "P2 : 0",
            "```",
            "",
            "DEPLOY BLOCKED",
        ]
    )
    (cfg.verification_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8-sig")
    for row in p0_rows:
        print(f"FAIL {LABEL_REPRESENTATIVE_URL} {row['original_url']} -> {row['final_url']}")
    print("====================")
    print(f"P0 : {len(p0_rows)}")
    print("P1 : 0")
    print("P2 : 0")
    print("====================")
    print("DEPLOY BLOCKED")
    return 1


def main() -> int:
    os.environ["STUDYHUB_GATE_ONLY"] = "1"
    live_http = os.environ.get("STUDYHUB_PRE_DEPLOY_LIVE_HTTP", "0") == "1"
    cfg = load_config(ROOT, mode="pre", live_http=live_http)
    quick_code = quick_host_gate(cfg)
    if quick_code:
        print("deploy_guard: CLOUDFLARE UPLOAD BLOCKED")
        return quick_code
    code, _summary = run_audit(cfg)
    if code:
        print("deploy_guard: CLOUDFLARE UPLOAD BLOCKED")
        return code
    print("deploy_guard: READY FOR CLOUDFLARE UPLOAD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
