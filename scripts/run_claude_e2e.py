#!/usr/bin/env python3
"""Default: read-only preflight. --execute additionally requires explicit approved manifest."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.claude_e2e import RuntimeNotReady, preflight, run
from sap_optimizer.policy import PolicyError


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--approval", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not args.execute:
        print(json.dumps(preflight(), indent=2))
        return 0
    if not args.approval or not args.output:
        p.error("--execute requires --approval and a NEW --output directory")
    try:
        report = run(ROOT, json.loads(args.approval.read_text()), args.output)
    except RuntimeNotReady as exc:
        print(json.dumps({"status": "runtime_not_ready", "preflight": exc.report,
                          "action": "No model invocation attempted; use approved provisioned runtime"}))
        return 1
    except (PolicyError, OSError, ValueError) as exc:
        # Do not expose CLI/provider stderr or arbitrary input values.
        print(json.dumps({"status": "refused_or_failed", "error_type": type(exc).__name__,
                          "action": "Inspect local protected reports; no automatic retry/login/install"}))
        return 1
    print(json.dumps({"status": "completed_pending_manual_evaluation", "runs": len(report["runs"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
