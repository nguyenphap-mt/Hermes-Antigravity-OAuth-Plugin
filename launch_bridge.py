import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from bridge.server import run_server

if __name__ == "__main__":
    print("[*] Starting bridge on http://127.0.0.1:8100 ...")
    run_server(host="127.0.0.1", port=8100)
