# B2.1 approved-runtime runbook

**Offline preparation only is complete here. Real Claude E2E is unexecuted.** Keep PR #2/#3/#4 unmerged, no JEV/model routing, private uploads, SAP writes, packages or deployment.

## One public task, one approved smoke invocation

First provision a clean POSIX runtime and Claude/provider/auth outside this tool. Read [CLI contract boundaries](CLI-CONTRACT.md) and the OS/provider requirements in [B2 instructions](README.md). No auto installation, login or key-file reading is supported. CLI flags/hooks do not replace filesystem/network isolation.

Copy `approval-smoke.example.json` to `.sap-context/b21.approval.local.json`; inspect task `keyword-document`, hashes, exact model/CLI version, budget and provider route. Change the two approval booleans only after authorization. Preflight-only command `python scripts/run_claude_e2e.py` has zero model calls; it can supply the observed numeric version. Defaults in the example refuse execution.

In the approved runtime, a **single command** then runs read-only preflight followed by exactly one B1 public-task CLI invocation:

```sh
python scripts/run_claude_e2e.py --execute --approval .sap-context/b21.approval.local.json --output .sap-context/b21-public-smoke
```

The output directory must be new, its parent must exist. It is mode 0700; raw stream/stderr are local and gitignored. Existing company policies/settings/sources are never staged. Inspect `summary.json`, raw answer/tool events and local stderr before sharing sanitized metrics. `execution_success` is CLI completion only; `answer_correctness` remains null until human review. Known model-ID mismatches abort. Unsupported flags, auth, changed approved hashes/version or malformed streams refuse/fail rather than falling back to interactive or broader permissions.

Client budget, turn and wall-time controls reduce exposure; **they cannot guarantee an invoice cap**. Accepted provider work may be charged after a stop/timeout. `requested_client_budget_total_usd` is a requested control sum only. `provider_cost_exceeds_client_budget` records a CLI-reported overrun if observed; actual invoice remains null until reconciled. No automatic retry or second model call occurs after failure. A successful print invocation may internally make multiple model calls; this count remains null if not observable.

## Counterbalanced comparison

Use a separately reviewed copy of `approval-counterbalanced.example.json`, not the smoke approval. It is false by default. `run_mode=counterbalanced` requires 6 or 12 repetitions per task; six repetitions cover every permutation:

```
A B0 B1 | A B1 B0 | B0 A B1 | B0 B1 A | B1 A B0 | B1 B0 A
```

Each arm occupies each position twice per six repeats. Each run has a fresh staged cwd and no persisted session; task/product/release/model/prompt hash and required evidence remain identical across arms. One task × six repetitions × three arms = 18 print invocations (at USD 0.50 client budget each, USD 9 requested controls, **not** a charge estimate/cap). Select tasks explicitly; all 14 tasks would be 252 invocations. No such experiment ran here. Legacy version-1 approval remains compatible with one fixed A→B0→B1 pass, explicitly `counterbalanced=false`; do not treat it as unbiased cost evidence.

This balances within-task arm position, not all provider state/time effects. Keep all terminal cache-create/cache-read counters, timestamps, per-model usage, repeated-identical tool-input counts, tool errors and payload bytes. Repeated input is not automatically a semantic retry; retry_count stays null unless manually observed. Add planned idle/warm/cold strata and task-order permutations on another approved schedule if necessary; never assume `--no-session-persistence` disables provider caches. Record failures as wall timeout, budget/turn limit, malformed/missing terminal stream, known model mismatch, generic process exit or terminal error. No error is silently scored as a successful answer.

Before seeing cost, SAP reviewers annotate source claims using `review-template.json`. Compare task success and mandatory-range gates; do not average away security failures, missing required code or the four missing FI/CO/MM/SD original-body oracles. Preserve the denominator and gap count separately.

## Same source standard for native Read and local MCP

