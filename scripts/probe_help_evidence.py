#!/usr/bin/env python3
"""Explicit opt-in GETs to two reviewed public SAP Help URLs; no source/model calls."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.gateway import Gateway
from sap_optimizer.help_evidence import CATALOG
from sap_optimizer.transport import ProtocolError


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if not args.execute:
        print(json.dumps({'network_calls': 0, 'reviewed_ids': list(CATALOG), 'status': 'not_executed'}))
        return 0
    if not args.output:
        p.error('--execute requires --output (metadata only, no copied document bodies)')
    rows = []
    with tempfile.TemporaryDirectory(prefix='sap-help-public-') as directory:
        root = Path(directory)
        (root / 'sap-context.json').write_text(json.dumps({'version': 1, 'external_access': True,
            'product': 'ABAP', 'release': '7.54', 'official_documents': {}}))
        gateway = Gateway(root)
        for key in CATALOG:
            try:
                result = gateway.call('sap_help_document', {'document_id': key})
                data = result['data']
                rows.append({'id': key, 'source_url': result['source_url'], 'body_retrieved': result['body_retrieved'],
                             'applicability_verified': result['applicability_verified'],
                             'declared_scope_comparison': result['declared_scope_comparison'],
                             'observed_body_chars': len(data['content']),
                             **{k: data[k] for k in ('title', 'observed_title', 'declared_product', 'declared_release',
                                  'http_status', 'access', 'retrieved_at_utc', 'response_sha256', 'body_sha256', 'body_validation')}})
            except ProtocolError as exc:
                rows.append({'id': key, 'body_retrieved': False, 'failure': str(exc)})
    report = {'calls': rows, 'model_calls': 0, 'actual_cost_usd': None,
              'limitations': ['Two ABAP 7.54 keyword pages only', 'No FI/CO/MM/SD product-error coverage certified',
                              'No SAP Note/KBA body access', 'No general Help Portal search']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if all(r['body_retrieved'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
