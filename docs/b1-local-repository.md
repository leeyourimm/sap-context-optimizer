# B1 local repository implementation

## Runtime and boundaries

Python 3.12 stdlib only: `os` dir-fd/no-follow reads for path safety, `ElementTree` with DTD/entity rejection for metadata, a character/token reader for a deliberately limited structural grammar, `math`/`collections` for BM25, `hashlib` for exact byte hashes. No package installation, vectors, Jev, pxpipe, external reranker or SAP connection. This avoids a runtime parser dependency while explicitly sacrificing complete ABAP grammar/type resolution; it is not an abaplint/SAP compiler replacement.

An in-memory index belongs to one resolved project and its configured roots. No persistent source/cache/log is written by local search/read/status/reference tools, including their MCP entry point. CLI demo generation is a separate explicit writer; Hook observational state still uses B0's protected local SQLite. Sources are never modified. Every operation scans/hashes eligible files again; unchanged content reuses the structural index. Even same-size/same-mtime edits change the hash. This costs local I/O and is not optimized for entire SAP systems.

Two separate permissions:

- `external_access`: existing B0 fixed public SAP HTTP requests. Not required for B1.
- `local_repository.allow_model_context`: allow source/metadata to leave the local MCP process for a potentially remote Claude model. Default false. CLI remains local and does not imply model approval. Enable only for public/synthetic sources or an approved model route. The included B1 example opts in for synthetic data only.

The gateway never routes a B1 query/snippet to official SAP, Jev or another provider. Closed B0 topic IDs remain separate. Managed code/policy permissions, Claude provider approval and OS/network egress controls are still required to police other processes, Bash, plugin edits and the model itself.

## abapGit validation and supported formats

Format review used official abapGit commit `1132cd91768a84ee32d2e9400e9ac86859bbecb0`:

