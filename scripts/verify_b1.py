#!/usr/bin/env python3
"""Reproduce PUBLIC SYNTHETIC B1 comparison + real stdio smoke. No network."""
import datetime
import argparse
import json
from pathlib import Path
import subprocess
import sys
import selectors
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sap_optimizer.benchmark import compare
from sap_optimizer.policy import load_policy
from sap_optimizer.repository import Repository


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify(project, folder):
    policy = load_policy(project)
    if policy.get("external_access") is not False or policy.get("local_repository", {}).get("roots") != ["examples/abapgit"]:
        raise SystemExit("Use the reviewed examples/b1-local-policy.json; this report must not contain private exports")
    if policy["local_repository"].get("allow_model_context") is not True:
        raise SystemExit("Synthetic MCP smoke requires explicit model-context permission for the public example")
    requirements = ["CLAS:ZCL_B1_LARGE", "CLAS:ZCL_B1_HELPER"]
    symbols = [{"object_id": obj, "symbol": method, "kind": kind}
               for obj, method in [(requirements[0], "FIND_RECEIPT"), (requirements[1], "CHECK")]
               for kind in ("method_declaration", "method_implementation")]
    measured = compare(Repository(project, policy), "find_receipt", requirements, symbols)
    require(measured["A_full_files"]["quality_gate_passed"] and measured["C_code_and_direct_references"]["quality_gate_passed"],
            "Full-file/dependency context is missing mandatory evidence")
    require(measured["B_selected_code"]["quality_gate_passed"] is False, "Synthetic omission control did not detect missing Helper")
    process = subprocess.Popen([sys.executable, str(ROOT / "scripts/sap_context.py"), "--root", str(project), "serve"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    records = []
    sequence = 0

    def request(method, params):
        nonlocal sequence
        sequence += 1
        payload = {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            require(bool(selector.select(timeout=10)), "MCP reply timeout")
        raw = process.stdout.readline()
        response = json.loads(raw)
        require(response.get("id") == sequence and "result" in response, "Invalid stdio JSON-RPC reply")
        return response["result"], raw

    def rpc(name, args):
        response, raw = request("tools/call", {"name": name, "arguments": args})
        if response.get("isError"):
            raise RuntimeError("Synthetic local MCP smoke failed")
        data = response["structuredContent"]
        text = response["content"][0]["text"]
        require(json.loads(text) == data, "Text/structured result compatibility changed")
        records.append({"tool": name, "isError": False, "wire_chars": len(raw), "wire_bytes": len(raw.encode()),
                        "content_text_utf8_bytes": len(text.encode()),
                        "structured_json_utf8_bytes": len(json.dumps(data, ensure_ascii=False).encode()),
                        "dual_representation_equal": True,
                        "snapshot": data.get("snapshot"), "source_chars": data.get("source_chars", len(data.get("source", ""))),
                        "ranges": [{k: s[k] for k in ("path", "start_line", "end_line", "sha256")} for s in data.get("results", [])]})
        return data

    try:
        initialization, _ = request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                   "clientInfo": {"name": "b1-offline-smoke", "version": "1"}})
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()
        discovered, _ = request("tools/list", {})
        require(any(t["name"] == "sap_repo_search" for t in discovered["tools"]), "Local tool not advertised")
        result = rpc("sap_repo_search", {"query": "find_receipt"})
        require(records[-1]["wire_bytes"] == measured["C_code_and_direct_references"]["mcp_response_bytes"], "Wire byte measurement mismatch")
        require(json.loads(request("tools/call", {"name": "sap_repo_search", "arguments": {"query": "find_receipt"}})[0]["content"][0]["text"]) == result,
                "Existing text/structuredContent dual contract changed")
        first = result["results"][1]
        original = rpc("sap_repo_read", {"path": first["path"], "expected_sha256": first["sha256"], "expected_snapshot": first["snapshot"]})
        require(original["full_original"], "Full original reread missing")
        refs = rpc("sap_repo_references", {"object_id": "CLAS:ZCL_B1_LARGE"})
        require(any(e["target"] == "ZCL_B1_HELPER" for e in refs["outgoing"]), "Direct dependency missing")
        rpc("sap_repo_status", {})
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    require(process.returncode == 0, "MCP subprocess failed")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "b1-context-comparison.json").write_text(json.dumps(measured, ensure_ascii=False, indent=2) + "\n")
    (folder / "b1-local-smoke.json").write_text(json.dumps({
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "client": "real stdio subprocess, NOT Claude Code model", "external_access": False,
        "initialize": initialization, "dual_output_contract_preserved": True,
        "data": "public authored synthetic fixture only", "records": records,
        "benchmark_wire_size_matched": True, "exit_code": process.returncode}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: {m: measured[k][m] for m in ("source_chars", "mcp_response_bytes", "quality_gate_passed")}
                      for k in ("A_full_files", "B_selected_code", "C_code_and_direct_references")}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated", action="store_true", help="Copy only public synthetic examples to a temporary project; preserve local policy")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    if args.isolated:
        with tempfile.TemporaryDirectory(prefix="sap-b1-public-") as directory:
            project = Path(directory)
            shutil.copytree(ROOT / "examples/abapgit", project / "examples/abapgit")
            shutil.copyfile(ROOT / "examples/b1-local-policy.json", project / "sap-context.json")
            verify(project, args.output_dir)
    else:
        verify(ROOT, args.output_dir)


if __name__ == "__main__":
    main()
