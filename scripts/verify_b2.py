#!/usr/bin/env python3
"""Offline B2 reproducibility check. Never launches a model or sends HTTP."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.compact import compact, expand, size_breakdown
from sap_optimizer.repository import Repository
from sap_optimizer.public_validation import verify_corpus, corpus_policy
from scripts.check_claude_runtime import inspect_runtime


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    manifest = verify_corpus(ROOT)
    result = Repository(ROOT, corpus_policy(manifest)).search('acceptTravel')
    packed = compact(result)
    if expand(packed) != result:
        raise RuntimeError('Lossless contract failed')
    synthetic = Repository(ROOT, json.loads((ROOT / 'examples/b1-local-policy.json').read_text())).search('find_receipt')
    report = {'synthetic_279_char_case': size_breakdown(synthetic), 'synthetic_source_chars': synthetic['source_chars'], 'fixture': 'pinned_public_RAP100', 'default': size_breakdown(result),
              'experimental_compact': size_breakdown(packed), 'lossless_roundtrip': True,
              'runtime': inspect_runtime(), 'real_claude_e2e': 'unexecuted', 'model_calls': 0,
              'token_savings': None, 'answer_accuracy': None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
