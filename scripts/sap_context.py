#!/usr/bin/env python3
"""Absolute entry point; subprocess current directory cannot change policy root."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.cli import main

if __name__ == "__main__":
    raise SystemExit(main(ROOT))
