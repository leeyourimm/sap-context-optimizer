"""Explicit live probe using only fixed public terms; never reads project content."""
import datetime
import json

from .policy import ENDPOINTS
from .transport import HTTP, ProtocolError, Remote, unpack


def shape(value):
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return {"type": "array", "count": len(value), "first_item": shape(value[0]) if value else None}
    return type(value).__name__


def probe(http=None):
    report = {"observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "client": "Python MCP protocol client, NOT Claude Code",
              "claude_code_verified": False, "calls": [], "services": {}}
    remotes = {}
    for service, url in ENDPOINTS.items():
        remote = Remote(url, http)
        try:
            info = remote.initialize()
            tools = remote.tools()
            report["services"][service] = {"url": url, "initialize": info, "tools": tools,
                                           "output_schema_note": "Only schemas actually advertised are recorded"}
            remotes[service] = remote
        except ProtocolError as exc:
            report["services"][service] = {"url": url, "error": str(exc)}

    def call(service, name, arguments):
        entry = {"service": service, "tool": name, "public_arguments": arguments}
        report["calls"].append(entry)
        try:
            raw = remotes[service].call(name, arguments)
            entry["raw_response"] = raw
            value = unpack(raw, name)
            entry["observed_shape"] = shape(value)
            return value
        except (ProtocolError, KeyError) as exc:
            entry["error"] = str(exc)
            return None

    hits = call("search", "search_tutorials", {"query": "ABAP RAP", "limit": 3})
    if isinstance(hits, list) and hits and isinstance(hits[0].get("slug"), str):
        slug = hits[0]["slug"]
        call("search", "get_tutorial", {"slug": slug})
        step = call("search", "get_tutorial_step", {"slug": slug, "stepNumber": 1, "format": "markdown"})
        if step is None:
            entry = {"service": "canonical_tutorial", "url": "https://developers.sap.com/tutorials/" + slug + ".md",
                     "purpose": "Explicit full-page fallback; not step API success"}
            report["calls"].append(entry)
            try:
                status, _, raw = (http or HTTP()).request(entry["url"])
                entry.update(status=status, body_bytes=len(raw), public_body=raw.decode())
            except ProtocolError as exc:
                entry["error"] = str(exc)
        call("graph", "kg_neighborhood", {"slug": slug, "depth": 2})
    # Invalid but public identifiers: distinguish null/empty/isError/transport errors.
    call("search", "get_tutorial", {"slug": "sap-context-optimizer-nonexistent-public-probe"})
    call("search", "get_tutorial_step", {"slug": "sap-context-optimizer-nonexistent-public-probe", "stepNumber": 1, "format": "markdown"})
    report["limitations"] = ["No Claude execution or model payload capture", "No SAP system/Notes access",
                             "No rate-limit stress testing", "No semantic/embedding/administrative tools invoked"]
    return report
