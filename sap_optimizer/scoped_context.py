"""Explicit range-scoped views; all deferred records remain snapshot-addressable."""
from collections import Counter
import copy

from .policy import PolicyError, bounded_integer


def search_scoped(repo, query):
    result = copy.deepcopy(repo.search(query))
    unresolved = result['unresolved_references']
    in_range = [edge for edge in unresolved if any(s['path'] == edge['path'] and
                s['start_line'] <= edge['line'] <= s['end_line'] for s in result['results'])]
    result['unresolved_references'] = in_range
    diagnostics = result.pop('diagnostics')
    result['diagnostics_summary'] = {'total': len(diagnostics),
        'by_status': dict(Counter(d.get('status', 'unknown') for d in diagnostics)),
        'details_deferred': bool(diagnostics), 'tool': 'sap_repo_diagnostics_page'}
    objects = sorted({s['object']['id'] for s in result['results'] if s.get('object')})
    result['reference_scope'] = {'selection': 'returned_original_line_ranges_only',
        'selected_unresolved_count': len(in_range), 'seed_object_unresolved_count': len(unresolved),
        'deferred_unresolved_count': len(unresolved) - len(in_range), 'object_ids': objects,
        'details_tool': 'sap_repo_references_page', 'expected_snapshot': result['snapshot'],
        'warning': 'Deferred does not mean absent or irrelevant. Inspect object-level references and diagnostics before changes.'}
    # Counts from the full legacy format do not describe this distinct view.
    result.pop('serialized_chars', None)
    result.pop('serialized_bytes', None)
    return result


def page(repo, kind, expected_snapshot, offset=0, limit=20, object_id=None, direction='outgoing', resolution='all'):
    bounded_integer(offset, 0, 1_000_000)
    bounded_integer(limit, 1, 100)
    repo.refresh()
    if not isinstance(expected_snapshot, str) or expected_snapshot != repo.signature:
        raise PolicyError('STALE_SOURCE: detail page requires current snapshot; search again')
    if kind == 'diagnostics':
        records = repo.diagnostics
    else:
        if not isinstance(object_id, str) or object_id not in repo.objects:
            raise PolicyError('Object not in current validated snapshot')
        if direction not in ('outgoing', 'incoming') or resolution not in ('all', 'unresolved'):
            raise PolicyError('Invalid reference scope')
        records = [e for e in repo.edges if (e['source_object'] == object_id if direction == 'outgoing'
                    else object_id in e['target_objects']) and (resolution == 'all' or e['resolution'] != 'resolved_in_snapshot')]
    selected = records[offset:offset + limit]
    return {'snapshot': repo.signature, 'kind': kind, 'object_id': object_id,
            'direction': direction if kind != 'diagnostics' else None, 'resolution': resolution,
            'offset': offset, 'limit': limit, 'total': len(records), 'records': selected,
            'next_offset': offset + len(selected) if offset + len(selected) < len(records) else None,
            'coverage': 'Only supported direct syntax; unresolved/external is not proof of absence',
            'untrusted_data': True}
