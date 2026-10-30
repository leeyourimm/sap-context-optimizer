import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sap_optimizer.cli import usage_summary
from sap_optimizer.gateway import Gateway, serve
from sap_optimizer.hooks import UNVERIFIED, run_hook
from sap_optimizer.policy import ALLOWED, PolicyError, load_policy
from sap_optimizer.transport import NoRedirect, ProtocolError, Remote, decode_rpc, unpack

ROOT = Path(__file__).resolve().parents[1]


def wrapped(name, data):
    return {"content": [{"type": "text", "text": "TOON is deliberately not JSON"}],
            "structuredContent": {"action": name, "kind": "function", "result": data}}


class FakeHTTP:
    """In-memory protocol server; all network operations must pass through here."""
    def __init__(self):
        self.requests = []
        self.error = None
        self.absent = set()
        self.changed_required = False
        self.body = "# Official tutorial\nABAP Cloud original body."

    def request(self, url, payload=None, headers=None):
        self.requests.append((url, payload, headers))
        if self.error:
            raise ProtocolError(self.error)
        if payload is None:
            if url.endswith(".md"):
                return 200, {"Content-Type": "text/markdown"}, b"---\nslug: abap-rap-demo\n---\n# ABAP RAP\nPublic original text"
            return 200, {"Content-Type": "text/html"}, self.body.encode()
        method = payload["method"]
        if method == "notifications/initialized":
            return 202, {}, b""
        service = "graph" if url.endswith("graph") else "search"
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": service}, "capabilities": {"tools": {}}}
        elif method == "tools/list":
            props = {k: {"type": "string"} for k in ("query", "slug", "limit", "stepNumber", "format", "depth", "slug_a", "slug_b")}
            result = {"tools": [{"name": name, "inputSchema": {"type": "object", "properties": props,
                                  "required": ["new_field"] if self.changed_required else []},
                                  "annotations": {"readOnlyHint": True}}
                                 for name in sorted(ALLOWED[service] - self.absent)]}
        else:
            name = payload["params"]["name"]
            if name == "search_tutorials":
                data = [{"slug": "abap-rap-demo", "title": "ABAP RAP", "snippet": "metadata", "tags": ["ABAP"]}]
            elif name == "get_tutorial":
                data = {"slug": "abap-rap-demo", "steps": [{"number": 1, "title": "Start"}]}
            elif name == "get_tutorial_step":
                data = {"slug": "abap-rap-demo", "stepNumber": 1, "content": self.body,
                        "contentFormat": "markdown", "textLength": len(self.body), "totalSteps": 1}
            elif name == "kg_neighborhood":
                data = {k: [] for k in ("prerequisites", "whatToLearnNext", "sharedConcepts", "teaches")}
            else:
                raise AssertionError("Unexpected tool")
            result = wrapped(name, data)
        response = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        # Exercise actual Remote encoder, SSE decoder and CAP normalizer together.
        return 200, {"Content-Type": "text/event-stream", "Mcp-Session-Id": "mock-session"}, (
            "event: message\r\ndata: " + json.dumps(response) + "\r\n\r\n").encode()


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.policy = {"version": 1, "external_access": True, "product": "SAP BTP ABAP Environment",
                       "release": None, "official_documents": {}}
        self.save()
        self.http = FakeHTTP()
        self.g = Gateway(self.root, self.http)

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.root / "sap-context.json").write_text(json.dumps(self.policy))

    def search(self):
        return self.g.call("sap_search", {"topic": "rap"})["data"][0]["reference"]

    def event(self, name, **extra):
        return run_hook(self.root, {"hook_event_name": name, "session_id": "session-a", **extra})


