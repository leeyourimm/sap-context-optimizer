#!/usr/bin/env python3
"""Offline scoped-context quality and wire-cost boundaries over unchanged public oracle."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.gateway import tool_result
from sap_optimizer.public_validation import CORPUS, corpus_policy, evaluate_result, verify_corpus
from sap_optimizer.repository import Repository
from sap_optimizer.scoped_context import page, search_scoped
from scripts.check_claude_runtime import inspect_runtime


def wire(value):
    return len((json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': tool_result(value)}, ensure_ascii=False) + '\n').encode())


def pages(repo, kind, snapshot, **kwargs):
    records, sizes, offset = [], [], 0
    while True:
        result = page(repo, kind, snapshot, offset=offset, limit=20, **kwargs)
        records.extend(result['records'])
        sizes.append(wire(result))
        if result['next_offset'] is None:
            return records, sizes
        offset = result['next_offset']


def evaluate():
    repo = Repository(ROOT, corpus_policy(verify_corpus(ROOT)))
    cases = json.loads((ROOT / CORPUS / 'cases.json').read_text())['cases']
    checks = []
    for case in cases:
        selected = search_scoped(repo, case['query'])
        # Scoped view uses the normal automatic expansion; apply the SAME source oracle.
        gate = evaluate_result(ROOT, case, selected)
        checks.append({'id': case['id'], **gate})
    full = repo.search('acceptTravel')
    scoped = search_scoped(repo, 'acceptTravel')
    if scoped['results'] != full['results'] or scoped['omitted_ranges'] != full['omitted_ranges']:
        raise RuntimeError('Scoped view changed source/required relations or omissions')
    diagnostics, detail_sizes = pages(repo, 'diagnostics', scoped['snapshot'])
    if diagnostics != full['diagnostics']:
        raise RuntimeError('Deferred diagnostics lost')
    retrieved_refs = []
    for obj in scoped['reference_scope']['object_ids']:
        records, sizes = pages(repo, 'references', scoped['snapshot'], object_id=obj, resolution='unresolved')
        retrieved_refs.extend(records)
        detail_sizes.extend(sizes)
    if sorted(map(json.dumps, retrieved_refs)) != sorted(map(json.dumps, full['unresolved_references'])):
        raise RuntimeError('Deferred unresolved references lost')
    return {'public_cases': checks, 'passed': sum(c['passed'] for c in checks), 'total': len(checks),
            'quality_basis': 'unchanged manually authored pinned public object/range oracle',
            'acceptTravel': {'default_wire_bytes': wire(full), 'scoped_initial_wire_bytes': wire(scoped),
                'default_calls': 1, 'scoped_initial_calls': 1, 'all_deferred_detail_calls': len(detail_sizes),
                'scoped_plus_all_details_wire_bytes': wire(scoped) + sum(detail_sizes),
                'unresolved_total': len(full['unresolved_references']),
                'unresolved_in_original_ranges': len(scoped['unresolved_references']),
                'diagnostic_count': len(diagnostics), 'all_deferred_records_recovered': True,
                'original_snippets_and_direct_relations_equal': True},
            'runtime': inspect_runtime(), 'real_Claude_E2E': 'unexecuted',
            'model_input_tokens': None, 'answer_accuracy': None, 'total_model_cost': None,
            'note': 'Deferred calls can cost more than one full response. Wire bytes are not billed tokens; quality impact requires a real run.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'total', 'acceptTravel', 'real_Claude_E2E')}, indent=2))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
