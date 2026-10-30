# M0/B0 validation — 2026-10-30

Public SAP terms only. No Claude model calls, confidential source, credentials, SAP writes, transports, package installation or publication. Runtime: Python 3.12.14, stdlib only. The shipped project policy is default-deny; a gitignored local policy enables the user-authorized fixed public queries in this instance.

## Live M0 (Python HTTP MCP client)

Recorded at 2026-10-30 19:48 KST (10:48 UTC). This is a point-in-time observation, not an SLA or general availability claim.

| Check | Observed outcome |
|---|---|
| Search initialize | HTTP 200, SSE, SearchService 1.0.0, negotiated 2025-03-26 |
| Graph initialize | HTTP 200, SSE, KnowledgeGraphService 1.0.0 |
| Search tools/list | 12 tools; exact input schemas retained in JSON |
| Graph tools/list | 15 tools; exact input schemas retained in JSON |
| Output schemas | Neither service advertised outputSchema; runtime shapes recorded instead |
| search_tutorials ABAP RAP | Public tutorial hits received |
| get_tutorial | Metadata and step titles received |
| get_tutorial_step | isError: step not found, despite a listed step 1 |
| Additional diagnosis | Same step call failed on two more returned public tutorial slugs; no general outage inference |
| Canonical public Markdown | HTTP 200; recorded probe body 12,467 bytes, full page rather than selected step |
| kg_neighborhood | prerequisites / whatToLearnNext / sharedConcepts / teaches arrays received |
| Nonexistent public tutorial | get_tutorial result null; get_tutorial_step isError |

Live wire format differs from the simplified source examples: content text uses TOON, while structuredContent contains `{action, kind, result}`. The client now validates and unwraps that action envelope. The initial observation is preserved in `m0-public-probe-initial.json`; it is not the final pass report.

Raw live tool manifests, input schemas, responses, observed result shapes and fixed public test arguments: [m0-public-probe.json](m0-public-probe.json). `probe-public` requires project permission; exit 0 means both service connections succeeded, not that every function passed. Inspect per-call error fields. No throttle stress, unauthorized admin/write call, auth refresh, or SAP Note access test was performed.

## Live B0 (real stdio subprocess → official services)

[b0-live-gateway.json](b0-live-gateway.json) records initialize, tools/list and calls to the actual executable project entry point.

- sap_search: succeeded; five metadata hits in this run, not body evidence.
- sap_tutorial: succeeded; not body evidence.
- sap_read_step: failed; preserved as tool isError.
- sap_read_tutorial_page: succeeded; full original Markdown body, applicability still false.
- sap_graph: succeeded; learning relationships, not Repository references.
- sap_status: local environment unknown, no reviewed Help documents, aggregate counts only.
- stdio subprocess exited 0; no server left running.

Thus official search and original public tutorial retrieval work through this MCP implementation. This does NOT prove Claude Code integration or automatic model tool selection.

## Offline checks

Command: `python3 -m unittest discover -s tests -v`

Result: **39 executed, 39 passed, 0 skipped**. [Captured runner output](offline-tests.txt). Tests include an in-memory JSON-RPC/SSE/CAP server, actual stdio entry-point subprocess, replay of live SAP response envelopes, and pre-network policy checks.

Coverage includes default/missing/corrupt policy, explicit bool permission, private/free-text/extra-field rejection before any HTTP request, caller-selected slug rejection, warm-connection revocation, tool allowlist, malicious Help URLs/redirects, state symlinks, changed live tool/schema, errors versus empty body, separate Help/tutorial/graph provenance, unknown applicability, Stop no-body detection and one-pass feedback, failed-tool evidence rejection, per-turn reset, direct MCP/web Hook denial, policy-edit guard, no prompt text in SQLite and usage-event de-duplication/unknown cost.

No actual `updatedToolOutput` compatibility test: this version does not use it. Hook output is additionalContext only. Mock tests do not stand in for Claude runtime compatibility.

## Completion criteria

1. **Claude Code searches official SAP material:** project config + runnable stdio + live official retrieval verified; actual Claude execution **UNVERIFIED** (`claude` executable absent).
2. **Distinguish source/applicability:** executable envelopes distinguish metadata/body, learning graph vs Help product document, declared scope vs unverified applicability; tested. SAP semantic correctness and release applicability are **not automatically certified**.
3. **Block unauthorized transfer:** gateway default deny and closed outbound vocabulary are tested before network; Hook guards are tested. Whole-machine/Claude model network enforcement is **not provided**.

Remaining external requirements: approved Claude runtime/auth and model request/usage observability; real product/release profile and reviewed FI/CO/MM/SD Help documents; optional live ADT/VFS compatibility and license checks. No total cost, token savings or SAP accuracy improvement claim is made.

## B1 proposal (not implemented)

Add local read-only abapGit snapshot exact object/method/function search, source hashes and active/snapshot status, then supported CDS/BDEF/class direct-reference expansion. Measure required-object recall and missing dependencies. Keep public egress vocabulary unchanged; do not upload sources. Live ADT integration is a separate capability gate, not an assumption. No Jev, pxpipe, embedding or full-system indexing until basic retrieval evaluation passes.
