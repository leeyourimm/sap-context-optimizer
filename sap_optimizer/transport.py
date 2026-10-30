"""Bounded JSON/SSE Streamable HTTP client. Preserves inherited proxy/TLS trust."""
import json
import urllib.error
import urllib.request

MAX_BYTES = 2_000_000


class ProtocolError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProtocolError("Redirect refused")


def decode_rpc(raw, content_type, request_id):
    try:
        if "text/event-stream" in content_type:
            candidates = []
            # SSE records may contain multiple data lines and CRLF separators.
            for event in raw.decode().replace("\r\n", "\n").split("\n\n"):
                data = "\n".join(line[5:].lstrip(" ") for line in event.splitlines()
                                 if line.startswith("data:"))
                if data:
                    candidates.append(json.loads(data))
        else:
            candidates = [json.loads(raw)]
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("Malformed JSON/SSE response") from exc
    for item in candidates:
        if isinstance(item, dict) and item.get("id") == request_id:
            if item.get("jsonrpc") != "2.0":
                raise ProtocolError("Invalid JSON-RPC version")
            if "error" in item:
                code = item["error"].get("code", "unknown")
                raise ProtocolError(f"Remote JSON-RPC error {code}")
            if not isinstance(item.get("result"), dict):
                raise ProtocolError("Missing JSON-RPC result")
            return item["result"]
    raise ProtocolError("Response ID missing or mismatched")


def unpack(result, expected_action=None):
    if result.get("isError"):
        raise ProtocolError("Remote tool returned isError")
    if "structuredContent" in result:
        data = result["structuredContent"]
        # Observed CAP live contract: text is TOON, structuredContent wraps
        # the actual function result. Do not attempt to parse TOON as JSON.
        if isinstance(data, dict) and "action" in data:
            if (data.get("action") != expected_action or data.get("kind") != "function"
                    or "result" not in data):
                raise ProtocolError("CAP action envelope mismatch")
            return data["result"]
        return data
    blocks = result.get("content", [])
    text = [b["text"] for b in blocks if b.get("type") == "text" and isinstance(b.get("text"), str)]
    if len(text) != 1:
        raise ProtocolError("Expected one JSON text block or structuredContent")
    try:
        return json.loads(text[0])
    except ValueError as exc:
        raise ProtocolError("Tool text is not JSON") from exc


class HTTP:
    def __init__(self, opener=None):
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def request(self, url, payload=None, headers=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers=headers or {})
        try:
            with self.opener.open(req, timeout=25) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ProtocolError("Response byte limit exceeded")
                return response.status, dict(response.headers.items()), raw
        except urllib.error.HTTPError as exc:
            raise ProtocolError(f"HTTP {exc.code}; access/throttle/upstream failure") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Do not include URLs, headers, or remote error bodies in logs.
            raise ProtocolError("Network unavailable or timed out") from exc


class Remote:
    def __init__(self, url, http=None):
        self.url = url
        self.http = http or HTTP()
        self.counter = 0
        self.session = None
        self.version = "2025-03-26"
        self.info = None

    def rpc(self, method, params=None, notification=False):
        self.counter += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            payload["id"] = self.counter
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": self.version}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        status, hs, raw = self.http.request(self.url, payload, headers)
        lower = {k.lower(): v for k, v in hs.items()}
        if "mcp-session-id" in lower:
            self.session = lower["mcp-session-id"]
        if notification:
            if status not in (200, 202, 204):
                raise ProtocolError("Notification rejected")
            return {}
        return decode_rpc(raw, lower.get("content-type", ""), self.counter)

    def initialize(self):
        self.info = self.rpc("initialize", {"protocolVersion": self.version, "capabilities": {},
                             "clientInfo": {"name": "sap-context-optimizer", "version": "0.1.0"}})
        version = self.info.get("protocolVersion")
        if version not in ("2024-11-05", "2025-03-26", "2025-06-18"):
            raise ProtocolError("Unsupported negotiated MCP version")
        self.version = version
        self.rpc("notifications/initialized", notification=True)
        return self.info

    def tools(self):
        tools, cursor, seen = [], None, set()
        for _ in range(20):
            result = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            page = result.get("tools")
            if not isinstance(page, list) or any(not isinstance(t, dict) or not isinstance(t.get("name"), str)
                                                or not isinstance(t.get("inputSchema"), dict) for t in page):
                raise ProtocolError("Invalid tools/list schema")
            tools.extend(page)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
            if not isinstance(cursor, str) or cursor in seen:
                raise ProtocolError("Invalid/repeated tools cursor")
            seen.add(cursor)
        raise ProtocolError("Tools pagination limit exceeded")

    def call(self, name, args):
        return self.rpc("tools/call", {"name": name, "arguments": args})
