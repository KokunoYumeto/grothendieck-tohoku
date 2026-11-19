"""Inventory final diplomatic/corrected French differences mechanically.

The only comparison exclusions are proved literal layer-metadata substitutions
in a first-line comment or simple LayerTarget labels. All exclusions are
reported separately. Hunk/ledger associations are literal candidates, never
justifications, image readings, or editorial decisions. No input is modified.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import os

from refresh_check_record import PAGES, LAYERS, load_rows, read_tsv, tsv_data
from final_validate import confidence_annotation, privacy_findings
from privacy_guard import safe_location, scan_bytes
from control_word_inventory import BLOCKED_DIRS, VERBATIM_ENVS, require_safe_name

TARGET = re.compile(r"(?<!\\)\\LayerTarget\{(?P<label>[A-Za-z0-9:._/-]+)\}")
LITERAL_CONTEXT = re.compile(r"\\(?:verb\*?|string|detokenize|noexpand|meaning|unexpanded)\b")
CONTROL_CONTEXT = re.compile(r"\\(?:def|gdef|edef|xdef|let|futurelet|catcode|newcommand|renewcommand|providecommand|DeclareRobustCommand|newenvironment|renewenvironment)\b")
VERBATIM_BEGIN = re.compile(r"\\begin\{(" + "|".join(re.escape(name) for name in sorted(VERBATIM_ENVS | {"filecontents", "filecontents*"}, key=lambda name: (-len(name), name))) + r")\}")
HUNK_FIELDS = [
    "hunk_id", "printed_page", "operation", "dip_file", "fr_file", "dip_start_line", "dip_line_count", "dip_boundary_after_line",
    "fr_start_line", "fr_line_count", "fr_boundary_after_line", "dip_fragment", "fr_fragment",
    "dip_context_before", "dip_context_after", "fr_context_before", "fr_context_after",
    "hunk_sha256", "candidate_correction_ids", "two_sided_candidate_ids", "privacy_filtered_fields", "review_status",
]
MATCH_FIELDS = [
    "hunk_id", "correction_id", "ledger_record", "row_fingerprint", "layer", "kind", "printed_page",
    "match_type", "direction", "literal_relations", "matched_characters", "candidate_only",
]
METADATA_FIELDS = ["printed_page", "metadata_type", "dip_line", "fr_line", "dip_original", "fr_original", "canonical_value", "rule", "proof", "privacy_filtered_fields"]
PAGE_FIELDS = [
    "printed_page", "dip_lines", "fr_lines", "raw_equal", "equal_after_declared_metadata", "hunks",
    "metadata_exclusions", "hunks_with_two_sided_candidates", "hunks_with_one_sided_candidates_only",
    "hunks_without_literal_candidates",
]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def comment_boundary(line: str) -> int:
    for index, character in enumerate(line):
        if character != "%":
            continue
        preceding, cursor = 0, index - 1
        while cursor >= 0 and line[cursor] == "\\":
            preceding += 1
            cursor -= 1
        if preceding % 2 == 0:
            return index
    return len(line)


def replace_span(text: str, first: int, last: int, replacement: str) -> str:
    return text[:first] + replacement + text[last:]


def normalize_header(dip: str, fr: str, page: int, rules: dict) -> tuple[str, str] | None:
    if dip == fr or not dip.lstrip("\ufeff \t").startswith("%") or not fr.lstrip("\ufeff \t").startswith("%"):
        return None
    if "<layer>" in dip or "<layer>" in fr:
        # A literal source occurrence must never collide with a comparison
        # placeholder and hide an actual movement or wording change.
        return None
    # Default proof 1: the same page-file locator, differing only in its folder.
    a, count_a = re.subn(rf"(?<![A-Za-z0-9_])dip/p{page}\.tex(?![A-Za-z0-9_])", f"<layer>/p{page}.tex", dip)
    b, count_b = re.subn(rf"(?<![A-Za-z0-9_])fr/p{page}\.tex(?![A-Za-z0-9_])", f"<layer>/p{page}.tex", fr)
    if count_a and count_a == count_b and a == b:
        return a, "first-line comment: identical page-file locator except dip/fr folder"
    # Default proof 2: a literal, explicitly named Layer field.
    pattern = re.compile(r"^(?P<prefix>\ufeff?[ \t]*%[ \t]*(?:Layer|layer)[ \t]*[:=][ \t]*)(?P<layer>dip|fr)(?=$|[ \t;,.\r\n])")
    match_a, match_b = pattern.search(dip), pattern.search(fr)
    if match_a and match_b and match_a["layer"] == "dip" and match_b["layer"] == "fr":
        a = replace_span(dip, *match_a.span("layer"), "<layer>")
        b = replace_span(fr, *match_b.span("layer"), "<layer>")
        if a == b:
            return a, "first-line comment: identical literal Layer field except dip/fr value"
    # An optional reviewer-supplied rule identifies one layer-label field.
    # Even then, no other byte may differ; a captured page must also agree.
    custom = rules.get("header_rule")
    if custom:
        expression = re.compile(custom["pattern"])
        a_text, b_text = dip.rstrip("\r\n"), fr.rstrip("\r\n")
        match_a, match_b = expression.fullmatch(a_text), expression.fullmatch(b_text)
        if match_a and match_b and match_a["layer"] == custom["dip_value"] and match_b["layer"] == custom["fr_value"]:
            if "page" in expression.groupindex and (match_a["page"] != str(page) or match_b["page"] != str(page)):
                return None
            a = replace_span(dip, *match_a.span("layer"), "<layer>")
            b = replace_span(fr, *match_b.span("layer"), "<layer>")
            if a == b:
                return a, "first-line comment: reviewer-declared layer field; every other byte identical"
    return None


def targets(lines: list[str], layer_token: str) -> list[dict]:
    result, verbatim, brace_depth = [], None, 0
    token = re.compile(r"(?<![A-Za-z0-9])" + re.escape(layer_token) + r"(?![A-Za-z0-9])")
    for line_number, line in enumerate(lines, 1):
        if verbatim:
            if "\\end{" + verbatim + "}" in line:
                if not re.fullmatch(r"\s*\\end\{" + re.escape(verbatim) + r"\}\s*(?:%[^\r\n]*)?[\r\n]*", line):
                    return []
                verbatim = None
            continue
        code = line[:comment_boundary(line)]
        # These controls can reinterpret tokens across physical lines. Rather
        # than attempt to execute arbitrary TeX, retain all target differences
        # on such a page. This also protects a preceding standalone \string.
        if LITERAL_CONTEXT.search(code) or CONTROL_CONTEXT.search(code):
            return []
        begin = VERBATIM_BEGIN.search(code)
        if begin:
            if code[:begin.start()].strip() or "\\end{" + begin.group(1) + "}" in code[begin.end():]:
                return []
            verbatim = begin.group(1)
            continue
        match = TARGET.search(code)
        if match and brace_depth == 0 and not code[:match.start()].strip() and not code[match.end():].strip():
            label = match["label"]
            canonical, count = token.subn("<layer>", label)
            if count:
                result.append({"line": line_number, "start": match.start("label"), "end": match.end("label"),
                               "label": label, "canonical": canonical, "token_count": count, "command": match.group(0)})
        for index, character in enumerate(code):
            if character not in "{}":
                continue
            preceding, cursor = 0, index - 1
            while cursor >= 0 and code[cursor] == "\\":
                preceding += 1
                cursor -= 1
            if preceding % 2 == 0:
                brace_depth += 1 if character == "{" else -1
                if brace_depth < 0:
                    return []
    return result if brace_depth == 0 and verbatim is None else []


def normalize_metadata(dip_lines: list[str], fr_lines: list[str], page: int, rules: dict) -> tuple[list[str], list[str], list[dict]]:
    dip, fr, exclusions = list(dip_lines), list(fr_lines), []
    if dip and fr:
        header = normalize_header(dip[0], fr[0], page, rules)
        if header:
            canonical, rule = header
            exclusions.append({"printed_page": page, "metadata_type": "first-line header comment", "dip_line": 1, "fr_line": 1,
                               "dip_original": dip[0], "fr_original": fr[0], "canonical_value": canonical, "rule": rule,
                               "proof": "Both are first-line percent comments; replacing only the identified layer field yields exact full-line equality, including all other text and line endings."})
            dip[0] = fr[0] = canonical
    tokens = rules.get("layer_tokens", {"dip": "dip", "fr": "fr"})
    a, b = defaultdict(list), defaultdict(list)
    # Literal placeholders elsewhere could otherwise collide with a normalized
    # target line when a target has moved; leave every target visible then.
    safe_marker = not any("<layer>" in line for line in dip_lines + fr_lines)
    for entry in targets(dip_lines, tokens["dip"]) if safe_marker else []:
        a[entry["canonical"]].append(entry)
    for entry in targets(fr_lines, tokens["fr"]) if safe_marker else []:
        b[entry["canonical"]].append(entry)
    replacements_a, replacements_b = defaultdict(list), defaultdict(list)
    for canonical in sorted(set(a) & set(b)):
        if len(a[canonical]) != len(b[canonical]):
            # Unequal multiplicity remains a literal difference for review.
            continue
        for item_a, item_b in zip(a[canonical], b[canonical]):
            if item_a["token_count"] != item_b["token_count"]:
                continue
            replacements_a[item_a["line"]].append((item_a["start"], item_a["end"], canonical))
            replacements_b[item_b["line"]].append((item_b["start"], item_b["end"], canonical))
            exclusions.append({"printed_page": page, "metadata_type": "LayerTarget label", "dip_line": item_a["line"], "fr_line": item_b["line"],
                               "dip_original": item_a["command"], "fr_original": item_b["command"], "canonical_value": canonical,
                               "rule": "standalone outer-level literal LayerTarget labels; declared layer tokens only",
                               "proof": "Canonical non-layer label bytes and token counts agree; matching canonical labels have equal multiplicity. Each command is a standalone invocation outside balanced brace groups and known verbatim contexts; ambiguous literal/control constructs prevent target exclusions. Only label spans are substituted in the comparison copy; command location, surrounding text and source bytes remain unchanged."})
    for virtual, replacements in ((dip, replacements_a), (fr, replacements_b)):
        for line_number, changes in replacements.items():
            for first, last, replacement in sorted(changes, reverse=True):
                virtual[line_number - 1] = replace_span(virtual[line_number - 1], first, last, replacement)
    return dip, fr, exclusions


def relation(value: str, fragment: str) -> tuple[str, int] | None:
    if not value or not fragment:
        return None
    if value in fragment:
        return "ledger fragment is contained in hunk", len(value)
    if fragment in value:
        return "hunk fragment is contained in ledger field", len(fragment)
    return None


def candidates(hunk: dict, entries: list[dict]) -> list[dict]:
    output = []
    dip, fr = hunk["dip_fragment"], hunk["fr_fragment"]
    for entry in entries:
        row = entry["row"]
        old, new = row["old"], row["new"]
        if old == new:
            continue
        relations = {"old→dip": relation(old, dip), "new→fr": relation(new, fr),
                     "new→dip": relation(new, dip), "old→fr": relation(old, fr)}
        if not dip and not old and new:
            relations["old→dip"] = ("both old sides are empty", 0)
        if not fr and not new and old:
            relations["new→fr"] = ("both new sides are empty", 0)
        if not dip and not new and old:
            relations["new→dip"] = ("both reverse-old sides are empty", 0)
        if not fr and not old and new:
            relations["old→fr"] = ("both reverse-new sides are empty", 0)
        present = {key: value for key, value in relations.items() if value is not None}
        # An empty-side agreement alone is not a literal fragment candidate.
        if not any(value[1] > 0 for value in present.values()):
            continue
        forward = "old→dip" in present and "new→fr" in present
        reverse = "new→dip" in present and "old→fr" in present
        match_type = "two-sided" if forward or reverse else "one-sided"
        direction = "forward and reverse" if forward and reverse else "forward" if forward else "reverse" if reverse else "partial only"
        output.append({"hunk_id": hunk["hunk_id"], "correction_id": entry["id"], "ledger_record": entry["ledger_record"],
                       "row_fingerprint": entry["fingerprint"], "layer": row["layer"], "kind": row["kind"], "printed_page": row["printed_page"],
                       "match_type": match_type, "direction": direction,
                       "literal_relations": "; ".join(key + ": " + value[0] for key, value in present.items()),
                       "matched_characters": sum(value[1] for value in present.values()),
                       "candidate_only": "yes; not a justification or coverage verdict"})
    return sorted(output, key=lambda row: (row["match_type"] != "two-sided", row["direction"] != "forward", -row["matched_characters"], row["correction_id"]))


def compare_page(page: int, dip_bytes: bytes, fr_bytes: bytes, entries: list[dict], rules: dict, context: int, all_literal: bool = False) -> tuple[list[dict], list[dict], list[dict], dict]:
    # LF defines source line numbers, including for CRLF inputs. Other Unicode
    # line separators are literal source characters, not physical TeX lines.
    def physical_lines(data):
        text = data.decode("utf-8")
        return re.findall(r"[^\n]*\n|[^\n]+$", text)
    dip_lines, fr_lines = physical_lines(dip_bytes), physical_lines(fr_bytes)
    virtual_dip, virtual_fr, exclusions = (dip_lines, fr_lines, []) if all_literal else normalize_metadata(dip_lines, fr_lines, page, rules)
    matcher = difflib.SequenceMatcher(a=virtual_dip, b=virtual_fr, autojunk=False)
    hunks, matches = [], []
    for operation, a1, a2, b1, b2 in matcher.get_opcodes():
        if operation == "equal":
            continue
        old, new = "".join(dip_lines[a1:a2]), "".join(fr_lines[b1:b2])
        hunk_id = f"D{page}-{len(hunks) + 1:03d}"
        digest = hashlib.sha256(json.dumps([page, operation, a1, a2, b1, b2, old, new], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        hunk = {"hunk_id": hunk_id, "printed_page": page, "operation": operation,
                "dip_file": f"sources/dip/p{page}.tex", "fr_file": f"sources/fr/p{page}.tex",
                "dip_start_line": a1 + 1 if a2 > a1 else "", "dip_line_count": a2 - a1, "dip_boundary_after_line": a1 if a2 == a1 else "",
                "fr_start_line": b1 + 1 if b2 > b1 else "", "fr_line_count": b2 - b1, "fr_boundary_after_line": b1 if b2 == b1 else "",
                "dip_fragment": old, "fr_fragment": new,
                "dip_context_before": "".join(dip_lines[max(0, a1 - context):a1]), "dip_context_after": "".join(dip_lines[a2:a2 + context]),
                "fr_context_before": "".join(fr_lines[max(0, b1 - context):b1]), "fr_context_after": "".join(fr_lines[b2:b2 + context]),
                "hunk_sha256": digest, "candidate_correction_ids": "", "two_sided_candidate_ids": "",
                "review_status": "pending manual review; no decision inferred"}
        found = candidates(hunk, entries)
        hunk["candidate_correction_ids"] = ",".join(row["correction_id"] for row in found)
        hunk["two_sided_candidate_ids"] = ",".join(row["correction_id"] for row in found if row["match_type"] == "two-sided")
        hunks.append(hunk)
        matches.extend(found)
    two_sided = sum(bool(hunk["two_sided_candidate_ids"]) for hunk in hunks)
    no_candidates = sum(not hunk["candidate_correction_ids"] for hunk in hunks)
    summary = {"printed_page": page, "dip_lines": len(dip_lines), "fr_lines": len(fr_lines), "raw_equal": "yes" if dip_bytes == fr_bytes else "no",
               "equal_after_declared_metadata": "yes" if virtual_dip == virtual_fr else "no", "hunks": len(hunks), "metadata_exclusions": len(exclusions),
               "hunks_with_two_sided_candidates": two_sided, "hunks_with_one_sided_candidates_only": len(hunks) - two_sided - no_candidates,
               "hunks_without_literal_candidates": no_candidates}
    return hunks, matches, exclusions, summary


def load_rules(path: Path | None, captured: bytes | None = None) -> dict:
    if path is None:
        return {"layer_tokens": {"dip": "dip", "fr": "fr"}}
    rules = json.loads(captured.decode("utf-8") if captured is not None else path.read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or set(rules) - {"layer_tokens", "header_rule"}:
        raise ValueError("Metadata rules may contain only layer_tokens and header_rule.")
    tokens = rules.setdefault("layer_tokens", {"dip": "dip", "fr": "fr"})
    if not isinstance(tokens, dict) or set(tokens) != {"dip", "fr"} or tokens["dip"] == tokens["fr"] or not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value) for value in tokens.values()):
        raise ValueError("Layer tokens must be two distinct literal identifier tokens.")
    custom = rules.get("header_rule")
    if "header_rule" in rules:
        if not isinstance(custom, dict) or set(custom) != {"pattern", "dip_value", "fr_value"} or not all(isinstance(value, str) for value in custom.values()):
            raise ValueError("A header rule requires pattern, dip_value and fr_value strings.")
        compiled = re.compile(custom["pattern"])
        if "layer" not in compiled.groupindex or custom["dip_value"] == custom["fr_value"]:
            raise ValueError("The header pattern must name one layer field with distinct declared values.")
    if privacy_findings(json.dumps(rules, ensure_ascii=False)):
        raise ValueError("Metadata rules contain a possible absolute path or email address.")
    return rules


def snapshot(path: Path) -> bytes:
    if any(part.casefold() in BLOCKED_DIRS for part in path.absolute().parts) or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("Inventory inputs must not pass through symlinks or protected context folders.")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("An input file changed while being inventoried; retry after editing stops.")
    return data


def captured_table(data: bytes) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t", strict=True)
    fields, rows = reader.fieldnames or [], list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Malformed captured TSV input.")
    return fields, rows


def captured_entries(ledger: bytes, mapping: bytes | None) -> list[dict]:
    # Reuse the existing ledger/map validator against the captured bytes,
    # so a concurrent edit and restoration cannot change what gets parsed.
    with tempfile.TemporaryDirectory(prefix="french-ledger-snapshot-") as temporary:
        root = Path(temporary)
        (root / "CORRECTIONS.tsv").write_bytes(ledger)
        map_path = root / "review-map.tsv" if mapping is not None else None
        if map_path is not None:
            map_path.write_bytes(mapping)
        entries = load_rows(root, map_path)
        if mapping is None:
            for entry in entries:
                if confidence_annotation(entry["row"]["confidence"]) is None:
                    entry["id"] = f"L{entry['ledger_record']:06d}"
        return entries


def bind_current_row_ids(entries: list[dict], path: Path, captured: bytes | None = None) -> list[dict]:
    """Bind identity only; never apply index verdicts or reviewed field values."""
    fields, rows = captured_table(captured) if captured is not None else read_tsv(path)
    required = {"review_id", "ledger_record", "current_ledger_fingerprint"}
    if not required.issubset(fields):
        raise ValueError("The row-ID index lacks its current-record identity columns.")
    current = {entry["ledger_record"]: entry for entry in entries}
    seen_records, seen_ids, bindings = set(), set(), []
    for row in rows:
        if not row["ledger_record"]:
            continue
        review_digits = row["review_id"][1:]
        if (not re.fullmatch(r"[1-9][0-9]*", row["ledger_record"]) or not re.fullmatch(r"R[0-9]{6,}", row["review_id"])
                or not review_digits.strip("0") or (len(review_digits) > 6 and review_digits.startswith("0"))):
            raise ValueError("The row-ID index has an invalid record number or review ID.")
        number, review_id = int(row["ledger_record"]), row["review_id"]
        if number in seen_records or review_id in seen_ids or number not in current:
            raise ValueError("The row-ID index has a duplicate or missing current-record binding.")
        entry = current[number]
        if row["current_ledger_fingerprint"] != entry["fingerprint"]:
            raise ValueError("The row-ID index has a stale current-record fingerprint at record " + str(number))
        if entry["id"].startswith("R") and entry["id"] != review_id:
            raise ValueError("The row-ID index disagrees with an explicit ledger review ID.")
        seen_records.add(number)
        seen_ids.add(review_id)
        bindings.append({"entry": entry, "review_id": review_id})
    if seen_records != set(current):
        raise ValueError("The row-ID index does not bind every current ledger record.")
    # Apply no partial mapping if validation fails, and keep every row/activity
    # field from the current ledger. The index contributes identity only.
    for binding in bindings:
        binding["entry"]["id"] = binding["review_id"]
    return [{"correction_id": entry["id"], "ledger_record": entry["ledger_record"],
             "row_fingerprint": entry["fingerprint"], "id_source": "fingerprint-bound current row-ID index"}
            for entry in entries]


def inventory(args) -> None:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside protected context folders.")
    if args.output.is_absolute():
        raise ValueError("Use a fresh report directory relative to the delivery root.")
    require_safe_name(args.output.as_posix())
    cursor = root
    for part in args.output.parts:
        cursor = cursor / part
        if part.casefold() in BLOCKED_DIRS or cursor.is_symlink():
            raise ValueError("The report path cannot pass through symlinks or protected context folders.")
    interim = bool(getattr(args, "interim", False))
    all_literal = bool(getattr(args, "all_literal", False))
    filter_derived = bool(getattr(args, "privacy_filter_derived", False))
    row_id_index = getattr(args, "row_id_index", None)
    if row_id_index and args.review_map:
        raise ValueError("Use either an export review map or a current row-ID index, not both.")
    input_snapshots = []
    def remember(role, path):
        data = snapshot(path)
        input_snapshots.append((role, path.resolve(), data))
        return data
    progress = remember("ordered page-completion log", root / "progress.log").decode("utf-8")
    if [int(value) for value in re.findall(r"(?m)^page (\d{3}) done\s", progress)] != PAGES:
        raise ValueError("The final French-layer inventory is deferred until all 102 ordered page-completion entries exist.")
    ledger_data = remember("correction ledger", root / "CORRECTIONS.tsv")
    map_data = remember("explicit review export map", args.review_map) if args.review_map else None
    entries = captured_entries(ledger_data, map_data)
    if row_id_index:
        index_data = remember("current row-ID index; identity only", row_id_index)
        id_bindings = bind_current_row_ids(entries, row_id_index, index_data)
    else:
        id_bindings = [{"correction_id": entry["id"], "ledger_record": entry["ledger_record"],
                        "row_fingerprint": entry["fingerprint"], "id_source": "current ledger annotation or explicit export map; otherwise snapshot record"}
                       for entry in entries]
    if args.review_map:
        _, mapping = captured_table(map_data)
        by_record = {entry["ledger_record"]: entry for entry in entries}
        for binding in mapping:
            if not binding["export_record"]:
                continue
            entry = by_record.get(int(binding["export_record"]))
            if entry is None:
                raise ValueError("The supplied review map references a missing current ledger record.")
            annotated = re.findall(r"\bR\d{6,}\b", entry["row"]["confidence"])
            if not binding.get("row_fingerprint") and binding["review_id"] not in annotated:
                raise ValueError("A plain-confidence review map must bind each row by fingerprint; use a fresh reviewed export map or omit the map to retain explicit ledger-record locators.")
    active = [entry for entry in entries if entry["active"]]
    unfinished = sum(bool(re.search(r"first[ -]reading|pending|provisional|not yet", entry["row"]["confidence"], re.I)) for entry in active)
    if unfinished and not interim:
        raise ValueError("The promoted ledger still explicitly marks unfinished second readings.")
    output = (root / args.output).resolve()
    if interim and "interim" not in output.name.lower():
        raise ValueError("An interim inventory requires an explicitly interim-named report directory.")
    if output == root or root not in output.parents or any(output == root / name or (root / name) in output.parents for name in ("sources", "pdf", "second-reading")):
        raise ValueError("Inventory output must be a new directory inside the delivery tree, outside sources, PDFs and review state.")
    if output.exists():
        raise ValueError("The report directory already exists; use a new name to preserve every live report.")
    if args.context_lines < 0:
        raise ValueError("Context-line count cannot be negative.")
    rule_data = remember("explicit metadata rule declarations", args.metadata_rules) if args.metadata_rules else None
    rules = load_rules(args.metadata_rules, rule_data)
    all_hunks, all_matches, all_exclusions, summaries, hashes = [], [], [], [], []
    for page in PAGES:
        dip_path, fr_path = root / "sources/dip" / f"p{page}.tex", root / "sources/fr" / f"p{page}.tex"
        dip, fr = snapshot(dip_path), snapshot(fr_path)
        for tree, data in (("dip", dip), ("fr", fr)):
            hashes.append({"file": f"sources/{tree}/p{page}.tex", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        scoped = [entry for entry in active if entry["row"]["layer"] in args.candidate_layers and (entry["row"]["printed_page"] == str(page) or (not entry["row"]["printed_page"] and entry["row"]["layer"] == "build"))]
        hunks, matches, exclusions, summary = compare_page(page, dip, fr, scoped, rules, args.context_lines, all_literal)
        all_hunks.extend(hunks); all_matches.extend(matches); all_exclusions.extend(exclusions); summaries.append(summary)
    # Verify that the final source state still matches the per-page snapshots.
    for item in hashes:
        if hashlib.sha256(snapshot(root / item["file"])).hexdigest() != item["sha256"]:
            raise RuntimeError("A French source changed during the inventory; no report was installed.")
    input_hashes = []
    for role, path, data in input_snapshots:
        if snapshot(path) != data:
            raise RuntimeError("A ledger, review map, rule or progress input changed during the inventory; no report was installed.")
        filename = path.relative_to(root).as_posix() if root in path.parents else "external-input:" + role.replace(" ", "-")
        input_hashes.append({"role": role, "file": filename, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    totals = {
        "pages_inventoried": len(summaries), "remaining_hunks": len(all_hunks), "metadata_exclusions": len(all_exclusions),
        "explicitly_unfinished_ledger_rows": unfinished,
        "pages_equal_after_declared_metadata": sum(row["equal_after_declared_metadata"] == "yes" for row in summaries),
        "hunks_with_two_sided_candidates": sum(row["hunks_with_two_sided_candidates"] for row in summaries),
        "hunks_with_one_sided_candidates_only": sum(row["hunks_with_one_sided_candidates_only"] for row in summaries),
        "hunks_without_literal_candidates": sum(row["hunks_without_literal_candidates"] for row in summaries),
        "candidate_associations": len(all_matches),
        "ledger_records_bound": len(id_bindings),
        "stable_review_ids_bound": sum(row["correction_id"].startswith("R") for row in id_bindings),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="french-inventory-", dir=output.parent) as temporary:
        prepared = Path(temporary) / "prepared"
        prepared.mkdir()
        privacy_filtering = []
        for filename, fields, rows in [
            ("FRENCH_LAYER_DIFFERENCES.tsv", HUNK_FIELDS, all_hunks), ("FRENCH_LAYER_MATCHES.tsv", MATCH_FIELDS, all_matches),
            ("METADATA_EXCLUSIONS.tsv", METADATA_FIELDS, all_exclusions), ("PAGE_SUMMARY.tsv", PAGE_FIELDS, summaries),
            ("SOURCE_HASHES.tsv", ["file", "bytes", "sha256"], hashes),
            ("INPUT_HASHES.tsv", ["role", "file", "bytes", "sha256"], input_hashes),
            ("LEDGER_ID_BINDINGS.tsv", ["correction_id", "ledger_record", "row_fingerprint", "id_source"], id_bindings),
        ]:
            presentation_rows = []
            for number, row in enumerate(rows, 1):
                presented, changed = dict(row), []
                if filter_derived:
                    for field, original in row.items():
                        if not isinstance(original, str):
                            continue
                        filtered = safe_location(original)
                        if filtered == original:
                            continue
                        presented[field] = filtered
                        changed.append(field)
                        privacy_filtering.append({"report_file": filename,
                                                  "record_locator": safe_location(str(row.get("hunk_id") or row.get("correction_id") or row.get("file") or number)),
                                                  "field": field, "original_value_sha256": hashlib.sha256(original.encode()).hexdigest(),
                                                  "filtered_value_sha256": hashlib.sha256(filtered.encode()).hexdigest(),
                                                  "privacy_pattern_kinds": "; ".join(sorted({kind for _, kind in privacy_findings(original)})),
                                                  "status": "presentation filtering only; original source unchanged"})
                if "privacy_filtered_fields" in fields:
                    presented["privacy_filtered_fields"] = ",".join(changed)
                presentation_rows.append(presented)
            (prepared / filename).write_bytes(tsv_data(fields, presentation_rows))
        (prepared / "PRIVACY_FILTERING.tsv").write_bytes(tsv_data(
            ["report_file", "record_locator", "field", "original_value_sha256", "filtered_value_sha256", "privacy_pattern_kinds", "status"], privacy_filtering))
        totals["privacy_filtered_derived_fields"] = len(privacy_filtering)
        (prepared / "METADATA_RULES.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        settings = {"comparison_mode": "all literal bytes; metadata exclusions disabled" if all_literal else "declared metadata substitutions",
                    "context_lines": args.context_lines, "candidate_layers": args.candidate_layers,
                    "row_id_index_role": "identity only; index verdicts and reviewed field values are not applied" if row_id_index else "not supplied",
                    "derived_excerpt_privacy_policy": "explicit filtering with per-field hashes and markers" if filter_derived else "block installation on any privacy finding; preserve exact excerpts"}
        (prepared / "COMPARISON_SETTINGS.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        heading = "# Interim mechanical French-layer difference inventory" if interim else "# Mechanical French-layer difference inventory"
        stage = ("Interim snapshot after ordered first-pass completion. Final-mode second-reading readiness is not asserted; every hunk remains pending manual review."
                 if interim else "Final-candidate comparison after the explicit pending-confidence gate; this does not infer that a scan rereading occurred.")
        report = [heading, "", "Generated " + utc() + ".", "", stage, "",
                  "| Measure | Count |", "| --- | ---: |"]
        report += [f"| {key.replace('_', ' ')} | {value} |" for key, value in totals.items()]
        report += ["", "## Scope and interpretation", "",
                   "All 102 supplied page pairs were compared in printed order. No source, ledger or existing report was edited. This is a literal comparison inventory, not a scan reading, proof check or verdict on the justification of a French correction.", "",
                   ("All-literal mode is enabled: no header, LayerTarget token or other source byte is normalized or excluded. Every non-equal line opcode is retained, including comments and metadata. METADATA_EXCLUSIONS.tsv is empty by construction."
                    if all_literal else "Only first-line comment layer fields and standalone outer-level literal LayerTarget layer tokens may be excluded. Every exclusion, its original values and its exact structural equality criterion appears in METADATA_EXCLUSIONS.tsv. Unrecognized comments, inline/nested/unmatched/complex targets, changed non-layer label bytes and unequal target multiplicities remain visible as differences. Known literal/control-definition constructs, unbalanced brace groups or existing comparison placeholders disable target exclusions conservatively. This lexical metadata detector is not a complete TeX environment parser; use all-literal mode when every literal difference must remain visible. Comparison substitutions never reach the source files."), "",
                   "FRENCH_LAYER_DIFFERENCES.tsv records original source fragments and context, except any explicitly marked privacy-filtered presentation fields. Each row is one non-equal line opcode. A zero-line side is described by its boundary after a source line; boundary 0 is the start of the file. Hunk IDs identify this snapshot; source and hunk hashes retain its byte-level provenance.", "",
                   ("Explicit derived-excerpt privacy filtering is enabled. Privacy-pattern spans are replaced only in presented report fields, after raw-byte comparison, hunk hashing and literal matching. Each affected field is named in privacy_filtered_fields and listed with original/filtered hashes in PRIVACY_FILTERING.tsv. No hunk is omitted and no source, credit, ledger or review bytes are rewritten. An excerpt marked as filtered must be checked at its original source locator for the complete literal bytes."
                    if filter_derived else "Exact derived excerpts are retained. A privacy-pattern finding blocks report installation; excerpts are never silently rewritten."), "",
                   "FRENCH_LAYER_MATCHES.tsv lists possible ledger associations from literal substring containment in either direction, including insertion/deletion empty-side cases. Matching is case-, accent-, punctuation-, TeX- and whitespace-sensitive. Short signs are retained as candidates. Neither a two-sided match nor multiple candidates establishes that the entire hunk is recorded, justified or mathematically correct. A missing candidate does not establish that a difference is unrecorded.", "",
                   "Candidate scope is the same printed page plus unpaged build rows, limited to the selected ledger layers: " + ", ".join(args.candidate_layers) + ". English candidates, if selected, cannot by themselves justify a corrected-French difference. Withdrawn rows are excluded only when explicitly marked in the supplied ledger annotation or review map.", "",
                   "Ledger locators beginning R are stable second-reading IDs from confidence annotations or a fingerprint-bound review map. A legacy map is accepted only where its ID agrees with the row's explicit confidence annotation. Locators beginning L identify the one-based ledger record in this snapshot only. Candidate records include their content fingerprint. INPUT_HASHES.tsv binds the ledger, progress and any supplied map/rule inputs to the same inventory.", "",
                   ("The supplied current row-ID index contributes stable R IDs only after every current ledger record and fingerprint matches. Its verdicts, withdrawals and amended field values are not applied; literal associations use the current CORRECTIONS.tsv fields and activity annotations. LEDGER_ID_BINDINGS.tsv records the identity mapping, and INPUT_HASHES.tsv binds the exact index bytes."
                    if row_id_index else "LEDGER_ID_BINDINGS.tsv records every current correction locator and fingerprint without changing the ledger or review state."), "",
                   "Every remaining hunk is pending manual review. No CORRECTIONS row, confidence, CHECK_RECORD section, CHECK_EVENTS entry or progress marker is changed by this inventory.", ""]
        (prepared / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
        if any(scan_bytes(item.name, item.read_bytes()) for item in prepared.iterdir()):
            raise RuntimeError("A derived report contains a privacy pattern or inspection blocker; exact excerpts were not rewritten and no report was installed.")
        for item in hashes:
            if hashlib.sha256(snapshot(root / item["file"])).hexdigest() != item["sha256"]:
                raise RuntimeError("A French source changed before report installation; no report was installed.")
        if any(snapshot(path) != data for _, path, data in input_snapshots):
            raise RuntimeError("A ledger, index, map, rule or progress input changed before report installation; no report was installed.")
        # Reserve the new directory exclusively. Each prepared report is then
        # hard-linked without a replacement operation, protecting a concurrent
        # report with the same name as well as every existing report.
        output.mkdir()
        installed = []
        try:
            for item in prepared.iterdir():
                destination = output / item.name
                os.link(item, destination)
                installed.append(destination)
        except BaseException:
            for item in installed:
                item.unlink()
            output.rmdir()
            raise
    print(json.dumps({**totals, "report_directory": output.name, "inventory_stage": "interim" if interim else "final-candidate", "manual_review_status": "pending for every remaining hunk"}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="New report directory relative to the delivery root")
    parser.add_argument("--interim", action="store_true", help="Explicit first-pass snapshot; requires all 102 completion entries and an interim-named output. Final-mode readiness gates remain unchanged")
    parser.add_argument("--review-map", type=Path, help="Matching second-reading export map if needed for stable ledger IDs")
    parser.add_argument("--row-id-index", type=Path, help="Current REVIEW_INDEX identity only; every current record/fingerprint must match and no index verdict is applied")
    parser.add_argument("--all-literal", action="store_true", help="Retain every literal difference, including all header and LayerTarget metadata; disable comparison exclusions")
    parser.add_argument("--privacy-filter-derived", action="store_true", help="Explicitly filter only privacy-pattern spans in derived presentation fields, with field markers and original hashes; original matching and sources are unchanged")
    parser.add_argument("--metadata-rules", type=Path, help="Optional explicit layer-token/header-field declarations; all other bytes must still match")
    parser.add_argument("--context-lines", type=int, default=2)
    parser.add_argument("--candidate-layers", nargs="+", choices=LAYERS, default=LAYERS)
    args = parser.parse_args()
    inventory(args)


if __name__ == "__main__":
    main()
