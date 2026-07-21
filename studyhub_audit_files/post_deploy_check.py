import sys
from pathlib import Path

from seo_audit.core import load_config, run_audit


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    cfg = load_config(root, mode="post", live_http=True)
    code, _summary = run_audit(cfg)
    sys.exit(code)

