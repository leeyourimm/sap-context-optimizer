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

from .policy import PolicyError
from .local_fs import LocalFS
from .public_validation import verify_corpus

ARMS = ("A", "B0", "B1")
REQUIRED_FLAGS = ("--print", "--verbose", "--output-format", "--model", "--max-turns",
                  "--max-budget-usd", "--permission-mode", "--allowedTools", "--disallowedTools",
                  "--tools", "--strict-mcp-config", "--mcp-config", "--setting-sources",
                  "--settings", "--no-session-persistence")
DENIED_TOOLS = "Bash,Write,Edit,NotebookEdit,WebSearch,WebFetch,Task,Agent"


def numeric(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def preflight():
    executable = shutil.which("claude")
    report = {"executable_present": bool(executable), "version": None, "auth_readiness": "unverified",
              "supported_flags": False, "ready": False, "model_calls": 0,
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
        report["supported_flags"] = all(f in help_.stdout for f in REQUIRED_FLAGS)
        auth = subprocess.run([executable, "auth", "status", "--json"], capture_output=True,
                              text=True, timeout=15)
        value = json.loads(auth.stdout) if auth.returncode == 0 else {}
        report["auth_readiness"] = "logged_in" if value.get("loggedIn") is True else "unverified"
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
    if not isinstance(value, dict) or set(value) != fields or value.get("version") != 1:
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
    if value["arms"] != list(ARMS):
        raise PolicyError("Use all A/B0/B1 arms in fixed order")
    if (not isinstance(value["task_ids"], list) or not value["task_ids"] or
            any(not isinstance(t, str) for t in value["task_ids"]) or len(set(value["task_ids"])) != len(value["task_ids"])):
        raise PolicyError("Explicit unique task IDs required")
    return value


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def summarize(events, task, corpus):
    """Only terminal results are summed; tool delivery is not final-model-input proof."""
    results, calls, delivered, failures = {}, {}, [], 0
    invalid_events = 0
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
            if block.get("type") == "tool_result":
                failures += int(block.get("is_error") is True)
                name = calls.get(block.get("tool_use_id"), "")
                if block.get("is_error") is True or not name.startswith("mcp__sap-context__sap_"):
                    continue
                blocks = block.get("content", [])
                if isinstance(blocks, str):
                    blocks = [{"type": "text", "text": blocks}]
                for b in blocks if isinstance(blocks, list) else []:
                    if isinstance(b, dict) and isinstance(b.get("text"), str):
                        try:
                            parsed = json.loads(b["text"])
                            if not isinstance(parsed, dict) or parsed.get("isError") is not True:
                                delivered.append(parsed)
                        except ValueError:
                            pass  # Native Read output is not JSON; do not pretend to inspect it.
    result = next(iter(results.values())) if len(results) == 1 else {}
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    tokens = {k: numeric(usage.get(k)) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                               "cache_creation_input_tokens")}
    observed = list(walk(delivered))
    required = task.get("required_ranges", [])
    coverage = []
    for r in required:
        from .local_fs import relative_parts
        relative_parts(r["path"])
        raw = (corpus / r["path"]).read_bytes()
        expected_hash = hashlib.sha256(raw).hexdigest()
        lines = raw.decode("utf-8-sig").splitlines(keepends=True)
        covered = any(d.get("path") == "public_exports/" + r["path"] and d.get("sha256") == expected_hash
                      and type(d.get("start_line")) is int and type(d.get("end_line")) is int
                      and d["start_line"] <= r["start"] and d["end_line"] >= r["end"]
                      and d.get("source") == "".join(lines[d["start_line"] - 1:d["end_line"]]) for d in observed)
        coverage.append({**r, "observed_exact_source_in_tool_result": covered})
    body_sources = sorted({d["source_url"] for d in observed if d.get("body_retrieved") is True
                           and isinstance(d.get("source_url"), str)})
    return {"terminal_result_count": len(results), "invalid_events": invalid_events,
            "execution_success": not invalid_events and result.get("is_error") is False and result.get("subtype") == "success",
            "model": task.get("model"), "provider_reported_usage": tokens,
            "provider_reported_model_usage": {model: {k: numeric(v) for k, v in values.items() if k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD", "webSearchRequests", "contextWindow", "maxOutputTokens")}
                                              for model, values in result["modelUsage"].items() if isinstance(values, dict)} if isinstance(result.get("modelUsage"), dict) else None,
            "provider_reported_cost_usd": numeric(result.get("total_cost_usd")),
            "cost_source": "CLI terminal result, not independently audited invoice",
            "tool_calls": len(calls), "tool_names": sorted(set(calls.values())),
            "tool_error_results": failures, "retry_count": None, "model_call_count": None,
            "mandatory_range_observations": coverage,
            "mandatory_range_gate": all(r["observed_exact_source_in_tool_result"] for r in coverage) if coverage else None,
            "body_source_urls_observed": body_sources, "answer_correctness": None,
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
                   "help_evidence", "hooks", "local_fs", "policy", "probe", "public_validation", "repository", "state", "transport")
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
    runtime = preflight()
    if runtime["version"] != manifest["expected_cli_version"]:
        raise PolicyError("Approved CLI version differs from runtime")
    if not runtime["ready"]:
        raise PolicyError("Claude runtime/auth/required CLI flags unverified; execution refused")
    corpus = root / "tests/fixtures/public_exports"
    verify_corpus(root)
    suite = json.loads((root / "experiments/b2/tasks.json").read_text())
    tasks = {t["id"]: t for t in suite["tasks"]}
    if set(manifest["task_ids"]) - tasks.keys():
        raise PolicyError("Unknown public task ID")
    # Exclusive output avoids overwriting evidence and following pre-existing symlinks.
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    report = {"runtime": runtime, "fixture_kind": "pinned_public_sources_only", "runs": [],
              "approval_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
              "workspace_policy": "New temporary public-only cwd; strict MCP; project-only settings; no interactive permissions",
              "maximum_suite_budget_usd": len(manifest["task_ids"]) * 3 * manifest["per_run_budget_usd"],
              "limitations": ["OS/network isolation must be supplied by operator; CLI permissions are not a sandbox",
                              "Raw CLI logs remain local and may contain account metadata; do not publish",
                              "No assertion about final model inputs, answer correctness or invoiced costs"]}
    for task_id in manifest["task_ids"]:
        task = tasks[task_id]
        for arm in ARMS:
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
                log = output / f"{task_id}-{arm}.stream.jsonl"
                err = output / f"{task_id}-{arm}.stderr.txt"
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
                summary = summarize(events, task | {"model": manifest["model"]}, corpus)
                summary.update(task_id=task_id, arm=arm, exit_code=code, timed_out=timed_out,
                               elapsed_seconds=round(time.monotonic() - start, 3), malformed_lines=malformed,
                               prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
                report["runs"].append(summary)
                (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
                if code != 0 or timed_out or malformed or not summary["execution_success"]:
                    raise PolicyError("Run failed or stream contract changed; partial local report preserved; no automatic retry")
    return report
