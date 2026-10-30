#!/usr/bin/env python3
"""Offline inventory by default. --execute revalidates only fixed public Help bodies."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.evidence_validation import validate_case
from sap_optimizer.transport import HTTP


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    cases = json.loads((ROOT / 'experiments/b2/product-cases.json').read_text())['cases']
    rows = [validate_case(c, HTTP() if args.execute else None) for c in cases]
    report = {'live_public_body_check_requested': args.execute, 'cases': rows, 'model_calls': 0,
              'model_answer_accuracy': None, 'module_accuracy_gap_cases': sum(c['status'] == 'evidence_not_acquired' for c in cases)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 1 if args.execute and any(r['evidence_state'] not in ('original_body_and_support_revalidated', 'evidence_not_acquired') for r in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
