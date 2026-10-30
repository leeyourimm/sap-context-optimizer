#!/usr/bin/env python3
"""Offline pinned public corpus evaluation. Does not call models or SAP services."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.public_validation import evaluate_corpus
from scripts.check_claude_runtime import inspect_runtime


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    report = evaluate_corpus(ROOT)
    report["claude_runtime"] = inspect_runtime()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("verified_upstream_files", "objects", "indexed_files", "passed", "total",
                                            "missing_required_objects", "missing_required_ranges", "model_calls", "billing_tokens")}, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
