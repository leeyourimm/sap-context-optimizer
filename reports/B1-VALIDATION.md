# B1 validation — 2026-10-30

## Preservation and regression

- Read GitHub [Issue #1](https://github.com/leeyourimm/sap-context-optimizer/issues/1). Its earlier B1 prohibition is superseded by the user's explicit B1 instruction in this task; preserve M0/B0 first, then work separately. No issue closure or merge is implied.
- Re-ran all original **39 M0/B0 tests: passed**. [Before-B1 output](b0-before-b1-tests.txt).
- Published the existing, inspected M0/B0 implementation as initial main commit `782abba9b21980b9114586c64115c77d4deca18b`, excluding gitignored local policy/cache. Added a pinned offline CI workflow. [Baseline GitHub Actions success](https://github.com/leeyourimm/sap-context-optimizer/actions/runs/41045046827).
- B1 developed on `feature/b1-local-abap`; M0/B0 official tools, closed public topic vocabulary, HTTP deny policy and previous wire-format handling retained. Same .mcp.json server, additive local tools; no second server/config collision.
- No new live SAP call during B1. Existing SAP Search/Graph contracts are covered by original regression tests, mock HTTP/SSE and recorded public responses; previous M0 live reports remain historical evidence. No claim that local tests establish current remote availability.

## Executed checks

```sh
python3 -m unittest discover -s tests -v
python3 scripts/verify_b1.py
git diff --check
```

**84 tests executed, 84 passed, 0 skipped:** 39 M0/B0 + 45 B1. [Runner output](b1-tests.txt). The final suite was run after parser, scope, read-only gateway and model-context permission changes. No packages were installed.

B1 cases include exact class, scoped/qualified method, declaration/implementation separation, interface, FUGR function/module membership, PROG/include, CDS/projection, BDEF Action and explicit alias-to-pool join, service definition/binding, static reference target implementation, missing object/member, Korean+English lexical query, repeated search, same-size/same-mtime source edit, stale hash/snapshot refusal, large-file snippets, full/range/empty original reads, unsupported/bad XML/raw fallback, partial parsing, unresolved dynamic/instance calls, configurable budget and omission, namespace encoding, synthetic context quality gates and actual JSON/UTF-8 measurements.

Security cases: no HTTP path used for B1; no source, cache, state or log writes by local MCP operations; project-relative allowed roots only; traversal/absolute path/backslash denial; symlink file/directory/root and post-index replacement denial; hardlink denial; XML entity/DTD rejection; project identity isolation; warm-root revocation; arbitrary local queries never forwarded to official SAP; default model-context permission denies MCP source sharing before indexing. CLI-only local investigation remains available without that permission. Hook state distinguishes local code from official document body so an unrelated tutorial is not required to certify a customer method.

The actual local MCP subprocess search/read/reference/status run is recorded in [b1-local-smoke.json](b1-local-smoke.json). Full-original reread and a ZCL_B1_HELPER direct syntax reference succeeded. Its actual serialized C response size exactly matched the comparison measurement. This is a real executable stdio run, **not a Claude Code model run**.

## Context size and explicit fixture accuracy

Fixture: publicly committed, project-authored synthetic ABAP export. Task `find_receipt`; required objects: CLAS:ZCL_B1_LARGE + CLAS:ZCL_B1_HELPER; required complete ranges: FIND_RECEIPT declaration/implementation + CHECK declaration/implementation. A covers whole relevant source files, not the entire repository.

| Mode | Source characters / UTF-8 bytes | Actual serialized MCP response bytes | Required evidence |
|---|---:|---:|---|
| A full relevant source files | 24,441 / 24,441 | 52,304 | pass |
| B selected code | 118 / 118 | 6,954 | **fail: Helper object + CHECK declaration/implementation missing** |
| C code + explicit references | 279 / 279 | 11,118 | pass for these declared requirements |

Both source sizes and full MCP text+structuredContent serialization are measured. C's wire size is validated against the executable response; ID=1 and newline counted. [Full ranges, hashes and gates](b1-context-comparison.json). Tests reject a small output that omits mandatory evidence. No requirements means an unknown/null gate, not success.

This is not a general SAP correctness score or a claim of complete dependency discovery. Extra referenced objects, unsupported constructs, source truncation and snapshot gaps remain explicit. No token estimates, billing tokens, model cost or savings percentages are reported.

## Implemented relationship scope

Validated abapGit serializer/XML/name/member structures plus token evidence, not extension-based object guessing. Actual code text is returned verbatim with original locations and byte hashes. Local export state is not active SAP state.

- Class/interface definition, methods and qualified methods, declaration/implementation companions; literal function calls, named include, inheritance, interface implementation, type refs, named constructor and static class/interface member references.
- CDS view entity and projection/source/association/composition references in the supported subset.
- BDEF entity/implementation class, Action/Validation/Determination declaration, explicit Action alias/pool join, EML entity and behavior-pool source links.
- SRVD expose and SRVB XML service-definition references in confirmed serialization formats.
- Incoming/outgoing exact snapshot resolution, missing/external/ambiguous/metadata-only targets; bounded automatic expansion and explicit omitted context.

## Remaining limits and next priorities

- `claude` is unavailable: actual automatic tool choice, Hook delivery, final model payload, usage and billing **unverified**. No claim of token savings or improved SAP answer accuracy.
- Native Windows not supported; security implementation uses Linux/POSIX dir-fd and O_NOFOLLOW.
- No full ABAP compiler/type checker, full RAP lifecycle graph, instance dispatch, dynamic calls, macro/template expansion, AFF structural parsing, implicit framework wiring or full standard SAP object corpus. Validation/Determination dispatch is not semantically resolved.
- Every operation re-reads/hashes the allowed tree; this is intentionally correct for same-mtime edits but can cost I/O on large exports. The index is memory-only with file/byte/unit/output caps. Scope errors/limits are not object absence.
- Model-context permission is distinct from local processing and from B0 external HTTP. Private code must not be exposed through MCP before the Claude/model route is approved. Hook/gateway alone cannot police Bash, other plugins or the whole network.
- No SAP server, object change, Transport, external model, Jev, pxpipe, embedding or npm deployment.

Next: approved Claude end-to-end evaluation; real/public export contract corpus for parser gaps and function/service naming variants; explicit validation/determination/projection handler relations; incremental index performance with freshness guarantees; review omitted mandatory ranges before any model-based optimization.
