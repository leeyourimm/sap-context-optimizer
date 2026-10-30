# B2 validation — tools prepared, real Claude E2E unexecuted

Scope: owner review [5711995440 on PR #3](https://github.com/leeyourimm/sap-context-optimizer/pull/3#pullrequestreview-5711995440). This branch is stacked on PR #3. PR #2/#3 remain unmerged. No JEV, extra model, dependency installation, SAP write, private-source upload or deployment.

## Executed validation

| Command | Result |
|---|---|
| `python -m unittest discover -s tests -v` | 147 passed: all previous 119 plus 28 B2 contracts |
| `python scripts/verify_b1.py --isolated --output-dir reports/b2-b1-regression` | Actual subprocess stdio initialization/list/search/read/reference/status smoke passed; prior A/B/C sizes and gates retained |
| `python scripts/verify_public_exports.py --output reports/b2-public-regression.json` | 64 upstream files verified, 48 indexed source files, 15 objects; 15/15 selected retrieval cases passed; 0 required objects/ranges missing |
| `python scripts/verify_b2.py --output reports/b2-offline.json` | Public-source compact lossless round-trip and field-size accounting passed; runtime unavailable |
| `python scripts/probe_help_evidence.py --execute --output reports/b2-help-probe.json` | Two fixed public SAP Help GETs returned HTTP 200 and matching title/body markers |

The public corpus and manual range oracle from B1 are unchanged. Its results measure selected source-retrieval regressions, not general SAP correctness. B2 tests cover approval/hash/version gates, read-only auth preflight, three mock CLI arms with identical prompt hash, exact source/hash observations, malformed/missing terminal data, cache/cost null semantics, timeout process-group termination, no automatic retry, exclusive output, allowlisted workspace copying, compact stdio/model-context denial, unchanged default wire, hook observations without updatedToolOutput, Help title/marker/shell/access/revocation checks.

Artifacts: [test log](b2-tests.txt), [B1 smoke](b2-b1-regression/b1-local-smoke.json), [public retrieval](b2-public-regression.json), [B2 offline](b2-offline.json), [public Help probe](b2-help-probe.json). No raw real-Claude logs are committed.

## Actual public product-document evidence

On 2026-10-30, both built-in IDs produced a real body:

| ID / declared scope | Observed title | Extracted body characters |
|---|---|---:|
| `abap-754-call-function` / ABAP 7.54 | CALL FUNCTION - ABAP Keyword Documentation | 2,436 |
| `abap-754-select` / ABAP 7.54 | SELECT - ABAP Keyword Documentation | 7,549 |

The probe retains exact official URLs, timestamps, HTTP status and raw/body SHA-256, without redistributing document bodies. Title and marker validation is a drift/login-shell check, not semantic certification. All responses retain `applicability_verified=false`; declared product/release comparison is separate.

This closes a small ABAP keyword-body retrieval gap only. **FI/CO/MM/SD error-specific product evidence remains incomplete.** The catalog exposes that gap, supports locally reviewed public Help IDs with scope/access/body markers, and refuses free URLs. Login-required records return no body and are not fetched; this implements no SAP Note/KBA login or subscription entitlement. Legacy configured documents remain compatible, explicitly labeled length-only validation. Do not claim a verified module-error solution from those entries or unrelated tutorials.

## Response-size explanation and compact experiment

Historical synthetic case is unchanged: 279 original source characters, 5,252 bytes of search JSON data. Default MCP carries those data twice (`content.text` and `structuredContent`): 10,504 bytes plus 614 bytes escaping/envelope = **11,118 wire bytes**. Within the result array, encoded original source values occupy 295 bytes, declaration/implementation locations 952, direct references 487, symbol metadata 446, SHA values 264, snapshot values 264; the JSON artifact includes every field and punctuation separately. These are useful provenance/context fields, not all source code.

Public RAP100 `acceptTravel` response: default **86,601 wire bytes**, experimental lossless compact **84,729 wire bytes** for this snapshot. Unresolved references alone occupy 24,399 bytes in default data; diagnostics occupy 4,492. The optional format factors repeated values and preserves all code/provenance/relationships/omissions/diagnostics, demonstrated by exact round-trip and actual compact stdio tests. Default tool/serializer behavior remains unchanged. A compact response can add overhead and requires model decoding; it is not automatically recommended or proven more efficient for Claude.

**No conversion to model tokens or cost is made.** Which text/structured fields Claude actually consumes is unobserved. Smaller server wire output does not prove reduced paid input, retained answer accuracy, or lower total cost.

## Real Claude Code status and remaining work

`claude` is absent. No model was invoked, installed or logged in. Actual automatic Skill/tool selection, option semantics, live hook delivery, final model input, tokens/cache/cost/retries and SAP answer quality are **unverified**. Official CLI reference fetch also returned HTTP 403 here; read-only installed-version/help/auth checks and execution fail-closed behavior are provided rather than claiming runtime compatibility.

[Approved-runtime instructions](../experiments/b2/README.md) and the opt-in runner provide nine public tasks × A/B0/B1, fixed scope/model/budget, approval of exact task/corpus hashes and CLI version, fresh public-only workspaces, protected local stream logs, terminal-only usage accounting and a blank manual review template. Missing observations remain null; exact MCP source delivery is distinct from answer correctness. Native Read coverage needs manual review. Mock CLI execution is contract validation only.

An operator must supply an isolated POSIX environment and approved provider route. CLI tool restrictions/hooks do not enforce a general network/filesystem boundary. Paid execution remains opt-in and requires a separate explicit local approval manifest; example approvals are false. Next priorities are an approved real run with SAP reviewers, reviewed FI/CO/MM/SD product passages, native Read observation parity, and counterbalanced repetitions/invoice reconciliation before any savings claim. Search/Graph gateway behavior is regression-tested; their live public service contracts were not re-probed in B2.
