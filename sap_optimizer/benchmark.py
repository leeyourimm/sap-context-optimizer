"""Local A/B/C context measurement, never model tokens or billing claims."""
import json

from .policy import PolicyError
from .gateway import tool_result


def compare(repo, query, required_objects, required_symbols=()):
    if not isinstance(required_objects, list) or any(not isinstance(k, str) for k in required_objects):
        raise PolicyError("required_objects must be explicit local object IDs")
    if not isinstance(required_symbols, (list, tuple)) or any(not isinstance(r, dict) or
            set(r) != {"object_id", "symbol", "kind"} or any(not isinstance(v, str) for v in r.values()) for r in required_symbols):
        raise PolicyError("required_symbols must contain object_id/symbol/kind string fields")
    b = repo.search(query, expand=False)
    c = repo.search(query, expand=True)
    paths = {s["path"] for r in (b, c) for s in r["results"]}
    for key in required_objects:
        if key in repo.objects:
            paths.update(repo.objects[key]["paths"])
    originals = [repo.read(p) for p in sorted(paths)]

    def measure(payload, snippets, full=False):
        objects = {s.get("object_id") for s in snippets} if full else {
            s["object"]["id"] for s in snippets if s.get("object") and
            (not s.get("symbol") or s["symbol"]["kind"] != "object_metadata")}
        missing_symbols = []
        for requirement in required_symbols:
            key, symbol, kind = requirement["object_id"], requirement["symbol"].upper(), requirement["kind"]
            covered = False
            for s in snippets:
                obj = s.get("object_id") if full else (s.get("object") or {}).get("id")
                if obj != key:
                    continue
                for decl in repo.files[s["path"]].get("symbols", []):
                    if decl["name"] == symbol and decl["kind"] == kind and s["start_line"] <= decl["start_line"] and s["end_line"] >= decl["end_line"]:
                        covered = True
            if not covered:
                missing_symbols.append(requirement)
        serialized = json.dumps(payload, ensure_ascii=False)
        # Measure the actual server serializer too, including both MCP text and
        # structuredContent. A full-file baseline is one read response per file.
        responses = snippets if full else [payload]
        wire = [json.dumps({"jsonrpc": "2.0", "id": 1, "result": tool_result(r)}, ensure_ascii=False) + "\n"
                for r in responses]
        return {"source_chars": sum(len(s["source"]) for s in snippets),
                "source_bytes": sum(len(s["source"].encode()) for s in snippets),
                "payload_chars": len(serialized), "payload_bytes": len(serialized.encode()),
                "mcp_response_chars": sum(len(r) for r in wire),
                "mcp_response_bytes": sum(len(r.encode()) for r in wire),
                "ranges": [{k: s[k] for k in ("path", "start_line", "end_line", "sha256")} for s in snippets],
                "missing_required_objects": sorted(set(required_objects) - objects),
                "missing_required_symbols": missing_symbols,
                "quality_gate_passed": (not (set(required_objects) - objects) and not missing_symbols)
                                       if required_objects or required_symbols else None,
                "tokens": None, "billing_cost": None}

    return {"snapshot": repo.signature, "fixture_kind": "explicit_local_requirements_not_SAP_accuracy_benchmark",
            "A_full_files": measure(originals, originals, True),
            "B_selected_code": measure(b, b["results"]), "C_code_and_direct_references": measure(c, c["results"]),
            "note": "Actual source and JSON payload size, no token estimate or billing savings. Missing code fails quality gate.",
            "wire_measurement": "Server serializer, response id=1, newline included; full files measured as separate read responses",
            "B_stages": b["stages"], "C_stages": c["stages"]}
