#!/usr/bin/env python3
"""Reproduce PUBLIC SYNTHETIC B1 comparison + real stdio smoke. No network."""
import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.benchmark import compare
from sap_optimizer.policy import load_policy
from sap_optimizer.repository import Repository


def main():
    policy = load_policy(ROOT)
    if policy.get("external_access") is not False or policy.get("local_repository", {}).get("roots") != ["examples/abapgit"]:
        raise SystemExit("Use the reviewed examples/b1-local-policy.json; this report must not contain private exports")
    if policy["local_repository"].get("allow_model_context") is not True:
        raise SystemExit("Synthetic MCP smoke requires explicit model-context permission for the public example")
    requirements = ["CLAS:ZCL_B1_LARGE", "CLAS:ZCL_B1_HELPER"]
    symbols = [{"object_id": obj, "symbol": method, "kind": kind}
               for obj, method in [(requirements[0], "FIND_RECEIPT"), (requirements[1], "CHECK")]
               for kind in ("method_declaration", "method_implementation")]
    measured = compare(Repository(ROOT, policy), "find_receipt", requirements, symbols)
    process = subprocess.Popen([sys.executable, str(ROOT / "scripts/sap_context.py"), "serve"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    records = []

    def rpc(name, args):
        request = {"jsonrpc": "2.0", "id": len(records) + 1, "method": "tools/call",
                   "params": {"name": name, "arguments": args}}
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        raw = process.stdout.readline()
        response = json.loads(raw)["result"]
        if response.get("isError"):
            raise RuntimeError("Synthetic local MCP smoke failed")
        data = response["structuredContent"]
        records.append({"tool": name, "isError": False, "wire_chars": len(raw), "wire_bytes": len(raw.encode()),
                        "snapshot": data.get("snapshot"), "source_chars": data.get("source_chars", len(data.get("source", ""))),
                        "ranges": [{k: s[k] for k in ("path", "start_line", "end_line", "sha256")} for s in data.get("results", [])]})
        return data

    try:
        result = rpc("sap_repo_search", {"query": "find_receipt"})
        assert records[-1]["wire_bytes"] == measured["C_code_and_direct_references"]["mcp_response_bytes"]
        first = result["results"][1]
        original = rpc("sap_repo_read", {"path": first["path"], "expected_sha256": first["sha256"], "expected_snapshot": first["snapshot"]})
        assert original["full_original"]
        refs = rpc("sap_repo_references", {"object_id": "CLAS:ZCL_B1_LARGE"})
        assert any(e["target"] == "ZCL_B1_HELPER" for e in refs["outgoing"])
        rpc("sap_repo_status", {})
    finally:
        process.stdin.close()
        process.wait(timeout=10)
    assert process.returncode == 0
    folder = ROOT / "reports"
    folder.mkdir(exist_ok=True)
    (folder / "b1-context-comparison.json").write_text(json.dumps(measured, ensure_ascii=False, indent=2) + "\n")
    (folder / "b1-local-smoke.json").write_text(json.dumps({
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "client": "real stdio subprocess, NOT Claude Code model", "external_access": False,
        "data": "public authored synthetic fixture only", "records": records,
        "benchmark_wire_size_matched": True, "exit_code": process.returncode}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: {m: measured[k][m] for m in ("source_chars", "mcp_response_bytes", "quality_gate_passed")}
                      for k in ("A_full_files", "B_selected_code", "C_code_and_direct_references")}, indent=2))


if __name__ == "__main__":
    main()
