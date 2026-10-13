#!/usr/bin/env python3
"""Convenience root launcher for Autonomous Web Research Synthesis Web Dashboard & REST Server.

Can be run directly:
  python run_server.py
  python run_server.py --port 8080 --mode mock
  python run_server.py --port 8080 --mode live --open-browser
"""

import sys
from pathlib import Path

# Ensure src is in search path
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from research_synthesis.server import main

if __name__ == "__main__":
    main()
