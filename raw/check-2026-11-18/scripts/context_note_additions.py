"""Add explicit primary anchors and query metadata to an immutable base report.

No note prose is assessed. New context content is deduplicated against the base;
mathematical-note page ranges and literal hits remain selection candidates only.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from context_anchor_search import extract_anchors, single_value, table
from context_search import compact, install, json_bytes, literal_match, notes_context_status, safe_tree, sha, source_inputs, text_value, tsv_bytes
from math_literal_groups import promoted_entries
from privacy_guard import safe_location


def run(args):
    root, context_root, cache, base, output = (path.resolve() for path in (args.root, args.context_root, args.cache, args.base_report, args.output))
    if output.exists() or output == context_root or context_root in output.parents or output == cache or cache in output.parents:
        raise ValueError("Use a fresh output separate from supplied context and parsed cache.")
    captured = {}

    def read(path):
        path = path.resolve()
        raw = path.read_bytes()
        captured[path] = raw
        return raw

    def jsonl(path):
        return [json.loads(line) for line in read(path).decode("utf-8-sig").splitlines() if line.strip()]

    manifest = json.loads(read(cache / "manifest.json"))
    raw_cache = read(cache / "records.jsonl")
    if sha(raw_cache) != manifest["cache_records_sha256"]:
        raise ValueError("Context cache does not match its manifest hash.")
    context_bytes = source_inputs(context_root)
    expected_context = {row["relative_file"]: row["sha256"] for row in manifest["source_files"]}
    if {name: sha(raw) for name, raw in context_bytes.items()} != expected_context:
        raise ValueError("Supplied context differs from the indexed snapshot.")
    status = notes_context_status(context_root, context_bytes)
    if status != manifest.get("notes_context_status"):
        raise ValueError("Notes-directory status differs from the context index.")
    records = [json.loads(line) for line in raw_cache.decode().splitlines()]
    by_record = {row["record_id"]: row for row in records}
    ref_by_record = {row["record_id"]: f"CX{number:05d}" for number, row in enumerate(records, 1)}
    record_by_ref = {ref_by_record[row["record_id"]]: row for row in records}
    base_summary = json.loads(read(base / "SUMMARY.json"))
    if base_summary["context_cache_sha256"] != manifest["cache_records_sha256"]:
        raise ValueError("Base report binds a different context cache.")
    base_records = jsonl(base / "CONTEXT_RECORDS.jsonl")
    base_ids = {row["record_id"] for row in base_records}
    for returned in base_records:
        current = by_record[returned["record_id"]]
        if returned["fields_sha256"] != current["fields_sha256"] or returned["source_sha256"] != current["source_sha256"]:
            raise ValueError("A base context record has a stale source or field binding.")
    base_joins = table(read(base / "NOTE_CONTEXT_BINDINGS.tsv"))
    base_notes = {row["note_id"]: row for row in table(read(base / "NOTE_SUMMARY.tsv"))}
    op_rows = {row["note_id"]: row for row in jsonl(args.op_notes)}
    if sha(captured[args.op_notes.resolve()]) != base_summary["notes_input_sha256"]:
        raise ValueError("OP notes changed since the base report; refresh their base query binding first.")
    slip_rows = {row["correction_id"]: row for row in table(read(args.slip_inventory / "ORIGINAL_SLIP_ROWS.tsv"))}
    ledger_entries = {entry["id"]: entry for entry in promoted_entries(read(root / "CORRECTIONS.tsv"))}
    manual = table(read(args.primary_bindings))
    math_rows, later_rows = jsonl(args.math_inputs), jsonl(args.later_inputs)
    programme_rows = jsonl(args.programme_inputs) if args.programme_inputs else []
    math_selections = jsonl(args.math_selections) if args.math_selections else []
    if any(len({row["note_id"] for row in cohort}) != len(cohort) for cohort in (math_rows, later_rows, programme_rows)):
        raise ValueError("Duplicate note IDs in a new query input.")
    roles = {"units": "stacks/tohoku_r71/units.csv", "map": "stacks/tohoku_r71/map.csv",
             "decisions": "stacks/tohoku_r71/dec.csv", "issues": "stacks/tohoku_r71/issues.csv"}
    role_by_file = {value: key for key, value in roles.items()}
    by_id = {role: defaultdict(list) for role in roles}
    for record in records:
        role = role_by_file.get(record["source_file"])
        if role:
            by_id[role][single_value(record, "id" if role == "units" else "unit_id")].append(record)
    added_notes, selected_anchors, applied, join_issues, applied_math = {}, defaultdict(set), [], [], []
    selection_origins = {}

    def metadata(row, family):
        note_id, printed_page, terms = row["note_id"], str(row["printed_page"]), row["context_search_terms"]
        if not re.fullmatch(r"[0-9]+", printed_page) or not isinstance(terms, list) or not terms or not all(isinstance(term, str) and term for term in terms):
            raise ValueError("New note queries need an explicit integer page and nonempty literal terms.")
        return {"note_id": note_id, "family": family, "printed_page": printed_page, "terms": list(dict.fromkeys(terms))}

    for row in math_rows:
        added_notes[row["note_id"]] = metadata(row, "primary mathematical-note candidates")
    if math_selections:
        selected_ids = [row["note_id"] for row in math_selections]
        if len(set(selected_ids)) != len(selected_ids) or set(selected_ids) != {row["note_id"] for row in math_rows}:
            raise ValueError("Explicit mathematical selections do not exactly cover the mathematical note IDs.")
        for choice in math_selections:
            note_id, unit_id = choice["note_id"], choice["context_unit_id"]
            matches = [record for record in by_id["map"][unit_id]
                if record["logical_record"] == int(choice["map_logical_record"])
                and record["physical_line_start"] == int(choice["map_physical_line"])]
            if len(matches) != 1:
                raise ValueError("A primary mathematical selection does not bind its exact unit ID and map-record/physical-line locator.")
            record = matches[0]
            added_notes[note_id]["family"] = "primary mathematical-note exact selection"
            selected_anchors[note_id].add(unit_id)
            selection_origins[(note_id, unit_id)] = "explicit primary context-unit and map-record selection"
            applied_math.append({"note_id": note_id, "context_unit_id": unit_id,
                "map_logical_record": record["logical_record"], "map_physical_line": record["physical_line_start"],
                "map_source_file": record["source_file"], "map_source_sha256": record["source_sha256"],
                "map_record_id": record["record_id"], "map_fields_sha256": record["fields_sha256"],
                "status": "exact supplied primary selection applied; no semantic assessment by helper"})
    for row in [*later_rows, *programme_rows]:
        if row["note_id"] in added_notes or row["note_id"] in base_notes:
            raise ValueError("A later-work ID collides with another note family.")
        family = "primary later-work anchors" if row in later_rows else "primary programme proposal anchors"
        added_notes[row["note_id"]] = metadata(row, family)
        anchors = row["context_anchor_ids"]
        if not isinstance(anchors, list) or not all(isinstance(anchor, str) and anchor for anchor in anchors):
            raise ValueError("Later-work anchors must be explicit nonempty strings.")
        selected_anchors[row["note_id"]].update(anchors)
    for binding in manual:
        note_id, source_item, source_file = binding["note_id"], binding["source_item"], binding["source_file"]
        if note_id not in base_notes or binding["decision"] != "explicit primary anchor" or binding["reviewer"] != "primary":
            raise ValueError("A manual anchor is not an explicit primary binding to an existing note.")
        if not re.fullmatch(r"sources/(?:dip|fr|en)/p[0-9]{3}\.tex", source_file):
            raise ValueError("A manual source filename is outside the authorized page scope.")
        page_path = root / source_file
        if page_path.is_symlink() or root not in page_path.resolve().parents:
            raise ValueError("A manual source escapes the delivery tree.")
        source_raw = read(page_path)
        source, anchors, unresolved = extract_anchors(source_raw)
        exact_locations = [anchor for anchor in anchors if anchor["anchor"] == binding["anchor"]]
        if binding["primary_anchor_line"] and not any(anchor["macro_line"] == int(binding["primary_anchor_line"]) for anchor in exact_locations):
            raise ValueError("The primary-supplied macro line is not an exact literal anchor in current source.")
        observed_hash = ""
        if note_id in op_rows:
            op = op_rows[note_id]
            if (source_item, source_file, binding["source_lines"], binding["primary_fragment_sha256"]) != (op["fragment_id"], op["source_file"], op["source_lines"], op["source_fragment_sha256"]):
                raise ValueError("A manual OP binding does not preserve the original primary fragment metadata.")
            numbers = [int(value) for value in re.findall(r"[0-9]+", binding["source_lines"])]
            lines = re.findall(r"[^\n]*\n|[^\n]+$", source)
            observed_hash = sha("".join(lines[numbers[0] - 1:numbers[-1]]).rstrip("\r\n").encode())
        else:
            row, entry = slip_rows.get(source_item), ledger_entries.get(source_item)
            if row is None or entry is None or not entry["active"] or (row["notes_group_id"], row["file"], row["row_fingerprint"]) != (note_id, source_file, binding["row_fingerprint"]) or entry["fingerprint"] != binding["row_fingerprint"]:
                raise ValueError("A manual slip binding does not preserve the current original ledger fingerprint.")
        selected_anchors[note_id].add(binding["anchor"])
        applied.append({**binding, "current_source_sha256": sha(source_raw),
            "current_exact_anchor_lines": compact([anchor["macro_line"] for anchor in exact_locations]),
            "observed_full_line_range_sha256": observed_hash,
            "binding_status": "explicit primary anchor applied; original fragment or ledger fingerprint preserved"})

    selected_records, added_joins = {}, []
    for note_id, anchors in selected_anchors.items():
        family = base_notes[note_id]["family"] if note_id in base_notes else added_notes[note_id]["family"]
        for anchor in sorted(anchors):
            direct = [record for role in ("units", "map") for record in by_id[role][anchor]]
            if not direct:
                join_issues.append({"note_id": note_id, "anchor": anchor, "issue": "No exact units/map identity match; no alias inferred."})
            parents = {single_value(record, "parent_id") for record in direct if single_value(record, "parent_id")}
            origin = selection_origins.get((note_id, anchor), "explicit primary exact anchor")
            for unit_id, basis in [(anchor, origin)] + [(parent, "one declared parent_id of " + origin) for parent in sorted(parents) if parent != anchor]:
                for role in roles:
                    for record in by_id[role][unit_id]:
                        selected_records[record["record_id"]] = record
                        added_joins.append({"note_id": note_id, "family": family, "anchor": anchor,
                            "selected_unit_id": unit_id, "join_basis": basis, "context_role": role,
                            **{key: record[key] for key in ("record_id", "source_file", "source_sha256", "logical_record", "physical_line_start", "physical_line_end")},
                            "join_field": "id" if role == "units" else "unit_id",
                            "content_location": "base CONTEXT_RECORDS.jsonl" if record["record_id"] in base_ids else "ADDED_CONTEXT_RECORDS.jsonl",
                            "primary_comparison": "pending primary review"})
    added_joins = list({compact(row): row for row in added_joins}.values())
    added_records = []
    for record in sorted(selected_records.values(), key=lambda row: (row["source_file"], row["logical_record"])):
        if record["record_id"] in base_ids:
            continue
        returned = {key: value for key, value in record.items() if key != "fields"}
        returned["fields"] = [{"position": field["position"], "name": field["name"], "value": safe_location(text_value(field["value"])),
            "value_sha256": field["value_sha256"], "privacy_masked": safe_location(text_value(field["value"])) != text_value(field["value"])} for field in record["fields"]]
        returned["primary_comparison"] = "pending primary review"
        added_records.append(safe_tree(returned))

    query_coverage, term_hits, needed_refs = [], [], set()
    for note in added_notes.values():
        source_counts_by_term = []
        for term in note["terms"]:
            counts = dict.fromkeys(expected_context, 0)
            hits = []
            for record in records:
                positions = [field["position"] for field in record["fields"] if literal_match(text_value(field["value"]), term)]
                if positions:
                    reference = ref_by_record[record["record_id"]]
                    needed_refs.add(reference)
                    hits.append([reference, positions])
                    counts[record["source_file"]] += 1
            source_counts_by_term.append({"term": term, "source_counts": counts, "matching_records": len(hits)})
            term_hits.append({"note_id": note["note_id"], "family": note["family"], "printed_page": note["printed_page"],
                              "term": term, "record_and_field_position_hits": hits})
        query_coverage.append({**note, "case_sensitive": False, "term_coverage": source_counts_by_term,
                               "primary_comparison": "pending primary selection or comparison"})

    range_records, range_anomalies = [], []
    for record in records:
        if record["source_file"] not in (roles["units"], roles["map"]):
            continue
        first, last = single_value(record, "source_start"), single_value(record, "source_end")
        if not re.fullmatch(r"[0-9]+", first) or not re.fullmatch(r"[0-9]+", last) or int(first) > int(last):
            range_anomalies.append({"record_ref": ref_by_record[record["record_id"]], "source_start": first, "source_end": last, "status": "excluded; no range normalization"})
            needed_refs.add(ref_by_record[record["record_id"]])
        else:
            range_records.append((record, int(first), int(last)))
    page_candidates = []
    for row in math_rows:
        page = int(row["printed_page"])
        matches = [ref_by_record[record["record_id"]] for record, first, last in range_records if first <= page <= last]
        needed_refs.update(matches)
        page_candidates.append({"note_id": row["note_id"], "printed_page": page, "candidate_count": len(matches),
            "record_refs": matches, "matching_rule": "literal integer source_start <= printed_page <= source_end; exact selected units/map fields",
            "status": "locator candidates for primary selection; page overlap is not semantic evidence"})
    lookup = []
    for reference in sorted(needed_refs):
        record = record_by_ref[reference]
        role = role_by_file.get(record["source_file"], "")
        fields = {field["name"]: field["value"] for field in record["fields"]}
        lookup.append({"record_ref": reference, **{key: record[key] for key in ("record_id", "source_file", "source_sha256", "kind", "logical_record", "physical_line_start", "physical_line_end", "character_start", "character_end", "fields_sha256")},
            "field_names_in_position_order": compact([field["name"] for field in record["fields"]]),
            "context_unit_id": fields.get("id", "") if role == "units" else fields.get("unit_id", ""),
            "parent_id": fields.get("parent_id", ""), "source_start": fields.get("source_start", ""), "source_end": fields.get("source_end", ""),
            "content_available_in_base": record["record_id"] in base_ids,
            "content_added_here": record["record_id"] in {row["record_id"] for row in added_records}})

    all_note_meta = {note_id: {"note_id": note_id, "family": row["family"], "printed_page": row["printed_page"]} for note_id, row in base_notes.items()}
    all_note_meta.update({note_id: {key: row[key] for key in ("note_id", "family", "printed_page")} for note_id, row in added_notes.items()})
    all_joins = base_joins + added_joins
    by_note, record_notes = defaultdict(set), defaultdict(set)
    for row in all_joins:
        by_note[row["note_id"]].add(row["record_id"])
        record_notes[row["record_id"]].add(row["note_id"])
    candidate_counts = {row["note_id"]: row["candidate_count"] for row in page_candidates}
    note_counts = []
    for note in sorted(all_note_meta.values(), key=lambda row: (int(row["printed_page"]), row["family"], row["note_id"])):
        selected = by_note[note["note_id"]]
        role_counts = Counter(role_by_file.get(by_record[record_id]["source_file"], "") for record_id in selected)
        note_counts.append({**note, "unique_context_records": len(selected),
            **{role + "_records": role_counts[role] for role in roles},
            "relation_binding_rows": sum(row["note_id"] == note["note_id"] for row in all_joins),
            "mathematical_page_candidates": candidate_counts.get(note["note_id"], ""),
            "primary_comparison": "pending primary review"})
    reading = []
    for record_id, notes in record_notes.items():
        record = by_record[record_id]
        pages = sorted({int(all_note_meta[note_id]["printed_page"]) for note_id in notes})
        role = role_by_file[record["source_file"]]
        reading.append({"record_id": record_id, "first_bound_note_page": pages[0], "all_bound_note_pages": compact(pages),
            "bound_note_count": len(notes), "context_role": role,
            "unit_id": single_value(record, "id" if role == "units" else "unit_id"),
            **{key: record[key] for key in ("source_file", "source_sha256", "logical_record", "physical_line_start", "physical_line_end")},
            "content_file": (base.relative_to(root) / "CONTEXT_RECORDS.jsonl").as_posix() if record_id in base_ids else (output.relative_to(root) / "ADDED_CONTEXT_RECORDS.jsonl").as_posix()})
    reading.sort(key=lambda row: (row["first_bound_note_page"], list(roles).index(row["context_role"]), row["unit_id"], row["logical_record"]))
    reading = [{"reading_id": f"CR{number:05d}", **row} for number, row in enumerate(reading, 1)]
    page_plan = []
    for page in sorted({int(row["printed_page"]) for row in all_note_meta.values()}):
        notes = [note_id for note_id, row in all_note_meta.items() if int(row["printed_page"]) == page]
        unique_records = set().union(*(by_note[note_id] for note_id in notes))
        first_rows = [row for row in reading if row["first_bound_note_page"] == page]
        page_plan.append({"printed_page": page, "notes": len(notes), "exact_context_records_bound_to_notes_on_page": len(unique_records),
            "first_use_records_to_read_here": len(first_rows), "records_already_listed_on_earlier_note_pages": len(unique_records) - len(first_rows),
            "reading_ids": compact([row["reading_id"] for row in first_rows]),
            "grouping_rule": "first printed page of a note binding; not a context-source page or semantic ranking"})
    if source_inputs(context_root) != context_bytes or any(path.read_bytes() != raw for path, raw in captured.items()):
        raise ValueError("A bound input changed during additions retrieval; no report installed.")
    summary = {"schema": "compact-context-note-additions-v1", "base_report": base.relative_to(root).as_posix(),
        "base_unique_context_records": len(base_ids), "primary_manual_bindings_applied": len(applied),
        "mathematical_notes_queried": len(math_rows), "primary_mathematical_selections_applied": len(applied_math),
        "later_work_notes_queried": len(later_rows), "programme_notes_queried": len(programme_rows),
        "new_keyword_note_count": len(added_notes), "keyword_term_queries": len(term_hits),
        "keyword_source_files_per_note": len(expected_context), "literal_term_record_hits": sum(len(row["record_and_field_position_hits"]) for row in term_hits),
        "mathematical_page_candidate_rows": sum(row["candidate_count"] for row in page_candidates),
        "structural_ranges_excluded": len(range_anomalies), "lookup_records": len(lookup),
        "added_exact_relation_bindings": len(added_joins), "new_unique_context_records": len(added_records),
        "combined_unique_context_records": len(reading), "combined_note_count": len(all_note_meta),
        "combined_notes_with_exact_context": sum(bool(by_note[note_id]) for note_id in all_note_meta),
        "explicit_anchor_join_issues": len(join_issues),
        "privacy_masked_added_context_fields": sum(field["privacy_masked"] for row in added_records for field in row["fields"]),
        "context_cache_sha256": manifest["cache_records_sha256"], "notes_context_status": status,
        "primary_comparison": "not assessed by helper; exact supplied primary selections are retained, and page matches/literal term hits remain candidates only"}
    def rows_tsv(rows, empty_fields):
        return tsv_bytes(list(rows[0]) if rows else empty_fields, safe_tree(rows))
    def lines_json(rows):
        return ("\n".join(compact(safe_tree(row)) for row in rows) + "\n").encode()
    payloads = {"SUMMARY.json": json_bytes(safe_tree(summary)),
        "PRIMARY_BINDINGS_APPLIED.tsv": rows_tsv(applied, ["note_id", "anchor"]),
        "MATHEMATICAL_SELECTIONS_APPLIED.tsv": rows_tsv(applied_math, ["note_id", "context_unit_id", "status"]),
        "ADDED_NOTE_CONTEXT_BINDINGS.tsv": rows_tsv(added_joins, ["note_id", "record_id"]),
        "ADDED_CONTEXT_RECORDS.jsonl": lines_json(added_records),
        "QUERY_COVERAGE.jsonl": lines_json(query_coverage), "LITERAL_TERM_HITS.jsonl": lines_json(term_hits),
        "MATHEMATICAL_PAGE_CANDIDATES.jsonl": lines_json(page_candidates),
        "MATCH_RECORD_LOCATORS.tsv": rows_tsv(lookup, ["record_ref", "record_id"]),
        "STRUCTURAL_RANGE_ANOMALIES.tsv": rows_tsv(range_anomalies, ["record_ref", "status"]),
        "EXPLICIT_ANCHOR_JOIN_ISSUES.tsv": rows_tsv(join_issues, ["note_id", "anchor", "issue"]),
        "PER_NOTE_BINDING_COUNTS.tsv": rows_tsv(note_counts, ["note_id", "unique_context_records"]),
        "READING_INDEX.tsv": rows_tsv(reading, ["reading_id", "record_id"]),
        "PAGE_READING_PLAN.tsv": rows_tsv(page_plan, ["printed_page", "first_use_records_to_read_here"]),
        "CONTEXT_SOURCE_HASHES.tsv": tsv_bytes(["source_file", "sha256"], [{"source_file": name, "sha256": digest} for name, digest in expected_context.items()]),
        "INPUT_HASHES.tsv": tsv_bytes(["input", "bytes", "sha256"], [{"input": path.relative_to(root).as_posix() if root in path.parents else path.name, "bytes": len(raw), "sha256": sha(raw)} for path, raw in captured.items() if path.parent != cache]),
        "READING_GUIDE.md": ("# Compact context additions and reading plan\n\n"
            "READING_INDEX lists every exact-joined context record once, grouped by the first printed page of a bound note. PAGE_READING_PLAN gives the per-page first-use reading IDs and previously listed counts. This is a note-reading order, not a claim about the context source's page or mathematical relevance. PER_NOTE_BINDING_COUNTS gives unique units/map/decision/issue counts for each note.\n\n"
            "The base report's CONTEXT_RECORDS.jsonl retains the complete summary/rationale and other fields for every existing context record. ADDED_CONTEXT_RECORDS.jsonl supplies only newly selected rows. READING_INDEX names the exact content file for each record. No broad keyword snippet dump or duplicate copy of base context content is produced.\n\n"
            "Four explicit primary anchor authorizations are retained in PRIMARY_BINDINGS_APPLIED. The bounded p183 fragments keep their original declared hashes; their full-line-range hashes are separately recorded without replacing them. The p211 slip bindings preserve their stable correction identities and original current row fingerprints. These are supplied primary decisions, not delegated source judgments.\n\n"
            "All mathematical, later-work and programme-proposal terms are taken exactly from the primary inputs. QUERY_COVERAGE provides every term's counts for all twelve sources, including zero. LITERAL_TERM_HITS records each matching record reference and exact field positions. MATCH_RECORD_LOCATORS resolves those references to source file/hash, logical record, physical lines, field names and original record-field hash. Full context outside the exact joins is not copied into this supplement. The generic query helper can retrieve a chosen candidate field for primary reading.\n\n"
            "MATHEMATICAL_SELECTIONS_APPLIED binds each supplied primary selection to its exact context unit ID, map logical record, physical line and current source/field hashes. Those explicit decisions drive the mathematical-note joins; no choice is inferred from text or proximity. MATHEMATICAL_PAGE_CANDIDATES retains integer source_start/source_end overlaps as candidates only. Two reversed intervals remain excluded and listed. Later-work and programme-proposal joins use only explicit context_anchor_ids, one declared parent level and exact unit_id joins. The helper does not assess any supplied prose or add a substantive comparison.\n").encode()}
    install(output, payloads)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    for name in ("context-root", "cache", "base-report", "op-notes", "slip-inventory", "primary-bindings", "math-inputs", "later-inputs", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--programme-inputs", type=Path)
    parser.add_argument("--math-selections", type=Path)
    args = parser.parse_args()
    try:
        result = run(args)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(2, safe_location(type(exc).__name__ + ": " + str(exc)) + "\n")
    print(json.dumps({key: result[key] for key in ("primary_manual_bindings_applied", "mathematical_notes_queried", "primary_mathematical_selections_applied", "later_work_notes_queried", "programme_notes_queried", "new_unique_context_records", "combined_unique_context_records", "combined_note_count", "combined_notes_with_exact_context", "explicit_anchor_join_issues", "privacy_masked_added_context_fields")},sort_keys=True))


if __name__ == "__main__":
    main()
