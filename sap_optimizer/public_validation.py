"""Offline provenance and independent range oracle for bundled PUBLIC exports."""
import hashlib
import json
import os
from pathlib import Path
import re

from .local_fs import LocalFS, relative_parts
from .policy import PolicyError
from .repository import Repository

CORPUS = "tests/fixtures/public_exports"


def verify_corpus(project):
    project = Path(project).resolve()
    base = project / CORPUS
    fs = LocalFS(project)
    manifest = json.loads(fs.read(CORPUS + "/manifest.json", 1_000_000))
    expected = {"manifest.json", "cases.json", "NOTICE.md"}
    for repo in manifest["repositories"]:
        if not re.fullmatch(r"[a-z][a-z0-9]*", repo["id"]) or not re.fullmatch(r"[0-9a-f]{40}", repo["commit"]):
            raise PolicyError("Invalid public corpus identity/pin")
        if repo["source_root"] != CORPUS + "/" + repo["id"] + "/src":
            raise PolicyError("Public evaluation root differs from its pinned export")
        for item in repo["files"]:
            relative_parts(item["path"])
            relative_parts(item["upstream_path"])
            if item["path"] != repo["id"] + "/" + item["upstream_path"]:
                raise PolicyError("Corpus path/provenance mismatch")
            url = f"https://raw.githubusercontent.com/{repo['repository']}/{repo['commit']}/{item['upstream_path']}"
            if item["url"] != url:
                raise PolicyError("Corpus URL is not pinned to its declared source")
            raw = fs.read(CORPUS + "/" + item["path"], 2_000_000)
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"] or blob != item["git_blob_sha1"]:
                raise PolicyError("Public fixture integrity mismatch")
            expected.add(item["path"])
    actual = set()
    for directory, dirs, files in os.walk(base, followlinks=False):
        for name in dirs + files:
            if (Path(directory) / name).is_symlink():
                raise PolicyError("Public corpus may not contain symlinks")
        actual.update(str((Path(directory) / name).relative_to(base)) for name in files)
    if expected != actual:
        raise PolicyError("Unlisted or missing public fixture files")
    return manifest


def corpus_policy(manifest):
    return {"version": 1, "external_access": False,
            "local_repository": {"roots": [r["source_root"] for r in manifest["repositories"]],
                                 "allow_model_context": False}}


def evaluate_result(project, case, result):
    """Oracle is raw pinned paths/ranges, never the parser's own symbol ranges."""
    project = Path(project)
    fs = LocalFS(project)
    snippets = result["results"]
    for s in snippets:
        relative_parts(s["path"])
        if not s["path"].startswith(CORPUS + "/"):
            raise PolicyError("Oracle accepts only the pinned public corpus")
        raw = fs.read(s["path"], 2_000_000)
        lines = raw.decode("utf-8-sig").splitlines(keepends=True)
        if s["source"] != "".join(lines[s["start_line"] - 1:s["end_line"]]) or hashlib.sha256(raw).hexdigest() != s["sha256"]:
            raise AssertionError("Returned text/hash differs from original public fixture")
    objects = {(s.get("object") or {}).get("id") for s in snippets
               if (s.get("symbol") or {}).get("kind") != "object_metadata"}
    missing_objects = sorted(set(case["required_objects"]) - objects)
    missing_ranges = []
    for need in case["ranges"]:
        path = CORPUS + "/" + need["path"]
        cursor = need["start"]
        for s in sorted((s for s in snippets if s["path"] == path), key=lambda s: s["start_line"]):
            if s["start_line"] <= cursor <= s["end_line"]:
                cursor = s["end_line"] + 1
        if cursor <= need["end"]:
            missing_ranges.append(need)
    wire_data = json.dumps(result, ensure_ascii=False)
    return {"id": case["id"], "passed": not missing_objects and not missing_ranges,
            "required_objects": len(case["required_objects"]), "missing_objects": missing_objects,
            "required_ranges": len(case["ranges"]), "missing_ranges": missing_ranges,
            "source_chars": result["source_chars"], "source_bytes": result["source_bytes"],
            "data_bytes": len(wire_data.encode()), "context_budget_limited": result["context_budget_limited"],
            "stages": result["stages"], "returned_ranges": [
                {k: s[k] for k in ("path", "start_line", "end_line", "sha256")} for s in snippets]}


def evaluate_corpus(project):
    manifest = verify_corpus(project)
    cases = json.loads((Path(project) / CORPUS / "cases.json").read_text())["cases"]
    repo = Repository(project, corpus_policy(manifest))
    results = [evaluate_result(project, c, repo.search(c["query"], expand=c.get("include_references", True))) for c in cases]
    status = repo.status()
    return {"upstreams": [{k: r[k] for k in ("repository", "commit", "license")} for r in manifest["repositories"]],
            "verified_upstream_files": sum(len(r["files"]) for r in manifest["repositories"]),
            "objects": status["objects"], "indexed_files": status["files"], "units": status["units"],
            "diagnostics": status["diagnostics"], "cases": results,
            "passed": sum(r["passed"] for r in results), "total": len(results),
            "missing_required_objects": sum(len(r["missing_objects"]) for r in results),
            "missing_required_ranges": sum(len(r["missing_ranges"]) for r in results),
            "model_calls": 0, "billing_tokens": None, "sap_answer_accuracy": "unverified",
            "scope": "Known pinned public source retrieval regression; not a representative or held-out SAP correctness score"}