- [Filename and namespace logic](https://github.com/abapGit/abapGit/blob/1132cd91768a84ee32d2e9400e9ac86859bbecb0/src/objects/core/zcl_abapgit_filename_logic.clas.abap)
- [FUGR serializer](https://github.com/abapGit/abapGit/blob/1132cd91768a84ee32d2e9400e9ac86859bbecb0/src/objects/zcl_abapgit_object_fugr.clas.abap)
- [DDLS](https://github.com/abapGit/abapGit/blob/1132cd91768a84ee32d2e9400e9ac86859bbecb0/src/objects/zcl_abapgit_object_ddls.clas.abap), [BDEF](https://github.com/abapGit/abapGit/blob/1132cd91768a84ee32d2e9400e9ac86859bbecb0/src/objects/zcl_abapgit_object_bdef.clas.abap), [SRVD](https://github.com/abapGit/abapGit/blob/1132cd91768a84ee32d2e9400e9ac86859bbecb0/src/objects/zcl_abapgit_object_srvd.clas.abap), [SRVB](https://github.com/abapGit/abapGit/blob/1132cd91768a84ee32d2e9400e9ac86859bbecb0/src/objects/zcl_abapgit_object_srvb.clas.abap)
- Actual metadata examples: [SAP RAP100](https://github.com/SAP-samples/abap-platform-rap100/tree/main/src), [SAP cheat sheets](https://github.com/SAP-samples/abap-cheat-sheets/tree/main/src), [FUGR fixture](https://github.com/abapGit-tests/FUGR/blob/main/src/zabapgit_unit_test.fugr.xml), [PROG fixture](https://github.com/abapGit-tests/PROG/blob/main/src/zag_unit_test.prog.xml).

Each typed object requires matching `<abapGit serializer>`, namespaced ABAP XML values, expected metadata node and object identity. Filename/type suffix alone is not proof. Lowercase filenames and basic `#namespace#`/percent filename decoding are supported; unfamiliar/AFF JSON serialization remains unvalidated raw fallback.

| Type | Metadata check | Source files |
|---|---|---|
| CLAS | VSEOCLASS/CLSNAME | name.clas.abap, locals_def/locals_imp/testclasses/macros.abap |
| INTF | VSEOINTERF/CLSNAME | name.intf.abap |
| FUGR / FUNC | FUGR serializer + FUNCTIONS/FUNCNAME and INCLUDES/SOBJ_NAME | group.fugr.function.abap, listed includes; function identity must appear in metadata |
| PROG / Include | PROGDIR/NAME, SUBC=I marks include | name.prog.abap |
| DDLS | DDLS/DDLNAME | name.ddls.asddls; entity name separately extracted |
| BDEF | BDEF/NAME | name.bdef.asbdef |
| SRVD | SRVD/NAME | name.srvd.srvdsrv; legacy assrvd recognized |
| SRVB | SRVB/METADATA/NAME | name.srvb.xml only; SRVD_REF/NAME relations parsed as XML |

FUGR has no universal group-name field in the observed XML; group identity uses the verified serializer/container structure plus abapGit filename convention, and functions/includes are checked against the member lists. No fabricated group metadata field is required. Includes serialized separately as PROG are also supported.

Missing source, listed member absent, conflicting identity, duplicate identity, unsupported object, partial parse, inaccessible root/file, file/byte/unit limits and unvalidated raw sources are distinguished in diagnostics. Only eligible UTF-8 text is indexed; unsupported extensions, hidden directories and .git/build/dependency directories are outside coverage. Local exports never prove live active/inactive SAP state. Hash is over original file bytes; UTF-8 BOM is removed for text parsing, CRLF/source line endings are preserved.

## Structural evidence, not inferred runtime calls

The token reader separates comments, quoted literals and opaque templates before recognizing statements. It keeps declaration and implementation ranges and their owners. Regex is used for lexical query tokens/filenames, not as proof of a call graph.

Supported explicit productions: CLASS/INTERFACE definitions, METHOD(S)/CLASS-METHODS (including simple chains), METHOD/ENDMETHOD, FUNCTION/ENDFUNCTION; INTERFACES, INHERITING FROM, TYPE REF TO, named NEW, static `class_or_interface=>member`, literal CALL FUNCTION, INCLUDE, FOR BEHAVIOR OF and READ/MODIFY ENTITIES OF. Direct references include file/line/column and a target name, plus resolution in the validated local snapshot. Instance `->` dispatch and dynamic calls remain unresolved. Class local declarations resolve only in their own parent object.

CDS `define [root] view entity`, legacy `define view`, select FROM/JOIN, AS PROJECTION ON, simple association/composition targets; BDEF behavior entity, implementation class, Action/Validation/Determination declarations; SRVD EXPOSE and SRVB metadata links are supported. Dynamic SQL, macros/templates, unsupported DDL forms and incomplete statements are not compiler-validated.

RAP Action-to-handler declaration uses three explicit facts: pool `FOR BEHAVIOR OF entity`, BDEF `define behavior for entity alias X`, method `FOR ACTION X~Action`. If that join is absent/ambiguous it stays unresolved. This is not proof of Action runtime dispatch. Validation/Determination declarations, local handler/saver class source, EML and behavior-class references are discoverable; a complete lifecycle graph, inherited/projection behavior semantics, validation/determination handler dispatch, implicit calls, full types and Customizing are NOT implemented.

## Search and context

`sap_repo_search(query)` automatically performs:

1. Exact case-insensitive object/symbol lookup. A single explicitly named validated object scopes primary method hits; multiple objects do not force a scope.
2. BM25 if primary candidates are below `min_candidates`. Keyword mode is also available. Composite `/NS/CLASS=>METHOD` and `IFACE~METHOD` terms are preserved alongside components. Hangul tokens remain original; there is no machine translation, Korean morphology or semantic matching.
3. Bounded outgoing and incoming explicit-reference expansion. A referenced static member prioritizes that target's matching declarations/implementations. No full dependency closure is promised.
4. Deduplicated original ranges within result/line/character budgets. Matching raw code that lacks trusted metadata remains clearly untyped fallback. Query hits already covered by structural snippets need not bring entire lexical windows along.

Returned data includes source kind, object ID/type, owner/symbol kind, exact original path/lines/source, source byte SHA-256, project-specific content snapshot, declaration/implementation companion locations, direct edges and unresolved targets. Omitted ranges/truncated snippets and parsing/scope warnings remain visible. Full original `sap_repo_read` is always available within the configured per-file byte limit; supply the previous hash AND snapshot to refuse stale reads before edits. A large single line or a budget may prevent a snippet; it is an omission, never proof of no source.

Local MCP tools: search, keyword, read, references, status. The same `sap-context` server exposes them, so .mcp.json needs no second server or new process. Hooks accept these local tools and distinguish local source evidence from official document evidence; they do not force unrelated tutorial retrieval just to discuss a customer method. Actual Claude model selection/payload remains unverified because the executable is unavailable here.

## Configuration

`local_repository.roots` must be non-overlapping project-relative directories. The example uses `examples/abapgit`. For company exports use gitignored `local-abap/` and retain `allow_model_context:false` until the model route is approved. Search tools have no root/policy mutation operations.

Settings (all configurable and validated): max_files 2000, max_file_bytes 2,000,000, max_total_bytes 20,000,000, max_units 20000, window_lines 35, max_results 8, max_lines 80, max_context_chars 18000, min_candidates 3, reference_depth 1, max_expanded_objects 12, bm25_k1 1.2, bm25_b 0.75. These are bounded initial defaults, not measured optima. Index and output limits can omit required evidence; inspect diagnostics and explicit omitted ranges. Config edits rebuild the in-memory index next call; external/model permissions are checked each call.

Security tests cover traversal, symlink root/directory/file including a post-index replacement, hard links, XML entities, project cache isolation, root revocation, no source/log writes and no HTTP use. Linux dir_fd/O_NOFOLLOW is required; native Windows support is not claimed. Source comments/strings are never executed. There is no persistent source index to mix between projects.

## Reproduce context comparison

```sh
python3 scripts/sap_context.py repo-compare find_receipt \
  --required-object CLAS:ZCL_B1_LARGE --required-object CLAS:ZCL_B1_HELPER \
  --required-symbol '{"object_id":"CLAS:ZCL_B1_LARGE","symbol":"FIND_RECEIPT","kind":"method_declaration"}' \
  --required-symbol '{"object_id":"CLAS:ZCL_B1_LARGE","symbol":"FIND_RECEIPT","kind":"method_implementation"}' \
  --required-symbol '{"object_id":"CLAS:ZCL_B1_HELPER","symbol":"CHECK","kind":"method_declaration"}' \
  --required-symbol '{"object_id":"CLAS:ZCL_B1_HELPER","symbol":"CHECK","kind":"method_implementation"}'
```

A reads whole relevant source files (union of selected paths and explicitly required objects' source paths), B returns selected code, C adds direct dependencies. A is not the entire repository baseline. Measure both source text and real MCP serialization including text+structuredContent wrappers, newline and a fixed one-digit response ID. The stdio smoke checks measured C response bytes against the actual executable output. Required object AND complete symbol-range coverage are separate; absent requirements produce a null quality gate, not a vacuous pass. Partial method truncation fails symbol coverage. No token estimates or model billing numbers are emitted.

This synthetic result only establishes those declared source requirements, not SAP answer correctness. B misses Helper and fails despite being smallest; C passes the fixture requirements. Inspect reports/b1-context-comparison.json and reports/B1-VALIDATION.md.
