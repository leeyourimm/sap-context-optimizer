# B2.1 validation: offline preparation complete, real E2E unexecuted

Scope: [latest PR #4 review](https://github.com/leeyourimm/sap-context-optimizer/pull/4#pullrequestreview-5712215986). Separate branch `feature/b2-1-validation`, stacked on PR #4. No merge, JEV/model routing, private-source upload, SAP write, installation, login, paid model call or deployment.

## Executed checks

| Command | Result |
|---|---|
| `python -m unittest discover -s tests -v` | **173 passed**, retaining the previous 147 and adding 26 B2.1 tests |
| `python scripts/verify_b1.py --isolated --output-dir reports/b21-b1-regression` | Actual subprocess stdio smoke and prior synthetic source/range gates passed |
| `python scripts/verify_public_exports.py --output reports/b21-public-regression.json` | 64 pinned upstream files verified; 48 indexed source files / 15 objects; 15/15 cases, zero required objects/ranges missing |
| `python scripts/verify_b21.py --output reports/b21-scoped.json` | Same 15 public source-oracle cases passed; scoped original snippets/direct relations unchanged; all deferred records recovered |
| `python scripts/verify_product_cases.py --execute --output reports/b21-product-evidence.json` | Two public ABAP original bodies/sections/support quotations/hashes revalidated; four module-product cases explicitly pending |
| `python scripts/run_claude_e2e.py` | CLI absent, ready=false, zero model calls, no install/login attempted |

Artifacts: [test log](b21-tests.txt), [stdio smoke](b21-b1-regression/b1-local-smoke.json), [public retrieval](b21-public-regression.json), [scoped cost/quality](b21-scoped.json), [live public source check](b21-product-evidence.json), [offline evidence readiness](b21-product-offline.json), [CLI preflight](b21-preflight.json). CI includes the tests plus explicit offline scoped quality/cost and product-readiness commands for Python 3.12/3.13. No real model logs are committed.

## Official source and accuracy boundaries

`product-cases.json` adds manually inspected ABAP 7.54 System Fields oracles for CALL FUNCTION and SELECT: original public URL, exact section, brief original supporting quotations, conditions and extracted-body SHA. Live GETs revalidated both. A changed hash/title/body/section blocks eligibility pending re-review. Source validation does not judge model prose or certify backend applicability. A separate human review gate binds evidence to the exact case/hash/section/conditions and requires supported claims, scope, original-source completeness, fact/inference separation, no fabrication and no security violation. No model judge is used.

The four existing no-error-code module questions remain uncertainty-handling tests. Four **separate concrete S/4HANA 2022 on-premise tasks** cover FI reconciliation accounts, CO order settlement rules, MM valuated/non-valuated goods receipt and SD billing versus accounting. Applicable public product passages/URLs/sections/answer keys were **not acquired**; all four are `evidence_not_acquired` with empty support and excluded from positive accuracy scoring. The public S/4 landing page returned a 1,160-byte shell, not a product passage. No SAP Note/KBA authentication restriction is bypassed. No general FI/CO/MM/SD accuracy improvement is claimed.

## CLI compatibility and fair comparison

Auth preflight now uses documented-default JSON `claude auth status`, without `--json`. Exact-token help detection is labeled flag availability only; `flag_semantics_verified=false`. The direct official CLI reference returned HTTP 403 and no CLI is installed, so actual option semantics remain unverified. [CLI contract](../experiments/b2/CLI-CONTRACT.md) distinguishes built-in `--tools` restriction from MCP restrictions, allow/deny permission rules, settings-source selection, strict MCP configuration, print events, client budget and invoice limits.

Version-2 approval enables exactly one selected public task/arm smoke (one print invocation after preflight), or 6/12 counterbalanced repetitions covering all six A/B0/B1 orders. Version-1 fixed order remains explicit legacy compatibility, not fair cost evidence. Same task/model/scope/prompt hash and source oracle are retained. Observed model identities are recorded; known mismatch stops. Default templates remain unapproved. No paid execution has happened here.

Native Read and MCP now share a required-original-line coverage gate. Native lines are accepted only for matched Read call IDs/approved staged paths, unchanged staged bytes and recognized number-arrow/tab formatting with exact original line contents. Its SHA is labeled a fixture hash, not a Read-returned hash; byte/newline delivery remains unverified. MCP retains exact source/range/returned-SHA validation. Adjacent segments can jointly cover requirements. Unsupported native formats require human review; unobserved evidence is not automatically an incorrect answer.

Reports separate terminal input/output/cache/cost, observed model IDs, call/error counts, identical-input repeats (not semantic retries), native/MCP text bytes, required ranges and manual answer status. Termination causes distinguish timeout, budget/turn limit, model mismatch, malformed/missing terminal contract, process exit and terminal failure. CLI-reported budget overrun stops further calls. Client controls **cannot guarantee final invoice limits**; actual invoice attribution, retries and final-model-input data remain null when unobservable. Runbook specifies human review before cost comparison, counterbalanced cache analysis and invoice reconciliation including failed/in-flight requests. OS/provider/network isolation remains the operator's responsibility.

## Unnecessary context and total-cost boundary

New read-only `sap_repo_search_scoped` preserves selected original snippets, direct relations, path/line/SHA/snapshot, required-object range gates and omissions. Only the top-level unresolved list is restricted to returned original ranges. Explicit scope/counts disclose deferred object-wide references; diagnostic status totals disclose failures. Original reference and diagnostic records remain available through bounded, snapshot-bound `sap_repo_references_page` / `sap_repo_diagnostics_page`. Source changes invalidate pages. Skill/Hook instructions require inspecting relevant deferred records before asserting causes/coverage or edits. Legacy full search/read and default wire contract remain intact; lossless compact remains opt-in.

For pinned RAP100 `acceptTravel`:

| Retrieval | Calls | Serialized MCP wire bytes |
|---|---:|---:|
| Existing full search | 1 | 86,601 |
| Scoped initial search | 1 | 32,619 |
| Scoped + all deferred detail pages | 8 total | 99,337 |

All 46 object-wide unresolved records and 33 diagnostics remain recoverable; 5 unresolved references are in the returned original ranges. Required code is unchanged, and all 15 selected public retrieval cases pass. The larger all-detail total explicitly shows the re-query boundary. These are server wire measurements, **not model tokens, total cost savings or SAP answer-accuracy measurements**. Quality impact and which deferred pages a real model needs remain unverified.

## Remaining work

Use the [approved-runtime one-command smoke procedure](../experiments/b2/B21-RUNBOOK.md) before a separately approved counterbalanced experiment. Real CLI/Skill/MCP/Hook behavior, exact model delivery, paid usage, invoices and SAP answers remain unverified. Acquire reviewed release/deployment-specific FI/CO/MM/SD passages before scoring that group; preserve the four-case gap count. Then evaluate quality/security gates and total calls/cache/retrieval costs before selecting an optimized default. No routing or deployment is part of B2.1.
