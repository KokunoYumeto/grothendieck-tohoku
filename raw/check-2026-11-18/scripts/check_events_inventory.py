"""Read-only CHECK_EVENTS structure, literal-value and ID-binding inventory.

Reference selection is explicitly lexical. No proof, outcome, event meaning,
reading or coverage is classified, and no event or review data is changed.
The optional gate requires a separately approved mechanical policy.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import io
import json
import os
from pathlib import Path
import re
import tempfile

from control_word_inventory import BLOCKED_DIRS, file_hash, read_snapshot, require_safe_name, sha, tsv_bytes, utc
from privacy_guard import safe_location, scan_bytes

EVENT_FIELDS = ["statement_id", "date", "who", "type", "outcome"]
MARKER_PATTERN = r"\b(?:refutation|refuted|refute|refutes|refuting)\b"
ATOM = r"[A-Za-z0-9]+(?:[_.:–-][A-Za-z0-9]+)*(?:\([A-Za-z0-9]+\))?"
ID_LEFT = r"(?<![A-Za-z0-9_.:–-])"
ID_RIGHT = r"(?![A-Za-z0-9_]|[_.:–-][A-Za-z0-9]|\([A-Za-z0-9])"
REFERENCE_RULES = [
    {"name": "TOH/page-prefixed ID candidate", "pattern": ID_LEFT + r"(?P<id>(?:TOH[0-9]*[-:]|p[0-9]{3}[:-])" + ATOM + ")" + ID_RIGHT, "identifier_shape_required": False},
    {"name": "qualified numeric ID candidate", "pattern": ID_LEFT + r"(?P<id>(?:[0-9]+\.)+[0-9]+:" + ATOM + ")" + ID_RIGHT, "identifier_shape_required": False},
    {"name": "backtick-delimited ID-shaped token", "pattern": r"`(?P<id>" + ATOM + r")`", "identifier_shape_required": True},
    {"name": "explicit statement-ID introducer", "pattern": r"\b(?:statement(?:['’]s)?\s+id|refined\s+statement(?:['’]s)?(?:\s+id)?|refinement\s+id)\s*[:=]?\s*[`'\"]?(?P<id>" + ATOM + ")" + ID_RIGHT, "identifier_shape_required": True},
]


def fingerprint(values: list[str]) -> str:
    return sha(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode())


def filtered(row: dict, fields: tuple[str, ...]) -> dict:
    result, changed = dict(row), []
    for field in fields:
        original = result.get(field, "")
        if isinstance(original, str):
            result[field] = safe_location(original)
            if result[field] != original:
                changed.append(field)
    result["privacy_filtered_fields"] = ",".join(changed)
    return result


def parse_events(data: bytes) -> dict:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        return {"header": [], "rows": [], "malformed": [{"event_record": "", "physical_start_line": "", "physical_end_line": "", "field_count": "", "issue": "UTF-8 decoding failed at byte " + str(error.start), "row_sha256": ""}], "parse_complete": False, "logical_records_seen": 0}
    physical = list(io.StringIO(text, newline=""))
    reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        return {"header": [], "rows": [], "malformed": [{"event_record": "", "physical_start_line": 1, "physical_end_line": reader.line_num, "field_count": "", "issue": "Missing or unparseable header", "row_sha256": ""}], "parse_complete": False, "logical_records_seen": 0}
    rows, malformed, previous, number, complete = [], [], reader.line_num, 0, True
    while True:
        first = previous + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            complete = False
            malformed.append({"event_record": number + 1, "physical_start_line": first, "physical_end_line": reader.line_num,
                              "field_count": "", "issue": "Strict TSV parse error: " + str(error), "row_sha256": ""})
            break
        number += 1
        last, previous = reader.line_num, reader.line_num
        metadata = {"event_record": number, "physical_start_line": first, "physical_end_line": last,
                    "row_sha256": fingerprint(cells), "serialized_record_sha256": sha("".join(physical[first - 1:last]).encode())}
        if len(cells) != len(header):
            malformed.append({**{key:metadata[key] for key in ("event_record", "physical_start_line", "physical_end_line", "row_sha256")},
                              "field_count": len(cells), "issue": "Cell count differs from the literal header width"})
            continue
        values = {field: cells[header.index(field)] if header.count(field) == 1 else None for field in EVENT_FIELDS}
        rows.append({**metadata, "cells": cells, "values": values})
    return {"header": header, "rows": rows, "malformed": malformed, "parse_complete": complete, "logical_records_seen": number}


def default_policy() -> dict:
    return {
        "approved": False,
        "allowed_event_types": [],
        "required_fields": list(EVENT_FIELDS),
        "reference_rules_reviewed": False,
        "refutation_marker_pattern": MARKER_PATTERN,
        "refutation_marker_fields": ["type", "outcome"],
        "reference_fields": ["type", "outcome"],
        "identifier_rules": [dict(rule) for rule in REFERENCE_RULES],
        "include_exact_declared_id_mentions": True,
        "exact_declared_id_left_boundary": ID_LEFT,
        "exact_declared_id_right_boundary": ID_RIGHT,
        "catalog_basis": "exact CHECK_EVENTS.statement_id values; no external catalogue implied",
        "require_reference_in_marker_rows": False,
        "duplicate_policy": "block exact parsed-value duplicates for manual resolution",
        "instructions": "The primary must explicitly approve the literal type vocabulary and reference contract. This policy approves no proof or editorial outcome. Do not derive approval from observed counts.",
    }


def find_references(text: str, catalog: dict[str, list[int]], policy: dict) -> list[dict]:
    found = []
    for rule in policy["identifier_rules"]:
        expression = re.compile(rule["pattern"], re.IGNORECASE)
        if "id" not in expression.groupindex:
            raise ValueError("Every identifier rule needs a named id capture group.")
        for match in expression.finditer(text):
            value = match.group("id")
            if rule.get("identifier_shape_required") and not (any(character.isdigit() for character in value) and any(character in "_.:–-" for character in value)):
                continue
            first, last = match.span("id")
            if any(first < item["end"] and item["start"] < last for item in found):
                continue
            found.append({"reference": value, "start": first, "end": last, "rule": rule["name"]})
    if policy.get("include_exact_declared_id_mentions"):
        for value in sorted(catalog, key=lambda item: (-len(item), item)):
            if not value or not value.strip():
                continue
            expression = re.compile(policy.get("exact_declared_id_left_boundary", ID_LEFT) + re.escape(value) + policy.get("exact_declared_id_right_boundary", ID_RIGHT))
            for match in expression.finditer(text):
                first, last = match.span()
                if not any(first < item["end"] and item["start"] < last for item in found):
                    found.append({"reference": value, "start": first, "end": last, "rule": "exact declared-ID mention"})
    return sorted(found, key=lambda item: (item["start"], item["end"]))


def analyze(data: bytes, policy: dict) -> tuple[dict, dict, list[dict]]:
    parsed = parse_events(data)
    header, rows = parsed["header"], parsed["rows"]
    required = policy["required_fields"]
    if not isinstance(required, list) or not set(required).issubset(EVENT_FIELDS):
        raise ValueError("Required fields must be explicit CHECK_EVENTS column names.")
    for name in policy["refutation_marker_fields"] + policy["reference_fields"]:
        if name not in {"type", "outcome"}:
            raise ValueError("Reference selection may use only explicitly named type/outcome fields.")
    marker = re.compile(policy["refutation_marker_pattern"], re.IGNORECASE)
    missing, types, ids, exact = [], defaultdict(list), defaultdict(list), defaultdict(list)
    for row in rows:
        for field in required:
            value = row["values"][field]
            reason = "column absent or ambiguous" if value is None else "empty" if value == "" else "whitespace-only" if not value.strip() else ""
            if reason:
                missing.append({"event_record": row["event_record"], "physical_start_line": row["physical_start_line"],
                                "physical_end_line": row["physical_end_line"], "field": field, "issue": reason,
                                "row_sha256": row["row_sha256"], "review_status": "pending"})
        if row["values"]["type"] is not None:
            types[row["values"]["type"]].append(row["event_record"])
        if row["values"]["statement_id"] is not None:
            ids[row["values"]["statement_id"]].append(row["event_record"])
        exact[tuple(row["cells"])].append(row)
    type_rows = [filtered({"type_literal": value, "type_json": json.dumps(value, ensure_ascii=False),
                           "type_sha256": sha(value.encode()), "count": len(records),
                           "event_records": ",".join(map(str, records)), "review_status": "pending"}, ("type_literal", "type_json"))
                 for value, records in sorted(types.items(), key=lambda item: item[1][0])]
    catalog_rows = [filtered({"statement_id": value, "id_sha256": sha(value.encode()), "event_rows": len(records),
                              "event_records": ",".join(map(str, records)), "review_status": "pending"}, ("statement_id",))
                    for value, records in sorted(ids.items(), key=lambda item: item[1][0])]
    duplicates, duplicate_members = [], []
    for entries in sorted((entries for entries in exact.values() if len(entries) > 1), key=lambda entries: entries[0]["event_record"]):
        group_id = f"D{len(duplicates) + 1:06d}"
        duplicates.append({"group_id": group_id, "rows": len(entries), "event_records": ",".join(str(row["event_record"]) for row in entries),
                           "row_sha256": entries[0]["row_sha256"], "serialization_variants": len({row["serialized_record_sha256"] for row in entries}), "review_status": "pending"})
        duplicate_members.extend({"group_id": group_id, **{field:row[field] for field in ("event_record", "physical_start_line", "physical_end_line", "row_sha256", "serialized_record_sha256")}, "review_status": "pending"} for row in entries)
    selected, references = [], []
    for row in rows:
        values = row["values"]
        markers = [(field, match.group()) for field in policy["refutation_marker_fields"] if values[field] is not None for match in marker.finditer(values[field])]
        if not markers:
            continue
        count, unresolved = 0, 0
        for field in policy["reference_fields"]:
            if values[field] is None:
                continue
            for item in find_references(values[field], ids, policy):
                target = item["reference"]
                literal_records = ids.get(target, [])
                count += 1
                unresolved += not literal_records
                references.append(filtered({
                    "event_record": row["event_record"], "statement_id": values["statement_id"] or "", "field": field,
                    "reference": target, "reference_sha256": sha(target.encode()), "start_character": item["start"] + 1,
                    "end_character": item["end"], "extraction_rule": item["rule"],
                    "literal_id_present": "yes" if literal_records else "no", "matching_event_records": ",".join(map(str, literal_records)),
                    "self_reference": "yes" if values["statement_id"] == target else "no",
                    "row_sha256": row["row_sha256"], "review_status": "pending",
                }, ("statement_id", "reference")))
        selected.append(filtered({"event_record": row["event_record"], "statement_id": values["statement_id"] or "",
                                  "marker_fields": ",".join(dict.fromkeys(field for field, _ in markers)),
                                  "literal_markers": ",".join(value for _, value in markers),
                                  "reference_candidates": count, "unmatched_reference_candidates": unresolved,
                                  "no_reference_candidate_extracted": "yes" if count == 0 else "no",
                                  "row_sha256": row["row_sha256"], "review_status": "pending"}, ("statement_id",)))
    unmatched = [row for row in references if row["literal_id_present"] == "no"]
    allowed = policy.get("allowed_event_types", [])
    if not isinstance(allowed, list) or not all(isinstance(value, str) for value in allowed) or len(allowed) != len(set(allowed)):
        raise ValueError("The event-type policy must be a literal list without duplicate values.")
    unapproved = [value for value in types if value not in allowed]
    checks = [
        {"check": "check-events-schema", "status": "pass" if header == EVENT_FIELDS else "fail", "detail": "Exact five-column header order is required."},
        {"check": "check-events-tsv", "status": "pass" if parsed["parse_complete"] and not parsed["malformed"] and rows else "fail", "detail": "Strict TSV must parse completely with consistent row widths and at least one event."},
        {"check": "check-events-required-fields", "status": "pass" if not missing else "fail", "detail": f"Missing/blank required cells: {len(missing)}; no field value is normalized."},
        {"check": "check-events-exact-duplicates", "status": "pass" if not duplicates else "fail", "detail": f"Exact parsed-value duplicate groups requiring manual resolution: {len(duplicates)}. Repeated IDs or dates alone are permitted."},
        {"check": "check-events-literal-types", "status": "pass" if not unapproved else "fail", "detail": f"Distinct type strings outside the explicit allowed list: {len(unapproved)}. No vocabulary is inferred from counts."},
        {"check": "check-events-refutation-id-bindings", "status": "pass" if not unmatched else "fail", "detail": f"Selected ID occurrences lacking an exact statement_id value: {len(unmatched)}. This is local literal binding only."},
        {"check": "check-events-reference-presence-policy", "status": "pass" if not policy.get("require_reference_in_marker_rows") or all(row["reference_candidates"] for row in selected) else "fail", "detail": f"Marker-selected rows without an extracted ID: {sum(not row['reference_candidates'] for row in selected)}. Requiring a reference in every such row is an explicit policy choice."},
        {"check": "check-events-policy-approved", "status": "pass" if policy.get("approved") is True and policy.get("reference_rules_reviewed") is True and required == EVENT_FIELDS else "fail", "detail": "The primary must approve the literal type vocabulary, complete field contract and reference-selection rules. The draft is not approval."},
    ]
    summary = {"logical_event_records_seen": parsed["logical_records_seen"], "valid_width_rows": len(rows),
               "parse_complete": parsed["parse_complete"], "schema_exact": header == EVENT_FIELDS,
               "malformed_rows_or_parse_errors": len(parsed["malformed"]), "missing_required_cells": len(missing),
               "distinct_literal_event_types": len(types), "distinct_statement_ids": len(ids),
               "exact_duplicate_groups": len(duplicates), "rows_in_exact_duplicate_groups": len(duplicate_members),
               "refutation_marker_rows": len(selected), "reference_candidate_occurrences": len(references),
               "unmatched_reference_occurrences": len(unmatched), "distinct_unmatched_id_candidates": len({row["reference_sha256"] for row in unmatched}),
               "marker_rows_without_reference_candidate": sum(not row["reference_candidates"] for row in selected),
               "gate_policy_approved": policy.get("approved") is True and policy.get("reference_rules_reviewed") is True and required == EVENT_FIELDS,
               "gate_checks_failed": sum(row["status"] != "pass" for row in checks)}
    reference_fields = ["event_record", "statement_id", "field", "reference", "reference_sha256", "start_character", "end_character", "extraction_rule", "literal_id_present", "matching_event_records", "self_reference", "row_sha256", "privacy_filtered_fields", "review_status"]
    tables = {
        "SCHEMA.tsv": (["position", "expected_field", "actual_field", "literal_equal"], [
            {"position": index + 1, "expected_field": EVENT_FIELDS[index] if index < len(EVENT_FIELDS) else "", "actual_field": safe_location(header[index]) if index < len(header) else "", "literal_equal": "yes" if index < len(header) and index < len(EVENT_FIELDS) and header[index] == EVENT_FIELDS[index] else "no"}
            for index in range(max(len(header), len(EVENT_FIELDS)))]),
        "EVENT_TYPE_COUNTS.tsv": (["type_literal", "type_json", "type_sha256", "count", "event_records", "privacy_filtered_fields", "review_status"], type_rows),
        "MALFORMED_ROWS.tsv": (["event_record", "physical_start_line", "physical_end_line", "field_count", "issue", "row_sha256"], parsed["malformed"]),
        "MISSING_REQUIRED_FIELDS.tsv": (["event_record", "physical_start_line", "physical_end_line", "field", "issue", "row_sha256", "review_status"], missing),
        "EXACT_DUPLICATE_GROUPS.tsv": (["group_id", "rows", "event_records", "row_sha256", "serialization_variants", "review_status"], duplicates),
        "EXACT_DUPLICATE_MEMBERS.tsv": (["group_id", "event_record", "physical_start_line", "physical_end_line", "row_sha256", "serialized_record_sha256", "review_status"], duplicate_members),
        "STATEMENT_ID_CATALOG.tsv": (["statement_id", "id_sha256", "event_rows", "event_records", "privacy_filtered_fields", "review_status"], catalog_rows),
        "REFUTATION_MARKER_ROWS.tsv": (["event_record", "statement_id", "marker_fields", "literal_markers", "reference_candidates", "unmatched_reference_candidates", "no_reference_candidate_extracted", "row_sha256", "privacy_filtered_fields", "review_status"], selected),
        "REFERENCE_CANDIDATES.tsv": (reference_fields, references),
        "UNMATCHED_ID_CANDIDATES.tsv": (reference_fields, unmatched),
        "PROPOSED_GATE_CHECKS.tsv": (["check", "status", "detail"], checks),
    }
    return tables, summary, checks


def run(args) -> dict:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside a protected context folder.")
    if args.output.is_absolute() or "interim" not in args.output.name.casefold():
        raise ValueError("Use a fresh relative report directory explicitly containing interim.")
    require_safe_name(args.output.as_posix())
    if any(part.casefold() in BLOCKED_DIRS for part in args.output.parts):
        raise ValueError("The report cannot be placed inside protected context folders.")
    cursor = root
    for part in args.output.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("The report path must not pass through a symbolic link.")
    output = (root / args.output).resolve()
    if output == root or root not in output.parents or any(output == root / name or root / name in output.parents for name in ("sources", "pdf", "second-reading")):
        raise ValueError("The report must be inside the delivery tree and outside source, PDF and review-state trees.")
    if output.exists():
        raise ValueError("An existing interim report is never overwritten.")
    events = root / "CHECK_EVENTS.tsv"
    if events.is_symlink():
        raise ValueError("CHECK_EVENTS must be a regular file.")
    data = read_snapshot(events)
    policy, policy_data, policy_path = default_policy(), None, None
    if args.policy:
        if args.policy.is_absolute():
            raise ValueError("Use a policy path relative to the delivery root.")
        require_safe_name(args.policy.as_posix())
        policy_path = root
        for part in args.policy.parts:
            policy_path = policy_path / part
            if policy_path.is_symlink() or part.casefold() in BLOCKED_DIRS:
                raise ValueError("The policy cannot pass through a symlink or protected context folder.")
        policy_path = policy_path.resolve()
        if root not in policy_path.parents:
            raise ValueError("The policy must be inside the delivery tree.")
        policy_data = read_snapshot(policy_path)
        policy = json.loads(policy_data.decode("utf-8"))
    tables, summary, checks = analyze(data, policy)
    input_rows = [{"role": "event-table snapshot", "file": "CHECK_EVENTS.tsv", "bytes": len(data), "sha256": sha(data)}]
    if policy_data is not None:
        input_rows.append({"role": "supplied mechanical policy", "file": safe_location(args.policy.name), "bytes": len(policy_data), "sha256": sha(policy_data)})
    tables["INPUT_HASHES.tsv"] = (["role", "file", "bytes", "sha256"], input_rows)
    report = ["# Interim CHECK_EVENTS mechanical inventory", "", "Generated " + utc() + ".", "",
              "This report makes no proof, refutation, editorial or coverage judgment. It preserves literal event types and compares only exact identifiers under documented lexical rules. CHECK_EVENTS and all review/source data remain unchanged.", "",
              "| Measure | Result |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items())
    report.extend(["", "## Structure and literal values", "",
                   "The expected column order is statement_id, date, who, type, outcome. Strict TSV parsing preserves parsed field values exactly. A parse error stops reliable enumeration; malformed widths, empty cells and whitespace-only required cells are reported by logical record and physical lines. Dates and statement IDs are not required to be unique. No outcome text is copied into this report's tables.", "",
                   "EVENT_TYPE_COUNTS.tsv preserves each distinct literal type value, an escaped JSON view, its count and hash. No event-type spelling, case or whitespace is normalized and no allowed vocabulary is inferred. Exact duplicate groups compare all five parsed values without normalization; raw serialized-record hashes distinguish quoting/line-ending variants.", "",
                   "## Literal reference candidates", "",
                   "Rows are selected only by the policy's literal refutation-word regex in type/outcome; this selection does not classify whether any proof was refuted. References are enumerated from those same fields using the recorded prefix, qualified-number, quoted-token and explicit-ID-introducer rules, plus exact declared-ID mentions. The catalog is the literal statement_id column of this table only. Case is preserved and matching is case-sensitive; identifiers are never renamed or normalized.", "",
                   "UNMATCHED_ID_CANDIDATES.tsv means no exactly equal statement_id cell was found. It does not mean that a statement or proof is absent from other documents. A marker row without an extracted reference remains visible for manual assessment. The rules cannot certify that arbitrary prose contains no other identifier. The full draft policy records the exact regexes and fields.", "",
                   "## Proposed final packaging gate", "",
                   "PROPOSED_GATE_CHECKS.tsv records mechanical findings under the draft or supplied policy. The default policy has no approved event-type vocabulary and is explicitly unapproved; its gate cannot pass. A primary-approved literal vocabulary and reference contract are required before adopting a final gate. All schema, parse, required-field, duplicate, type and ID-binding checks must then pass; requiring an ID in every marker row is an explicit policy option.", "",
                   "The current final validator and checkpoint helper are not changed by this inventory. Adoption requires integrating these named checks into final_validate and requiring them in checkpoint preflight's mandatory set; their omission must not qualify as a pass. Current inventory hashes must bind CHECK_EVENTS and the adopted policy. No mechanical gate substitutes for the primary's proof or editorial work.", "",
                   "Every finding remains pending manual review. Inputs were rechecked before exclusive installation. Previous snapshots are unchanged. See scripts/CHECK_EVENTS_VALIDATION.md for the proposed integration and limitations.", ""])
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads["REPORT.md"] = "\n".join(report).encode()
    payloads["SUMMARY.json"] = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    payloads["PROPOSED_GATE_POLICY.json"] = (json.dumps(policy, indent=2, ensure_ascii=False) + "\n").encode()
    if any(scan_bytes(name, value) for name, value in payloads.items()):
        raise RuntimeError("A generated report has a privacy pattern or inspection blocker; no report was installed.")
    with tempfile.TemporaryDirectory(prefix="check-events-inventory-", dir=root.parent) as temporary:
        prepared = Path(temporary)
        for name, value in payloads.items():
            (prepared / name).write_bytes(value)
        if file_hash(events) != (len(data), sha(data)):
            raise RuntimeError("CHECK_EVENTS changed after the snapshot; no report was installed.")
        if policy_data is not None and file_hash(policy_path) != (len(policy_data), sha(policy_data)):
            raise RuntimeError("The policy changed after the snapshot; no report was installed.")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir()
        installed = []
        try:
            for name in sorted(payloads):
                target = output / name
                os.link(prepared / name, target)
                installed.append(target)
        except BaseException:
            for target in installed:
                target.unlink()
            output.rmdir()
            raise
    print(json.dumps({**summary, "report_directory": output.relative_to(root).as_posix()}, indent=2))
    if args.require_gate and any(check["status"] != "pass" for check in checks):
        raise SystemExit(1)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="Fresh relative interim directory")
    parser.add_argument("--policy", type=Path, help="Optional explicit mechanical policy; no approval is inferred")
    parser.add_argument("--require-gate", action="store_true", help="Exit nonzero unless every mechanical check passes under an approved policy; still changes no event data")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
