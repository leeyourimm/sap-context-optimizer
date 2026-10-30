import argparse
import json
import sys
from pathlib import Path

from .gateway import Gateway, serve
from .hooks import run_hook
from .policy import PolicyError, load_policy, require_external
from .probe import probe
from .transport import ProtocolError


def usage_summary(path):
    """Only terminal result events; no cumulative assistant usage summation."""
    results, seen = [], set()
    with open(path) as stream:
        for line in stream:
            item = json.loads(line)
            if item.get("type") != "result":
                continue
            identity = item.get("uuid")
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
            results.append({k: item.get(k) for k in ("uuid", "usage", "modelUsage", "total_cost_usd", "is_error", "num_turns")})
    return {"result_events": results, "cost_usd": None if not results or any(
        type(r.get("total_cost_usd")) not in (int, float) for r in results)
        else sum(r["total_cost_usd"] for r in results),
        "note": "Result events only. Feed one isolated run; do not mix resumed/cumulative sessions. Missing cost is unknown, not zero."}


def main(default_root):
    parser = argparse.ArgumentParser(description="SAP Context Optimizer M0/B0 (Python 3.12+, stdlib only)")
    parser.add_argument("--root", default=str(default_root))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("status")
    sub.add_parser("hook")
    p = sub.add_parser("probe-public", help="Public-only live MCP probe; requires reviewed project external_access=true")
    p.add_argument("--output", required=True)
    p = sub.add_parser("usage")
    p.add_argument("file")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "serve":
            serve(root, sys.stdin, sys.stdout)
        elif args.command == "hook":
            print(json.dumps(run_hook(root, json.load(sys.stdin)), ensure_ascii=False))
        elif args.command == "status":
            print(json.dumps(Gateway(root).call("sap_status", {}), ensure_ascii=False, indent=2))
        elif args.command == "probe-public":
            require_external(load_policy(root))
            report = probe()
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"report": str(path), "calls": len(report["calls"]),
                              "services": {k: "error" if "error" in v else "connected" for k, v in report["services"].items()}}))
            return 1 if any("error" in v for v in report["services"].values()) else 0
        elif args.command == "usage":
            print(json.dumps(usage_summary(args.file), ensure_ascii=False, indent=2))
    except (PolicyError, ProtocolError, OSError, ValueError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    return 0
