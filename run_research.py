#!/usr/bin/env python3
"""Convenience root launcher for Autonomous Web Research Synthesis CLI.

Can be run directly:
  python run_research.py "Next-Generation Solid-State Battery Commercialization"
  python run_research.py --interactive
"""

import sys
from pathlib import Path

# Ensure src is in search path
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from research_synthesis.cli import main

if __name__ == "__main__":
    main()
