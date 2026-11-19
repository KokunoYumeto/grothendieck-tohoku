"""Read-only interim notation recurrences and cross-page ledger pair groups.

All review statuses remain pending. The helper reports literal/lexical data,
never content correctness, semantic categories, scan readings or coverage of
corrections. It changes no source, ledger, review state or existing snapshot.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
import io
import json
import os
from pathlib import Path
import re
import tempfile

from control_word_inventory import (
    BLOCKED_DIRS, coordinates, file_hash, lex_control_words, read_snapshot,
    require_safe_name, sha, skip_space_comments, tsv_bytes, utc,
)
from math_font_context import FONT_COMMANDS, balanced_end, scan_font_context, token
from privacy_guard import safe_location, scan_bytes
from recurrence_inventory import LAYER_RANK, PAGE_RANK, PAGES, match_context, source_paths
from second_reading import FIELDS

CONTROL_WORDS = ["mathcal", "mathbb", "longrightarrow", "longleftarrow", "longleftrightarrow",
                 "longmapsto", "leq", "geq", "varepsilon", "epsilon", "varinjlim", "varprojlim"]
CONTROL_SPELLINGS = ["noindentAB", "inZ", "toI", "toII", "cdotb", "cdotu"]
LITERAL_PHRASES = ["de homologies", "de homomorphisme", "du homomorphisme"]
PATTERNS = [
    {"family": name, "kind": "bounded control word", "literal": "\\" + name,
     "pattern": re.escape("\\" + name) + r"(?![A-Za-z])", "leading_control": name}
    for name in CONTROL_WORDS + CONTROL_SPELLINGS
] + [
    {"family": phrase.replace(" ", "_"), "kind": "bounded literal phrase", "literal": phrase,
     "pattern": r"(?<![\w\\])" + re.escape(phrase) + r"(?!\w)", "leading_control": ""}
    for phrase in LITERAL_PHRASES
] + [
    {"family": "mathrm_g_generalement", "kind": "literal TeX spelling",
     "literal": r"\mathrm{g}énéralement", "pattern": re.escape(r"\mathrm{g}énéralement") + r"(?!\w)",
     "leading_control": "mathrm"}
]
FAMILY_RANK = {row["family"]: index for index, row in enumerate(PATTERNS)}
NESTED_FONT_COMMANDS = FONT_COMMANDS | frozenset({
    "mathnormal", "mathit", "mathsf", "mathtt", "textrm", "textsf", "texttt",
    "textnormal", "textup", "textit", "textsl", "textsc", "textbf", "textmd", "emph",
})
MATCH_FIELDS = [
    "match_id", "family", "layer", "file", "printed_page", "line", "column",
    "end_line", "end_column", "matched_token", "match_category", "token_role",
    "argument_kind", "argument_source", "argument_tokens", "argument_sha256",
    "argument_line", "argument_end_line", "lexical_mode", "context_category",
    "context_name", "context_caveat", "file_has_lexical_notes", "source_line",
    "source_line_sha256", "privacy_filtered_fields", "review_status",
]


def safe_record(row: dict, fields: tuple[str, ...]) -> dict:
    result = dict(row)
    filtered = []
    for field in fields:
        value = result.get(field, "")
        if isinstance(value, str):
            result[field] = safe_location(value)
            if result[field] != value:
                filtered.append(field)
    result["privacy_filtered_fields"] = ",".join(filtered)
    return result


def next_argument(text: str, offset: int, limit: int | None = None) -> dict:
    """Capture one explicit lexical argument without expansion or inference."""
    bounded = text if limit is None else text[:limit]
    at = skip_space_comments(bounded, offset)
    if at >= len(bounded):
        return {"kind": "no following argument token available", "source": "", "tokens": "", "start": at, "end": at}
    if bounded[at] == "{":
        end = balanced_end(bounded, at)
        if end is None:
            return {"kind": "unclosed explicit group", "source": bounded[at:], "tokens": bounded[at + 1:], "start": at, "end": len(bounded)}
        return {"kind": "explicit braced group", "source": bounded[at:end], "tokens": bounded[at + 1:end - 1], "start": at, "end": end}
    kind, _, end = token(bounded, at)
    return {"kind": "single " + kind, "source": bounded[at:end], "tokens": bounded[at:end], "start": at, "end": end}


def structural_candidates(text: str, lexical: dict, metadata: dict) -> tuple[list, list, list]:
    """Return location-only nested-font and exact per-file anchor candidates."""
    starts = [0] + [match.end() for match in re.finditer("\n", text)]
    scopes = {"source": [(item, None) for item in lexical["occurrences"]]}
    comment_tokens = []
    wanted = NESTED_FONT_COMMANDS | {"LayerTarget"}
    expression = re.compile(r"\\(" + "|".join(sorted(wanted, key=len, reverse=True)) + r")(?![A-Za-z])")
    for first, last in lexical["comment_ranges"]:
        for match in expression.finditer(text, first, last):
            line, column = coordinates(match.start(), starts)
            comment_tokens.append(({"command": match.group(1), "offset": match.start(), "end": match.end(),
                                    "line": line, "column": column}, last))
    scopes["comment"] = comment_tokens
    nested, anchors, parse_notes = [], [], []
    for scope, tokens in scopes.items():
        by_font = defaultdict(list)
        by_anchor = defaultdict(list)
        for item, limit in tokens:
            if item["command"] in NESTED_FONT_COMMANDS:
                by_font[item["command"]].append((item, limit))
            elif item["command"] == "LayerTarget":
                argument = next_argument(text, item["end"], limit)
                if argument["kind"] == "explicit braced group":
                    by_anchor[argument["tokens"]].append(item)
                else:
                    parse_notes.append({**metadata, "scope": scope, "line": item["line"], "column": item["column"],
                                        "argument_kind": argument["kind"], "review_status": "pending"})
        for command, items in by_font.items():
            positions = [item["offset"] for item, _ in items]
            for outer, limit in items:
                argument = next_argument(text, outer["end"], limit)
                first = bisect_left(positions, argument["start"])
                last = bisect_left(positions, argument["end"])
                for inner, _ in items[first:last]:
                    payload_start = argument["start"] + int(argument["kind"] == "explicit braced group")
                    payload_start = skip_space_comments(text if limit is None else text[:limit], payload_start)
                    nested.append({**metadata, "scope": scope, "command": command,
                                   "outer_line": outer["line"], "outer_column": outer["column"],
                                   "inner_line": inner["line"], "inner_column": inner["column"],
                                   "nesting_position": "first payload token" if inner["offset"] == payload_start else "later token in argument",
                                   "outer_argument_kind": argument["kind"],
                                   "outer_argument_sha256": sha(argument["source"].encode()), "review_status": "pending"})
        for anchor, items in by_anchor.items():
            if len(items) < 2:
                continue
            anchors.append(safe_record({
                **metadata, "scope": scope, "anchor": anchor, "anchor_sha256": sha(anchor.encode()),
                "simple_literal_identifier": "yes" if re.fullmatch(r"[A-Za-z0-9:._/-]+", anchor) else "no",
                "occurrences": len(items), "locations": ";".join(f"{item['line']}:{item['column']}" for item in items),
                "first_line": items[0]["line"], "first_column": items[0]["column"], "review_status": "pending",
            }, ("anchor",)))
    return nested, anchors, parse_notes


def source_inventory(snapshot: dict[str, bytes]) -> tuple[dict, dict]:
    matches, notes, source_rows = [], [], []
    nested_fonts, duplicate_anchors, anchor_notes = [], [], []
    for name, data in snapshot.items():
        location = re.fullmatch(r"sources/(dip|fr|en)/p([0-9]{3})\.tex", name)
        if location is None:
            raise ValueError("A source snapshot member is not a relative page filename.")
        layer, page = location.group(1), int(location.group(2))
        text = data.decode("utf-8-sig")
        starts = [0] + [match.end() for match in re.finditer("\n", text)]
        lexical = lex_control_words(data, include_comment_ranges=True)
        metadata = {"file": name, "layer": layer, "printed_page": page}
        nested, anchors, failures = structural_candidates(text, lexical, metadata)
        nested_fonts.extend(nested)
        duplicate_anchors.extend(anchors)
        anchor_notes.extend(failures)
        controls = {item["offset"]: item for item in lexical["occurrences"]}
        comments = lexical["comment_ranges"]
        comment_starts = [first for first, _ in comments]
        raw = [(pattern, found) for pattern in PATTERNS
               for found in re.finditer(pattern["pattern"], text)]
        ordinary_probes = {position for pattern, found in raw if not pattern["leading_control"]
                           for position in (found.start(), found.end() - 1)}
        modes = scan_font_context(data, ordinary_probes)
        probes = {item["offset"]: item for item in modes["probes"]}
        fonts = {(item["line"], item["column"], item["command"]): item for item in modes["occurrences"]}
        for pattern, found in raw:
            line, column = coordinates(found.start(), starts)
            end_line, end_column = coordinates(found.end() - 1, starts)
            comment_index = bisect_right(comment_starts, found.start()) - 1
            in_comment = comment_index >= 0 and found.end() <= comments[comment_index][1]
            control = controls.get(found.start())
            leading = pattern["leading_control"]
            lexical_mode, context_category, context_name, caveat, role = "", "", "", "", ""
            if in_comment:
                category = "comment"
                role, context_category = "unexecuted comment spelling", "comment"
            elif leading:
                category = "source" if control and control["command"] == leading else "reference"
                role = "lexical control-word token" if category == "source" else "raw spelling without a recognized control-word token"
                font = fonts.get((line, column, leading))
                if font:
                    lexical_mode, context_category = font["observed_mode"], font["context_category"]
                    context_name, caveat, role = font["context_name"], font["context_caveat"], font["token_role"]
                elif pattern["family"] in {"mathcal", "mathbb"}:
                    lexical_mode, context_category = "unknown", "not visited by font-context scanner"
                    caveat = "possible literal or skipped syntax; no invocation or mode inferred"
            else:
                lexical_mode, context_category, context_name, caveat, exclusion = match_context(
                    probes[found.start()], probes[found.end() - 1]
                )
                category = "reference" if exclusion else "source"
                role = "literal source phrase" if category == "source" else "literal spelling in skipped material or syntax"
            argument = {"kind": "", "source": "", "tokens": "", "start": found.end(), "end": found.end()}
            if pattern["family"] in {"mathcal", "mathbb"}:
                if role in {"declaration target", "assignment target", "literal alias source", "literal definition-signature token"} or role.startswith("literal token reference"):
                    argument["kind"] = "reference token; no argument inferred"
                else:
                    argument = next_argument(text, found.end(), comments[comment_index][1] if in_comment else None)
                    if in_comment:
                        argument["kind"] = "comment spelling: " + argument["kind"]
            span_end = max(found.end(), argument["end"])
            span_last_line = coordinates(max(found.start(), span_end - 1), starts)[0]
            line_end = starts[span_last_line] if span_last_line < len(starts) else len(text)
            source_line = text[starts[line - 1]:line_end].rstrip("\r\n")
            row = {
                "family": pattern["family"], "layer": layer, "file": name, "printed_page": page,
                "line": line, "column": column, "end_line": end_line, "end_column": end_column,
                "matched_token": found.group(), "match_category": category, "token_role": role,
                "argument_kind": argument["kind"], "argument_source": argument["source"],
                "argument_tokens": argument["tokens"], "argument_sha256": sha(argument["source"].encode()) if argument["source"] else "",
                "argument_line": coordinates(argument["start"], starts)[0] if argument["source"] else "",
                "argument_end_line": coordinates(argument["end"] - 1, starts)[0] if argument["source"] else "",
                "lexical_mode": lexical_mode, "context_category": context_category,
                "context_name": context_name, "context_caveat": caveat,
                "file_has_lexical_notes": "yes" if modes["notes"] else "no",
                "source_line": source_line, "source_line_sha256": sha(source_line.encode()),
                "review_status": "pending",
            }
            matches.append(safe_record(row, ("matched_token", "argument_source", "argument_tokens", "source_line")))
        notes.extend({"file": name, "layer": layer, "printed_page": page, **item, "review_status": "pending"} for item in modes["notes"])
        source_rows.append({"file": name, "bytes": len(data), "sha256": sha(data)})
    matches.sort(key=lambda row: (PAGE_RANK[row["printed_page"]], LAYER_RANK[row["layer"]],
                                  row["line"], row["column"], FAMILY_RANK[row["family"]]))
    for number, row in enumerate(matches, 1):
        row["match_id"] = f"N{number:06d}"
    nested_fonts.sort(key=lambda row: (PAGE_RANK[row["printed_page"]], LAYER_RANK[row["layer"]], row["outer_line"], row["outer_column"], row["inner_line"], row["inner_column"]))
    duplicate_anchors.sort(key=lambda row: (PAGE_RANK[row["printed_page"]], LAYER_RANK[row["layer"]], row["first_line"], row["first_column"]))
    for number, row in enumerate(nested_fonts, 1):
        row["candidate_id"] = f"F{number:06d}"
    for number, row in enumerate(duplicate_anchors, 1):
        row["group_id"] = f"A{number:06d}"
    counts = Counter((row["printed_page"], row["layer"], row["family"], row["match_category"]) for row in matches)
    matrix, family_matrix, family_totals = [], [], []
    categories = ("source", "comment", "reference")
    for page in PAGES:
        total = {"printed_page": page, "review_status": "pending"}
        for layer in LAYER_RANK:
            for category in categories:
                count = sum(counts[page, layer, pattern["family"], category] for pattern in PATTERNS)
                total[f"{layer}_{category}_matches"] = count
                total[f"{layer}_{category}_zero_or_nonzero"] = "nonzero" if count else "zero"
            total[f"{layer}_nested_font_pairs"] = sum(row["printed_page"] == page and row["layer"] == layer and row["scope"] == "source" for row in nested_fonts)
            total[f"{layer}_duplicate_anchor_groups"] = sum(row["printed_page"] == page and row["layer"] == layer and row["scope"] == "source" for row in duplicate_anchors)
        matrix.append(total)
        for pattern in PATTERNS:
            entry = {"printed_page": page, "family": pattern["family"], "review_status": "pending"}
            for layer in LAYER_RANK:
                for category in categories:
                    entry[f"{layer}_{category}_matches"] = counts[page, layer, pattern["family"], category]
            family_matrix.append(entry)
    for pattern in PATTERNS:
        for layer in LAYER_RANK:
            family_totals.append({"family": pattern["family"], "literal": pattern["literal"], "layer": layer,
                                  **{category + "_matches": sum(counts[page, layer, pattern["family"], category] for page in PAGES) for category in categories},
                                  "review_status": "pending"})
    matrix_fields = ["printed_page"] + [f"{layer}_{category}_{suffix}" for layer in LAYER_RANK for category in categories for suffix in ("matches", "zero_or_nonzero")] + [f"{layer}_{kind}" for layer in LAYER_RANK for kind in ("nested_font_pairs", "duplicate_anchor_groups")] + ["review_status"]
    family_matrix_fields = ["printed_page", "family"] + [f"{layer}_{category}_matches" for layer in LAYER_RANK for category in categories] + ["review_status"]
    tables = {
        "ALL_MATCHES.tsv": (MATCH_FIELDS, matches),
        "SOURCE_CANDIDATES.tsv": (MATCH_FIELDS, [row for row in matches if row["match_category"] == "source"]),
        "COMMENT_MATCHES.tsv": (MATCH_FIELDS, [row for row in matches if row["match_category"] == "comment"]),
        "REFERENCE_MATCHES.tsv": (MATCH_FIELDS, [row for row in matches if row["match_category"] == "reference"]),
        "PAGE_LAYER_MATRIX.tsv": (matrix_fields, matrix),
        "FAMILY_PAGE_LAYER_MATRIX.tsv": (family_matrix_fields, family_matrix),
        "FAMILY_COUNTS.tsv": (["family", "literal", "layer", "source_matches", "comment_matches", "reference_matches", "review_status"], family_totals),
        "SOURCE_HASHES.tsv": (["file", "bytes", "sha256"], source_rows),
        "LEXICAL_NOTES.tsv": (["file", "layer", "printed_page", "line", "column", "kind", "syntax_name", "detail", "review_status"], notes),
        "PATTERNS.tsv": (["family", "kind", "literal", "pattern", "leading_control"], PATTERNS),
        "NESTED_FONT_CANDIDATES.tsv": (["candidate_id", "file", "layer", "printed_page", "scope", "command", "outer_line", "outer_column", "inner_line", "inner_column", "nesting_position", "outer_argument_kind", "outer_argument_sha256", "review_status"], nested_fonts),
        "DUPLICATE_LAYER_TARGETS.tsv": (["group_id", "file", "layer", "printed_page", "scope", "anchor", "anchor_sha256", "simple_literal_identifier", "occurrences", "locations", "first_line", "first_column", "privacy_filtered_fields", "review_status"], duplicate_anchors),
        "LAYER_TARGET_PARSE_NOTES.tsv": (["file", "layer", "printed_page", "scope", "line", "column", "argument_kind", "review_status"], anchor_notes),
    }
    summary = {"source_files": len(snapshot), "printed_pages_in_matrix": len(matrix),
               "pattern_families": len(PATTERNS), "all_matches": len(matches),
               **{category + "_matches": sum(row["match_category"] == category for row in matches) for category in categories},
               "match_rows_with_privacy_filtering": sum(bool(row["privacy_filtered_fields"]) for row in matches),
               "lexical_notes": len(notes),
               "nested_font_source_pairs": sum(row["scope"] == "source" for row in nested_fonts),
               "nested_font_comment_pairs": sum(row["scope"] == "comment" for row in nested_fonts),
               "duplicate_source_anchor_groups": sum(row["scope"] == "source" for row in duplicate_anchors),
               "duplicate_comment_anchor_groups": sum(row["scope"] == "comment" for row in duplicate_anchors),
               "layer_target_parse_notes": len(anchor_notes)}
    return tables, summary


def ledger_groups(data: bytes) -> tuple[dict, dict]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), delimiter="\t")
    if reader.fieldnames != FIELDS:
        raise ValueError("The correction ledger does not have the required column schema and order.")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("The ledger contains a malformed TSV record.")
    by_pair = defaultdict(list)
    for position, row in enumerate(rows, 1):
        page = row["printed_page"]
        if page and (not page.isdigit() or int(page) not in PAGE_RANK):
            raise ValueError("A ledger printed-page locator is outside the required order; no page is inferred.")
        by_pair[row["old"], row["new"]].append((position, row))
    selected = [(pair, entries) for pair, entries in by_pair.items()
                if len({row["printed_page"] for _, row in entries if row["printed_page"]}) >= 2]
    selected.sort(key=lambda item: (min(PAGE_RANK[int(row["printed_page"])] for _, row in item[1] if row["printed_page"]), item[1][0][0]))
    groups, members, page_counts = [], [], []
    for number, ((old, new), entries) in enumerate(selected, 1):
        group_id = f"D{number:06d}"
        pages = sorted({int(row["printed_page"]) for _, row in entries if row["printed_page"]}, key=PAGE_RANK.get)
        groups.append(safe_record({
            "group_id": group_id, "pair_sha256": sha(json.dumps([old, new], ensure_ascii=False, separators=(",", ":")).encode()),
            "ledger_rows": len(entries), "distinct_printed_pages": len(pages),
            "printed_pages": ",".join(map(str, pages)), "unpaged_rows": sum(not row["printed_page"] for _, row in entries),
            "layers": ",".join(sorted({row["layer"] for _, row in entries})),
            "kinds": "; ".join(sorted({row["kind"] for _, row in entries})),
            "old": old, "new": new, "old_empty": "yes" if old == "" else "no",
            "new_empty": "yes" if new == "" else "no", "review_status": "pending",
        }, ("old", "new", "layers", "kinds")))
        counts = Counter()
        for position, row in entries:
            counts[row["printed_page"], row["layer"]] += 1
            members.append(safe_record({
                "group_id": group_id, "ledger_record": position, "file": row["file"], "layer": row["layer"],
                "printed_page": row["printed_page"], "line": row["line"], "kind": row["kind"],
                "row_sha256": sha(json.dumps([row[field] for field in FIELDS], ensure_ascii=False, separators=(",", ":")).encode()),
                "review_status": "pending",
            }, ("file", "layer", "line", "kind")))
        for (page, layer), count in sorted(counts.items(), key=lambda item: (PAGE_RANK[int(item[0][0])] if item[0][0] else len(PAGES), item[0][1])):
            page_counts.append({"group_id": group_id, "printed_page": page, "layer": layer, "ledger_rows": count, "review_status": "pending"})
    tables = {
        "LEDGER_PAIR_GROUPS.tsv": (["group_id", "pair_sha256", "ledger_rows", "distinct_printed_pages", "printed_pages", "unpaged_rows", "layers", "kinds", "old", "new", "old_empty", "new_empty", "privacy_filtered_fields", "review_status"], groups),
        "LEDGER_PAIR_MEMBERS.tsv": (["group_id", "ledger_record", "file", "layer", "printed_page", "line", "kind", "row_sha256", "privacy_filtered_fields", "review_status"], members),
        "LEDGER_PAIR_PAGE_COUNTS.tsv": (["group_id", "printed_page", "layer", "ledger_rows", "review_status"], page_counts),
    }
    return tables, {"ledger_rows": len(rows), "cross_page_exact_pair_groups": len(groups),
                    "ledger_rows_in_cross_page_groups": len(members),
                    "ledger_group_rows_with_privacy_filtering": sum(bool(row["privacy_filtered_fields"]) for row in groups)}


def recheck(root: Path, snapshot: dict[str, bytes], ledger: bytes) -> None:
    paths = source_paths(root)
    if set(paths) != set(snapshot):
        raise RuntimeError("The eligible page-file set changed; no report was installed.")
    if any(file_hash(path) != (len(snapshot[name]), sha(snapshot[name])) for name, path in paths.items()):
        raise RuntimeError("A page source changed after the snapshot; no report was installed.")
    if file_hash(root / "CORRECTIONS.tsv") != (len(ledger), sha(ledger)):
        raise RuntimeError("The correction ledger changed after the snapshot; no report was installed.")


def run(args) -> dict:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside a protected context folder.")
    if args.output.is_absolute() or "interim" not in args.output.name.casefold():
        raise ValueError("Use a new relative output name explicitly containing interim.")
    require_safe_name(args.output.as_posix())
    if any(part.casefold() in BLOCKED_DIRS for part in args.output.parts):
        raise ValueError("The output cannot be inside a protected context folder.")
    cursor = root
    for part in args.output.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("The output path must not pass through a symbolic link.")
    output = (root / args.output).resolve()
    if output == root or root not in output.parents or any(output == root / name or root / name in output.parents for name in ("sources", "pdf")):
        raise ValueError("The output must be inside the delivery tree and outside sources/PDFs.")
    if output.exists():
        raise ValueError("The interim output already exists; no snapshot is overwritten.")
    paths = source_paths(root)
    expected = {f"sources/{layer}/p{page}.tex" for layer in LAYER_RANK for page in PAGES}
    if set(paths) != expected:
        raise ValueError("This complete-coverage snapshot requires all 102 page files in each of the three layers.")
    snapshot = {name: read_snapshot(path) for name, path in paths.items()}
    ledger_path = root / "CORRECTIONS.tsv"
    if ledger_path.is_symlink():
        raise ValueError("The correction ledger must be a regular file.")
    ledger = read_snapshot(ledger_path)
    tables, summary = source_inventory(snapshot)
    duplicate_tables, duplicate_summary = ledger_groups(ledger)
    tables.update(duplicate_tables)
    summary.update(duplicate_summary)
    tables["INPUT_HASHES.tsv"] = (["role", "file", "bytes", "sha256"], [
        {"role": "correction-ledger snapshot", "file": "CORRECTIONS.tsv", "bytes": len(ledger), "sha256": sha(ledger)},
        {"role": "source inventory", "file": "SOURCE_HASHES.tsv logical rows", "bytes": "", "sha256": sha(json.dumps(tables["SOURCE_HASHES.tsv"][1], sort_keys=True, separators=(",", ":")).encode())},
        {"role": "exact matching rules", "file": "PATTERNS.tsv", "bytes": "", "sha256": sha(tsv_bytes(*tables["PATTERNS.tsv"]))},
    ])
    report = ["# Interim notation and ledger recurrence inventory", "", "Generated " + utc() + ".", "",
              "All review statuses are pending. This report inventories lexical/literal occurrences and exact ledger pairs. It makes no content, mathematical, translation or correction-coverage judgment. No source, ledger or review state was changed, and no build or scan reading was performed.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items())
    report.extend(["", "## Source occurrence tables", "",
                   "SOURCE_CANDIDATES.tsv contains recognized source control-word tokens and literal phrases. COMMENT_MATCHES.tsv contains exact bounded spellings in lexical comments. REFERENCE_MATCHES.tsv preserves raw spellings that are not recognized source tokens, including escaped/literal material. ALL_MATCHES.tsv retains all three categories. Every row contains exact matched text, a relative file and printed-page locator, surrounding source line(s), and pending review status.", "",
                   "Control words use ASCII-letter token boundaries and cannot match longer words. Matching is case-sensitive. French phrases have literal single spaces and word boundaries. PATTERNS.tsv records all 22 exact expressions. Comments are located by the existing lexer, which consumes escaped control symbols and skips documented verbatim bodies. This is a lexical model, not TeX execution.", "",
                   "For mathcal and mathbb, argument_source includes the next explicit braced group or single token, and argument_tokens contains the group payload or that single token. No expansion or semantic classification occurs. Known declaration/reference tokens do not receive an inferred argument. Comment arguments are bounded by their comment line. Lexical text/math/unknown context comes from the existing font-context scanner; unknown, custom or cross-input behavior still requires manual assessment.", "",
                   "PAGE_LAYER_MATRIX.tsv explicitly covers all 102 pages and all three layers, with separate source/comment/reference counts and zero/nonzero values. FAMILY_PAGE_LAYER_MATRIX.tsv supplies the complete page-by-family-by-layer grid, including numeric zeros. A zero means only no match under these rules; it is not a source-reading or correction-coverage verdict.", "",
                   "Source context spans the match and any captured font argument, preserving complete surrounding lines except the final line ending. Privacy filtering, if needed, changes only derived report fields and is explicitly marked; hashes bind the original unfiltered arguments/lines. Source files remain unchanged.", "",
                   "## Additional location-only structural candidates", "",
                   "NESTED_FONT_CANDIDATES.tsv lists pairs of identical named font/style tokens when the inner token lies in the next explicit argument of the outer token. The fixed command set is documented in scripts/NOTATION_LEDGER_INVENTORY.md. All containment pairs are listed, not assumed to be independent errors. Source and comment scopes remain distinct; no argument text or surrounding prose is copied into this table.", "",
                   "DUPLICATE_LAYER_TARGETS.tsv groups exactly equal unexpanded braced LayerTarget argument strings within the same page file and scope. It lists the identifier/hash and every line:column location. It does not compare anchors across files, combine comment and source occurrences, expand computed labels or establish a duplicate PDF destination. LAYER_TARGET_PARSE_NOTES.tsv retains locations where no balanced explicit argument was recognized. Every candidate remains pending.", "",
                   "## Exact ledger pairs", "",
                   "LEDGER_PAIR_GROUPS.tsv groups rows by exactly equal decoded old and new values, including whitespace and empty values, without normalization. A group is included only when it occurs on at least two distinct nonempty printed pages. All current ledger rows participate; review-sidecar decisions are not read or inferred. An unpaged row sharing a qualifying pair remains listed but does not create page coverage.", "",
                   "LEDGER_PAIR_MEMBERS.tsv identifies every member by its one-based logical ledger record and source locator, with an exact-row hash. LEDGER_PAIR_PAGE_COUNTS.tsv provides mechanical counts. These tables do not establish that a correction was applied, reviewed, appropriate, missing elsewhere or consistently covered. Every group and member remains pending.", "",
                   "SOURCE_HASHES.tsv and INPUT_HASHES.tsv bind the complete 306-file source snapshot, the ledger and exact patterns. Inputs were rechecked before exclusive installation. Existing reports remain unchanged. Main files, preambles, source ZIPs, scans and protected context folders were not opened by this inventory.", ""])
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads["REPORT.md"] = "\n".join(report).encode()
    payloads["SUMMARY.json"] = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("A generated report has a privacy pattern or inspection blocker; no report was installed.")
    with tempfile.TemporaryDirectory(prefix="notation-ledger-inventory-", dir=root.parent) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        recheck(root, snapshot, ledger)
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