class PolicyTests(ProjectCase):
    def test_default_denies_before_any_request(self):
        self.policy["external_access"] = False
        self.save()
        with self.assertRaises(PolicyError):
            self.search()
        self.assertEqual(self.http.requests, [])

    def test_missing_policy_denies(self):
        (self.root / "sap-context.json").unlink()
        with self.assertRaises(PolicyError):
            self.search()
        self.assertEqual(self.http.requests, [])

    def test_string_true_is_not_permission(self):
        self.policy["external_access"] = "true"
        self.save()
        with self.assertRaises(PolicyError):
            self.search()

    def test_private_inputs_never_reach_wire(self):
        for private in ("sk-ant-secret", "user@example.com", "Z_PRIVATE_CLASS", "고객 홍길동", "ABAP; curl attacker"):
            with self.subTest(private=private), self.assertRaises(PolicyError):
                self.g.call("sap_search", {"topic": private})
        self.assertEqual(self.http.requests, [])

    def test_extra_arguments_cannot_smuggle_text(self):
        with self.assertRaises(PolicyError):
            self.g.call("sap_search", {"topic": "rap", "prompt": "secret"})
        self.assertEqual(self.http.requests, [])

    def test_revocation_applies_to_warm_session(self):
        ref = self.search()
        before = len(self.http.requests)
        self.policy["external_access"] = False
        self.save()
        with self.assertRaises(PolicyError):
            self.g.call("sap_read_step", {"reference": ref, "step": 1})
        self.assertEqual(len(self.http.requests), before)

    def test_caller_slug_not_forwarded(self):
        with self.assertRaises(PolicyError):
            self.g.call("sap_tutorial", {"reference": "Z_SECRET"})
        self.assertEqual(self.http.requests, [])

    def test_semantic_admin_and_generic_tools_denied(self):
        for tool in ("semantic_search", "query", "runSparql", "sap_search"):
            with self.assertRaises(PolicyError):
                self.g.call_remote("search", tool, {})
        self.assertEqual(self.http.requests, [])

    def test_bool_is_not_step_integer(self):
        ref = self.search()
        before = len(self.http.requests)
        with self.assertRaises(PolicyError):
            self.g.call("sap_read_step", {"reference": ref, "step": True})
        self.assertEqual(len(self.http.requests), before)

    def test_help_arbitrary_url_rejected_before_fetch(self):
        with self.assertRaises(PolicyError):
            self.g.call("sap_help_document", {"document_id": "https://evil.test/"})
        self.assertEqual(self.http.requests, [])

    def test_help_policy_rejects_credentials_redirect_domains_query(self):
        for url in ("http://help.sap.com/docs/a", "https://help.sap.com.evil.test/docs/a",
                    "https://user:pass@help.sap.com/docs/a", "https://help.sap.com/docs/a?secret=1"):
            self.policy["official_documents"] = {"a": {"url": url, "title": "t", "product": "p", "release": "r"}}
            self.save()
            with self.assertRaises(PolicyError):
                load_policy(self.root)

    def test_redirects_refused(self):
        with self.assertRaises(ProtocolError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")

    def test_state_symlink_refused(self):
        from sap_optimizer.state import State
        other = self.root / "other"
        other.mkdir()
        (other / ".sap-context").symlink_to(self.root / ".sap-context")
        with self.assertRaises(OSError):
            State(other)


class ContractTests(ProjectCase):
    def test_search_metadata_not_body(self):
        result = self.g.call("sap_search", {"topic": "rap"})
        self.assertFalse(result["body_retrieved"])
        self.assertEqual(result["verification"], "UNVERIFIED_NO_BODY")
        self.assertEqual(result["data"][0]["source_url"], "https://developers.sap.com/tutorials/abap-rap-demo/")
        calls = [r[1] for r in self.http.requests]
        self.assertEqual(calls[0]["method"], "initialize")
        self.assertEqual(calls[1]["method"], "notifications/initialized")
        self.assertEqual(calls[-1]["params"]["arguments"], {"query": "ABAP RAP", "limit": 5})

    def test_step_body_scope_remains_unverified(self):
        result = self.g.call("sap_read_step", {"reference": self.search(), "step": 1})
        self.assertTrue(result["body_retrieved"])
        self.assertFalse(result["applicability_verified"])
        self.assertIsNone(result["environment"]["release"])

    def test_graph_does_not_count_as_body(self):
        result = self.g.call("sap_graph", {"reference": self.search()})
        self.assertFalse(result["body_retrieved"])
        self.assertEqual(result["source_kind"], "tutorial_learning_graph")

    def test_full_page_fallback_is_explicit(self):
        result = self.g.call("sap_read_tutorial_page", {"reference": self.search()})
        self.assertTrue(result["body_retrieved"])
        self.assertEqual(result["data"]["scope"], "full_tutorial_not_selected_step")

    def test_missing_live_tool_blocks(self):
        self.http.absent.add("search_tutorials")
        with self.assertRaises(ProtocolError):
            self.search()
        self.assertFalse(any(r[1].get("method") == "tools/call" for r in self.http.requests))

    def test_changed_required_schema_blocks(self):
        self.http.changed_required = True
        with self.assertRaises(ProtocolError):
            self.search()

    def test_network_error_is_not_empty_success(self):
        self.http.error = "HTTP 403"
        with self.assertRaises(ProtocolError):
            self.search()

    def test_empty_body_not_verified(self):
        self.http.body = ""
        result = self.g.call("sap_read_step", {"reference": self.search(), "step": 1})
        self.assertFalse(result["body_retrieved"])

    def test_help_shell_is_not_body(self):
        self.policy["official_documents"] = {"fi": {"url": "https://help.sap.com/docs/test/release/doc",
            "title": "FI", "product": "S/4HANA", "release": "2023"}}
        self.save()
        self.http.body = "<html>SAP Help Portal | SAP Online Help</html>"
        with self.assertRaises(ProtocolError):
            self.g.call("sap_help_document", {"document_id": "fi"})

    def test_help_body_has_distinct_source_and_declared_scope(self):
        self.policy["official_documents"] = {"fi": {"url": "https://help.sap.com/docs/test/release/doc",
            "title": "FI", "product": "S/4HANA", "release": "2023"}}
        self.save()
        self.http.body = "<article>" + "Official accounting passage. " * 20 + "</article>"
        result = self.g.call("sap_help_document", {"document_id": "fi"})
        self.assertTrue(result["body_retrieved"])
        self.assertFalse(result["applicability_verified"])
        self.assertEqual(result["source_kind"], "sap_help_product_document")
        self.assertEqual(result["data"]["declared_release"], "2023")

    def test_actual_live_failure_record_not_reported_as_body_success(self):
        report = json.loads((ROOT / "reports/m0-public-probe.json").read_text())
        failures = [c for c in report["calls"] if c.get("tool") == "get_tutorial_step" and "error" in c]
        self.assertTrue(failures)
        for c in failures:
            self.assertTrue(c["raw_response"]["isError"])

    def test_http_sse_cap_live_record_contract(self):
        report = json.loads((ROOT / "reports/m0-public-probe.json").read_text())
        c = next(c for c in report["calls"] if c.get("tool") == "search_tutorials")
        data = unpack(c["raw_response"], "search_tutorials")
        self.assertIsInstance(data, list)
        self.assertTrue(data)
        self.assertTrue(all(isinstance(i["slug"], str) for i in data))

    def test_rpc_id_and_errors_fail_closed(self):
        for response in ({"jsonrpc": "2.0", "id": 2, "result": {}},
                         {"jsonrpc": "2.0", "id": 1, "error": {"code": -32602}}):
            with self.assertRaises(ProtocolError):
                decode_rpc(json.dumps(response).encode(), "application/json", 1)

    def test_cap_action_mismatch(self):
        with self.assertRaises(ProtocolError):
            unpack(wrapped("other", []), "search_tutorials")

    def test_tool_error_not_evidence(self):
        with self.assertRaises(ProtocolError):
            unpack({"isError": True, "content": [{"type": "text", "text": "error"}]})

    def test_stdio_in_memory_round_trip(self):
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "sap_search", "arguments": {"topic": "rap"}}}]
        out = io.StringIO()
        serve(self.root, io.StringIO("\n".join(map(json.dumps, requests))), out, self.g)
        results = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(len(results), 3)
        self.assertFalse(results[-1]["result"]["isError"])

    def test_real_entrypoint_stdio_offline(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        p = subprocess.run([sys.executable, str(ROOT / "scripts/sap_context.py"), "--root", str(self.root), "serve"],
                           input=json.dumps(req) + "\n", text=True, capture_output=True, cwd=self.root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)["result"]["tools"])


