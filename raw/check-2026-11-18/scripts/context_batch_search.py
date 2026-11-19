"""Retrieve explicit primary note queries without making context judgments.

Only note_id, printed_page, context_search_terms and optional fragment_id are
used from the supplied notes JSONL. Keyword and structural page-window results
remain separate; all returned comparisons are pending primary review.
"""

from __future__ import annotations

import argparse
from collections import Counter
import fnmatch
import json
from pathlib import Path
import re

from context_search import (compact, install, json_bytes, notes_context_status,
    safe_tree, select_record, sha, source_inputs, text_value, tsv_bytes)
from privacy_guard import safe_location


def read_queries(raw):
    notes = {}
    logical = 0
    for physical_line, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        logical += 1
        row = json.loads(line)
        note_id = row.get("note_id")
        page = row.get("printed_page")
        terms = row.get("context_search_terms")
        if not isinstance(note_id, str) or not note_id or not isinstance(terms, list) or not terms:
            raise ValueError("Each input record needs a note ID and explicit nonempty search-term list.")
        if not all(isinstance(term, str) and term.strip() for term in terms):
            raise ValueError("A supplied search term is empty or is not text.")
        if not isinstance(page, (str, int)) or not re.fullmatch(r"[0-9]+", str(page)):
            raise ValueError("Each input printed page must be an explicit integer token.")
        page = str(page)
        if note_id in notes and notes[note_id]["printed_page"] != page:
            raise ValueError("The same note ID has inconsistent supplied printed pages.")
        note = notes.setdefault(note_id, {"note_id": note_id, "printed_page": page,
            "context_search_terms": [], "input_records": []})
        for term in terms:
            if term not in note["context_search_terms"]:
                note["context_search_terms"].append(term)
        note["input_records"].append({"logical_record": logical, "physical_line": physical_line,
            "fragment_id": row.get("fragment_id", "")})
    if not notes:
        raise ValueError("No supplied note query records found.")
    return list(notes.values()), logical


def structural_ranges(records, args):
    valid, anomalies = [], []
    if args.page_window is None:
        return valid, anomalies
    if args.page_window < 0 or not args.range_source or not args.range_start_field or not args.range_end_field:
        raise ValueError("Page windows need a nonnegative radius and explicit source, start-field and end-field options.")
    for record in records:
        if not any(fnmatch.fnmatchcase(record["source_file"], pattern) for pattern in args.range_source):
            continue
        first = [field["value"] for field in record["fields"] if field["name"] == args.range_start_field]
        last = [field["value"] for field in record["fields"] if field["name"] == args.range_end_field]
        issue = ""
        if len(first) != 1 or len(last) != 1:
            issue = "missing or duplicate structural field"
        elif not re.fullmatch(r"[0-9]+", text_value(first[0])) or not re.fullmatch(r"[0-9]+", text_value(last[0])):
            issue = "structural bounds are not literal integers"
        elif int(first[0]) > int(last[0]):
            issue = "reversed structural bounds; not normalized"
        if issue:
            anomalies.append({key: record[key] for key in ("source_file", "source_sha256", "record_id", "logical_record", "physical_line_start", "physical_line_end")}
                | {"start_field": args.range_start_field, "end_field": args.range_end_field,
                   "start_values": compact(first), "end_values": compact(last), "issue": issue})
        else:
            valid.append((record, int(first[0]), int(last[0])))
    return valid, anomalies


def match_terms(record):
    return {term for field in record["fields"] for term in field["matching_terms"]}


def flat_matches(note, basis, records):
    result = []
    for row in records:
        for value in row["fields"] or [{}]:
            result.append({"note_id": note["note_id"], "printed_page": note["printed_page"], "retrieval_basis": basis,
                **{key: row[key] for key in ("source_file", "source_sha256", "record_id", "kind", "logical_record", "physical_line_start", "physical_line_end", "character_start", "character_end")},
                "field_position": value.get("position", ""), "field_name": value.get("name", ""),
                "value_sha256": value.get("value_sha256", ""), "text": value.get("text", ""),
                "matching_terms": compact(value.get("matching_terms", [])),
                "privacy_masked": value.get("privacy_masked", False),
                "snippet_truncated": value.get("snippet_truncated", False),
                "primary_comparison": "pending primary review"})
    return result


