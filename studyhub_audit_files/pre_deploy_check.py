import os
import sys
from pathlib import Path

from seo_audit.core import load_config, run_audit


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    live_http = os.environ.get("STUDYHUB_PRE_DEPLOY_LIVE_HTTP", "0") == "1"
    cfg = load_config(root, mode="pre", live_http=live_http)
    code, _summary = run_audit(cfg)
    sys.exit(code)

