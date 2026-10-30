# B2: approved-runtime experiment

**Real Claude Code E2E has NOT run in the Codex environment.** The CLI is absent. Offline/mock tests prove runner and serialization contracts only. No installation, login, paid model request, JEV, or deployment is performed here.

## Read-only preflight

```sh
python scripts/run_claude_e2e.py
```

This probes executable presence, numeric CLI version, required help flags, read-only `claude auth status --json`, cwd read/write permission and POSIX process-group support. It prints no credentials, CLI stderr, account identity or credential-file contents. Unknown authentication/options/version fails closed. Provider-specific auth implementations which do not return `loggedIn: true` need a reviewed adapter; the runner does not try an interactive fallback.

## Prepare an approved environment

Use a fresh, operator-controlled POSIX container/VM with this branch checked out and an already provisioned, approved Claude account/provider route. Do not mount company sources, home directories containing unrelated files, cloud credentials, other project indices, or unrelated global Claude memory/plugins/hooks. Provision Claude/authentication outside this script; **do not paste keys into the manifest**. Keep the normal TLS/proxy configuration. Supply OS filesystem and egress restrictions independently (approved model provider, SAP Developers MCP and reviewed SAP Help only). CLI `dontAsk`, denied tools, strict MCP configuration, and the gateway are workflow controls, not an OS/network sandbox.

The runner stages new temporary workspaces from only 64 hash-pinned public upstream files, fixed integration Python modules and three reviewed `.claude` files. It does not copy project-local policies/settings, private exports, `.git`, arbitrary modules, oracle files, or credentials. Same prompt/product/release/model/budget is used across arms. The normal repository policy remains unchanged.

1. Run the preflight. Review CLI version, approved provider route, isolation, auth, budgets and the nine public tasks in `tasks.json`. Version/help checks cannot prove all flag semantics; an unsupported live CLI fails and preserves local logs.
2. Copy `approval.example.json` to an **ignored local path**, e.g. `.sap-context/b2-approval.json`. Set the two approval booleans only after authorization, set `approved_by`, an exact approved model ID and observed CLI version. Review task/corpus hashes against the approved checkout. Select task IDs and bound cost/turn/time explicitly. Do not lower accuracy requirements to fit the budget. Example default cap is 9 × 3 × USD 0.50 = USD 13.50, not a predicted charge; actual invoice and failed/timeout charges require reconciliation.
3. Run one opt-in command (output parent must already exist; leaf must be NEW):

```sh
python scripts/run_claude_e2e.py --execute --approval .sap-context/b2-approval.json --output .sap-context/b2-approved-run
```

Never run this command merely to complete CI. No automatic retry, login, install, session reuse or permission bypass occurs. First failed/invalid stream stops the suite. Timeout kills the CLI process group on POSIX; an already accepted provider request can still incur cost. Reports/logs remain in a mode-0700 directory; raw stream/stderr can contain account metadata and **must not be published**. Review/sanitize before sharing any summaries.

## Arms and what is actually observed

| Arm | Configuration | Source access |
|---|---|---|
| A | Fresh CLI, no SAP hooks/Skill/MCP; strict empty MCP config | Built-in Read over the same public export |
| B0 | SAP evidence Skill/hooks, policy gateway to official Search/Graph + reviewed Help | Read remains available for fair baseline; local MCP source tools denied by policy and CLI |
| B1 | B0 plus local ABAP MCP | Same public export, explicit `allow_model_context=true` |

B0 is the existing policy-enforced official MCP integration, not unrestricted direct access to SAP. Settings sources are project-only; strict MCP ignores ambient MCP servers. Read, the reviewed Skill (B arms), approved MCP tools and hooks are permitted; Bash/Edit/Write/WebFetch/WebSearch/Task/Agent are denied. Automatic tool choice is part of the experiment, never a premise. Integration code itself can be read in B arms; this is a disclosed difference from A.

The nine tasks cover tutorial evidence, deliberately underspecified FI/CO/MM/SD errors, a real ABAP keyword document, pinned public Function Module, RAP Action and Validation. Product/release conditions are fixed per task across arms. S/4HANA 2022 is an experimental declaration, not proof that the RAP100 sample or a proposed fix is applicable. Module-error cases intentionally lack message codes; success requires admitting missing evidence and requesting the necessary code/long text/Customizing, not inventing a fix.

