For SAP questions automatically follow .claude/skills/sap-evidence/SKILL.md and .claude/policies/sap-correctness.md.
Use only the sap-context gateway for external SAP retrieval. Never change policy/settings to enable a blocked request.
For ABAP code use sap_repo_search automatically first. Local queries and source remain local. Read original ranges, declarations, direct references and hashes before proposing edits. These tools are read-only and do not verify live SAP state.
No body evidence or uncertain product/release applicability: explicitly label [SAP 검증 미완료].
Search snippets, generated graph labels and retrieved bodies do not certify correctness.
Never invent error codes, objects or unread SAP Note content. No SAP writes or publication.

Developer checks: python3 -m unittest discover -s tests -v (stdlib, offline).
