"""Local Claude hooks. These are workflow guards, not an OS network sandbox."""
import json
import re
import sqlite3

from .policy import PolicyError, load_policy
from .state import State

UNVERIFIED = "[SAP 검증 미완료]"
SAP = re.compile(r"sap|abap|\brap\b|\bcds\b|\bbdef\b|\beml\b|\b(fi|co|mm|sd)\b|전표|입고|송장|정산|출고|청구|메서드|클래스|\b(?:zcl_|zif_|zbp_|zi_|zc_|lcl_|lhc_|lsc_)[a-z0-9_]+", re.I)


def hook(root, event):
    state = State(root)
    name = event.get("hook_event_name")
    session = str(event.get("session_id", "unknown"))[:200]
    if name == "PreToolUse":
        tool = event.get("tool_name", "")
        args = event.get("tool_input", {})
        reason = None
        if tool.startswith("mcp__") and not tool.startswith("mcp__sap-context__sap_"):
            reason = "Use the policy-enforced sap-context gateway; direct MCP tools bypass its outbound policy."
        if tool in ("WebFetch", "WebSearch"):
            reason = "Direct web transfer is disabled in this B0 profile. Use a reviewed SAP Help document ID."
        if tool in ("Write", "Edit", "MultiEdit"):
            path = str(args.get("file_path", "")).replace("\\", "/")
            if any(p in path for p in ("sap-context.json", "sap-context.local.json", ".mcp.json", ".claude/settings")):
                reason = "The agent must not change the reviewed outbound policy or hook/MCP configuration."
        if reason:
            state.metric("hook_denied")
            return {"hookSpecificOutput": {"hookEventName": name, "permissionDecision": "deny",
                                          "permissionDecisionReason": reason}}
        return {}
    if name == "UserPromptSubmit":
        is_sap = state.begin(session, bool(SAP.search(str(event.get("prompt", "")))))
        if not is_sap:
            return {}
        state.metric("sap_turn")
        p = load_policy(root)
        scope = {k: p.get(k) for k in ("product", "release", "deployment", "abap_language_version")}
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                "SAP evidence required this turn. Use sap-context tools automatically; topic IDs only, never send private text. "
                "For object/code questions use local sap_repo_search first (auto exact/BM25/references); free local query stays local. "
                "Search snippets/graph are not body evidence. Fetch applicable original text before concluding. "
                f"If evidence or applicability is missing, include {UNVERIFIED} and explain the gap. "
                "Never invent error codes, objects or SAP Note contents. Customizing-dependent fixes are conditional. "
                "External access: " + str(p["external_access"]) + "; declared scope (not independently verified): " + json.dumps(scope, ensure_ascii=False)}}
    if name == "PostToolUse":
        if event.get("tool_name") in ("mcp__sap-context__sap_repo_search", "mcp__sap-context__sap_repo_read"):
            result = event.get("tool_response", {})
            if isinstance(result, dict) and not result.get("isError"):
                data = result.get("structuredContent")
                if data is None:
                    try:
                        data = json.loads(result["content"][0]["text"])
                    except (KeyError, IndexError, TypeError, ValueError):
                        data = {}
                if isinstance(data, dict) and (data.get("source") or any(s.get("source") for s in data.get("results", []))):
                    state.mark_repository(session)
                    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                            "Local snapshot source observed, not official documentation or runtime proof. Check hash, declarations, "
                            "missing references and full original before edits. Never send this source externally."}}
            return {}
        if event.get("tool_name") not in ("mcp__sap-context__sap_read_step", "mcp__sap-context__sap_help_document",
                                           "mcp__sap-context__sap_read_tutorial_page"):
            return {}
        result = event.get("tool_response", {})
        if isinstance(result, dict) and not result.get("isError"):
            data = result.get("structuredContent")
            if data is None:
                try:
                    data = json.loads(result["content"][0]["text"])
                except (KeyError, IndexError, ValueError, TypeError):
                    data = {}
            if isinstance(data, dict) and data.get("body_retrieved") is True:
                state.mark_body(session)
                return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                        "Body retrieved; product/release applicability and claim support remain UNVERIFIED. "
                        "Do not treat retrieval as a correctness certificate."}}
        return {}
    if name == "Stop":
        sap, body, warned = state.turn(session)
        if not sap or warned or event.get("stop_hook_active"):
            return {}
        # One feedback pass only: never create an automatic retry loop.
        state.warn(session)
        if state.repository_seen(session) and not body:
            state.metric("local_repository_review_required")
            return {"decision": "block", "reason": "Local snapshot source was retrieved. Do not require an unrelated tutorial "
                    "as proof of customer code. Cite local paths/lines/hash; disclose missing dependencies and runtime/release "
                    f"uncertainty using {UNVERIFIED} where relevant. Do not claim execution or backend state verification."}
        state.metric("evidence_gap" if not body else "applicability_review_required")
        return {"decision": "block", "reason":
                ("No official body was observed this turn. " if not body else "A retrieved body does not certify applicability. ")
                + f"Check product/release and claim support. If incomplete, put {UNVERIFIED} in the answer and state what is missing. "
                  "Do not repeat failed searches indefinitely. This is the only automatic evidence reminder."}
    return {}


def run_hook(root, event):
    try:
        load_policy(root)
        return hook(root, event)
    except (PolicyError, OSError, ValueError, sqlite3.Error):
        if event.get("hook_event_name") == "PreToolUse":
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": "SAP policy/state unavailable; fail closed."}}
        return {"systemMessage": "[SAP 검증 미완료] Policy/state unavailable. Do not transmit project data or claim verification."}