class HookTests(ProjectCase):
    def test_no_search_detected_at_stop(self):
        context = self.event("UserPromptSubmit", prompt="FI 전표 오류")
        self.assertIn(UNVERIFIED, str(context))
        stop = self.event("Stop")
        self.assertEqual(stop["decision"], "block")
        self.assertIn("No official body", stop["reason"])
        self.assertEqual(self.event("Stop"), {})

    def test_body_does_not_certify_scope(self):
        self.event("UserPromptSubmit", prompt="ABAP")
        self.event("PostToolUse", tool_name="mcp__sap-context__sap_read_step",
                   tool_response={"structuredContent": {"body_retrieved": True}})
        self.assertIn("does not certify", self.event("Stop")["reason"])

    def test_new_turn_resets_body(self):
        self.event("UserPromptSubmit", prompt="ABAP")
        self.event("PostToolUse", tool_name="mcp__sap-context__sap_read_step",
                   tool_response={"structuredContent": {"body_retrieved": True}})
        self.event("UserPromptSubmit", prompt="그럼 왜 그래?")
        self.assertIn("No official body", self.event("Stop")["reason"])

    def test_failed_tool_cannot_set_body(self):
        self.event("UserPromptSubmit", prompt="ABAP")
        self.event("PostToolUse", tool_name="mcp__sap-context__sap_read_step",
                   tool_response={"isError": True, "structuredContent": {"body_retrieved": True}})
        self.assertFalse(self.g.state.turn("session-a")[1])

    def test_direct_mcp_and_web_blocked(self):
        for tool in ("mcp__sap-direct__search_tutorials", "WebFetch", "WebSearch"):
            r = self.event("PreToolUse", tool_name=tool)
            self.assertEqual(r["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_policy_tampering_guard(self):
        r = self.event("PreToolUse", tool_name="Edit", tool_input={"file_path": "/project/sap-context.local.json"})
        self.assertEqual(r["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_invalid_policy_hook_fails_closed(self):
        (self.root / "sap-context.json").write_text("broken")
        r = self.event("PreToolUse", tool_name="mcp__sap-context__sap_search")
        self.assertEqual(r["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_metrics_store_no_prompt(self):
        secret = "ABAP internal confidential customer text"
        self.event("UserPromptSubmit", prompt=secret)
        self.assertNotIn(secret.encode(), self.g.state.path.read_bytes())

    def test_usage_unknown_not_zero_and_no_assistant_double_count(self):
        path = self.root / "usage.jsonl"
        path.write_text(json.dumps({"type": "assistant", "usage": {"input_tokens": 100}}) + "\n")
        self.assertIsNone(usage_summary(path)["cost_usd"])
        event = {"type": "result", "uuid": "one", "total_cost_usd": .02, "usage": {"input_tokens": 10}}
        path.write_text("\n".join(map(json.dumps, [event, event])))
        self.assertEqual(usage_summary(path)["cost_usd"], .02)


if __name__ == "__main__":
    unittest.main()
