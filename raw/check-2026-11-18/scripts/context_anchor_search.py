"""Bind primary notes to exact source anchors and deduplicated context rows.

The only page-source content retained is an explicit LayerTarget argument and
its coordinates/hash. No mathematical source text or context verdict is emitted.
Source metadata and the primary's current hashes govern every association.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
import re

from context_search import (compact, install, json_bytes, literal_match,
    notes_context_status, safe_tree, sha, source_inputs, text_value, tsv_bytes)
from control_word_inventory import lex_control_words
from math_literal_groups import promoted_entries
from notation_ledger_inventory import next_argument
from privacy_guard import safe_location


def table(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
    rows = list(reader)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or any(None in row for row in rows):
        raise ValueError("Malformed or duplicate-column TSV input.")
    return rows


def extract_anchors(raw):
    text = raw.decode("utf-8-sig")
    starts = [0] + [match.end() for match in re.finditer("\n", text)]
    lexical = lex_control_words(raw)
    anchors, unresolved = [], []
    for item in lexical["occurrences"]:
        if item["command"] != "LayerTarget":
            continue
        argument = next_argument(text, item["end"])
        if argument["kind"] != "explicit braced group" or not re.fullmatch(r"[A-Za-z0-9:._-]+", argument["tokens"]):
            unresolved.append({"line": item["line"], "column": item["column"], "argument_kind": argument["kind"],
                               "argument_sha256": sha(argument["tokens"].encode())})
            continue
        anchors.append({"anchor": argument["tokens"], "macro_line": item["line"], "macro_column": item["column"],
            "macro_offset": item["offset"], "argument_end_line": bisect_right(starts, argument["end"] - 1),
            "argument_sha256": sha(argument["tokens"].encode())})
    return text, anchors, unresolved


def range_anchors(anchors, first, last):
    within = [anchor for anchor in anchors if first <= anchor["macro_line"] <= last]
    if within:
        return [(anchor, "literal LayerTarget within exact source range") for anchor in within]
    preceding = [anchor for anchor in anchors if anchor["macro_line"] < first]
    return [(preceding[-1], "nearest preceding literal LayerTarget in the same file")] if preceding else []


def single_value(record, name):
    values = [field["value"] for field in record["fields"] if field["name"] == name]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError("Required context identifier field is missing, duplicate or nontextual.")
    return values[0]


def run(args):
    root, context_root, cache, output = args.root.resolve(), args.context_root.resolve(), args.cache.resolve(), args.output.resolve()
    if output.exists() or output == context_root or context_root in output.parents or output == cache or cache in output.parents:
        raise ValueError("Use a fresh output outside supplied context and scratch cache.")
    context_manifest = json.loads((cache / "manifest.json").read_text())
    raw_cache = (cache / "records.jsonl").read_bytes()
    if sha(raw_cache) != context_manifest["cache_records_sha256"]:
        raise ValueError("Scratch context cache hash mismatch.")
    context_bytes = source_inputs(context_root)
    expected_context = {row["relative_file"]: row["sha256"] for row in context_manifest["source_files"]}
    if {name: sha(raw) for name, raw in context_bytes.items()} != expected_context:
        raise ValueError("Context sources differ from the indexed snapshot.")
    context_records = [json.loads(line) for line in raw_cache.decode().splitlines()]
    context_status = notes_context_status(context_root, context_bytes)
    if context_status != context_manifest.get("notes_context_status"):
        raise ValueError("Supplied notes-directory status differs from the index.")
    roles = {"units": args.units_source, "map": args.map_source, "decisions": args.decisions_source, "issues": args.issues_source}
    by_role = {role: [row for row in context_records if row["kind"] == "csv" and row["source_file"] == source] for role, source in roles.items()}
    if any(not rows for rows in by_role.values()):
        raise ValueError("An explicitly selected context relation source has no indexed CSV records.")
    by_id = {role: defaultdict(list) for role in roles}
    for role, records in by_role.items():
        key = "id" if role == "units" else "unit_id"
        for record in records:
            by_id[role][single_value(record, key)].append(record)
    identifiers = set(by_id["units"]) | set(by_id["map"])
    captured, page_cache, source_hashes, anchor_parse_notes = {}, {}, {}, []

    def capture(name, path):
        raw = path.read_bytes()
        captured[name] = (path, raw)
        return raw

    def page(name):
        if not re.fullmatch(r"sources/(?:dip|fr|en)/p[0-9]{3}\.tex", name):
            raise ValueError("A note source is not an authorized relative page filename.")
        path = root / name
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError("A page input escapes the selected delivery tree.")
        if name not in page_cache:
            raw = capture(name, path)
            text, anchors, unresolved = extract_anchors(raw)
            page_cache[name] = (text, anchors, unresolved)
            source_hashes[name] = sha(raw)
            anchor_parse_notes.extend({"source_file": name, "source_sha256": sha(raw), **row} for row in unresolved)
        return page_cache[name]

    notes_raw = capture(args.notes_jsonl.name, args.notes_jsonl)
    op_rows = [json.loads(line) for line in notes_raw.decode("utf-8-sig").splitlines() if line.strip()]
    note_meta, anchor_bindings, extraction_issues = {}, [], []

    def add_note(note_id, family, printed_page, terms, term_origin):
        note = note_meta.setdefault(note_id, {"note_id": note_id, "family": family, "printed_page": str(printed_page),
            "explicit_terms": [], "term_origin": term_origin, "source_items": []})
        if note["family"] != family or note["printed_page"] != str(printed_page):
            raise ValueError("Duplicate note ID has inconsistent family or printed page.")
        for term in terms:
            if not isinstance(term, str) or not term:
                raise ValueError("A supplied query term is empty or nontextual.")
            if term not in note["explicit_terms"]:
                note["explicit_terms"].append(term)
        return note

    def bind(note, source_item, name, first, last, chosen, basis, fragment_hash="", hunk_id="", hunk_hash=""):
        for anchor, locator_basis in chosen:
            anchor_bindings.append({"note_id": note["note_id"], "family": note["family"], "printed_page": note["printed_page"],
                "source_item": source_item, "source_file": name, "source_sha256": source_hashes[name],
                "source_range_start": first, "source_range_end": last, "source_fragment_sha256": fragment_hash,
                "hunk_id": hunk_id, "bound_hunk_sha256": hunk_hash, "binding_basis": basis, "anchor_locator_basis": locator_basis,
                "anchor": anchor["anchor"], "anchor_macro_line": anchor.get("macro_line", ""),
                "anchor_macro_column": anchor.get("macro_column", ""), "anchor_argument_sha256": anchor["argument_sha256"],
                "primary_comparison": "pending primary review"})

    for input_record, row in enumerate(op_rows, 1):
        note = add_note(row["note_id"], "primary OP fragment", row["printed_page"], row["context_search_terms"], "explicit primary context_search_terms")
        note["source_items"].append(row["fragment_id"])
        name, locator = row["source_file"], row["source_lines"]
        text, anchors, unresolved = page(name)
        match = re.fullmatch(r"([0-9]+)(?:[ \t]*[-–—][ \t]*([0-9]+))?", locator)
        if not match:
            raise ValueError("An OP source range is not an exact line or inclusive line pair.")
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        lines = re.findall(r"[^\n]*\n|[^\n]+$", text)
        if first < 1 or last < first or last > len(lines):
            raise ValueError("An OP source range is outside its supplied page file.")
        fragment_hash = sha("".join(lines[first - 1:last]).rstrip("\r\n").encode())
        if fragment_hash != row["source_fragment_sha256"]:
            extraction_issues.append({"note_id": note["note_id"], "source_item": row["fragment_id"], "source_file": name,
                "issue": "current source range does not match the primary fragment hash; no anchor selected",
                "details": compact({"input_record": input_record, "expected": row["source_fragment_sha256"], "observed": fragment_hash})})
            continue
        chosen = range_anchors(anchors, first, last)
        if not chosen:
            extraction_issues.append({"note_id": note["note_id"], "source_item": row["fragment_id"], "source_file": name,
                "issue": "no literal LayerTarget within or preceding the exact range in this file", "details": locator})
        bind(note, row["fragment_id"], name, first, last, chosen, "primary source range and exact fragment hash", fragment_hash)

    slip_rows = []
    if args.slip_inventory:
        if not args.slip_notes_jsonl:
            raise ValueError("Original-slip retrieval requires the primary's explicit slip query inputs.")
        inventory = args.slip_inventory
        slip_rows = table(capture("ORIGINAL_SLIP_ROWS.tsv", inventory / "ORIGINAL_SLIP_ROWS.tsv"))
        slip_queries_raw = capture(args.slip_notes_jsonl.name, args.slip_notes_jsonl)
        slip_queries = [json.loads(line) for line in slip_queries_raw.decode("utf-8-sig").splitlines() if line.strip()]
        query_by_group = {row["note_id"]: row for row in slip_queries}
        if len(query_by_group) != len(slip_queries) or set(query_by_group) != {row["notes_group_id"] for row in slip_rows}:
            raise ValueError("Primary slip-query IDs do not exactly cover the existing inventory groups.")
        group_rows = defaultdict(list)
        for row in slip_rows:
            group_rows[row["notes_group_id"]].append(row)
        for group_id, members in group_rows.items():
            query_input = query_by_group[group_id]
            if set(query_input["correction_ids"]) != {member["correction_id"] for member in members} or set(query_input["source_statements"]) != {member["statement"] for member in members}:
                raise ValueError("A primary slip query has a different exact member or statement set.")
            if {str(query_input["printed_page"])} != {member["printed_page"] for member in members}:
                raise ValueError("A primary slip query has a different printed page.")
        hunks = table(capture("FRENCH_REVIEW_HUNKS.tsv", inventory / "FRENCH_REVIEW_HUNKS.tsv"))
        refs = table(capture("FRENCH_HUNK_CORRECTION_REFERENCES.tsv", inventory / "FRENCH_HUNK_CORRECTION_REFERENCES.tsv"))
        current = {entry["id"]: entry for entry in promoted_entries(capture("CORRECTIONS.tsv", root / "CORRECTIONS.tsv"))}
        hunk_by_id = {row["hunk_id"]: row for row in hunks}
        refs_by_id = defaultdict(list)
        for ref in refs:
            refs_by_id[ref["correction_id"]].append(ref)
        for row in slip_rows:
            rid, statement, name = row["correction_id"], row["statement"], row["file"]
            entry = current.get(rid)
            if entry is None or not entry["active"] or entry["fingerprint"] != row["row_fingerprint"] or entry["row"]["kind"] != "misprint of the original":
                raise ValueError("An original-slip inventory member has a stale or inactive ledger binding.")
            query_input = query_by_group[row["notes_group_id"]]
            note = add_note(row["notes_group_id"], "pending original-slip group", row["printed_page"], query_input["context_search_terms"], "explicit primary ORIGINAL_SLIP_NOTE_INPUTS.context_search_terms")
            note["source_items"].append(rid)
            text, anchors, unresolved = page(name)
            chosen = []
            direct = [statement] if statement in identifiers else []
            if not direct and re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", statement):
                candidates = sorted(identifier for identifier in identifiers if identifier.rsplit(":", 1)[-1] == statement)
                supported = [identifier for identifier in candidates if any(anchor["anchor"] == identifier or anchor["anchor"].startswith(identifier + ":") for anchor in anchors)]
                direct = supported or candidates
                basis = "exact numeric heading suffix; same-file anchor prefix" if supported else "exact numeric heading suffix; no same-file anchor prefix available"
            else:
                basis = "exact ledger statement equals context identifier"
            if direct:
                for identifier in direct:
                    exact = [anchor for anchor in anchors if anchor["anchor"] == identifier]
                    anchor = exact[0] if exact else {"anchor": identifier, "argument_sha256": sha(identifier.encode())}
                    chosen.append((anchor, "exact literal statement identifier"))
                bind(note, rid, name, "", "", chosen, basis)
                if len(direct) > 1:
                    extraction_issues.append({"note_id": note["note_id"], "source_item": rid, "source_file": name,
                        "issue": "multiple exact numeric identifier candidates retained without choosing meaning", "details": compact(direct)})
                continue
            linked = [ref for ref in refs_by_id[rid] if ref["ledger_file"] == name and ref["row_fingerprint"] == row["row_fingerprint"]]
            used_hunk = False
            for ref in linked:
                hunk = hunk_by_id[ref["hunk_id"]]
                if hunk["fr_file"] != name or hunk["hunk_sha256"] != ref["hunk_sha256"]:
                    continue
                first, count = int(hunk["fr_start_line"] or 0), int(hunk["fr_line_count"])
                if count:
                    last = first + count - 1
                    selected_text = "".join(re.findall(r"[^\n]*\n|[^\n]+$", text)[first - 1:last])
                    if selected_text != hunk["fr_fragment"]:
                        raise ValueError("A primary-referenced French hunk is not exact in current source lines.")
                else:
                    first = int(hunk["fr_boundary_after_line"]) + 1
                    last = first - 1
                    selected_text = ""
                chosen = range_anchors(anchors, first, last)
                bind(note, rid, name, first, last, chosen, "existing primary French-hunk reference and exact current fragment", sha(selected_text.encode()), hunk["hunk_id"], hunk["hunk_sha256"])
                if not chosen:
                    extraction_issues.append({"note_id": note["note_id"], "source_item": rid, "source_file": name,
                        "issue": "primary-bound French hunk has no within-range or same-file preceding anchor", "details": hunk["hunk_id"]})
                used_hunk = True
            if used_hunk:
                continue
            line_match = re.fullmatch(r"([0-9]+)(?:[ \t]*[-–—][ \t]*([0-9]+))?", row["line"])
            if line_match:
                first, last = int(line_match.group(1)), int(line_match.group(2) or line_match.group(1))
                chosen = range_anchors(anchors, first, last)
                bind(note, rid, name, first, last, chosen, "exact numeric ledger source-line locator")
            elif row["new"]:
                positions = [match.start() for match in re.finditer(re.escape(row["new"]), text)]
                distinct = {}
                for position in positions:
                    first = text.count("\n", 0, position) + 1
                    last = text.count("\n", 0, position + len(row["new"]) - 1) + 1
                    preceding = [anchor for anchor in anchors if anchor["macro_offset"] <= position]
                    nearby = [(preceding[-1], "nearest preceding literal LayerTarget at the exact character offset")] if preceding else []
                    for anchor, rule in nearby:
                        distinct[(anchor["anchor"], anchor["macro_line"], first, last)] = (anchor, rule)
                for (_, _, first, last), chosen_anchor in distinct.items():
                    bind(note, rid, name, first, last, [chosen_anchor], "exact current ledger-new literal occurrence; no semantic choice among repeats")
                chosen = list(distinct.values())
                if len(positions) > 1:
                    extraction_issues.append({"note_id": note["note_id"], "source_item": rid, "source_file": name,
                        "issue": "multiple exact ledger-new occurrences retained", "details": str(len(positions))})
            if not chosen:
                extraction_issues.append({"note_id": note["note_id"], "source_item": rid, "source_file": name,
                    "issue": "no exact statement, primary-hunk or current literal source locator resolved", "details": "No anchor or context relation inferred."})

    selected_records, joins, note_anchors = {}, [], defaultdict(set)
    for binding in anchor_bindings:
        note_anchors[binding["note_id"]].add(binding["anchor"])
    for note_id, anchors in note_anchors.items():
        for anchor in sorted(anchors):
            direct_records = [record for role in ("units", "map") for record in by_id[role][anchor]]
            parents = {single_value(record, "parent_id") for record in direct_records if single_value(record, "parent_id")}
            selected_ids = [(anchor, "direct exact anchor identity")] + [(parent, "one declared parent_id of a direct identity") for parent in sorted(parents) if parent != anchor]
            for unit_id, basis in selected_ids:
                for role in roles:
                    for record in by_id[role][unit_id]:
                        selected_records[record["record_id"]] = record
                        joins.append({"note_id": note_id, "family": note_meta[note_id]["family"], "anchor": anchor,
                            "selected_unit_id": unit_id, "join_basis": basis, "context_role": role,
                            **{key: record[key] for key in ("record_id", "source_file", "source_sha256", "logical_record", "physical_line_start", "physical_line_end")},
                            "join_field": "id" if role == "units" else "unit_id", "primary_comparison": "pending primary review"})
            if not direct_records:
                extraction_issues.append({"note_id": note_id, "source_item": "", "source_file": "",
                    "issue": "exact source anchor has no units/map identity match", "details": anchor})
    unique_joins = {compact(row): row for row in joins}
    joins = sorted(unique_joins.values(), key=lambda row: (row["note_id"], row["anchor"], row["selected_unit_id"], row["context_role"], row["logical_record"]))
    review_records, flat_context = [], []
    for record in sorted(selected_records.values(), key=lambda row: (row["source_file"], row["logical_record"])):
        returned = {key: value for key, value in record.items() if key != "fields"}
        returned["fields"] = []
        for value in record["fields"]:
            raw = text_value(value["value"])
            masked = safe_location(raw)
            field = {"position": value["position"], "name": value["name"], "value": masked,
                     "value_sha256": value["value_sha256"], "privacy_masked": masked != raw}
            returned["fields"].append(field)
            flat_context.append({key: record[key] for key in ("record_id", "source_file", "source_sha256", "logical_record", "physical_line_start", "physical_line_end")}
                | {"field_position": value["position"], "field_name": value["name"], "value": masked,
                   "value_sha256": value["value_sha256"], "privacy_masked": masked != raw})
        returned["primary_comparison"] = "pending primary review"
        review_records.append(safe_tree(returned))
    keyword_logs = []
    fields_by_source = defaultdict(list)
    for record in context_records:
        fields_by_source[record["source_file"]].append([text_value(field["value"]) for field in record["fields"]])
    summaries = []
    for note_id, note in note_meta.items():
        note_joins = [row for row in joins if row["note_id"] == note_id]
        summaries.append({**note, "source_items": compact(note["source_items"]), "explicit_terms": compact(note["explicit_terms"]),
            "source_anchor_count": len(note_anchors[note_id]), "context_record_count": len({row["record_id"] for row in note_joins}),
            "join_count": len(note_joins), "extraction_issues": sum(row["note_id"] == note_id for row in extraction_issues),
            "primary_comparison": "pending primary review"})
        for term in note["explicit_terms"]:
            for source_name in expected_context:
                count = sum(any(literal_match(value, term) for value in fields) for fields in fields_by_source[source_name])
                keyword_logs.append({"note_id": note_id, "family": note["family"], "term": term,
                    "term_origin": note["term_origin"], "source_file": source_name, "source_sha256": expected_context[source_name],
                    "matching_records": count, "case_sensitive": False, "scope": "literal term anywhere within an indexed record; no semantic inference"})
    for name, (path, raw) in captured.items():
        if name != args.notes_jsonl.name and path.read_bytes() != raw:
            raise ValueError("A bound source or ledger input changed during extraction.")
    if source_inputs(context_root) != context_bytes:
        raise ValueError("Supplied context changed during exact-anchor retrieval.")
    summary = {"schema": "exact-note-context-anchors-v1", "OP_input_records": len(op_rows),
        "OP_notes": sum(row["family"] == "primary OP fragment" for row in note_meta.values()),
        "original_slip_rows": len(slip_rows), "original_slip_groups": sum(row["family"] == "pending original-slip group" for row in note_meta.values()),
        "source_anchor_bindings": len(anchor_bindings), "distinct_context_records": len(review_records),
        "context_record_counts_by_source": dict(Counter(row["source_file"] for row in review_records)),
        "note_context_bindings": len(joins), "keyword_log_rows": len(keyword_logs),
        "notes_without_any_anchor": sum(not note_anchors[note_id] for note_id in note_meta),
        "notes_without_joined_context": sum(not any(row["note_id"] == note_id for row in joins) for note_id in note_meta),
        "extraction_issue_rows": len(extraction_issues), "anchor_parse_note_rows": len(anchor_parse_notes), "privacy_masked_context_fields": sum(row["privacy_masked"] for row in flat_context),
        "notes_input_sha256": sha(notes_raw), "notes_input_unchanged_at_completion": args.notes_jsonl.read_bytes() == notes_raw,
        "context_cache_sha256": context_manifest["cache_records_sha256"], "notes_context_status": context_status,
        "join_rule": "Exact units.id and map.unit_id, plus one parent_id level from those direct records, then exact decisions/issues.unit_id; no descendants or semantic expansion.",
        "keyword_rule": "Every explicit primary OP and original-slip query term is logged against all indexed sources; no additional terms are invented, and keywords do not select or classify joined content.",
        "primary_comparison": "pending primary review"}
    anchor_fields = ["note_id", "family", "printed_page", "source_item", "source_file", "source_sha256", "source_range_start", "source_range_end", "source_fragment_sha256", "hunk_id", "bound_hunk_sha256", "binding_basis", "anchor_locator_basis", "anchor", "anchor_macro_line", "anchor_macro_column", "anchor_argument_sha256", "primary_comparison"]
    issue_fields = ["note_id", "source_item", "source_file", "issue", "details"]
    payloads = {"SUMMARY.json": json_bytes(safe_tree(summary)),
        "SOURCE_ANCHOR_BINDINGS.tsv": tsv_bytes(anchor_fields, safe_tree(anchor_bindings)),
        "NOTE_SUMMARY.tsv": tsv_bytes(list(summaries[0]), safe_tree(summaries)),
        "NOTE_CONTEXT_BINDINGS.tsv": tsv_bytes(list(joins[0]) if joins else ["note_id", "record_id"], safe_tree(joins)),
        "CONTEXT_RECORDS.jsonl": ("\n".join(compact(row) for row in review_records) + "\n").encode(),
        "CONTEXT_FIELDS.tsv": tsv_bytes(list(flat_context[0]) if flat_context else ["record_id", "field_name", "value"], safe_tree(flat_context)),
        "KEYWORD_QUERY_LOG.tsv": tsv_bytes(list(keyword_logs[0]) if keyword_logs else ["note_id", "term", "matching_records"], safe_tree(keyword_logs)),
        "EXTRACTION_ISSUES.tsv": tsv_bytes(issue_fields, safe_tree(extraction_issues)),
        "ANCHOR_PARSE_NOTES.tsv": tsv_bytes(["source_file", "source_sha256", "line", "column", "argument_kind", "argument_sha256"], safe_tree(anchor_parse_notes)),
        "SOURCE_HASHES.tsv": tsv_bytes(["file", "sha256"], [{"file": name, "sha256": digest} for name, digest in sorted(source_hashes.items())]),
        "INPUT_HASHES.tsv": tsv_bytes(["input", "bytes", "sha256"], [{"input": name, "bytes": len(raw), "sha256": sha(raw)} for name, (_, raw) in captured.items()]),
        "CONTEXT_SOURCE_HASHES.tsv": tsv_bytes(["file", "sha256"], [{"file": name, "sha256": digest} for name, digest in expected_context.items()]),
        "REPORT.md": ("# Exact source-anchor context joins\n\n"
            "OP notes are bound to their exact current source ranges and primary fragment hashes. Only literal LayerTarget identifiers are extracted; if the range has none, the last preceding identifier in the same file is used and labelled. Comment/verbatim bodies are skipped lexically, no macros are expanded, and no source mathematical text is reproduced.\n\n"
            "Original-slip groups retain their inventory group IDs and current ledger fingerprints. Exact statement identifiers or pure numeric heading suffixes are used first. Otherwise existing primary French-hunk references provide exact current source ranges; explicit numeric ledger lines or exact current ledger-new literal occurrences provide fallback locators. Ambiguous or unresolved associations remain visible. No reading or correction judgment is added.\n\n"
            "The relational join selects exact units.id/map.unit_id matches, one declared parent_id level, and decisions/issues with exactly equal selected unit_id. It does not traverse descendants or interpret source intervals, keywords, dispositions or rationales. CONTEXT_RECORDS and CONTEXT_FIELDS contain each selected source record once, preserving every field with privacy masking and original-value hashes. NOTE_CONTEXT_BINDINGS explains each selection.\n\n"
            "KEYWORD_QUERY_LOG retains actual literal term counts across all authorized indexed sources for every note. Both OP and original-slip terms are exactly supplied by the primary; no terms are added. Keyword results do not select joined context or establish a relation. The notes directory remains absent with its exact README locator recorded. All substantive comparisons remain pending primary review.\n").encode()}
    install(output, payloads)
    return {key: summary[key] for key in ("OP_input_records", "original_slip_rows", "original_slip_groups", "distinct_context_records", "note_context_bindings", "notes_without_any_anchor", "notes_without_joined_context", "extraction_issue_rows", "privacy_masked_context_fields", "notes_input_unchanged_at_completion")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--context-root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--notes-jsonl", type=Path, required=True)
    parser.add_argument("--slip-inventory", type=Path)
    parser.add_argument("--slip-notes-jsonl", type=Path)
    parser.add_argument("--units-source", default="stacks/tohoku_r71/units.csv")
    parser.add_argument("--map-source", default="stacks/tohoku_r71/map.csv")
    parser.add_argument("--decisions-source", default="stacks/tohoku_r71/dec.csv")
    parser.add_argument("--issues-source", default="stacks/tohoku_r71/issues.csv")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (ValueError, OSError, UnicodeError, csv.Error) as exc:
        parser.exit(2, safe_location(type(exc).__name__ + ": " + str(exc)) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
