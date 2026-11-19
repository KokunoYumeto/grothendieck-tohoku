"""Enumerate math-font command candidates outside recognized TeX math contexts.

This is a static lexical aid, not a TeX execution, source reading or validity
certificate. It emits command names and coordinates without source excerpts.
No source, correction ledger, review state or existing report is changed.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile

from control_word_inventory import (
    BLOCKED_DIRS, SYNTAX_SIGNALS, VERBATIM_ENVS, coordinates, current_files,
    file_hash, letter, read_snapshot, require_safe_name, sha, skip_space_comments,
    tsv_bytes, utc,
)
from privacy_guard import scan_bytes

FONT_COMMANDS = frozenset({"mathrm", "mathbf", "mathcal", "mathfrak", "mathbb", "boldsymbol"})
OUTER_MATH_ENVS = frozenset({
    "math", "displaymath", "equation", "equation*", "eqnarray", "eqnarray*",
    "align", "align*", "alignat", "alignat*", "xalignat", "xalignat*",
    "xxalignat", "flalign", "flalign*", "gather", "gather*", "multline", "multline*",
})
INNER_MATH_ENVS = frozenset({
    "array", "cases", "dcases", "dcases*", "rcases", "rcases*", "matrix", "matrix*",
    "pmatrix", "pmatrix*", "bmatrix", "bmatrix*", "Bmatrix", "Bmatrix*",
    "vmatrix", "vmatrix*", "Vmatrix", "Vmatrix*", "smallmatrix", "psmallmatrix",
    "bsmallmatrix", "vsmallmatrix", "Vsmallmatrix", "aligned", "alignedat", "gathered", "split",
})
TEXT_BODY_ENVS = frozenset({"minipage", "tabular", "tabular*", "tabularx", "longtable"})
INHERITING_ENVS = frozenset({
    "document", "subequations", "figure", "figure*", "table", "table*", "center",
    "flushleft", "flushright", "itemize", "enumerate", "description", "quote",
    "quotation", "verse", "list", "trivlist", "thebibliography", "proof",
})
TEXT_DIRECT = frozenset({
    "text", "textrm", "textsf", "texttt", "textnormal", "textup", "textit",
    "textsl", "textsc", "textbf", "textmd", "emph", "mbox", "fbox",
    "intertext", "shortintertext",
})
TEXT_OPTIONAL = frozenset({"makebox", "framebox", "footnote", "footnotetext", "caption"})
COMMAND_DEFS = frozenset({"newcommand", "renewcommand", "providecommand", "DeclareRobustCommand"})
XPARSE_DEFS = frozenset({"NewDocumentCommand", "RenewDocumentCommand", "ProvideDocumentCommand", "DeclareDocumentCommand"})
ENV_DEFS = frozenset({"newenvironment", "renewenvironment", "provideenvironment"})
XPARSE_ENV_DEFS = frozenset({"NewDocumentEnvironment", "RenewDocumentEnvironment", "ProvideDocumentEnvironment", "DeclareDocumentEnvironment"})
PRIMITIVE_DEFS = frozenset({"def", "gdef", "edef", "xdef"})
EXPANSION_SIGNALS = frozenset({"if", "ifx", "ifmmode", "iftrue", "iffalse", "else", "fi", "noexpand", "expandafter", "unexpanded"})


def token(text: str, offset: int) -> tuple[str, str, int]:
    if text[offset] != "\\":
        return "character", text[offset], offset + 1
    if offset + 1 == len(text):
        return "symbol", "", offset + 1
    if not letter(text[offset + 1]):
        return "symbol", text[offset + 1], offset + 2
    end = offset + 2
    while end < len(text) and letter(text[end]):
        end += 1
    return "word", text[offset + 1:end], end


def balanced_end(text: str, start: int) -> int | None:
    """End after a literal brace/optional group; escaped delimiters do not count."""
    opening = text[start:start + 1]
    if opening not in {"{", "["}:
        return None
    depth, braces, offset = 1, 0, start + 1
    while offset < len(text):
        character = text[offset]
        if character == "%":
            end = text.find("\n", offset)
            offset = len(text) if end < 0 else end
            continue
        if character == "\\":
            _, _, offset = token(text, offset)
            continue
        if opening == "{":
            depth += int(character == "{") - int(character == "}")
        else:
            if character == "{":
                braces += 1
            elif character == "}":
                braces = max(0, braces - 1)
            elif braces == 0:
                depth += int(character == "[") - int(character == "]")
        offset += 1
        if depth == 0:
            return offset
    return None


def scan_font_context(data: bytes, probe_offsets: set[int] | None = None) -> dict:
    text = data.decode("utf-8-sig")
    requested = set() if probe_offsets is None else set(probe_offsets)
    if any(type(position) is not int or not 0 <= position < len(text) for position in requested):
        raise ValueError("Context probes must be valid decoded-character offsets.")
    starts = [0] + [match.end() for match in re.finditer("\n", text)]
    stack = [{"kind": "root", "mode": "text", "label": "file entry assumed text", "offset": 0}]
    group_modes, token_modes, references = {}, {}, {}
    region_starts, region_ends, literal_ranges = {}, {}, {}
    occurrences, notes, probes, uncertain_scopes = [], [], [], set()

    def scope_key(frame: dict) -> tuple:
        return frame["kind"], frame["label"], frame["offset"]

    def mark_uncertain(frames: list[dict]) -> None:
        uncertain_scopes.update(scope_key(frame) for frame in frames if frame["mode"] == "math")

    def note(offset: int, kind: str, name: str, detail: str) -> None:
        line, column = coordinates(offset, starts)
        notes.append({"line": line, "column": column, "kind": kind, "syntax_name": name, "detail": detail})

    def context(offset: int) -> tuple[int, dict]:
        if offset in token_modes:
            return len(stack), token_modes[offset]
        for index in range(len(stack) - 1, -1, -1):
            if stack[index]["mode"] is not None:
                return index, stack[index]
        raise AssertionError("The scanner always retains a root mode.")

    def describe(offset: int, role: str = "invocation token") -> dict:
        _, active = context(offset)
        mode = active["mode"]
        deferred = next((frame for frame in reversed(stack) if frame.get("deferred")), None)
        candidate = role == "invocation token" and mode != "math"
        if role != "invocation token":
            category = "literal or declaration reference"
        elif deferred:
            category = "deferred definition body"
        elif mode == "math":
            category = "recognized math"
        elif mode == "unknown":
            category = "uncertain context"
        elif active["kind"] in {"group", "single-token"}:
            category = "recognized text argument"
        elif active["kind"] == "environment":
            category = "recognized text environment"
        else:
            category = "lexically plain text"
        line, column = coordinates(offset, starts)
        return {
            "line": line, "column": column, "token_role": role,
            "observed_mode": mode, "context_category": category,
            "context_name": deferred["label"] if deferred else active["label"],
            "context_start_line": coordinates((deferred or active)["offset"], starts)[0],
            "candidate": "yes" if candidate else "no",
            "context_caveat": "",
            "_scope_key": scope_key(active), "_deferred": bool(deferred),
        }

    def record(offset: int, name: str, role: str = "invocation token") -> None:
        occurrences.append({"command": name, **describe(offset, role)})

    def optional_arguments(offset: int) -> int:
        offset = skip_space_comments(text, offset)
        while offset < len(text) and text[offset] == "[":
            end = balanced_end(text, offset)
            if end is None:
                return offset
            offset = skip_space_comments(text, end)
        return offset

    def group_after(offset: int) -> tuple[int, int] | None:
        start = skip_space_comments(text, offset)
        if start < len(text) and text[start] == "{":
            end = balanced_end(text, start)
            if end is not None:
                return start, end
        return None

    def scope_argument(offset: int, mode: str, name: str, command_at: int,
                       *, deferred: bool = False, require_group: bool = False) -> None:
        start = skip_space_comments(text, offset)
        frame = {"kind": "group", "mode": mode, "label": name, "offset": command_at, "deferred": deferred}
        if start >= len(text):
            note(command_at, "missing argument", name, "No argument token is available; context was not changed.")
        elif text[start] == "{":
            group_modes[start] = frame
            if balanced_end(text, start) is None:
                note(command_at, "unclosed argument", name, "The explicit argument group is not balanced; later context is uncertain.")
        elif require_group:
            note(command_at, "unsupported argument form", name, "No explicit body group was recognized; its execution context is not inferred.")
            _, active = context(command_at)
            mark_uncertain([active])
        else:
            token_modes[start] = {**frame, "kind": "single-token"}
            note(command_at, "single-token argument", name, "Only the next TeX token receives this lexical argument mode; macro expansion is not modeled.")

    def target_after(offset: int) -> tuple[int, int] | None:
        start = skip_space_comments(text, offset)
        braced = start < len(text) and text[start] == "{"
        at = skip_space_comments(text, start + 1) if braced else start
        if at >= len(text) or text[at] != "\\":
            return None
        kind, _, end = token(text, at)
        if kind != "word":
            return None
        after = skip_space_comments(text, end)
        if braced:
            if after >= len(text) or text[after] != "}":
                return None
            after += 1
        return at, after

    def definition(name: str, command_at: int, end: int) -> None:
        position = skip_space_comments(text, end)
        if position < len(text) and text[position] == "*":
            position = skip_space_comments(text, position + 1)
        environment = name in ENV_DEFS | XPARSE_ENV_DEFS
        if environment:
            target = group_after(position)
            if target is None:
                note(command_at, "unrecognized definition", name, "The literal definition signature was not recognized; no expansion is inferred.")
                return
            position = target[1]
        else:
            target = target_after(position)
            if target is None:
                note(command_at, "unrecognized definition", name, "The literal definition target was not recognized; no expansion is inferred.")
                return
            references[target[0]] = "declaration target"
            position = target[1]
        if name in PRIMITIVE_DEFS:
            parameter_start = position
            while position < len(text) and text[position] != "{":
                if text[position] == "%":
                    newline = text.find("\n", position)
                    position = len(text) if newline < 0 else newline
                elif text[position] == "\\":
                    _, _, position = token(text, position)
                else:
                    position += 1
            if parameter_start < position:
                literal_ranges[parameter_start] = (position, "literal definition-signature token")
        elif name in XPARSE_DEFS | XPARSE_ENV_DEFS:
            signature = group_after(position)
            if signature is None:
                note(command_at, "unrecognized definition", name, "The document-command argument specification was not recognized.")
                return
            scope_argument(signature[0], "unknown", name + " signature", command_at, deferred=True, require_group=True)
            position = signature[1]
        else:
            position = skip_space_comments(text, position)
            while position < len(text) and text[position] == "[":
                optional_end = balanced_end(text, position)
                if optional_end is None:
                    note(command_at, "unrecognized definition", name, "An optional definition argument is not balanced.")
                    return
                frame = {"kind": "deferred optional", "mode": "unknown",
                         "label": name + " optional signature/default", "offset": position, "deferred": True}
                region_starts[position] = frame
                region_ends[optional_end - 1] = scope_key(frame)
                position = skip_space_comments(text, optional_end)
        count = 2 if environment else 1
        for _ in range(count):
            body = group_after(position)
            if body is None:
                note(command_at, "unrecognized definition", name, "A balanced literal replacement body was not recognized.")
                return
            scope_argument(body[0], "unknown", name + " replacement body", command_at, deferred=True, require_group=True)
            position = body[1]

    def close_math(delimiter: str, offset: int) -> None:
        index, active = context(offset)
        if active["kind"] != "math" or active["label"] != delimiter:
            note(offset, "mismatched math close", delimiter, "No matching active lexical math opener is available; context is left unchanged.")
            return
        if index != len(stack) - 1:
            note(offset, "math close crosses an open scope", delimiter, "Open groups or environments were recovered at this delimiter; affected context requires manual review.")
            mark_uncertain(stack[index:])
        del stack[index:]

    def open_math(delimiter: str, offset: int) -> None:
        _, active = context(offset)
        if active["mode"] == "math":
            note(offset, "nested math opener", delimiter, "A math opener occurs inside recognized math; this lexical recovery is not TeX validation.")
        stack.append({"kind": "math", "mode": "math", "label": delimiter, "offset": offset})

    offset = 0
    while offset < len(text):
        if offset in literal_ranges:
            end, role = literal_ranges[offset]
            while offset < end:
                if text[offset] == "%":
                    newline = text.find("\n", offset)
                    offset = end if newline < 0 else min(end, newline)
                elif text[offset] == "\\":
                    kind, name, after = token(text, offset)
                    if kind == "word" and name in FONT_COMMANDS:
                        record(offset, name, role)
                    offset = after
                else:
                    offset += 1
            continue
        if offset in region_starts:
            stack.append(region_starts[offset])
            offset += 1
            continue
        if offset in region_ends:
            key = region_ends[offset]
            index = next((i for i in range(len(stack) - 1, 0, -1) if scope_key(stack[i]) == key), None)
            if index is None:
                note(offset, "unmatched deferred-argument close", "optional argument", "The deferred argument scope was already lost during lexical recovery.")
            else:
                if index != len(stack) - 1:
                    note(offset, "deferred-argument close crosses an open scope", "optional argument", "Open nested frames were recovered at a deferred argument boundary.")
                    mark_uncertain(stack[index:])
                del stack[index:]
            offset += 1
            continue
        character = text[offset]
        if character == "%":
            newline = text.find("\n", offset)
            offset = len(text) if newline < 0 else newline
            continue
        if character == "{":
            stack.append(group_modes.get(offset, {"kind": "group", "mode": None, "label": "ordinary group", "offset": offset}))
            offset += 1
            continue
        if character == "}":
            index = next((i for i in range(len(stack) - 1, 0, -1) if stack[i]["kind"] == "group"), None)
            if index is None:
                note(offset, "unmatched group close", "brace", "A closing brace has no lexical opener in this file.")
            else:
                if index != len(stack) - 1:
                    note(offset, "group close crosses an open scope", "brace", "Open math or environment frames were recovered at this group boundary.")
                    mark_uncertain(stack[index:])
                del stack[index:]
            offset += 1
            continue
        if character == "$":
            _, active = context(offset)
            if active["kind"] == "math" and active["label"] == "$":
                # Adjacent inline spans close one dollar, then open the next.
                close_math("$", offset)
                offset += 1
            elif active["kind"] == "math" and active["label"] == "$$":
                if text.startswith("$$", offset):
                    close_math("$$", offset)
                    offset += 2
                else:
                    note(offset, "single dollar inside display math", "$", "A display close needs two dollars in this model; the mode remains uncertain math.")
                    offset += 1
            else:
                delimiter = "$$" if text.startswith("$$", offset) else "$"
                open_math(delimiter, offset)
                offset += len(delimiter)
            continue
        if character != "\\":
            if offset in requested and offset not in references:
                probes.append({"offset": offset, **describe(offset)})
            offset += 1
            continue
        kind, name, end = token(text, offset)
        if kind == "symbol":
            if name in {"(", "["}:
                open_math("\\" + name, offset)
            elif name in {")", "]"}:
                close_math("\\" + {")": "(", "]": "["}[name], offset)
            offset = end
            continue
        if name in FONT_COMMANDS:
            record(offset, name, references.get(offset, "invocation token"))
        if offset in references:
            offset = end
            continue
        if name in SYNTAX_SIGNALS | EXPANSION_SIGNALS:
            note(offset, "uninterpreted execution signal", name, "Catcodes, constructed names, conditionals and expansion control are not executed by this scanner.")
        if name == "verb":
            delimiter_at = end + int(end < len(text) and text[end] == "*")
            if delimiter_at >= len(text) or text[delimiter_at] in "\r\n":
                note(offset, "incomplete inline literal", name, "No same-line literal delimiter was available.")
                offset = end
                continue
            line_end = text.find("\n", delimiter_at)
            line_end = len(text) if line_end < 0 else line_end
            close = text.find(text[delimiter_at], delimiter_at + 1, line_end)
            if close < 0:
                note(offset, "incomplete inline literal", name, "The remainder of the line was treated as literal because no closing delimiter was found.")
            offset = line_end if close < 0 else close + 1
            continue
        if name in {"string", "meaning"}:
            at = skip_space_comments(text, end)
            if at < len(text):
                next_kind, next_name, after = token(text, at)
                if next_kind == "word" and next_name in FONT_COMMANDS:
                    record(at, next_name, "literal token reference via " + name)
                offset = after
                continue
        if name == "detokenize":
            body = group_after(end)
            if body is not None:
                offset = body[1]
                continue
            note(offset, "unsupported literal argument", name, "No balanced literal group was recognized; following tokens remain visible.")
        if name in {"let", "futurelet"}:
            target = target_after(end)
            if target is not None:
                references[target[0]] = "assignment target"
                if name == "let":
                    at = skip_space_comments(text, target[1])
                    if at < len(text) and text[at] == "=":
                        at = skip_space_comments(text, at + 1)
                    if at < len(text):
                        references[at] = "literal alias source"
        if name in COMMAND_DEFS | XPARSE_DEFS | ENV_DEFS | XPARSE_ENV_DEFS | PRIMITIVE_DEFS | {"DeclareMathOperator"}:
            definition(name, offset, end)
        if name in {"begin", "end"}:
            argument = skip_space_comments(text, end)
            match = re.match(r"\{([A-Za-z][A-Za-z0-9*_-]*)\}", text[argument:])
            if match:
                environment = match.group(1)
                after = argument + match.end()
                if name == "begin" and environment in VERBATIM_ENVS:
                    marker = "\\end{" + environment + "}"
                    close = text.find(marker, after)
                    if close < 0:
                        note(offset, "unclosed literal environment", environment, "The remaining file was treated as literal; no matching literal end marker was found.")
                        offset = len(text)
                    else:
                        offset = close + len(marker)
                    continue
                if name == "begin":
                    _, active = context(offset)
                    mode = None
                    if environment in OUTER_MATH_ENVS:
                        mode = "math"
                        if active["mode"] == "math":
                            note(offset, "outer math environment inside math", environment, "An outer math environment was encountered while already in lexical math.")
                    elif environment in INNER_MATH_ENVS:
                        if active["mode"] != "math":
                            mode = "unknown"
                            note(offset, "inner math environment outside recognized math", environment, "This environment requires surrounding math; its contents are retained as uncertain context.")
                    elif environment in TEXT_BODY_ENVS:
                        mode = "text"
                    elif environment not in INHERITING_ENVS:
                        note(offset, "unrecognized environment mode", environment, "The environment inherits surrounding mode; a custom definition could change it.")
                    stack.append({"kind": "environment", "mode": mode, "label": environment, "offset": offset})
                else:
                    index = next((i for i in range(len(stack) - 1, 0, -1)
                                  if stack[i]["kind"] == "environment" and stack[i]["label"] == environment), None)
                    if index is None:
                        note(offset, "unmatched environment close", environment, "No matching lexical environment opener occurs in the current file scope.")
                    else:
                        if index != len(stack) - 1:
                            note(offset, "environment close crosses an open scope", environment, "Nested open scopes were recovered at this environment boundary.")
                            mark_uncertain(stack[index:])
                        del stack[index:]
                offset = after
                continue
            note(offset, "unrecognized environment argument", name, "A literal environment name was not recognized; no mode change was inferred.")
        if name == "ensuremath":
            scope_argument(end, "math", name, offset)
        elif name in TEXT_DIRECT:
            scope_argument(end, "text", name, offset)
        elif name in TEXT_OPTIONAL:
            scope_argument(optional_arguments(end), "text", name, offset)
        elif name in {"hbox", "vbox", "vtop"}:
            at = skip_space_comments(text, end)
            specification = re.match(r"(?:to|spread)(?![A-Za-z])", text[at:])
            if specification:
                dimension_at = skip_space_comments(text, at + specification.end())
                dimension = re.match(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)[ \t]*(?:pt|pc|in|bp|cm|mm|dd|cc|sp|em|ex)(?![A-Za-z])", text[dimension_at:])
                body_at = skip_space_comments(text, dimension_at + dimension.end()) if dimension else None
                if body_at is not None and body_at < len(text) and text[body_at] == "{":
                    scope_argument(body_at, "text", name, offset, require_group=True)
                else:
                    note(offset, "unsupported box dimension", name, "A literal dimension followed by its body group was not recognized; font occurrences in the containing math scope are retained as uncertain candidates.")
                    _, active = context(offset)
                    mark_uncertain([active])
            else:
                scope_argument(at, "text", name, offset, require_group=True)
        elif name == "parbox":
            width = group_after(optional_arguments(end))
            if width:
                scope_argument(width[1], "text", name, offset, require_group=True)
            else:
                note(offset, "unsupported argument form", name, "The width/body argument sequence was not recognized.")
        elif name == "raisebox":
            lift = group_after(end)
            if lift:
                scope_argument(optional_arguments(lift[1]), "text", name, offset, require_group=True)
            else:
                note(offset, "unsupported argument form", name, "The lift/body argument sequence was not recognized.")
        offset = end
    for frame in stack[1:]:
        note(frame["offset"], "unclosed lexical scope", frame["label"], "This scope remained open at the end of the file; input boundaries and macro execution are not reconstructed.")
    mark_uncertain(stack[1:])
    for item in occurrences + probes:
        if item["_scope_key"] in uncertain_scopes and item["token_role"] == "invocation token":
            item["observed_mode"] = "unknown"
            item["context_category"] = "deferred definition body" if item["_deferred"] else "uncertain context"
            item["candidate"] = "yes"
            item["context_caveat"] = "math scope marked uncertain; see lexical notes"
        del item["_scope_key"], item["_deferred"]
        item["file_has_lexical_notes"] = "yes" if notes else "no"
    result = {"occurrences": occurrences, "notes": notes,
              "lines": data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))}
    if probe_offsets is not None:
        for item in probes:
            del item["candidate"], item["token_role"]
            item["visited"] = True
        visited = {item["offset"] for item in probes}
        result["probes"] = sorted(probes + [
            {"offset": position, "visited": False,
             "context_category": "skipped lexical material or syntax"}
            for position in requested - visited
        ], key=lambda item: item["offset"])
    return result


def recheck_sources(sources: Path, snapshot: dict[str, bytes]) -> None:
    paths = current_files(sources)
    if set(paths) != set(snapshot):
        raise RuntimeError("The eligible source-file set changed; no report was installed.")
    if any(file_hash(path) != (len(snapshot[name]), sha(snapshot[name])) for name, path in paths.items()):
        raise RuntimeError("A source changed after the lexical snapshot; no report was installed.")


def run(args) -> dict:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside a protected context folder.")
    if args.output.is_absolute() or "interim" not in args.output.name.casefold():
        raise ValueError("Use a new relative report-directory name explicitly containing interim.")
    require_safe_name(args.output.as_posix())
    if any(part.casefold() in BLOCKED_DIRS for part in args.output.parts):
        raise ValueError("The report cannot be placed inside a protected context folder.")
    cursor = root
    for part in args.output.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("The report path must not pass through a symbolic link.")
    output = (root / args.output).resolve()
    if output == root or root not in output.parents or any(
        output == root / name or root / name in output.parents for name in ("sources", "pdf")
    ):
        raise ValueError("The report must be inside the delivery tree and outside source/PDF trees.")
    if output.exists():
        raise ValueError("The interim report already exists; snapshots are never overwritten.")
    sources = root / "sources"
    paths = current_files(sources)
    if not paths:
        raise ValueError("No eligible current TeX sources were found.")
    snapshot = {name: read_snapshot(path) for name, path in paths.items()}
    occurrences, candidates, notes, source_rows, file_rows = [], [], [], [], []
    for name, data in snapshot.items():
        result = scan_font_context(data)
        locator = "sources/" + name
        page = re.fullmatch(r"(dip|fr|en)/p(\d{3})\.tex", name)
        metadata = {"file": locator, "layer": page.group(1) if page else "build",
                    "printed_page": page.group(2) if page else ""}
        for item in result["occurrences"]:
            entry = {**metadata, **item}
            occurrences.append(entry)
            if item["candidate"] == "yes":
                candidates.append({"candidate_id": f"M{len(candidates) + 1:06d}", **entry,
                                   "review_status": "pending manual review"})
        notes.extend({**metadata, **item} for item in result["notes"])
        source_rows.append({"file": locator, "bytes": len(data), "sha256": sha(data)})
        file_rows.append({**metadata, "lines": result["lines"], "font_command_tokens": len(result["occurrences"]),
                          "candidates": sum(item["candidate"] == "yes" for item in result["occurrences"]),
                          "lexical_notes": len(result["notes"])})
    base = ["file", "layer", "printed_page", "line", "column", "command", "token_role",
            "observed_mode", "context_category", "context_name", "context_start_line", "candidate", "context_caveat", "file_has_lexical_notes"]
    source_inventory = sha(json.dumps(source_rows, sort_keys=True, separators=(",", ":")).encode())
    counts = Counter(item["context_category"] for item in candidates)
    summary = {"source_files": len(snapshot), "font_command_tokens": len(occurrences),
               "candidate_occurrences": len(candidates), "candidate_files": len({item["file"] for item in candidates}),
               "candidate_contexts": dict(sorted(counts.items())), "lexical_notes": len(notes),
               "files_with_lexical_notes": len({item["file"] for item in notes})}
    tables = {
        "CANDIDATES.tsv": (["candidate_id"] + base + ["review_status"], candidates),
        "FONT_COMMAND_OCCURRENCES.tsv": (base, occurrences),
        "LEXICAL_NOTES.tsv": (["file", "layer", "printed_page", "line", "column", "kind", "syntax_name", "detail"], notes),
        "FILE_SUMMARY.tsv": (["file", "layer", "printed_page", "lines", "font_command_tokens", "candidates", "lexical_notes"], file_rows),
        "SOURCE_HASHES.tsv": (["file", "bytes", "sha256"], source_rows),
        "INPUT_HASHES.tsv": (["role", "file", "sha256"], [{"role": "current lexical source inventory", "file": "SOURCE_HASHES.tsv logical rows", "sha256": source_inventory}]),
    }
    report = ["# Interim math-font context candidates", "", "Generated " + utc() + ".", "",
              "This report is a static candidate enumeration, not a reading, TeX validity check or certification. It changes no source and runs no build.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items() if key != "candidate_contexts")
    report.extend(["", "## Candidate contexts", "", "| Context | Count |", "| --- | ---: |"])
    report.extend(f"| {key} | {value} |" for key, value in sorted(counts.items()))
    report.extend(["", "## Interpretation and limits", "",
                   "The six literal command names are mathrm, mathbf, mathcal, mathfrak, mathbb and boldsymbol. Candidate rows are invocation tokens outside a recognized math context, including explicitly uncertain contexts. Definition bodies are deferred templates, not assertions that their tokens execute in text. Literal/declaration references are recorded separately in FONT_COMMAND_OCCURRENCES.tsv and are not invocation candidates.", "",
                   "The scanner recognizes common inline/display delimiters, outer versus inner math environments, text argument nesting, ensuremath, and the text bodies of common boxes. It consumes escaped control symbols, skips comments, simple verb bodies, documented verbatim environments and balanced detokenize bodies. Details and the exact supported sets are in scripts/MATH_FONT_CONTEXT.md and the helper constants.", "",
                   "Each file starts in assumed text mode. No input expansion, macro execution, package loading, conditional evaluation, catcode reconstruction, constructed command-name resolution or cross-file state propagation occurs. Unknown environments inherit their surrounding lexical mode and generate a note. Unclosed/recovered math scopes and unsupported box dimensions retain font occurrences as uncertain candidates. Malformed boundaries, deferred definitions and custom macros require manual context. Absence of candidates or notes does not establish correct TeX or faithful text.", "",
                   "All command locations are one-based physical LF lines and character columns. No prose or formula excerpts are emitted. Candidate IDs belong only to this snapshot. Every candidate remains pending manual review.", "",
                   "The current eligible file set and every source hash were rechecked before exclusive report installation. Sources under programme, notes or stacks directories and symbolic links are not opened. This directory is an immutable interim snapshot; later edits need a new output name.", ""])
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads["REPORT.md"] = "\n".join(report).encode("utf-8")
    payloads["SUMMARY.json"] = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Generated metadata has a privacy pattern or inspection blocker; no report was installed.")
    with tempfile.TemporaryDirectory(prefix="math-font-context-", dir=root.parent) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        recheck_sources(sources, snapshot)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir()
        installed = []
        try:
            for name in sorted(payloads):
                path = output / name
                os.link(prepared / name, path)
                installed.append(path)
        except BaseException:
            for path in installed:
                path.unlink()
            output.rmdir()
            raise
    print(json.dumps({**summary, "report_directory": output.relative_to(root).as_posix()}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="Fresh relative directory explicitly named interim")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
