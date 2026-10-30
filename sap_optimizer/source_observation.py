"""Conservative common original-line oracle for MCP and native Read streams."""
import hashlib
from pathlib import Path
import re

from .local_fs import LocalFS, relative_parts
from .policy import PolicyError


LINE = re.compile(r'^\s*([0-9]+)(?:→|\t)(.*)$')


def native_read(args, blocks, workspace, corpus):
    if workspace is None or not isinstance(args, dict) or not isinstance(args.get('file_path'), str):
        return None
    try:
        requested = Path(args['file_path'])
        if not requested.is_absolute():
            requested = workspace / requested
        path = requested.resolve().relative_to((workspace / 'public_exports').resolve()).as_posix()
        relative_parts(path)
        raw = LocalFS(corpus).read(path, 2_000_000)
        if LocalFS(workspace).read('public_exports/' + path, 2_000_000) != raw:
            return None  # Read was not of the staged pinned source snapshot.
    except (ValueError, OSError, PolicyError):
        return None
    original = raw.decode('utf-8-sig').splitlines()
    verified, ambiguous = set(), set()
    for block in blocks:
        text = block.get('text') if isinstance(block, dict) else None
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            m = LINE.fullmatch(line)
            if not m:
                continue
            n, value = int(m[1]), m[2]
            if 1 <= n <= len(original) and original[n - 1] == value:
                verified.add(n)
            else:
                ambiguous.add(n)
    return {'path': 'public_exports/' + path, 'verified_lines': sorted(verified - ambiguous),
            'sha256': hashlib.sha256(raw).hexdigest(), 'hash_origin': 'approved_fixture_not_native_Read',
            'format_status': 'number_arrow_or_tab_exact_lines' if verified else 'unrecognized_or_mismatched',
            'original_byte_delivery_verified': False}


def ranges(task, observed, native, corpus):
    coverage = []
    for r in task.get('required_ranges', []):
        relative_parts(r['path'])
        raw = LocalFS(corpus).read(r['path'], 2_000_000)
        sha = hashlib.sha256(raw).hexdigest()
        lines = raw.decode('utf-8-sig').splitlines(keepends=True)
        mcp_lines, native_lines = set(), set()
        for d in observed:
            start, end = d.get('start_line'), d.get('end_line')
            if (d.get('path') == 'public_exports/' + r['path'] and d.get('sha256') == sha and
                    type(start) is int and type(end) is int and 1 <= start <= end <= len(lines) and
                    d.get('source') == ''.join(lines[start - 1:end])):
                mcp_lines.update(range(start, end + 1))
        for d in native:
            if d['path'] == 'public_exports/' + r['path'] and d['sha256'] == sha:
                native_lines.update(d['verified_lines'])
        needed = set(range(r['start'], r['end'] + 1))
        coverage.append({**r, 'observed_exact_source_in_tool_result': needed <= (mcp_lines | native_lines),
                         'mcp_original_range_complete': needed <= mcp_lines,
                         'native_Read_original_lines_complete': needed <= native_lines,
                         'missing_observed_lines': sorted(needed - mcp_lines - native_lines),
                         'gate_basis': 'same_pinned_original_lines; native newline/byte delivery unverified'})
    return coverage
