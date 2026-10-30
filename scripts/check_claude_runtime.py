#!/usr/bin/env python3
"""Local capability inventory only: never logs values or calls a model/provider."""
import importlib.util
import json
import os
import shutil


def inspect_runtime():
    executable = shutil.which("claude")
    sdk = importlib.util.find_spec("claude_agent_sdk") is not None
    bindings = {name: bool(os.environ.get(name)) for name in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")}
    return {"claude_executable_present": executable is not None, "agent_sdk_discoverable": sdk,
            "binding_presence_only": bindings, "credential_readiness": "not_tested",
            "runtime_test_attempted": False, "model_calls": 0,
            "automatic_tool_selection": "unverified", "final_model_input": "unverified",
            "actual_billing_tokens": None, "actual_cost": None,
            "reason": "Claude Code executable unavailable" if executable is None else
                      "Executable present; approved runtime/auth/payload observation still required",
            "output_contract": "content.text and structuredContent preserved; wire duplication is not billing-token evidence"}


if __name__ == "__main__":
    print(json.dumps(inspect_runtime(), indent=2))
