"""Opt-in public-fixture Claude CLI experiment. Offline by default; no SDK/dependencies."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from itertools import permutations

from .policy import PolicyError
from .local_fs import LocalFS
from .public_validation import verify_corpus
from .source_observation import native_read, ranges

ARMS = ("A", "B0", "B1")
REQUIRED_FLAGS = ("--print", "--verbose", "--output-format", "--model", "--max-turns",
                  "--max-budget-usd", "--permission-mode", "--allowedTools", "--disallowedTools",
                  "--tools", "--strict-mcp-config", "--mcp-config", "--setting-sources",
                  "--settings", "--no-session-persistence")
DENIED_TOOLS = "Bash,Write,Edit,NotebookEdit,WebSearch,WebFetch,Task,Agent"


class RuntimeNotReady(PolicyError):
    def __init__(self, report):
        super().__init__('Claude runtime prerequisites unverified; no model invocation attempted')
        self.report = report


def numeric(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def preflight():
    executable = shutil.which("claude")
    report = {"executable_present": bool(executable), "version": None, "auth_readiness": "unverified",
              "supported_flags": False, "flag_detection_only": True, "flag_semantics_verified": False,
              "auth_command": "claude auth status (JSON default)", "ready": False, "model_calls": 0,
              "cwd_readable": os.access(Path.cwd(), os.R_OK), "cwd_writable": os.access(Path.cwd(), os.W_OK),
              "process_group_timeout_supported": os.name == "posix",
              "permissions": "CLI restrictions configured by runner; OS/provider isolation requires operator approval"}
    if not executable:
        report["reason"] = "Claude Code executable unavailable; no installation or login attempted"
        return report
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=15)
        help_ = subprocess.run([executable, "--help"], capture_output=True, text=True, timeout=15)
        # Do not include arbitrary CLI output (or stderr) in sharable reports.
        import re
        match = re.search(r"\b\d+\.\d+\.\d+\b", version.stdout)
        report["version"] = match.group() if match else None
        report["supported_flags"] = all(re.search(r"(?<![\w-])" + re.escape(f) + r"(?![\w-])", help_.stdout) for f in REQUIRED_FLAGS)
        auth = subprocess.run([executable, "auth", "status"], capture_output=True,
                              text=True, timeout=15)
        value = json.loads(auth.stdout) if auth.returncode == 0 else {}
        report["auth_readiness"] = "logged_in" if isinstance(value, dict) and value.get("loggedIn") is True else "unverified"
        report["ready"] = bool(version.returncode == help_.returncode == 0 and
                               report["version"] and report["supported_flags"] and
                               report["auth_readiness"] == "logged_in" and report["cwd_readable"] and
                               report["cwd_writable"] and report["process_group_timeout_supported"])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        report["reason"] = "Read-only version/help/auth-status preflight failed; no login attempted"
    return report


def approval(value):
    fields = {"version", "approved_public_model_calls", "approved_runtime_isolated", "approved_by",
              "model", "expected_cli_version", "suite_sha256", "corpus_manifest_sha256", "per_run_budget_usd", "max_turns", "timeout_seconds", "arms", "task_ids"}
    if isinstance(value, dict) and value.get("version") == 2:
        fields |= {"run_mode", "smoke_arm", "repetitions", "evidence_suite_sha256"}
    if (not isinstance(value, dict) or set(value) != fields or type(value.get("version")) is not int
            or value["version"] not in (1, 2)):
        raise PolicyError("Invalid explicit approval manifest")
    if value["approved_public_model_calls"] is not True or value["approved_runtime_isolated"] is not True:
        raise PolicyError("Explicit public model-call and isolated runtime approval required")
    for k in ("approved_by", "model", "expected_cli_version"):
        if not isinstance(value[k], str) or not value[k].strip() or len(value[k]) > 120 or value[k].startswith("-"):
            raise PolicyError("Invalid approval identity/model")
    if not numeric(value["per_run_budget_usd"]) or value["per_run_budget_usd"] > 10:
        raise PolicyError("Budget must be positive and at most 10 USD per run")
    for k, lo, hi in (("max_turns", 1, 30), ("timeout_seconds", 10, 1800)):
        if type(value[k]) is not int or not lo <= value[k] <= hi:
            raise PolicyError("Invalid run bound")
    if (not isinstance(value["task_ids"], list) or not value["task_ids"] or
            any(not isinstance(t, str) for t in value["task_ids"]) or len(set(value["task_ids"])) != len(value["task_ids"])):
        raise PolicyError("Explicit unique task IDs required")
    if value["version"] == 2:
        if value["run_mode"] not in ("smoke", "counterbalanced") or value["smoke_arm"] not in ARMS:
            raise PolicyError("Invalid experiment mode/arm")
        n = value["repetitions"]
        if type(n) is not int or (value["run_mode"] == "smoke" and (n != 1 or len(value["task_ids"]) != 1)):
            raise PolicyError("Smoke requires exactly one public task, one arm, one repetition")
        if value["run_mode"] == "counterbalanced" and n not in (6, 12):
            raise PolicyError("Counterbalance requires 6 or 12 repetitions covering all permutations")
    if value["arms"] != list(ARMS):
        raise PolicyError("Declare the A/B0/B1 arm vocabulary")
    return value


def execution_plan(manifest):
    if manifest.get("run_mode") == "smoke":
        return [(0, manifest["smoke_arm"])]
    if manifest.get("run_mode") == "counterbalanced":
        orders = list(permutations(ARMS))
        return [(r, arm) for r in range(manifest["repetitions"]) for arm in orders[r % len(orders)]]
    return [(0, arm) for arm in ARMS]  # Explicit legacy v1 compatibility; not counterbalanced.


def failure_reason(summary, code, timed_out, malformed):
    if timed_out:
        return "wall_timeout"
    if summary.get("model_identity_match") is False:
        return "model_identity_mismatch"
    if summary["terminal_subtype"] in ("error_max_turns", "error_max_budget_usd"):
        return summary["terminal_subtype"]
    if malformed or summary["invalid_events"]:
        return "malformed_stream"
    if code != 0:
        return "process_nonzero_inspect_private_stderr"
    if summary["terminal_result_count"] != 1:
        return "terminal_contract"
    if not summary["execution_success"]:
        return "terminal_error"
    return None


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def summarize(events, task, corpus, workspace=None):
    """Only terminal results are summed; tool delivery is not final-model-input proof."""
    results, calls, delivered, failures = {}, {}, [], 0
    invalid_events = 0
    call_inputs, native, payload_metrics = {}, [], []
    observed_models = set()
    for event in events:
        if not isinstance(event, dict):
            invalid_events += 1
            continue
        if event.get("type") == "result":
            # A print invocation must have exactly one terminal result. Dedup repeated UUID.
            key = event.get("uuid") if isinstance(event.get("uuid"), str) and event["uuid"] else "missing-uuid-" + str(len(results))
            if key in results and results[key] != event:
                invalid_events += 1
            results[key] = event
        message = event.get("message", {})
        if event.get("type") == "assistant" and isinstance(message, dict) and isinstance(message.get("model"), str):
            observed_models.add(message["model"])
        content = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                if not isinstance(block.get("name"), str):
                    invalid_events += 1
                calls[block["id"]] = block["name"] if isinstance(block.get("name"), str) else "unknown"
                call_inputs[block["id"]] = block.get("input", {})
            if block.get("type") == "tool_result":
                failures += int(block.get("is_error") is True)
                use_id = block.get("tool_use_id")
                name = calls.get(use_id, "") if isinstance(use_id, str) else ""
                blocks = block.get("content", [])
                if isinstance(blocks, str):
                    blocks = [{"type": "text", "text": blocks}]
                blocks = blocks if isinstance(blocks, list) else []
                text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str))
                payload_metrics.append({"tool_name": name or "unmatched", "chars": len(text), "bytes": len(text.encode()),
                                        "model_input_tokens": None})
                if name == "Read" and block.get("is_error") is not True:
                    reading = native_read(call_inputs.get(block.get("tool_use_id")), blocks, workspace, corpus)
                    if reading:
                        native.append(reading)
                if block.get("is_error") is True or not name.startswith("mcp__sap-context__sap_"):
                    continue
                for b in blocks:
                    if isinstance(b, dict) and isinstance(b.get("text"), str):
                        try:
                            parsed = json.loads(b["text"])
                            if isinstance(parsed, dict) and parsed.get("format") == "sap-context-lossless/1":
                                from .compact import expand
                                parsed = expand(parsed)
                            if not isinstance(parsed, dict) or parsed.get("isError") is not True:
                                delivered.append(parsed)
                        except (ValueError, KeyError, IndexError, TypeError):
                            pass  # Native Read output is not JSON; do not pretend to inspect it.
    result = next(iter(results.values())) if len(results) == 1 else {}
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    tokens = {k: numeric(usage.get(k)) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                               "cache_creation_input_tokens")}
    if isinstance(result.get("modelUsage"), dict):
        observed_models.update(result["modelUsage"])
    observed = list(walk(delivered))
    coverage = ranges(task, observed, native, corpus)
    body_sources = sorted({d["source_url"] for d in observed if d.get("body_retrieved") is True
                           and isinstance(d.get("source_url"), str)})
    return {"observed_model_ids": sorted(observed_models),
            "model_identity_match": all(m == task.get("model") for m in observed_models) if observed_models and task.get("model") else None,
            "terminal_result_count": len(results), "invalid_events": invalid_events,
            "execution_success": not invalid_events and result.get("is_error") is False and result.get("subtype") == "success",
            "terminal_subtype": result.get("subtype") if result.get("subtype") in ("success", "error_max_turns", "error_max_budget_usd", "error_during_execution") else "unknown",
            "model": task.get("model"), "provider_reported_usage": tokens,
            "provider_reported_model_usage": {model: {k: numeric(v) for k, v in values.items() if k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD", "webSearchRequests", "contextWindow", "maxOutputTokens")}
                                              for model, values in result["modelUsage"].items() if isinstance(values, dict)} if isinstance(result.get("modelUsage"), dict) else None,
            "provider_reported_cost_usd": numeric(result.get("total_cost_usd")),
            "cost_source": "CLI terminal result, not independently audited invoice",
            "tool_calls": len(calls), "tool_names": sorted(set(calls.values())),
            "tool_result_text_payloads": payload_metrics, "native_Read_observations": native,
            "repeated_identical_tool_inputs": len(call_inputs) - len({(calls[k], json.dumps(v, sort_keys=True)) for k, v in call_inputs.items()}),
            "tool_error_results": failures, "retry_count": None, "model_call_count": None,
            "mandatory_range_observations": coverage,
            "mandatory_range_gate": all(r["observed_exact_source_in_tool_result"] for r in coverage) if coverage else None,
            "body_source_urls_observed": body_sources, "answer_correctness": None,
            "evaluation_group": task.get("evaluation_group"), "accuracy_case_id": task.get("accuracy_case_id"),
            "answer_evidence_status": "manual_review_required", "final_model_input": "unobserved",
            "automatic_tool_selection": "observed_tool_calls_only_not_completeness_proof",
            "actual_invoiced_cost": None}


def prepare(root, workspace, arm, task):
    """Only pinned public fixtures and reviewed integration code enter the test workspace."""
    manifest = verify_corpus(root)
    fs = LocalFS(root)
    # Copy only hash-pinned upstream files, never local policies, oracle/NOTICE
    # edits, credentials, extra CLI settings or untracked files.
    for repository in manifest["repositories"]:
        for item in repository["files"]:
            raw = fs.read("tests/fixtures/public_exports/" + item["path"], 2_000_000)
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise PolicyError("Public source changed while staging")
            destination = workspace / "public_exports" / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    policy = {"version": 1, "external_access": arm != "A", "product": task["product"],
              "release": task["release"], "deployment": task["deployment"],
              "abap_language_version": task["abap_language_version"], "official_documents": {},
              "local_repository": {"roots": ["public_exports/" + d for d in ("clas", "intf", "fugr", "prog", "rap100")],
                                   "allow_model_context": arm == "B1"}}
    (workspace / "sap-context.json").write_text(json.dumps(policy))
    servers = {}
    if arm != "A":
        modules = ("__init__", "abap_syntax", "benchmark", "claude_e2e", "cli", "compact", "gateway",
                   "help_evidence", "hooks", "local_fs", "policy", "probe", "public_validation", "repository", "state", "transport", "scoped_context", "source_observation")
        for module in modules:
            destination = workspace / "sap_optimizer" / (module + ".py")
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(fs.read("sap_optimizer/" + module + ".py", 1_000_000))
        (workspace / "scripts").mkdir()
        (workspace / "scripts/sap_context.py").write_bytes(fs.read("scripts/sap_context.py", 1_000_000))
        import sys
        servers = {"sap-context": {"command": sys.executable, "args": [str(workspace / "scripts/sap_context.py"), "serve"]}}
        for filename in (".claude/settings.json", ".claude/skills/sap-evidence/SKILL.md", ".claude/policies/sap-correctness.md"):
            destination = workspace / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(fs.read(filename, 1_000_000))
    (workspace / "mcp-test.json").write_text(json.dumps({"mcpServers": servers}))
    settings = {"permissions": {"deny": DENIED_TOOLS.split(",") + ["Read(**/.env*)", "Read(**/*credential*)"]}}
    (workspace / "test-settings.json").write_text(json.dumps(settings))
    return workspace / "mcp-test.json", workspace / "test-settings.json"


def run(root, manifest, output):
    manifest = approval(manifest)
    for filename, field in (("experiments/b2/tasks.json", "suite_sha256"),
                            ("tests/fixtures/public_exports/manifest.json", "corpus_manifest_sha256")):
        if hashlib.sha256((root / filename).read_bytes()).hexdigest() != manifest[field]:
            raise PolicyError("Approved public suite/corpus changed; review again")
    if manifest["version"] == 2 and hashlib.sha256((root / "experiments/b2/product-cases.json").read_bytes()).hexdigest() != manifest["evidence_suite_sha256"]:
        raise PolicyError("Approved accuracy evidence suite changed")
    runtime = preflight()
    if not runtime["ready"]:
        raise RuntimeNotReady(runtime)
    if runtime["version"] != manifest["expected_cli_version"]:
        raise PolicyError("Approved CLI version differs from runtime")
    corpus = root / "tests/fixtures/public_exports"
    verify_corpus(root)
    suite = json.loads((root / "experiments/b2/tasks.json").read_text())
    tasks = {t["id"]: t for t in suite["tasks"]}
    evidence_cases = {c["id"]: c for c in json.loads((root / "experiments/b2/product-cases.json").read_text())["cases"]} if manifest["version"] == 2 else {}
    if set(manifest["task_ids"]) - tasks.keys():
        raise PolicyError("Unknown public task ID")
    # Exclusive output avoids overwriting evidence and following pre-existing symlinks.
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    plan = execution_plan(manifest)
    report = {"runtime": runtime, "execution_plan": plan, "counterbalanced": manifest.get("run_mode") == "counterbalanced", "fixture_kind": "pinned_public_sources_only", "runs": [],
              "approval_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
              "workspace_policy": "New temporary public-only cwd; strict MCP; project-only settings; no interactive permissions",
              "requested_client_budget_total_usd": len(manifest["task_ids"]) * len(plan) * manifest["per_run_budget_usd"],
              "billing_cap_guaranteed": False, "invoice_reconciliation": None,
              "limitations": ["OS/network isolation must be supplied by operator; CLI permissions are not a sandbox",
                              "Raw CLI logs remain local and may contain account metadata; do not publish",
                              "No assertion about final model inputs, answer correctness or invoiced costs",
                              "Client budget controls do not guarantee a final invoice cap; interrupted/failed calls may still be charged"]}
    for task_id in manifest["task_ids"]:
        task = tasks[task_id]
        for repetition, arm in plan:
            with tempfile.TemporaryDirectory(prefix="sap-b2-public-") as directory:
                workspace = Path(directory)
                mcp, settings = prepare(root, workspace, arm, task)
                command = [shutil.which("claude"), "--print", "--verbose", "--output-format", "stream-json",
                           "--model", manifest["model"], "--max-turns", str(manifest["max_turns"]),
                           "--max-budget-usd", str(manifest["per_run_budget_usd"]), "--permission-mode", "dontAsk",
                           "--tools", "Read,Skill" if arm != "A" else "Read",
                           "--allowedTools", "Read,Skill,mcp__sap-context__*" if arm != "A" else "Read",
                           "--disallowedTools", DENIED_TOOLS + (",mcp__sap-context__sap_repo_*" if arm == "B0" else ""), "--strict-mcp-config", "--mcp-config", str(mcp),
                           "--setting-sources", "project", "--settings", str(settings), "--no-session-persistence"]
                prompt = (f"Environment: product={task['product']}; release={task['release']}; "
                          f"deployment={task['deployment']}; ABAP={task['abap_language_version']}.\n"
                          "Public abapGit files, if needed, are under public_exports. Do not modify anything. "
                          "State missing evidence and cite original sources/ranges.\n" + task["prompt"])
                run_id = f"{task_id}-r{repetition}-{arm}"
                log = output / f"{run_id}.stream.jsonl"
                err = output / f"{run_id}.stderr.txt"
                start = time.monotonic()
                timed_out = False
                # No stdout logging to the console, no credentials read or copied by this runner.
                with log.open("x", encoding="utf-8") as stdout, err.open("x", encoding="utf-8") as stderr:
                    try:
                        child = subprocess.Popen(command, stdin=subprocess.PIPE, text=True, stdout=stdout,
                                                 stderr=stderr, cwd=workspace, start_new_session=True)
                        child.communicate(prompt, timeout=manifest["timeout_seconds"])
                        code = child.returncode
                    except subprocess.TimeoutExpired:
                        import signal
                        os.killpg(child.pid, signal.SIGKILL)
                        child.communicate()
                        timed_out, code = True, None
                events, malformed = [], 0
                for line in log.read_text().splitlines():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        malformed += 1
                summary = summarize(events, task | {"model": manifest["model"]}, corpus, workspace)
                summary.update(task_id=task_id, arm=arm, repetition=repetition, exit_code=code, timed_out=timed_out,
                               oracle_state=evidence_cases.get(task.get("accuracy_case_id"), {}).get("status"),
                               oracle_live_revalidated_by_runner=False,
                               failure_reason=failure_reason(summary, code, timed_out, malformed),
                               provider_cost_exceeds_client_budget=(summary["provider_reported_cost_usd"] > manifest["per_run_budget_usd"])
                                   if summary["provider_reported_cost_usd"] is not None else None,
                               elapsed_seconds=round(time.monotonic() - start, 3), malformed_lines=malformed,
                               prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
                if summary['provider_cost_exceeds_client_budget'] and summary['failure_reason'] is None:
                    summary['failure_reason'] = 'provider_reported_client_budget_overrun'
                report["runs"].append(summary)
                (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
                if summary["failure_reason"] is not None:
                    raise PolicyError("Run failed or stream contract changed; partial local report preserved; no automatic retry")
    return report
