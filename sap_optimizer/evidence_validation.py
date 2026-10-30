"""Verify human-authored original-body oracles; never judge model prose automatically."""
from .help_evidence import CATALOG, read_body
from .policy import PolicyError
from .transport import ProtocolError


def validate_case(case, http=None):
    base = {'case_id': case['id'], 'group': case['group'], 'answer_accuracy': None,
            'applicability_verified': False, 'eligible_for_accuracy_review': False}
    if case['status'] == 'evidence_not_acquired':
        return base | {'evidence_state': 'evidence_not_acquired', 'reason': 'No applicable original product passage; exclude from positive accuracy denominator'}
    doc = CATALOG.get(case.get('document_id'))
    if (not doc or case.get('source_url') != doc['url'] or
            (case['scope']['product'], case['scope']['release']) != (doc['product'], doc['release']) or
            not case.get('section') or not case.get('conditions') or not case.get('supporting_quotes')):
        raise PolicyError('Reviewed case must match catalog scope, section, conditions and original support')
    if http is None:
        return base | {'evidence_state': 'live_revalidation_not_run'}
    try:
        body = read_body(http, doc)
    except ProtocolError:
        return base | {'evidence_state': 'body_access_failed_or_changed'}
    if body['body_sha256'] != case['body_sha256']:
        return base | {'evidence_state': 'body_hash_changed_re_review_required'}
    text = body['content']
    start = text.find(case['section'])
    if start < 0 or not all(q in text[start:] for q in case['supporting_quotes']):
        return base | {'evidence_state': 'section_support_not_found'}
    return base | {'evidence_state': 'original_body_and_support_revalidated',
                   'eligible_for_accuracy_review': True, 'source_url': doc['url'],
                   'body_sha256': body['body_sha256'], 'section': case['section'],
                   'conditions': case['conditions'], 'retrieved_at_utc': body['retrieved_at_utc']}


def review_gate(case, evidence, review):
    """Review assertions must come from human SAP reviewers, not retrieval success."""
    if not evidence.get('eligible_for_accuracy_review'):
        return {'accuracy_pass': None, 'reason': 'evidence_unavailable_not_scored'}
    if any(evidence.get(k) != case.get(k) for k in ('source_url', 'section', 'body_sha256', 'conditions')) or evidence.get('case_id') != case['id']:
        return {'accuracy_pass': False, 'reason': 'oracle_evidence_binding_mismatch'}
    fields = ('claims_supported', 'scope_conditions_matched', 'required_source_complete',
              'facts_and_inference_separated', 'no_fabricated_claim', 'no_security_violation')
    reviewers = review.get('human_reviewers') if isinstance(review, dict) else None
    if (not isinstance(reviewers, list) or not reviewers or
            any(not isinstance(r, str) or not r.strip() for r in reviewers) or
            any(type(review.get(k)) is not bool for k in fields)):
        return {'accuracy_pass': None, 'reason': 'human_review_incomplete'}
    if review.get('source_url') != case['source_url'] or review.get('section') != case['section']:
        return {'accuracy_pass': False, 'reason': 'citation_scope_mismatch'}
    return {'accuracy_pass': all(review[k] for k in fields), 'reason': 'human_reviewed_not_model_judged'}
