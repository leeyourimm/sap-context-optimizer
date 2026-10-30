"""Real upstream bytes; oracle ranges are authored independently of the parser."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sap_optimizer.gateway import tool_result
from sap_optimizer.policy import PolicyError
from sap_optimizer.public_validation import CORPUS, corpus_policy, evaluate_corpus, evaluate_result, verify_corpus
from sap_optimizer.repository import Repository, tokenize
from scripts.check_claude_runtime import inspect_runtime

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / CORPUS / "cases.json").read_text())["cases"]


class PublicRetrievalCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = verify_corpus(ROOT)


def make_case(case):
    def run(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline tests may not use HTTP")):
            repo = Repository(ROOT, corpus_policy(self.manifest))
            result = repo.search(case["query"], expand=case.get("include_references", True))
            outcome = evaluate_result(ROOT, case, result)
        self.assertTrue(outcome["passed"], outcome)
    return run


for case in CASES:
    setattr(PublicRetrievalCases, "test_public_" + case["id"].replace("-", "_"), make_case(case))


class PublicGapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        shutil.copytree(ROOT / CORPUS, self.project / CORPUS)
        self.manifest = verify_corpus(self.project)
        self.policy = corpus_policy(self.manifest)
        self.repo = Repository(self.project, self.policy)

    def tearDown(self):
        self.tmp.cleanup()

    def case(self, name):
        return next(c for c in CASES if c["id"] == name)

    def test_missing_required_public_object_fails_oracle(self):
        case = copy.deepcopy(self.case("rap-action"))
        case["required_objects"].append("CLAS:NOT_IN_EXPORT")
        r = evaluate_result(self.project, case, self.repo.search(case["query"]))
        self.assertFalse(r["passed"])
        self.assertEqual(r["missing_objects"], ["CLAS:NOT_IN_EXPORT"])

    def test_missing_body_is_not_satisfied_by_metadata(self):
        path = self.project / CORPUS / "rap100/src/zrap100_bp_traveltp_sol.clas.locals_imp.abap"
        path.unlink()
        case = self.case("rap-action")
        r = evaluate_result(self.project, case, self.repo.search(case["query"]))
        self.assertFalse(r["passed"])
        self.assertTrue(r["missing_ranges"])
        self.assertIn("CLAS:ZRAP100_BP_TRAVELTP_SOL", self.repo.objects)

    def test_undeclared_public_dependency_not_invented(self):
        refs = self.repo.references("CLAS:ZRAP100_BP_TRAVELTP_SOL")
        namespaced = [e for e in refs["outgoing"] if e["target"] == "/DMO/CM_FLIGHT_MESSAGES"]
        self.assertTrue(namespaced)
        self.assertTrue(all(e["resolution"] == "missing_from_snapshot_or_external" for e in namespaced))

    def test_context_budget_reports_mandatory_range_omission(self):
        self.policy["local_repository"]["settings"] = {"max_results": 1, "max_lines": 2, "max_context_chars": 180}
        repo = Repository(self.project, self.policy)
        case = self.case("rap-action")
        result = repo.search(case["query"])
        self.assertTrue(result["context_budget_limited"])
        self.assertTrue(result["omitted_ranges"] or any(s["truncated"] for s in result["results"]))
        self.assertFalse(evaluate_result(self.project, case, result)["passed"])

    def test_file_budget_is_a_scope_gap(self):
        self.policy["local_repository"]["settings"] = {"max_files": 1}
        r = Repository(self.project, self.policy).search("acceptTravel")
        self.assertTrue(any(d["status"] == "file_limit_reached" for d in r["diagnostics"]))
        self.assertFalse(evaluate_result(self.project, self.case("rap-action"), r)["passed"])

    def test_unit_budget_is_reported(self):
        self.policy["local_repository"]["settings"] = {"max_units": 1}
        status = Repository(self.project, self.policy).status()
        self.assertIn("unit_limit_reached", {d["status"] for d in status["diagnostics"]})

    def test_file_byte_budget_not_mislabeled_as_encoding_failure(self):
        self.policy["local_repository"]["settings"] = {"max_file_bytes": 200}
        status = Repository(self.project, self.policy).status()
        self.assertIn("source_byte_limit_or_access_denied", {d["status"] for d in status["diagnostics"]})

    def test_two_real_same_name_methods_have_distinct_owners(self):
        r = self.repo.search("IF_OO_ADT_CLASSRUN~MAIN", expand=False)
        owners = {(s["object"]["id"], s["symbol"]["owner"]) for s in r["results"]
                  if s.get("symbol") and s["symbol"]["kind"] == "method_implementation"}
        self.assertIn(("CLAS:ZCL_RAP100_GEN_DATA_SOL", "ZCL_RAP100_GEN_DATA_SOL"), owners)
        self.assertIn(("CLAS:ZRAP100_CL_EML_SOL", "ZRAP100_CL_EML_SOL"), owners)

    def test_explicit_class_scoping_excludes_other_main(self):
        r = self.repo.search("ZRAP100_CL_EML_SOL IF_OO_ADT_CLASSRUN~MAIN", expand=False)
        self.assertEqual({s["object"]["id"] for s in r["results"]}, {"CLAS:ZRAP100_CL_EML_SOL"})

    def test_real_namespace_preserved_in_query_and_static_reference(self):
        self.assertIn("/DMO/CM_FLIGHT_MESSAGES", tokenize("한국어 /dmo/cm_flight_messages=>enter_customer_id"))
        edges = self.repo.references("CLAS:ZRAP100_BP_TRAVELTP_SOL")["outgoing"]
        self.assertTrue(any(e["target"] == "/DMO/CM_FLIGHT_MESSAGES" and e.get("target_symbol") == "ENTER_CUSTOMER_ID" for e in edges))

    def test_same_size_same_mtime_public_source_edit_rejects_hash(self):
        path = CORPUS + "/clas/src/zcl_ag_unit_test.clas.abap"
        before = self.repo.read(path)
        actual = self.project / path
        st = actual.stat()
        actual.write_bytes(actual.read_bytes().replace(b"HELLO", b"OTHER"))
        os.utime(actual, ns=(st.st_atime_ns, st.st_mtime_ns))
        with self.assertRaises(PolicyError):
            self.repo.read(path, expected_sha256=before["sha256"])

    def test_dependency_edit_rejects_expected_snapshot_with_unchanged_source(self):
        path = CORPUS + "/clas/src/zcl_ag_unit_test.clas.abap"
        before = self.repo.read(path)
        dep = self.project / CORPUS / "rap100/src/zrap100_r_traveltp_sol.bdef.asbdef"
        dep.write_bytes(dep.read_bytes() + b"\n// local test mutation\n")
        with self.assertRaises(PolicyError):
            self.repo.read(path, expected_sha256=before["sha256"], expected_snapshot=before["snapshot"])

    def test_real_abstract_entity_parsed_not_merely_raw_hit(self):
        self.repo.refresh()
        f = self.repo.files[CORPUS + "/rap100/src/zrap100_a_travel_sol.ddls.asddls"]
        self.assertTrue(any(s["name"] == "ZRAP100_A_TRAVEL_SOL" and s.get("cds_entity_kind") == "abstract" for s in f["symbols"]))
        self.assertEqual(f["parse_status"], "supported_subset")

    def test_prepare_reference_is_not_a_duplicate_validation_declaration(self):
        self.repo.refresh()
        symbols = self.repo.files[CORPUS + "/rap100/src/zrap100_r_traveltp_sol.bdef.asbdef"]["symbols"]
        decl = [s["start_line"] for s in symbols if s["name"] == "VALIDATEDATES" and s["kind"] == "rap_validation"]
        refs = [s["start_line"] for s in symbols if s["name"] == "VALIDATEDATES" and s["kind"] == "rap_validation_reference"]
        self.assertEqual(decl, [36])
        self.assertEqual(refs, [52])

    def test_unknown_real_object_types_remain_explicit(self):
        ds = self.repo.status()["diagnostics"]
        self.assertTrue(any(d["status"] == "unsupported_object_type" and d["type"] == "TABL" for d in ds))

    def test_fixture_tamper_fails_integrity(self):
        p = self.project / CORPUS / "clas/src/zcl_ag_unit_test.clas.abap"
        p.write_bytes(p.read_bytes() + b"\n")
        with self.assertRaises(PolicyError):
            verify_corpus(self.project)

    def test_unlisted_source_file_blocks_public_evaluation(self):
        (self.project / CORPUS / "clas/src/extra.abap").write_text("Not an approved public fixture")
        with self.assertRaises(PolicyError):
            evaluate_corpus(self.project)


class RuntimeAndWireTests(unittest.TestCase):
    def test_dual_output_contract_kept_without_guessing_model_tokens(self):
        result = tool_result({"source": "PUBLIC_CANARY", "tokens": None})
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertIsNone(result["structuredContent"]["tokens"])

    def test_runtime_check_never_logs_credential_value_or_claims_measurement(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "DO_NOT_LOG_SYNTHETIC_SENTINEL"}), patch("shutil.which", return_value=None):
            r = inspect_runtime()
        self.assertNotIn("DO_NOT_LOG_SYNTHETIC_SENTINEL", json.dumps(r))
        self.assertTrue(r["binding_presence_only"]["ANTHROPIC_API_KEY"])
        self.assertIsNone(r["actual_billing_tokens"])
        self.assertEqual(r["model_calls"], 0)
        self.assertEqual(r["final_model_input"], "unverified")

    def test_isolated_executable_smoke_preserves_current_policy(self):
        local = ROOT / "sap-context.local.json"
        before = local.read_bytes() if local.exists() else None
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, str(ROOT / "scripts/verify_b1.py"), "--isolated", "--output-dir", tmp],
                               text=True, capture_output=True, timeout=25)
            self.assertEqual(p.returncode, 0, p.stderr)
            report = json.loads((Path(tmp) / "b1-local-smoke.json").read_text())
            self.assertTrue(report["dual_output_contract_preserved"])
            self.assertTrue(report["benchmark_wire_size_matched"])
        self.assertEqual(local.read_bytes() if local.exists() else None, before)


if __name__ == "__main__":
    unittest.main()