def batch(args):
    root, cache, output = args.context_root.resolve(), args.cache.resolve(), args.output.resolve()
    if output == root or root in output.parents or output == cache or cache in output.parents:
        raise ValueError("Search results must be separate from supplied context and parsed cache.")
    if output.exists() or args.limit < 1 or args.range_limit < 1 or args.snippet_chars < 40:
        raise ValueError("Use a fresh output, positive limits and at least 40 snippet characters.")
    manifest = json.loads((cache / "manifest.json").read_text())
    raw_cache = (cache / "records.jsonl").read_bytes()
    if sha(raw_cache) != manifest["cache_records_sha256"]:
        raise ValueError("Scratch cache hash differs from its manifest.")
    captured = source_inputs(root)
    expected = {item["relative_file"]: item["sha256"] for item in manifest["source_files"]}
    if {name: sha(raw) for name, raw in captured.items()} != expected:
        raise ValueError("Supplied context changed; prepare a fresh index.")
    status = notes_context_status(root, captured)
    if manifest.get("notes_context_status") != status:
        raise ValueError("Notes-directory status changed; prepare a fresh index.")
    records = [json.loads(line) for line in raw_cache.decode().splitlines()]
    input_raw = args.notes_jsonl.read_bytes()
    notes, input_record_count = read_queries(input_raw)
    ranges, anomalies = structural_ranges(records, args)
    all_results, summaries, coverage, term_coverage, flattened = [], [], [], [], []
    source_counts = Counter(row["source_file"] for row in records)
    for note in notes:
        search_args = argparse.Namespace(**vars(args), term=note["context_search_terms"], anchor=[], page=[], page_field=[])
        hits = [result for record in records if (result := select_record(record, search_args)) is not None]
        hits.sort(key=lambda row: (-len(match_terms(row)), row["source_file"], row["kind"], row["logical_record"]))
        selected = hits[:args.limit]
        window_results, window_start, window_end = [], "", ""
        if args.page_window is not None:
            page = int(note["printed_page"])
            window_start, window_end = page - args.page_window, page + args.page_window
            for record, first, last in ranges:
                if first > window_end or last < window_start:
                    continue
                display = args.range_show_field or [field["name"] for field in record["fields"]]
                page_args = argparse.Namespace(**{**vars(search_args), "term": [], "source": [], "kind": [],
                    "field": [], "show_field": list(dict.fromkeys([*display, args.range_start_field, args.range_end_field]))})
                result = select_record(record, page_args)
                result["structural_range"] = {"start": first, "end": last,
                    "start_field": args.range_start_field, "end_field": args.range_end_field}
                window_results.append(result)
            window_results.sort(key=lambda row: (row["structural_range"]["end"] - row["structural_range"]["start"],
                                                 row["source_file"], row["logical_record"]))
        selected_window = window_results[:args.range_limit]
        item = {**note, "keyword": {"combination": args.match, "total_records": len(hits),
                    "returned_records": len(selected), "truncated": len(hits) > len(selected), "results": selected},
            "structural_page_window": {"requested": args.page_window is not None, "radius": args.page_window,
                    "window_start": window_start, "window_end": window_end,
                    "total_records": len(window_results), "returned_records": len(selected_window),
                    "truncated": len(window_results) > len(selected_window), "results": selected_window},
            "notes_context_status": status, "primary_comparison": "pending primary review"}
        all_results.append(safe_tree(item))
        summaries.append({"note_id": note["note_id"], "printed_page": note["printed_page"],
            "input_records": compact(note["input_records"]), "explicit_terms": compact(note["context_search_terms"]),
            "keyword_total": len(hits), "keyword_returned": len(selected), "keyword_truncated": len(hits) > len(selected),
            "page_window_requested": args.page_window is not None, "page_window_start": window_start, "page_window_end": window_end,
            "page_window_total": len(window_results), "page_window_returned": len(selected_window), "page_window_truncated": len(window_results) > len(selected_window),
            "notes_directory_status": status["status"], "primary_comparison": "pending primary review"})
        for term in note["context_search_terms"]:
            term_coverage.append({"note_id": note["note_id"], "term": term,
                "qualified_keyword_records": sum(term in match_terms(row) for row in hits),
                "returned_keyword_records": sum(term in match_terms(row) for row in selected)})
        for source_file in expected:
            coverage.append({"note_id": note["note_id"], "source_file": source_file, "source_sha256": expected[source_file],
                "indexed_records": source_counts[source_file],
                "keyword_total": sum(row["source_file"] == source_file for row in hits),
                "keyword_returned": sum(row["source_file"] == source_file for row in selected),
                "page_window_total": sum(row["source_file"] == source_file for row in window_results),
                "page_window_returned": sum(row["source_file"] == source_file for row in selected_window)})
        flattened.extend(flat_matches(note, "explicit keyword", selected))
        flattened.extend(flat_matches(note, "explicit structural page window", selected_window))
    if source_inputs(root) != captured or notes_context_status(root, captured) != status:
        raise ValueError("Supplied context changed during batch retrieval; no report installed.")
    totals = {key: sum(row[key] for row in summaries) for key in
        ("keyword_total", "keyword_returned", "keyword_truncated", "page_window_total", "page_window_returned", "page_window_truncated")}
    summary = safe_tree({"schema": "primary-note-context-batch-v1", "query_input_file": args.notes_jsonl.name,
        "query_input_sha256": sha(input_raw), "query_input_records": input_record_count,
        "query_input_unchanged_at_completion": args.notes_jsonl.read_bytes() == input_raw,
        "distinct_notes": len(notes), "source_files": len(expected), "indexed_records": len(records),
        "cache_records_sha256": manifest["cache_records_sha256"], "source_hashes": expected,
        "notes_context_status": status, "totals": totals,
        "keyword_limit_per_note": args.limit, "keyword_order": "Descending number of explicit terms matched, then source, kind and logical record.",
        "keyword_combination": args.match, "case_sensitive": args.case_sensitive,
        "structural_page_window_radius": args.page_window, "structural_sources": args.range_source,
        "structural_start_field": args.range_start_field, "structural_end_field": args.range_end_field,
        "structural_valid_records": len(ranges), "structural_anomalies_excluded": len(anomalies),
        "structural_limit_per_note": args.range_limit,
        "structural_order": "Narrowest declared source interval first, then source and logical record; integer overlap only, no lexical inference.",
        "privacy_masked_fields": sum(row["privacy_masked"] for row in flattened),
        "truncated_field_snippets": sum(row["snippet_truncated"] for row in flattened),
        "primary_comparison": "pending primary review",
        "input_scope": "Only explicit note_id, printed_page, context_search_terms and optional fragment_id are used; claim and proof-needs prose is not interpreted."})
    flat_fields = ["note_id", "printed_page", "retrieval_basis", "source_file", "source_sha256", "record_id", "kind", "logical_record", "physical_line_start", "physical_line_end", "character_start", "character_end", "field_position", "field_name", "value_sha256", "text", "matching_terms", "privacy_masked", "snippet_truncated", "primary_comparison"]
    anomaly_fields = ["source_file", "source_sha256", "record_id", "logical_record", "physical_line_start", "physical_line_end", "start_field", "end_field", "start_values", "end_values", "issue"]
    payloads = {"BATCH_SUMMARY.json": json_bytes(summary),
        "NOTE_RESULTS.jsonl": ("\n".join(compact(item) for item in all_results) + "\n").encode(),
        "QUERY_SUMMARY.tsv": tsv_bytes(list(summaries[0]), safe_tree(summaries)),
        "TERM_COVERAGE.tsv": tsv_bytes(list(term_coverage[0]), safe_tree(term_coverage)),
        "SOURCE_COVERAGE.tsv": tsv_bytes(list(coverage[0]), safe_tree(coverage)),
        "MATCHES.tsv": tsv_bytes(flat_fields, safe_tree(flattened)),
        "STRUCTURAL_RANGE_ANOMALIES.tsv": tsv_bytes(anomaly_fields, safe_tree(anomalies)),
        "REPORT.md": ("# Explicit primary note queries: context retrieval\n\n"
            "Every note uses only its supplied search terms and printed page. Keyword matches and optional integer source-page-window overlaps are separate result sets. Each returned field has its source file/hash, logical record, inclusive physical lines, original-value hash and bounded privacy-safe snippet. Supplied context is unchanged; no whole context file is copied here.\n\n"
            "QUERY_SUMMARY and TERM_COVERAGE show limits and unmatched terms explicitly. SOURCE_COVERAGE lists every indexed file for every note, including zero matches. NOTE_RESULTS contains the per-note results and the narrow context README evidence for the absent notes directory. Invalid or reversed source intervals remain excluded and are listed unchanged in STRUCTURAL_RANGE_ANOMALIES.\n\n"
            "The batch binds its exact notes-input snapshot. If the primary appends notes during retrieval, query_input_unchanged_at_completion records that difference; generate another fresh batch to include later records. No judgment is transferred from keywords or page proximity. All adds/restates/differs comparisons remain pending primary review.\n").encode()}
    install(output, payloads)
    return {"notes": len(notes), "input_records": input_record_count, "source_files": len(expected),
            "totals": totals, "privacy_masked_fields": summary["privacy_masked_fields"],
            "query_input_unchanged_at_completion": summary["query_input_unchanged_at_completion"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--notes-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--field", action="append", default=[])
    parser.add_argument("--show-field", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--kind", action="append", choices=("csv", "html_static", "html_DATA.rows", "markdown_text"), default=[])
    parser.add_argument("--match", choices=("all", "any"), default="any")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--full-fields", action="store_true")
    parser.add_argument("--snippet-chars", type=int, default=260)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--page-window", type=int)
    parser.add_argument("--range-source", action="append", default=[])
    parser.add_argument("--range-start-field")
    parser.add_argument("--range-end-field")
    parser.add_argument("--range-show-field", action="append", default=[])
    parser.add_argument("--range-limit", type=int, default=25)
    args = parser.parse_args()
    try:
        result = batch(args)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(2, safe_location(type(exc).__name__ + ": " + str(exc)) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
