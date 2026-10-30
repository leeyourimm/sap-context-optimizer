"""Small token-based structural reader, NOT an ABAP compiler or complete parser.

Edges carry exact token positions and syntactic meaning, never a guessed runtime
dispatch. Unsupported/dynamic forms remain diagnostics and lexical-searchable.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    start: int
    end: int
    line: int


def lex(text, ddl=False):
    result, errors = [], []
    i, line, column = 0, 1, 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            if c == "\n":
                line, column = line + 1, 0
            else:
                column += 1
            i += 1
            continue
        if (not ddl and c == '"') or (c == "*" and column == 0) or (ddl and text.startswith("//", i)):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            column += end - i
            i = end
            continue
        if ddl and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                errors.append("unterminated_comment")
                break
            fragment = text[i:end + 2]
            line += fragment.count("\n")
            column = len(fragment.rsplit("\n", 1)[-1]) if "\n" in fragment else column + len(fragment)
            i = end + 2
            continue
        start, startline = i, line
        if c in ("'", "`", "|"):
            quote = c
            i += 1
            while i < len(text):
                if text[i] == "\n":
                    line += 1
                if text[i] == quote:
                    if quote != "|" and i + 1 < len(text) and text[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                if quote == "|" and text[i] == "\\":
                    i += 2
                else:
                    i += 1
            else:
                errors.append("unterminated_literal")
            result.append(Token(text[start:i], "string" if quote == "'" else "opaque", start, i, startline))
        elif c.isalpha() or c in ("_", "/") and (c != "/" or i + 1 < len(text) and text[i + 1].isalnum()):
            i += 1
            while i < len(text) and (text[i].isalnum() or text[i] in "_/-"):
                if text.startswith("->", i):
                    break
                i += 1
            result.append(Token(text[start:i].upper(), "id", start, i, startline))
        elif text[i:i + 2] in ("=>", "->"):
            i += 2
            result.append(Token(text[start:i], "operator", start, i, startline))
        else:
            i += 1
            result.append(Token(c, "punctuation", start, i, startline))
        column += i - start
    return result, errors


def qualified(tokens, i):
    if i >= len(tokens) or tokens[i].kind != "id":
        return None, i
    name = tokens[i].value
    if i + 2 < len(tokens) and tokens[i + 1].value == "~" and tokens[i + 2].kind == "id":
        return name + "~" + tokens[i + 2].value, i + 3
    return name, i + 1


def analyze(text, object_type):
    ddl = object_type in ("DDLS", "BDEF", "SRVD")
    tokens, diagnostics = lex(text, ddl)
    symbols, edges = [], []
    lines = text.splitlines(keepends=True)
    owner, class_kind, method = None, None, None

    def symbol(name, kind, token, end=None, parent=None):
        row = {"name": name, "kind": kind, "start_line": token.line,
               "end_line": end or token.line, "owner": parent if parent is not None else owner}
        symbols.append(row)
        return row

    def edge(target, relation, token, target_type=None, target_symbol=None):
        edges.append({"target": target, "relation": relation, "line": token.line,
                      "column": token.start - (text.rfind("\n", 0, token.start) + 1) + 1,
                      "target_type": target_type, "target_symbol": target_symbol,
                      "owner": owner, "source_symbol": method["name"] if method else None,
                      "certainty": "explicit_syntax_not_runtime_resolution"})

    if not ddl:
        statements, current = [], []
        for token in tokens:
            if token.value == ".":
                if current:
                    statements.append((current, token.line))
                    current = []
            else:
                current.append(token)
        if current:
            diagnostics.append("unterminated_statement")
        for ts, endline in statements:
            vs = [t.value for t in ts]
            first = vs[0]
            if first in ("CLASS", "INTERFACE") and len(ts) > 1 and ts[1].kind == "id":
                if first == "CLASS" and "DEFERRED" in vs:
                    symbol(vs[1], "class_forward_declaration", ts[0], endline)
                    continue
                owner = vs[1]
                class_kind = "implementation" if "IMPLEMENTATION" in vs else "declaration"
                symbol(owner, ("interface_" if first == "INTERFACE" else "class_") + class_kind, ts[0], endline, owner)
            elif first in ("ENDCLASS", "ENDINTERFACE"):
                owner, class_kind = None, None
            elif first in ("METHODS", "CLASS-METHODS"):
                # Support simple and chained declarations; commas delimit methods.
                chunks, chunk = [], []
                for t in ts[1:]:
                    if t.value == ",":
                        if chunk:
                            chunks.append(chunk)
                        chunk = []
                    elif t.value != ":":
                        chunk.append(t)
                if chunk:
                    chunks.append(chunk)
                for chunk in chunks:
                    name, _ = qualified(chunk, 0)
                    if name:
                        symbol(name, "method_declaration", chunk[0], endline)
                    for j in range(len(chunk) - 3):
                        if [x.value for x in chunk[j:j + 2]] == ["FOR", "ACTION"]:
                            act, _ = qualified(chunk, j + 2)
                            if act:
                                handler = symbol(act, "action_handler_declaration", chunk[j], endline)
                                handler["handler_method"] = name
                                edge(act.split("~")[0], "action_handler_entity", chunk[j + 2], "DDLS", act)
            elif first == "METHOD":
                if method:
                    diagnostics.append("nested_method")
                name, _ = qualified(ts, 1)
                if name:
                    method = symbol(name, "method_implementation", ts[0], endline)
            elif first == "ENDMETHOD":
                if method:
                    method["end_line"] = endline
                    method = None
                else:
                    diagnostics.append("unmatched_endmethod")
            elif first == "FUNCTION":
                name, _ = qualified(ts, 1)
                if name:
                    method = symbol(name, "function_implementation", ts[0], endline)
            elif first == "ENDFUNCTION":
                if method:
                    method["end_line"] = endline
                    method = None
            if first in ("DEFINE", "END-OF-DEFINITION") or any(t.kind == "opaque" for t in ts):
                diagnostics.append("unsupported_macro_or_template")
            if first in ("PERFORM", "SUBMIT", "EXEC"):
                diagnostics.append("unsupported_reference_construct")
            if first == "INCLUDE" and len(ts) == 2 and ts[1].kind == "id":
                edge(vs[1], "include", ts[1], "PROG")
            if vs[:2] == ["CALL", "FUNCTION"]:
                if len(ts) > 2 and ts[2].kind == "string":
                    edge(ts[2].value[1:-1].replace("''", "'").upper(), "function_call", ts[2], "FUNC")
                else:
                    diagnostics.append("dynamic_function_call_unresolved")
            for j in range(len(ts)):
                remaining = vs[j:]
                if remaining[:2] == ["INHERITING", "FROM"] and len(remaining) > 2:
                    if ts[j + 2].kind == "id":
                        edge(vs[j + 2], "inherits", ts[j + 2], "CLAS")
                if remaining[:2] == ["TYPE", "REF"] and len(remaining) > 3 and remaining[2] == "TO" and ts[j + 3].kind == "id":
                    edge(vs[j + 3], "type_ref", ts[j + 3])
                if remaining[0] == "INTERFACES" and len(remaining) > 1:
                    candidates = ts[j + 1:]
                    expect_name = True
                    for candidate in candidates:
                        if candidate.value in (":", ","):
                            expect_name = True
                        elif expect_name and candidate.kind == "id":
                            edge(candidate.value, "implements", candidate, "INTF")
                            expect_name = False
                if remaining[:3] == ["FOR", "BEHAVIOR", "OF"] and len(remaining) > 3:
                    edge(vs[j + 3], "behavior_pool_for", ts[j + 3], "DDLS")
                if remaining[:3] == ["READ", "ENTITIES", "OF"] or remaining[:3] == ["MODIFY", "ENTITIES", "OF"]:
                    if len(remaining) > 3 and ts[j + 3].kind == "id":
                        edge(vs[j + 3], "eml_entity", ts[j + 3], "DDLS")
                if ts[j].kind == "id" and len(remaining) > 2 and remaining[1] == "=>" and ts[j + 2].kind == "id":
                    edge(vs[j], "static_call_or_member", ts[j], "CLASS_OR_INTERFACE", vs[j + 2])
                if remaining[0] == "NEW" and len(remaining) > 2 and ts[j + 1].kind == "id" and remaining[2] == "(":
                    edge(vs[j + 1], "new_class", ts[j + 1], "CLAS")
                if len(remaining) > 1 and remaining[1] == "->":
                    diagnostics.append("instance_dispatch_unresolved")
        if method:
            method["end_line"] = len(lines)
            diagnostics.append("unterminated_method_or_function")
    else:
        vs = [t.value for t in tokens]
        stack = []
        for token in tokens:
            if token.kind == "punctuation" and token.value in ("{", "(", "["):
                stack.append(token.value)
            elif token.kind == "punctuation" and token.value in ("}", ")", "]"):
                if not stack or stack.pop() != {"}": "{", ")": "(", "]": "["}[token.value]:
                    diagnostics.append("unbalanced_ddl_delimiters")
        if stack:
            diagnostics.append("unbalanced_ddl_delimiters")
        # Recognize explicit token productions only; comments/literals excluded.
        for i, t in enumerate(tokens):
            v = vs[i:]
            if t.kind != "id":
                continue
            if object_type == "DDLS":
                if v[:2] == ["VIEW", "ENTITY"] and len(v) > 2:
                    symbol(v[2], "cds_entity", tokens[i + 2], len(lines))
                elif v[:2] == ["DEFINE", "VIEW"] and len(v) > 2 and v[2] != "ENTITY":
                    symbol(v[2], "cds_entity", tokens[i + 2], len(lines))
                if v[:3] == ["AS", "PROJECTION", "ON"] and len(v) > 3:
                    edge(v[3], "projection_on", tokens[i + 3], "DDLS")
                if v[0] in ("FROM", "JOIN") and len(v) > 1 and tokens[i + 1].kind == "id":
                    edge(v[1], "cds_data_source", tokens[i + 1])
                if v[0] in ("ASSOCIATION", "COMPOSITION"):
                    # Search only within this production before its alias/condition.
                    tail = tokens[i + 1:]
                    for j, candidate in enumerate(tail):
                        if candidate.value in ("AS", "ON", ";", "{"):
                            break
                        if candidate.value in ("TO", "OF"):
                            k = j + 1
                            if k < len(tail) and tail[k].value == "PARENT":
                                k += 1
                            if k < len(tail) and tail[k].kind == "id":
                                edge(tail[k].value, "cds_" + v[0].lower(), tail[k], "DDLS")
                            break
            elif object_type == "BDEF":
                if v[:2] == ["IMPLEMENTATION", "IN"]:
                    k = i + 2 + int(len(v) > 2 and v[2] == "CLASS")
                    if k < len(tokens) and tokens[k].kind == "id":
                        edge(vs[k], "behavior_implementation", tokens[k], "CLAS")
                if v[:3] == ["DEFINE", "BEHAVIOR", "FOR"] and len(v) > 3:
                    entry = symbol(v[3], "behavior_entity", tokens[i + 3])
                    if len(v) > 5 and v[4] == "ALIAS":
                        entry["alias"] = v[5]
                    edge(v[3], "behavior_entity", tokens[i + 3], "DDLS")
                if v[0] in ("ACTION", "VALIDATION", "DETERMINATION") and (i == 0 or vs[i - 1] not in ("USE", "FOR")):
                    k = i + 1
                    if k < len(tokens) and tokens[k].value == "(":
                        while k < len(tokens) and tokens[k].value != ")":
                            k += 1
                        k += 1
                    if k < len(tokens) and tokens[k].kind == "id":
                        end, depth = k, 0
                        while end < len(tokens):
                            value = tokens[end].value
                            if value == "{":
                                depth += 1
                            elif value == "}":
                                if depth == 0:
                                    break
                                depth -= 1
                                if depth == 0:
                                    break
                            elif value == ";" and depth == 0:
                                break
                            end += 1
                        symbol(tokens[k].value, "rap_" + v[0].lower(), tokens[k], tokens[min(end, len(tokens) - 1)].line)
            elif object_type == "SRVD" and v[0] == "EXPOSE" and len(v) > 1 and tokens[i + 1].kind == "id":
                edge(v[1], "service_exposes", tokens[i + 1], "DDLS")
        if object_type == "DDLS" and not any(s["kind"] == "cds_entity" for s in symbols):
            diagnostics.append("unsupported_cds_declaration")
        if object_type == "BDEF" and not any(s["kind"] == "behavior_entity" for s in symbols):
            diagnostics.append("unsupported_bdef_declaration")
    return symbols, edges, sorted(set(diagnostics))
