# B2.1 Claude Code CLI contract boundaries

Reference: https://code.claude.com/docs/en/cli-reference ; owner review https://github.com/leeyourimm/sap-context-optimizer/pull/4#pullrequestreview-5712215986 . Direct retrieval returned **HTTP 403 on 2026-10-30** in this environment; no installed `claude` is available. The distinctions below implement the documented contract identified by review, not an independently successful installed-version test. No flag semantics are certified by mock CLI tests.

| Interface | Expected contract and runner treatment | Still requires actual installed-version smoke |
|---|---|---|
| `claude auth status` | Read-only, default JSON; `--text` is the alternate human format. Removed unsupported `--json`. Parse `loggedIn: true` only, print no raw account output. | Real provider/version/auth-status JSON shape; unrecognized output refuses execution |
| `--print` / `--output-format stream-json` / `--verbose` | Noninteractive print experiment and local event stream, not interactive session automation | Terminal events, tool events, hook/Skill behavior and usage field meanings |
| `--tools Read,Skill` (A: Read) | Limits built-in tools only; **does not restrict MCP tools** | Availability of Skill and Read; actual built-in restriction |
| `--allowedTools` | Permission allow rules for named built-ins and gateway MCP; not proof the model selects them | Wildcard matching, permission behavior and route |
| `--disallowedTools` | Denies write/command/web/delegation tools; B0 explicitly denies repository MCP, which is independently denied by policy | Denial precedence and actual attempts |
| `--setting-sources project` + `--settings` | Project source selection plus explicit permission settings in a new staged cwd; not an OS isolation mechanism | Ambient configuration/memory/plugin exclusion on installed version; operator must use clean approved runtime |
| `--strict-mcp-config` + `--mcp-config` | Only staged MCP servers; A uses an empty server map, B0/B1 use policy gateway | Real MCP discovery, protocol negotiation and tool return delivery |
| `--max-budget-usd` | Print-mode **client-side control**, not an absolute invoice cap | CLI-reported stop subtype, overshoot, already accepted/in-flight charges and invoice reconciliation |
| `--max-turns` / external timeout | Independent turn and POSIX process-group limits; no automatic retry | Turn accounting and accepted provider requests after termination |
| `--model` | Approved exact model ID supplied identically across arms; observed model IDs recorded | Alias/provider substitution: known mismatch stops the suite; missing model observations stay null |

`preflight()` checks read-only version/help/auth, cwd permissions and POSIX process-group support. Exact help-token detection avoids substring false positives but remains **availability detection only**. `flag_semantics_verified=false` remains in its report. `ready=true` means prerequisites were observed and execution can be attempted under the explicit approval manifest, not that a live experiment succeeded.

Offline tests exercise CLI argument construction/default-JSON auth, unsupported auth/schema refusal, strict config/permission files, mocks, termination and report semantics. They do not install/log in/call a paid model. Smoke completion still requires manual inspection of actual tool choice, returned source, scope and answer; unknown observations cannot count as a pass.