Both arms use the same pinned original source line oracle from PR #3. Native `Read` results are associated with their tool-use ID and approved staged `public_exports` input path. Only observed numbered-arrow/tab lines matching the exact original line content count. Unrecognized, reformatted, unmatched, failed, truncated or outside-root results give no machine proof and require manual inspection; absence of proof is not proof of absence. MCP results require exact original text plus returned SHA and line range. Adjacent verified segments can jointly cover a required range in either arm.

The shared gate is **required original line coverage**, not equal transport format. Native Read's reported hash is explicitly a fixture hash, not a hash returned by Read; line-ending/byte preservation is unverified. Collect both native and MCP tool-result text characters/UTF-8 bytes under the same definition, plus call/error counts. Actual final-model input tokens are unobserved; terminal CLI usage is provider-reported, not attributable automatically to one tool. Unknown fields are null. Inspect actual model choices rather than forcing the same tool sequence.

Invoice reconciliation: after the approved run, manually obtain the account/provider's billing export through its authorized process (runner reads no billing credentials). Match time/account/model/run references, include failed/aborted calls, cache classes, retries, pricing/discounts, currency/tax and reporting delay. Record CLI USD sum, invoice attributed USD and unmatched difference; use null for unattributable cost. No savings claim until task quality/security gates and attribution pass.

## Official-product accuracy versus uncertainty handling

`tasks.json` now has 14 tasks. The original four module-error tasks remain an **uncertainty-handling** group. A separate **product accuracy** group asks concrete S/4HANA 2022 on-premise FI reconciliation-account, CO settlement-rule, MM valuated/non-valuated GR and SD billing-accounting questions. Their applicable original product passage, URL, section and answer key are **not acquired**; `product-cases.json` marks all four `evidence_not_acquired`, empty support, no fabricated answers. They are not eligible for a positive accuracy score. The S/4 product landing page returned a shell and is not an answer source. SAP Notes/KBA login is not bypassed.

Two ABAP 7.54 cases have manually inspected source URLs, System Fields sections, exact scope conditions, brief support quotations and pinned extracted-body hashes. Revalidation proves source support persists, not that a model answered correctly or that an SAP backend matches the declared scope. A changed body/title/section/hash or unavailable source blocks scoring pending review. Human answer review must match the exact citation and all applicable conditions and check required code, fact/inference separation, fabricated claims and security. No automatic model judge is used.

```sh
# Pure offline readiness inventory, no HTTP/models:
python scripts/verify_product_cases.py --output .sap-context/b21-oracle-offline.json
# Explicit public GETs only, no model calls; pending module cases are NOT fetched:
python scripts/verify_product_cases.py --execute --output .sap-context/b21-oracle-live.json
```

## Scoped context and cost boundary

`sap_repo_search_scoped` returns the same original snippets/direct relations/locations/SHA/snapshot/omissions as ordinary automatic search, but limits the top-level unresolved-reference list to those original returned ranges. The original object-wide totals, deferral count, object IDs and detail tools are explicit. Diagnostic status counts are supplied; all original diagnostic records and object-wide incoming/outgoing resolved/unresolved references remain available via snapshot-bound paginated tools. Pages require `expected_snapshot`, `offset` (default 0), `limit` (1–100, default 20), and next_offset; stale snapshots fail. Before asserting a cause/complete dependency coverage or editing, inspect deferred records relevant to the task. Parser/index gaps remain unknown, not nonexistence. Full-source and legacy full-search APIs remain unchanged. Lossless compact remains opt-in and is not the new default.

```sh
python scripts/verify_b21.py --output .sap-context/b21-scoped.json
```

All 15 existing public object/range oracle cases still pass. `acceptTravel`: legacy one-call wire 86,601 bytes; scoped initial one-call wire 32,619; fetching **all** deferred details adds 7 calls and totals 99,337 bytes. Original snippets and direct relations are identical, all 46 unresolved edges and 33 diagnostics recoverable. These are server serialization measurements, not real model context/token savings or answer-accuracy evidence. Evaluate whether selected detail pages reduce total paid cost while retaining required evidence in an actual approved run; fetching every detail can be more expensive.
