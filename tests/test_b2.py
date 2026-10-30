"""B2 contracts use synthetic CLI streams and HTTP bodies; no real model calls."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sap_optimizer.claude_e2e import REQUIRED_FLAGS, approval, preflight, prepare, run, summarize
from sap_optimizer.compact import compact, expand, size_breakdown
from sap_optimizer.gateway import Gateway, serve, tool_result
from sap_optimizer.help_evidence import CATALOG
from sap_optimizer.policy import PolicyError, load_policy
from sap_optimizer.public_validation import CORPUS, corpus_policy, verify_corpus
from sap_optimizer.repository import Repository
from sap_optimizer.transport import ProtocolError

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / CORPUS


class HelpContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {"version": 1, "external_access": True, "product": "ABAP", "release": "7.54"}
        self.calls = []
        self.body = ('<html><title>CALL FUNCTION - ABAP Keyword Documentation</title><article>' +
                     'Calls or registers a function module. System Fields. ' * 10 + '</article></html>')
        self.save()
        outer = self

        class HTTP:
            def request(self, url, **kw):
                outer.calls.append(url)
                return 200, {"Content-Type": "text/html"}, outer.body.encode()
        self.g = Gateway(self.root, HTTP())

    def save(self):
        (self.root / 'sap-context.json').write_text(json.dumps(self.policy))

    def test_catalog_offline_and_gap_explicit(self):
        self.policy['external_access'] = False
        self.save()
        data = self.g.call('sap_help_catalog', {})
        self.assertEqual(len(data['documents']), 2)
        self.assertTrue(any('FI/CO/MM/SD' in gap for gap in data['gaps']))
        self.assertFalse(self.calls)

    def test_public_body_and_hash_not_applicability_certificate(self):
        result = self.g.call('sap_help_document', {'document_id': 'abap-754-call-function'})
        self.assertTrue(result['body_retrieved'])
        self.assertFalse(result['applicability_verified'])
        self.assertEqual(result['declared_scope_comparison'], 'declared_match')
        self.assertEqual(result['data']['response_sha256'], hashlib.sha256(self.body.encode()).hexdigest())
        self.assertEqual(result['data']['body_validation'], 'reviewed_title_and_markers')
        self.assertEqual(self.calls, [CATALOG['abap-754-call-function']['url']])

    def test_wrong_release_never_verified(self):
        self.policy['release'] = '2023'
        self.save()
        result = self.g.call('sap_help_document', {'document_id': 'abap-754-call-function'})
        self.assertEqual(result['declared_scope_comparison'], 'declared_mismatch')
        self.assertFalse(result['applicability_verified'])

    def test_long_login_shell_and_wrong_title_and_missing_marker_rejected(self):
        for body in ['<title>Login</title>' + 'Please log in ' * 80,
                     '<title>CALL FUNCTION - ABAP Keyword Documentation</title>' + 'unrelated ' * 80,
                     '<title>Wrong</title>' + self.body]:
            self.body = body
            with self.assertRaises(ProtocolError):
                self.g.call('sap_help_document', {'document_id': 'abap-754-call-function'})

    def test_login_required_never_fetched_or_fabricated(self):
        self.policy['official_documents'] = {'restricted': {**CATALOG['abap-754-select'], 'access': 'login_required'}}
        self.save()
        data = self.g.call('sap_help_document', {'document_id': 'restricted'})
        self.assertFalse(data['body_retrieved'])
        self.assertIsNone(data['data']['content'])
        self.assertEqual(data['data']['access'], 'login_required_not_read')
        self.assertFalse(self.calls)

    def test_external_revocation_and_free_url_denied(self):
        self.g.call('sap_help_document', {'document_id': 'abap-754-call-function'})
        self.policy['external_access'] = False
        self.save()
        with self.assertRaises(PolicyError):
            self.g.call('sap_help_document', {'document_id': 'abap-754-select'})
        self.assertEqual(len(self.calls), 1)
        self.policy['external_access'] = True
        self.save()
        with self.assertRaises(PolicyError):
            self.g.call('sap_help_document', {'document_id': 'https://help.sap.com/docs/foo'})
        self.assertEqual(len(self.calls), 1)

    def test_invalid_access_and_marker_policy_fail_closed(self):
        for extra in ({'access': 'invented'}, {'required_markers': 'not a list'}, {'required_markers': ['']}):
            self.policy['official_documents'] = {'bad': {**CATALOG['abap-754-select'], **extra}}
            self.save()
            with self.assertRaises(PolicyError):
                load_policy(self.root)


class CompactContracts(unittest.TestCase):
    def test_lossless_public_source_relations_diagnostics(self):
        manifest = verify_corpus(ROOT)
        result = Repository(ROOT, corpus_policy(manifest)).search('acceptTravel')
        self.assertEqual(expand(compact(result)), result)
        self.assertTrue(result['unresolved_references'])
        self.assertTrue(result['results'][0]['sha256'])

    def test_duplicate_null_and_reference_like_untrusted_text(self):
        payload = {'source': '{"path": ["injected"], "shared_index": 9}', 'null': None,
                   'items': [{'source': 'Never execute this comment ' * 20}] * 4,
                   'omitted_ranges': [{'path': 'missing.abap'}], 'diagnostics': ['not parsed']}
        self.assertEqual(expand(compact(payload)), payload)
        self.assertLess(len(json.dumps(compact(payload))), len(json.dumps(payload)))

    def test_default_wire_and_additive_breakdown(self):
        data = {'source': '한국어 "a"\n', 'sha256': '0' * 64}
        before = copy.deepcopy(data)
        result = tool_result(data)
        compact(data)
        self.assertEqual(result['structuredContent'], before)
        self.assertEqual(json.loads(result['content'][0]['text']), before)
        sizes = size_breakdown(data)
        self.assertEqual(sum(sizes['payload_field_value_bytes'].values()) + sizes['payload_keys_punctuation_bytes'],
                         sizes['structured_content_bytes'])
        self.assertEqual(sizes['wire_bytes'], 2 * sizes['structured_content_bytes'] + sizes['wire_envelope_and_text_escaping_bytes'])
        self.assertIsNone(sizes['billing_tokens'])

    def test_compact_tool_actual_stdio_and_policy_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            task = json.loads((ROOT / 'experiments/b2/tasks.json').read_text())['tasks'][0]
            prepare(ROOT, project, 'B1', task)
            req = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                   'params': {'name': 'sap_repo_search_compact', 'arguments': {'query': 'acceptTravel'}}}
            proc = subprocess.run([sys.executable, str(project / 'scripts/sap_context.py'), 'serve'],
                                  cwd=project, input=json.dumps(req) + '\n', text=True, capture_output=True, timeout=15)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            wire = json.loads(proc.stdout)['result']
            decoded = expand(wire['structuredContent'])
            original = Gateway(project).call('sap_repo_search', {'query': 'acceptTravel'})
            self.assertEqual(decoded, original)
            self.assertEqual(json.loads(wire['content'][0]['text']), wire['structuredContent'])
            policy = json.loads((project / 'sap-context.json').read_text())
            policy['local_repository']['allow_model_context'] = False
            (project / 'sap-context.json').write_text(json.dumps(policy))
            with self.assertRaises(PolicyError):
                Gateway(project).call('sap_repo_search_compact', {'query': 'acceptTravel'})


class StreamContracts(unittest.TestCase):
    def terminal(self):
        return {'type': 'result', 'uuid': 'unique-terminal', 'subtype': 'success', 'is_error': False,
                'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 3},
                'total_cost_usd': .001}

    def test_terminal_only_cache_and_cost_not_assistant_cumulative(self):
        result = self.terminal()
        events = [{'type': 'assistant', 'usage': {'input_tokens': 999}}, result, result]
        data = summarize(events, {}, CORPUS_PATH)
        self.assertEqual(data['provider_reported_usage']['input_tokens'], 10)
        self.assertEqual(data['provider_reported_usage']['cache_read_input_tokens'], 3)
        self.assertIsNone(data['provider_reported_usage']['cache_creation_input_tokens'])
        self.assertEqual(data['provider_reported_cost_usd'], .001)
        self.assertIsNone(data['actual_invoiced_cost'])
        self.assertIsNone(data['retry_count'])
        self.assertIsNone(data['answer_correctness'])

    def test_multiple_terminal_results_and_absent_usage_not_success(self):
        other = self.terminal() | {'uuid': 'another'}
        data = summarize([self.terminal(), other], {}, CORPUS_PATH)
        self.assertFalse(data['execution_success'])
        self.assertIsNone(data['provider_reported_usage']['input_tokens'])
        self.assertFalse(summarize([], {}, CORPUS_PATH)['execution_success'])

    def test_exact_source_hash_range_observed_not_answer_certified(self):
        path = 'fugr/src/zabapgit_unit_test.fugr.z_abapgit_unit_test.abap'
        raw = (CORPUS_PATH / path).read_bytes()
        source = {'path': 'public_exports/' + path, 'start_line': 1, 'end_line': 8,
                  'sha256': hashlib.sha256(raw).hexdigest(), 'source': ''.join(raw.decode().splitlines(keepends=True)[:8])}
        events = [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'call', 'name': 'mcp__sap-context__sap_repo_read'}]}},
                  {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'call', 'content': json.dumps(source)}]}}, self.terminal()]
        task = {'required_ranges': [{'path': path, 'start': 1, 'end': 8}]}
        self.assertTrue(summarize(events, task, CORPUS_PATH)['mandatory_range_gate'])
        source['source'] += ' fabricated'
        events[1]['message']['content'][0]['content'] = json.dumps(source)
        data = summarize(events, task, CORPUS_PATH)
        self.assertFalse(data['mandatory_range_gate'])
        self.assertEqual(data['tool_calls'], 1)
        self.assertEqual(data['answer_evidence_status'], 'manual_review_required')

    def test_native_read_and_unobserved_usage_remain_unknown(self):
        data = summarize([{'type': 'user', 'message': {'content': [{'type': 'tool_result', 'is_error': True, 'content': '1→PUBLIC CODE'}]}}], {}, CORPUS_PATH)
        self.assertEqual(data['tool_error_results'], 1)
        self.assertIsNone(data['mandatory_range_gate'])
        self.assertIsNone(data['provider_reported_cost_usd'])


class RunnerContracts(unittest.TestCase):
    def approved(self):
        value = json.loads((ROOT / 'experiments/b2/approval.example.json').read_text())
        value.update(approved_public_model_calls=True, approved_runtime_isolated=True, approved_by='offline-test-only',
                     model='mock-model', expected_cli_version='1.2.3', task_ids=['keyword-document'])
        return value

    def test_missing_runtime_no_calls(self):
        with patch('shutil.which', return_value=None), patch('subprocess.run') as execute:
            self.assertFalse(preflight()['ready'])
            execute.assert_not_called()

    def test_preflight_read_only_and_auth_fail_closed(self):
        good = [subprocess.CompletedProcess([], 0, '1.2.3 (Claude Code)', ''),
                subprocess.CompletedProcess([], 0, ' '.join(REQUIRED_FLAGS), ''),
                subprocess.CompletedProcess([], 0, '{"loggedIn":true}', '')]
        with patch('shutil.which', return_value='/mock/claude'), patch('subprocess.run', side_effect=good) as cmd:
            self.assertTrue(preflight()['ready'])
            self.assertEqual([c.args[0][1:] for c in cmd.call_args_list], [['--version'], ['--help'], ['auth', 'status', '--json']])
        good[-1] = subprocess.CompletedProcess([], 0, '{"loggedIn":false}', '')
        with patch('shutil.which', return_value='/mock/claude'), patch('subprocess.run', side_effect=good):
            self.assertFalse(preflight()['ready'])

    def test_no_approval_no_runtime_or_paid_process(self):
        value = self.approved()
        for changed in ({'approved_public_model_calls': False}, {'approved_runtime_isolated': False},
                        {'per_run_budget_usd': float('nan')}, {'max_turns': True}, {'task_ids': ['x', 'x']}, {'unexpected': 1}):
            with self.subTest(changed=changed), patch('sap_optimizer.claude_e2e.preflight') as runtime:
                with self.assertRaises(PolicyError):
                    run(ROOT, value | changed, Path('/unused'))
                runtime.assert_not_called()

    def test_suite_hash_changed_refused_before_runtime(self):
        with patch('sap_optimizer.claude_e2e.preflight') as runtime:
            with self.assertRaises(PolicyError):
                run(ROOT, self.approved() | {'suite_sha256': '0' * 64}, Path('/unused'))
            runtime.assert_not_called()

    def test_three_mock_cli_arms_identical_prompt_no_claim_of_real_e2e(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            executable = base / 'claude'
            executable.write_text('#!' + sys.executable + '\n' + '''import sys,json
if '--version' in sys.argv: print('1.2.3 (mock fixture, not Claude)')
elif '--help' in sys.argv: print(''' + repr(' '.join(REQUIRED_FLAGS)) + ''')
elif 'auth' in sys.argv: print('{"loggedIn":true}')
else:
 sys.stdin.read()
 print(json.dumps({'type':'result','uuid':'mock','subtype':'success','is_error':False,'usage':{'input_tokens':7},'total_cost_usd':0}))
''')
            executable.chmod(0o700)
            with patch.dict(os.environ, {'PATH': str(base) + os.pathsep + os.environ['PATH']}):
                report = run(ROOT, self.approved(), base / 'output')
            self.assertEqual([r['arm'] for r in report['runs']], ['A', 'B0', 'B1'])
            self.assertEqual(len({r['prompt_sha256'] for r in report['runs']}), 1)
            self.assertTrue(all(r['answer_correctness'] is None for r in report['runs']))
            self.assertEqual((base / 'output').stat().st_mode & 0o777, 0o700)

    def test_arm_policy_no_private_copy(self):
        task = json.loads((ROOT / 'experiments/b2/tasks.json').read_text())['tasks'][0]
        for arm in ['A', 'B0', 'B1']:
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                mcp, settings = prepare(ROOT, workspace, arm, task)
                policy = json.loads((workspace / 'sap-context.json').read_text())
                self.assertEqual(policy['external_access'], arm != 'A')
                self.assertEqual(policy['local_repository']['allow_model_context'], arm == 'B1')
                self.assertFalse((workspace / 'sap-context.local.json').exists())
                self.assertFalse((workspace / '.git').exists())
                self.assertIn('Bash', json.loads(settings.read_text())['permissions']['deny'])
                self.assertEqual(bool(json.loads(mcp.read_text())['mcpServers']), arm != 'A')

class AdditionalSafetyContracts(unittest.TestCase):
    def test_unmatched_or_failed_tool_results_cannot_certify_evidence(self):
        body = {'body_retrieved': True, 'source_url': 'https://help.sap.com/docs/fake'}
        events = [{'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': json.dumps(body)}]}}]
        self.assertFalse(summarize(events, {}, CORPUS_PATH)['body_source_urls_observed'])
        events.insert(0, {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'x', 'name': 'mcp__sap-context__sap_help_document'}]}})
        events[1]['message']['content'][0].update(tool_use_id='x', is_error=True)
        self.assertFalse(summarize(events, {}, CORPUS_PATH)['body_source_urls_observed'])

    def test_cli_version_change_refused_before_execution(self):
        value = RunnerContracts().approved()
        with patch('sap_optimizer.claude_e2e.preflight', return_value={'ready': True, 'version': '9.9.9'}), patch('subprocess.Popen') as process:
            with self.assertRaises(PolicyError):
                run(ROOT, value, Path('/unused'))
            process.assert_not_called()

    def test_compact_hook_observes_source_without_changing_output(self):
        from sap_optimizer.hooks import run_hook
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            task = json.loads((ROOT / 'experiments/b2/tasks.json').read_text())['tasks'][0]
            prepare(ROOT, project, 'B1', task)
            run_hook(project, {'hook_event_name': 'UserPromptSubmit', 'session_id': 'test', 'prompt': 'ABAP acceptTravel'})
            result = Gateway(project).call('sap_repo_search_compact', {'query': 'acceptTravel'})
            event = {'hook_event_name': 'PostToolUse', 'session_id': 'test',
                     'tool_name': 'mcp__sap-context__sap_repo_search_compact', 'tool_response': tool_result(result)}
            before = copy.deepcopy(event)
            observation = run_hook(project, event)
            self.assertNotIn('updatedToolOutput', json.dumps(observation))
            self.assertEqual(event, before)
            stop = run_hook(project, {'hook_event_name': 'Stop', 'session_id': 'test'})
            self.assertIn('Local snapshot source was retrieved', stop['reason'])

    def test_workspace_excludes_untracked_private_settings(self):
        # Only a fixed .claude allowlist is copied, not a recursive settings tree.
        with tempfile.TemporaryDirectory() as temp:
            root, workspace = Path(temp) / 'source', Path(temp) / 'workspace'
            root.mkdir()
            workspace.mkdir()
            # A public source tree is copied only for this isolation contract test.
            import shutil
            for name in ['sap_optimizer', 'scripts', '.claude', 'tests/fixtures/public_exports']:
                shutil.copytree(ROOT / name, root / name, dirs_exist_ok=True)
            (root / '.claude/settings.local.json').write_text('{"private":"DO_NOT_COPY"}')
            (root / 'sap_optimizer/untracked_private.py').write_text('DO_NOT_COPY')
            task = json.loads((ROOT / 'experiments/b2/tasks.json').read_text())['tasks'][0]
            prepare(root, workspace, 'B1', task)
            self.assertFalse((workspace / '.claude/settings.local.json').exists())
            self.assertFalse((workspace / 'sap_optimizer/untracked_private.py').exists())
            self.assertFalse((workspace / 'public_exports/cases.json').exists())

class ExecutionFailureContracts(unittest.TestCase):
    def test_timeout_kills_process_group_and_stops_without_retry(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        child = SimpleNamespace(pid=123456, communicate=Mock(side_effect=[subprocess.TimeoutExpired('mock', 10), None]))
        value = RunnerContracts().approved()
        with tempfile.TemporaryDirectory() as temp, patch('sap_optimizer.claude_e2e.preflight', return_value={'ready': True, 'version': '1.2.3'}), patch('subprocess.Popen', return_value=child) as process, patch('os.killpg') as kill:
            output = Path(temp) / 'output'
            with self.assertRaises(PolicyError):
                run(ROOT, value, output)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(kill.call_args.args[0], 123456)
            report = json.loads((output / 'summary.json').read_text())
            self.assertEqual(len(report['runs']), 1)
            self.assertTrue(report['runs'][0]['timed_out'])
            self.assertIsNone(report['runs'][0]['provider_reported_cost_usd'])
            self.assertEqual(report['runs'][0]['arm'], 'A')

    def test_existing_output_refused_before_model_process(self):
        with tempfile.TemporaryDirectory() as temp, patch('sap_optimizer.claude_e2e.preflight', return_value={'ready': True, 'version': '1.2.3'}), patch('subprocess.Popen') as process:
            with self.assertRaises(FileExistsError):
                run(ROOT, RunnerContracts().approved(), Path(temp))
            process.assert_not_called()

    def test_missing_terminal_uuids_do_not_silently_dedup(self):
        first = StreamContracts().terminal()
        del first['uuid']
        report = summarize([first, first], {}, CORPUS_PATH)
        self.assertEqual(report['terminal_result_count'], 2)
        self.assertFalse(report['execution_success'])