`summary.json` separates terminal CLI usage (input/output/cache), provider-reported USD, per-model usage, tool-use IDs/names/errors, elapsed time, exact source/hash/range observations, and answer evaluation. Terminal UUIDs are deduplicated; assistant cumulative counters are not summed. Multiple terminal results fail. Missing data is null. Model-call counts, semantic retry counts, final model input, answer correctness and independently invoiced cost remain null/unobserved. CLI cost is not an audited invoice. Tool calls are observed calls, not proof that all necessary tools were selected.

Mandatory ranges come from the manually inspected PR #3 public-source oracle. A range observation requires a matching MCP tool-use/result ID, success, exact path/SHA and exact original snippet. Native `Read` text is deliberately not parsed; a false observation gate means **no machine-verified range delivery**, not proof that A failed to read it. Compare A/B0 native reads manually. JSON wire size is not billed tokens. Hooks use additionalContext only; `updatedToolOutput` is not used and no schema rewriting is assumed.

## Human evaluation, before comparing costs

Review raw answers and tool results locally; record one row per task/arm with:

- correct/incorrect/unverifiable answer; each supported claim's original body/section and applicable product/release;
- exact required range coverage (including native Read), missing objects, unresolved references and omitted ranges;
- confirmed facts vs inference, Customizing prerequisites, correct handling of absent error codes and inaccessible Notes;
- fabricated object/API/message/Note claims, unapproved external transfer or policy bypass;
- execution/task success and observed retries (use null if not observable).

`review-template.json` supplies blank rows and gates. Two SAP reviewers should resolve disagreements without seeing token/cost results first. Do not use a model judge in B2. Reject any security violation or required-code omission; only compare cost among runs meeting the same reviewed accuracy/security gate. No percentage savings or SAP accuracy claim is justified until a real approved experiment, invoice reconciliation, and this review are complete. Fixed A→B0→B1 order and provider caching can bias results; preserve cache metrics, repeat on a separate approved schedule with counterbalanced order in a later benchmark rather than attributing differences to retrieval alone.

## Public product-document evidence

```sh
python scripts/probe_help_evidence.py
# Explicit opt-in, fixed public GETs only, no model calls:
python scripts/probe_help_evidence.py --execute --output .sap-context/help-probe.json
```

`sap_help_catalog` is offline and discloses gaps. `sap_help_document` accepts catalog/configured IDs only. Built-in ABAP 7.54 CALL FUNCTION/SELECT pages require HTTP 200, matching observed title and reviewed body markers, with raw-response/body SHA-256 and timestamp. Redirects, shells, changed markers and inaccessible responses fail. Product/release comparison remains declared, applicability and claim support still need human review.

There is **no verified FI/CO/MM/SD product-error catalog yet**, no full Help search and no Note/KBA body access. A reviewer can add a specific public Help document to project policy with URL, title, product, release, `access: "public"`, and non-empty `required_markers` (up to 10). Verify the real passage first; do not use a product landing page. Legacy entries retain length-only behavior for compatibility and are explicitly labeled `legacy_length_check_only`. `access: "login_required"` returns no body and makes no fetch; it does not implement Note authentication or authorize a restricted body. Notes domains remain outside the gateway's URL allowlist.

## Experimental compact response

Default `sap_repo_search` and `tool_result` are unchanged. Explicit research tool `sap_repo_search_compact` returns `sap-context-lossless/1`: `data`, `shared`, `references`. For each reference, replace `data`'s null at the list-of-keys/indices `path` with the full `shared[shared_index]`. Shared values contain no nested references. `sap_optimizer.compact.expand` is the reference decoder. All original source, paths, line numbers, SHA, snapshot, relations, unresolved/omitted/parse diagnostics survive exact round-trip. Original full-source reads remain available and policy-gated. Skills default to the ordinary tool; live model comprehension of compact data is unverified.

```sh
python -m unittest discover -s tests -v
python scripts/verify_b1.py --isolated --output-dir .sap-context/b1-regression
python scripts/verify_public_exports.py --output .sap-context/public-regression.json
python scripts/verify_b2.py --output .sap-context/b2-offline.json
```

The last command breaks down the historical 279-character / 11,118-byte case and public RAP100 response by field, including repeated metadata/relations/diagnostics, content-text/structuredContent duplication, escaping and envelope. CI runs offline/mocked contracts only. Compact encoding has decoding overhead and may be larger for some cases; no billing savings are inferred.
