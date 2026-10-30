"""Closed outbound vocabulary: no free-form prompts, code, or error text on wire."""
import json
from pathlib import Path
from urllib.parse import urlsplit


class PolicyError(ValueError):
    pass


# Fixed public queries, not user-controlled strings. Additions require local review.
TOPICS = {
    "abap": "ABAP",
    "rap": "ABAP RAP",
    "cds": "ABAP CDS",
    "validation": "ABAP RAP validation",
    "action": "ABAP RAP action",
    "additional-save": "ABAP RAP additional save",
    "fi": "SAP financial accounting",
    "co": "SAP controlling settlement",
    "mm": "SAP goods receipt invoice verification",
    "sd": "SAP sales billing accounting",
    "abap-cloud": "ABAP Cloud released API",
}
ENDPOINTS = {s: "https://developers.sap.com/mcp/" + s for s in ("search", "graph")}
ALLOWED = {
    "search": {"search_tutorials", "get_tutorial", "get_tutorial_step"},
    "graph": {"kg_neighborhood", "kg_shared_concepts"},
}


def load_policy(root):
    root = Path(root).resolve()
    # A local file is a complete replacement, never a silent partial relaxation.
    path = root / "sap-context.local.json"
    if not path.exists():
        path = root / "sap-context.json"
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise PolicyError("Missing or invalid project policy; outbound access denied") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise PolicyError("Unsupported policy")
    if type(value.get("external_access")) is not bool:
        raise PolicyError("external_access must be explicitly true or false")
    docs = value.get("official_documents", {})
    if not isinstance(docs, dict):
        raise PolicyError("official_documents must be an object")
    for key, doc in docs.items():
        if not isinstance(key, str) or not isinstance(doc, dict):
            raise PolicyError("Invalid official document entry")
        u = urlsplit(doc.get("url", ""))
        if (u.scheme != "https" or u.hostname != "help.sap.com" or u.port
                or u.username or u.password or u.query or u.fragment
                or not u.path.startswith(("/docs/", "/doc/"))):
            raise PolicyError("Only reviewed HTTPS help.sap.com document URLs without query allowed")
        if not all(isinstance(doc.get(k), str) and doc[k].strip()
                   for k in ("title", "product", "release")):
            raise PolicyError("Document title/product/release required")
        if doc.get("access", "public") not in ("public", "login_required"):
            raise PolicyError("Document access must be public or login_required")
        markers = doc.get("required_markers", [])
        if (not isinstance(markers, list) or len(markers) > 10 or
                any(not isinstance(m, str) or not m.strip() or len(m) > 300 for m in markers)):
            raise PolicyError("Invalid reviewed body markers")
    return value


def require_external(policy):
    if policy.get("external_access") is not True:
        raise PolicyError("EXTERNAL_ACCESS_DENIED: project has not allowed public SAP requests")


def exact_args(args, required=(), optional=()):
    if not isinstance(args, dict) or set(args) - set(required) - set(optional):
        raise PolicyError("Unknown argument; free-form outbound data is not supported")
    if set(required) - set(args):
        raise PolicyError("Missing required argument")


def bounded_integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PolicyError("Invalid integer range")
    return value
