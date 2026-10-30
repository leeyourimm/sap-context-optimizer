"""B2.1 contracts: no real Claude or model calls, no HTTP except explicit mock transport."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sap_optimizer.claude_e2e import approval, execution_plan, failure_reason, preflight, prepare, run, summarize
from sap_optimizer.evidence_validation import review_gate, validate_case
from sap_optimizer.gateway import Gateway
from sap_optimizer.help_evidence import CATALOG, PageText
from sap_optimizer.policy import PolicyError
from sap_optimizer.public_validation import CORPUS, corpus_policy, evaluate_result, verify_corpus
from sap_optimizer.repository import Repository
from sap_optimizer.scoped_context import page, search_scoped

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / CORPUS


class ScopedContracts(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(ROOT, corpus_policy(verify_corpus(ROOT)))

    def test_code_hash_relations_and_required_ranges_unchanged(self):
        full = self.repo.search('acceptTravel')
        scoped = search_scoped(self.repo, 'acceptTravel')
        self.assertEqual(scoped['results'], full['results'])
        self.assertEqual(scoped['omitted_ranges'], full['omitted_ranges'])
        self.assertEqual(scoped['snapshot'], full['snapshot'])
        self.assertLess(len(scoped['unresolved_references']), len(full['unresolved_references']))
        case = next(c for c in json.loads((CORPUS_PATH / 'cases.json').read_text())['cases'] if c['id'] == 'rap-action')
        self.assertTrue(evaluate_result(ROOT, case, scoped)['passed'])
        self.assertTrue(scoped['reference_scope']['deferred_unresolved_count'])
        self.assertTrue(scoped['diagnostics_summary']['details_deferred'])

    def test_all_unresolved_pages_and_diagnostics_exactly_recoverable(self):
        full = self.repo.search('acceptTravel')
        scoped = search_scoped(self.repo, 'acceptTravel')
        def fetch(kind, **kwargs):
            records, offset = [], 0
            while True:
                result = page(self.repo, kind, scoped['snapshot'], offset=offset, limit=3, **kwargs)
                records += result['records']
                if result['next_offset'] is None:
                    return records
                self.assertGreater(result['next_offset'], offset)
                offset = result['next_offset']
        edges = [e for obj in scoped['reference_scope']['object_ids']
                 for e in fetch('references', object_id=obj, resolution='unresolved')]
        self.assertEqual(sorted(map(json.dumps, edges)), sorted(map(json.dumps, full['unresolved_references'])))
        self.assertEqual(fetch('diagnostics'), full['diagnostics'])

    def test_page_limits_unknown_object_and_stale_snapshot_fail_closed(self):
        result = search_scoped(self.repo, 'acceptTravel')
        for extra in ({'offset': -1}, {'offset': True}, {'limit': 0}, {'limit': 101}, {'limit': False}):
            with self.subTest(extra=extra), self.assertRaises(PolicyError):
                page(self.repo, 'diagnostics', result['snapshot'], **extra)
        with self.assertRaises(PolicyError):
            page(self.repo, 'diagnostics', '0' * 64)
        with self.assertRaises(PolicyError):
            page(self.repo, 'references', result['snapshot'], object_id='../../private')

    def test_detail_incoming_edges_match_existing_api(self):
        scoped = search_scoped(self.repo, 'acceptTravel')
        obj = 'BDEF:ZRAP100_R_TRAVELTP_SOL'
        result = page(self.repo, 'references', scoped['snapshot'], object_id=obj, direction='incoming', limit=100)
        self.assertEqual(result['records'], self.repo.references(obj)['incoming'])

    def test_actual_stdio_scoped_and_policy_denial(self):
        task = json.loads((ROOT / 'experiments/b2/tasks.json').read_text())['tasks'][0]
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            prepare(ROOT, workspace, 'B1', task)
            request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': 'sap_repo_search_scoped', 'arguments': {'query': 'acceptTravel'}}}
            process = subprocess.run([sys.executable, str(workspace / 'scripts/sap_context.py'), 'serve'], cwd=workspace,
                                     input=json.dumps(request) + '\n', text=True, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            response = json.loads(process.stdout)['result']
            self.assertFalse(response['isError'])
            data = response['structuredContent']
            self.assertEqual(json.loads(response['content'][0]['text']), data)
            gateway = Gateway(workspace)
            details = gateway.call('sap_repo_diagnostics_page', {'expected_snapshot': data['snapshot'], 'limit': 2})
            self.assertLessEqual(len(details['records']), 2)
            self.assertFalse((workspace / '.sap-context').exists())
            policy = json.loads((workspace / 'sap-context.json').read_text())
            policy['local_repository']['allow_model_context'] = False
            (workspace / 'sap-context.json').write_text(json.dumps(policy))
            for name, args in [('sap_repo_search_scoped', {'query': 'private'}),
                               ('sap_repo_diagnostics_page', {'expected_snapshot': data['snapshot']}),
                               ('sap_repo_references_page', {'expected_snapshot': data['snapshot'], 'object_id': 'CLAS:X'})]:
                with self.subTest(name=name), self.assertRaises(PolicyError):
                    gateway.call(name, args)

    def test_index_change_invalidates_detail_page(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            shutil.copytree(ROOT / 'examples/abapgit', workspace / 'src')
            repo = Repository(workspace, {'version': 1, 'external_access': False,
                'local_repository': {'roots': ['src']}})
            result = search_scoped(repo, 'find_receipt')
            path = workspace / result['results'][0]['path']
            path.write_bytes(path.read_bytes() + b'\n* changed snapshot\n')
            with self.assertRaises(PolicyError):
                page(repo, 'diagnostics', result['snapshot'])


class NativeReadContracts(unittest.TestCase):
    path = 'fugr/src/zabapgit_unit_test.fugr.z_abapgit_unit_test.abap'

    def trace(self, workspace, separator='→', tamper=False):
        staged = workspace / 'public_exports' / self.path
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes((CORPUS_PATH / self.path).read_bytes())
        lines = (CORPUS_PATH / self.path).read_text().splitlines()
        text = '\n'.join(f'{i + 1:6}{separator}' + line for i, line in enumerate(lines[:8]))
        if tamper:
            text = text.replace('FUNCTION', 'INVENTED')
        return [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'read-1', 'name': 'Read',
                'input': {'file_path': str(workspace / 'public_exports' / self.path)}}]}},
                {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'read-1', 'content': text}]}}]

    def test_native_read_and_MCP_same_original_line_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            task = {'required_ranges': [{'path': self.path, 'start': 1, 'end': 8}]}
            for separator in ('→', '\t'):
                report = summarize(self.trace(workspace, separator), task, CORPUS_PATH, workspace)
                self.assertTrue(report['mandatory_range_gate'])
                self.assertTrue(report['mandatory_range_observations'][0]['native_Read_original_lines_complete'])
                self.assertEqual(report['native_Read_observations'][0]['hash_origin'], 'approved_fixture_not_native_Read')
                self.assertIsNone(report['tool_result_text_payloads'][0]['model_input_tokens'])

    def test_native_read_tampering_or_unrecognized_format_not_certified(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            task = {'required_ranges': [{'path': self.path, 'start': 1, 'end': 8}]}
            for events in [self.trace(workspace, tamper=True), self.trace(workspace, separator=':')]:
                self.assertFalse(summarize(events, task, CORPUS_PATH, workspace)['mandatory_range_gate'])

    def test_native_outside_workspace_and_unmatched_results_not_read(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            events = self.trace(workspace)
            events[0]['message']['content'][0]['input']['file_path'] = '/etc/passwd'
            self.assertFalse(summarize(events, {}, CORPUS_PATH, workspace)['native_Read_observations'])
            events = self.trace(workspace)
            events[1]['message']['content'][0]['tool_use_id'] = 'spoofed'
            self.assertFalse(summarize(events, {}, CORPUS_PATH, workspace)['native_Read_observations'])

    def test_complementary_MCP_snippets_share_same_coverage_gate(self):
        lines = (CORPUS_PATH / self.path).read_text().splitlines(keepends=True)
        sha = hashlib.sha256((CORPUS_PATH / self.path).read_bytes()).hexdigest()
        records = [{'path': 'public_exports/' + self.path, 'sha256': sha, 'start_line': a, 'end_line': b,
                    'source': ''.join(lines[a - 1:b])} for a, b in [(1, 4), (5, 8)]]
        events = [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'x', 'name': 'mcp__sap-context__sap_repo_read'}]}},
                  {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'x', 'content': json.dumps(records)}]}}]
        report = summarize(events, {'required_ranges': [{'path': self.path, 'start': 1, 'end': 8}]}, CORPUS_PATH)
        self.assertTrue(report['mandatory_range_gate'])


class PlanContracts(unittest.TestCase):
    def manifest(self, filename='approval-smoke.example.json'):
        result = json.loads((ROOT / 'experiments/b2' / filename).read_text())
        result.update(approved_public_model_calls=True, approved_runtime_isolated=True, approved_by='mock-only',
                      model='mock-model', expected_cli_version='1.2.3')
        return result

    def test_smoke_exactly_one_task_and_one_arm(self):
        value = approval(self.manifest())
        self.assertEqual(execution_plan(value), [(0, 'B1')])
        for change in ({'repetitions': 6}, {'task_ids': ['keyword-document', 'fi']}, {'task_ids': False}):
            with self.subTest(change=change), self.assertRaises(PolicyError):
                approval(value | change)

    def test_counterbalance_covers_all_orders_and_positions(self):
        from collections import Counter
        value = approval(self.manifest('approval-counterbalanced.example.json'))
        plan = execution_plan(value)
        orders = [tuple(a for r, a in plan if r == n) for n in range(6)]
        self.assertEqual(len(set(orders)), 6)
        for position in range(3):
            self.assertEqual(Counter(o[position] for o in orders), {'A': 2, 'B0': 2, 'B1': 2})
        with self.assertRaises(PolicyError):
            approval(value | {'repetitions': 1})

    def test_failure_and_model_identity_causes_separate(self):
        base = {'terminal_subtype': 'success', 'invalid_events': 0, 'terminal_result_count': 1, 'execution_success': True}
        self.assertIsNone(failure_reason(base, 0, False, 0))
        self.assertEqual(failure_reason(base, None, True, 0), 'wall_timeout')
        self.assertEqual(failure_reason(base | {'terminal_subtype': 'error_max_budget_usd'}, 1, False, 0), 'error_max_budget_usd')
        self.assertEqual(failure_reason(base | {'terminal_subtype': 'error_max_turns'}, 1, False, 0), 'error_max_turns')
        self.assertEqual(failure_reason(base | {'model_identity_match': False}, 0, False, 0), 'model_identity_mismatch')
        self.assertEqual(failure_reason(base, 0, False, 1), 'malformed_stream')
        self.assertEqual(failure_reason(base, 1, False, 0), 'process_nonzero_inspect_private_stderr')

    def test_observed_model_mismatch_and_unknown_usage_not_assumed(self):
        report = summarize([{'type': 'result', 'uuid': 'x', 'subtype': 'success', 'is_error': False,
                             'modelUsage': {'other-model': {'inputTokens': 8}}}], {'model': 'approved-model'}, CORPUS_PATH)
        self.assertFalse(report['model_identity_match'])
        self.assertIsNone(report['provider_reported_cost_usd'])
        self.assertIsNone(summarize([], {'model': 'approved-model'}, CORPUS_PATH)['model_identity_match'])

    def test_read_only_default_json_auth_and_help_detection_not_semantics(self):
        from sap_optimizer.claude_e2e import REQUIRED_FLAGS
        responses = [subprocess.CompletedProcess([], 0, '1.2.3', ''),
                     subprocess.CompletedProcess([], 0, ' '.join(REQUIRED_FLAGS), ''),
                     subprocess.CompletedProcess([], 0, '{"loggedIn":true}', '')]
        with patch('shutil.which', return_value='/mock/claude'), patch('subprocess.run', side_effect=responses) as calls:
            result = preflight()
            self.assertTrue(result['ready'])
            self.assertFalse(result['flag_semantics_verified'])
            self.assertEqual(calls.call_args_list[-1].args[0], ['/mock/claude', 'auth', 'status'])
        responses[-1] = subprocess.CompletedProcess([], 0, '[]', '')
        with patch('shutil.which', return_value='/mock/claude'), patch('subprocess.run', side_effect=responses):
            self.assertFalse(preflight()['ready'])

    def test_single_smoke_mock_process_and_no_billing_cap_claim(self):
        from sap_optimizer.claude_e2e import REQUIRED_FLAGS
        import os
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            executable = base / 'claude'
            executable.write_text('#!' + sys.executable + '\n' + '''import sys,json
if '--version' in sys.argv: print('1.2.3')
elif '--help' in sys.argv: print(''' + repr(' '.join(REQUIRED_FLAGS)) + ''')
elif 'auth' in sys.argv:
 if '--json' in sys.argv: sys.exit(2)
 print('{"loggedIn":true}')
else:
 sys.stdin.read()
 print(json.dumps({'type':'result','uuid':'mock-only','subtype':'success','is_error':False,'total_cost_usd':0.01,'modelUsage':{'mock-model':{'inputTokens':2}}}))
''')
            executable.chmod(0o700)
            with patch.dict(os.environ, {'PATH': str(base) + os.pathsep + os.environ['PATH']}):
                report = run(ROOT, self.manifest(), base / 'output')
            self.assertEqual(len(report['runs']), 1)
            self.assertEqual(report['runs'][0]['arm'], 'B1')
            self.assertFalse(report['billing_cap_guaranteed'])
            self.assertIsNone(report['invoice_reconciliation'])
            self.assertIsNone(report['runs'][0]['answer_correctness'])
            self.assertFalse(report['runs'][0]['provider_cost_exceeds_client_budget'])


class ProductEvidenceContracts(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((ROOT / 'experiments/b2/product-cases.json').read_text())['cases']
        self.case = copy.deepcopy(self.cases[0])
        # Synthetic HTTP contract body, never presented as a real SAP fixture.
        self.html = '<title>' + CATALOG[self.case['document_id']]['title'] + '</title><p>' + 'System Fields ' + ' '.join(self.case['supporting_quotes']) + ' Calls or registers a function module ' * 10 + '</p>'
        parser = PageText()
        parser.feed(self.html)
        content = ' '.join(' '.join(parser.parts).split())
        self.case['body_sha256'] = hashlib.sha256(content.encode()).hexdigest()
        outer = self
        class HTTP:
            def request(self, url, **kwargs):
                self.url = url
                return 200, {'Content-Type': 'text/html'}, outer.html.encode()
        self.http = HTTP()

    def test_concrete_module_cases_pending_not_fake_accuracy_oracle(self):
        pending = [c for c in self.cases if c['group'] == 'module_product_accuracy']
        self.assertEqual({c['module'] for c in pending}, {'FI', 'CO', 'MM', 'SD'})
        for case in pending:
            with self.subTest(case=case['id']), patch.object(self.http, 'request') as request:
                result = validate_case(case, self.http)
                self.assertFalse(result['eligible_for_accuracy_review'])
                self.assertIsNone(result['answer_accuracy'])
                self.assertIsNone(case['source_url'])
                self.assertEqual(case['scope']['release'], '2022')
                self.assertEqual(case['scope']['deployment'], 'on-premise')
                request.assert_not_called()
                self.assertIsNone(review_gate(case, result, {})['accuracy_pass'])

    def test_original_body_section_hash_conditions_and_manual_review(self):
        evidence = validate_case(self.case, self.http)
        self.assertTrue(evidence['eligible_for_accuracy_review'])
        self.assertFalse(evidence['applicability_verified'])
        self.assertIsNone(evidence['answer_accuracy'])
        self.assertIsNone(review_gate(self.case, evidence, {})['accuracy_pass'])
        fields = ['claims_supported', 'scope_conditions_matched', 'required_source_complete',
                  'facts_and_inference_separated', 'no_fabricated_claim', 'no_security_violation']
        review = {k: True for k in fields} | {'human_reviewers': ['synthetic-contract-reviewer'],
                  'source_url': self.case['source_url'], 'section': self.case['section']}
        self.assertTrue(review_gate(self.case, evidence, review)['accuracy_pass'])
        self.assertFalse(review_gate(self.case, evidence, review | {'no_security_violation': False})['accuracy_pass'])
        self.assertFalse(review_gate(self.case, evidence, review | {'section': 'wrong'})['accuracy_pass'])
        self.assertFalse(review_gate(self.case, evidence | {'case_id': 'different-case'}, review)['accuracy_pass'])

    def test_drift_missing_section_and_scope_mismatch_block_accuracy(self):
        self.assertEqual(validate_case(self.case | {'body_sha256': '0' * 64}, self.http)['evidence_state'], 'body_hash_changed_re_review_required')
        self.assertEqual(validate_case(self.case | {'section': 'NONEXISTENT'}, self.http)['evidence_state'], 'section_support_not_found')
        changed = copy.deepcopy(self.case)
        changed['scope']['release'] = '2023'
        with self.assertRaises(PolicyError):
            validate_case(changed, self.http)
        self.assertEqual(validate_case(self.case)['evidence_state'], 'live_revalidation_not_run')

    def test_case_free_URL_and_login_shell_not_treated_as_support(self):
        with self.assertRaises(PolicyError):
            validate_case(self.case | {'source_url': 'https://evil.test/private'}, self.http)
        self.html = '<title>Login</title>' + 'Please log in ' * 60
        self.assertFalse(validate_case(self.case, self.http)['eligible_for_accuracy_review'])

class AdditionalCompatibilityTests(unittest.TestCase):
    def test_runtime_refusal_carries_safe_preflight_diagnostic(self):
        from sap_optimizer.claude_e2e import RuntimeNotReady
        value = PlanContracts().manifest()
        report = {'ready': False, 'version': None, 'executable_present': False, 'model_calls': 0}
        with patch('sap_optimizer.claude_e2e.preflight', return_value=report), patch('subprocess.Popen') as process:
            with self.assertRaises(RuntimeNotReady) as caught:
                run(ROOT, value, Path('/unused'))
            self.assertEqual(caught.exception.report, report)
            process.assert_not_called()

    def test_help_substring_is_not_flag_availability(self):
        from sap_optimizer.claude_e2e import REQUIRED_FLAGS
        text = ' '.join(f if f != '--tools' else '--tools-example' for f in REQUIRED_FLAGS)
        responses = [subprocess.CompletedProcess([], 0, '1.2.3', ''),
                     subprocess.CompletedProcess([], 0, text, ''),
                     subprocess.CompletedProcess([], 0, '{"loggedIn":true}', '')]
        with patch('shutil.which', return_value='/mock/claude'), patch('subprocess.run', side_effect=responses):
            result = preflight()
            self.assertFalse(result['supported_flags'])
            self.assertFalse(result['ready'])

    def test_live_oracle_hash_change_refuses_before_preflight(self):
        value = PlanContracts().manifest()
        with patch('sap_optimizer.claude_e2e.preflight') as runtime:
            with self.assertRaises(PolicyError):
                run(ROOT, value | {'evidence_suite_sha256': '0' * 64}, Path('/unused'))
            runtime.assert_not_called()

    def test_native_changed_staged_source_not_certified(self):
        case = NativeReadContracts()
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            events = case.trace(workspace)
            path = workspace / 'public_exports' / case.path
            path.write_bytes(path.read_bytes() + b'\n* changed after staging\n')
            result = summarize(events, {}, CORPUS_PATH, workspace)
            self.assertFalse(result['native_Read_observations'])

    def test_repeated_tool_inputs_are_not_semantic_retry_count(self):
        events = [{'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': 'one', 'name': 'mcp__sap-context__sap_repo_search_scoped', 'input': {'query': 'acceptTravel'}},
            {'type': 'tool_use', 'id': 'two', 'name': 'mcp__sap-context__sap_repo_search_scoped', 'input': {'query': 'acceptTravel'}}]}}]
        report = summarize(events, {}, CORPUS_PATH)
        self.assertEqual(report['repeated_identical_tool_inputs'], 1)
        self.assertIsNone(report['retry_count'])

class BudgetStopTests(unittest.TestCase):
    def test_reported_overrun_stops_without_followup_invocation(self):
        from types import SimpleNamespace
        value = PlanContracts().manifest() | {'per_run_budget_usd': .001}
        def fake(command, **kwargs):
            kwargs['stdout'].write(json.dumps({'type': 'result', 'uuid': 'mock-only',
                'subtype': 'success', 'is_error': False, 'total_cost_usd': .01}) + '\n')
            return SimpleNamespace(returncode=0, communicate=lambda *a, **k: None)
        with tempfile.TemporaryDirectory() as temp, patch('sap_optimizer.claude_e2e.preflight', return_value={'ready': True, 'version': '1.2.3'}), patch('subprocess.Popen', side_effect=fake) as process:
            output = Path(temp) / 'output'
            with self.assertRaises(PolicyError):
                run(ROOT, value, output)
            self.assertEqual(process.call_count, 1)
            report = json.loads((output / 'summary.json').read_text())
            self.assertEqual(report['runs'][0]['failure_reason'], 'provider_reported_client_budget_overrun')
            self.assertFalse(report['billing_cap_guaranteed'])
