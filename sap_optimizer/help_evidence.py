"""Small reviewed public Help catalog, not a general crawler or SAP Notes client."""
import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser

from .transport import ProtocolError


CATALOG = {
    "abap-754-call-function": {
        "url": "https://help.sap.com/doc/abapdocu_754_index_htm/7.54/en-US/abapcall_function.htm",
        "title": "CALL FUNCTION - ABAP Keyword Documentation", "product": "ABAP", "release": "7.54",
        "access": "public", "required_markers": ["Calls or registers a function module", "System Fields"],
        "reviewed": "2026-10-30", "coverage": "ABAP keyword; not S/4HANA module-error or ABAP Cloud release evidence"},
    "abap-754-select": {
        "url": "https://help.sap.com/doc/abapdocu_754_index_htm/7.54/en-US/abapselect.htm",
        "title": "SELECT - ABAP Keyword Documentation", "product": "ABAP", "release": "7.54",
        "access": "public", "required_markers": ["SELECT", "INTO", "FROM"],
        "reviewed": "2026-10-30", "coverage": "ABAP keyword; not S/4HANA module-error or ABAP Cloud release evidence"},
}


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.titles = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.in_title:
                self.titles.append(data)


def read_body(http, doc):
    """Never equate a successful HTTP status with applicable claim evidence."""
    status, headers, raw = http.request(doc["url"], headers={"Accept": "text/html, text/plain"})
    if status != 200:
        raise ProtocolError("Help response is not HTTP 200")
    text = raw.decode("utf-8", errors="strict")
    title = None
    if "html" in next((v for k, v in headers.items() if k.lower() == "content-type"), ""):
        parser = PageText()
        parser.feed(text)
        text = " ".join(" ".join(parser.parts).split())
        title = " ".join(" ".join(parser.titles).split())
    if len(text.strip()) < 300 or text.strip() in ("SAP Help Portal | SAP Online Help", "SAP Help Portal"):
        raise ProtocolError("Help Portal returned a shell/insufficient body; document unverified")
    markers = doc.get("required_markers", [])
    if markers and (title != doc["title"] or not all(m in text for m in markers)):
        raise ProtocolError("Help title/body markers changed or login shell returned; re-review required")
    return {"title": doc["title"], "observed_title": title, "content": text,
            "declared_product": doc["product"], "declared_release": doc["release"],
            "scope_origin": "reviewed_local_configuration_not_auto_verified",
            "access": "public_body_retrieved", "http_status": status,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "body_validation": "reviewed_title_and_markers" if markers else "legacy_length_check_only",
            "claim_support": "requires_reader_review", "applicability_verified": False}
