"""Prepare exact literal groups and expand explicit mathematical classifications.

Only a captured promoted ledger and explicitly selected decision TSVs are read.
Literal equality is organizational metadata, never a mathematical judgment.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import tempfile

from control_word_inventory import sha, tsv_bytes
from final_validate import confidence_annotation
from french_layer_rebind import capture, guard_path, relative_path, recheck_snapshots
from privacy_guard import privacy_findings, safe_location, scan_bytes
from refresh_check_record import FIELDS, MATH_FIELDS, MATH_REQUIRED, MATH_CANDIDATE_KINDS, PAGE_ORDER, load_rows, load_classifications, pending_math_rows


HASH = re.compile(r"[0-9a-f]{64}")
GROUP_REQUIRED = ["group_id", "group_sha256", "membership_sha256", "mathematical_change", "summary", "reason"]
GROUP_FIELDS = GROUP_REQUIRED + ["member_count", "printed_pages", "layers", "correction_ids", "kind", "old", "new"]
PROVENANCE_FIELDS = ["group_id", "group_sha256", "membership_sha256", "decision_origin", "application_route", "decision_input_sha256", "decision_input_record", "decision_group_id", "decision_membership_sha256", "row_exception", "decision_value_sha256"]
CLASSIFICATION_FIELDS = MATH_FIELDS + PROVENANCE_FIELDS
MEMBER_FIELDS = ["group_id", "group_sha256", "membership_sha256", "correction_id", "row_fingerprint", "ledger_record"] + FIELDS
DISPLAY_FIELDS = frozenset(FIELDS + ["printed_pages", "layers", "correction_ids"])


def digest(value) -> str:
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def read_table(data: bytes, required: list[str]) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t", strict=True)
    fields, rows = reader.fieldnames or [], list(reader)
    if (len(fields) != len(set(fields)) or not set(required).issubset(fields)
            or any(None in row or any(value is None for value in row.values()) for row in rows)):
        raise ValueError("A selected TSV has a malformed record, duplicate column or unsupported schema.")
    return fields, rows


def promoted_entries(data: bytes) -> list[dict]:
    # Reuse the established loader against captured bytes, never the live path.
    with tempfile.TemporaryDirectory(prefix="math-group-ledger-") as temporary:
        root = Path(temporary)
        (root / "CORRECTIONS.tsv").write_bytes(data)
        entries = load_rows(root, None)
    events = set()
    for entry in entries:
        annotation = confidence_annotation(entry["row"]["confidence"])
        if annotation is None or annotation["review_id"] != entry["id"] or annotation["event_id"] in events:
            raise ValueError("A promoted ledger with canonical, unique annotated R IDs and last-event IDs is required.")
        events.add(annotation["event_id"])
    return entries


def literal_groups(entries: list[dict]) -> tuple[list[dict], dict[str, dict], list[dict]]:
    buckets = defaultdict(list)
    for entry in entries:
        if entry["active"]:
            row = entry["row"]
            buckets[(row["kind"], row["old"], row["new"])].append(entry)
    groups, by_member, members = [], {}, []
    for key, items in buckets.items():
        group_hash = digest(list(key))
        member_hash = digest([group_hash, sorted([[entry["id"], entry["fingerprint"]] for entry in items])])
        group = {"group_id": "G" + group_hash, "group_sha256": group_hash, "membership_sha256": member_hash,
                 "mathematical_change": "pending", "summary": "", "reason": "", "member_count": len(items),
                 "printed_pages": ",".join(page if page else "unpaged" for page in sorted({entry["row"]["printed_page"] for entry in items}, key=PAGE_ORDER.__getitem__)),
                 "layers": ",".join(sorted({entry["row"]["layer"] for entry in items})),
                 "correction_ids": ",".join(sorted(entry["id"] for entry in items)), "kind": key[0], "old": key[1], "new": key[2]}
        groups.append(group)
        for entry in items:
            by_member[entry["id"]] = group
            members.append({**{field: group[field] for field in GROUP_REQUIRED[:3]}, "correction_id": entry["id"],
                            "row_fingerprint": entry["fingerprint"], "ledger_record": entry["ledger_record"], **entry["row"]})
    groups.sort(key=lambda row: (min(PAGE_ORDER[page] for page in row["printed_pages"].replace("unpaged", "").split(",")), row["kind"], row["group_id"]))
    members.sort(key=lambda row: (PAGE_ORDER[row["printed_page"]], row["ledger_record"]))
    return groups, by_member, members


def check_decision(row: dict) -> None:
    choice = row["mathematical_change"]
    if choice not in {"yes", "no", "pending"}:
        raise ValueError("Decisions must be explicit lowercase yes, no or pending.")
    if choice in {"yes", "no"} and not row["reason"].strip():
        raise ValueError("Every explicit yes/no decision needs a reviewer-supplied reason.")
    if choice == "yes" and not row["summary"].strip():
        raise ValueError("Every explicit yes decision also needs a reviewer-supplied summary.")
    if privacy_findings(row["summary"] + "\n" + row["reason"]):
        raise ValueError("Decision summary/reason contains a privacy pattern; decision prose is never filtered.")


def group_decisions(data: bytes, groups: list[dict]) -> dict[str, dict]:
    _, rows = read_table(data, GROUP_REQUIRED)
    current = {row["group_id"]: row for row in groups}
    result = {}
    for number, row in enumerate(rows, 1):
        key = row["group_id"]
        if key in result or key not in current:
            raise ValueError("A group decision has a duplicate or missing current group identity.")
        if any(row[field] != current[key][field] for field in GROUP_REQUIRED[:3]):
            raise ValueError("A group identity or membership changed; prepare and review a fresh group snapshot.")
        check_decision(row)
        result[key] = {**row, "_record": number}
    return result


def row_decisions(data: bytes, entries: list[dict], *, existing: bool) -> dict[str, dict]:
    fields, rows = read_table(data, MATH_REQUIRED)
    active = [entry for entry in entries if entry["active"]]
    with tempfile.TemporaryDirectory(prefix="math-group-decisions-") as temporary:
        path = Path(temporary) / "decisions.tsv"
        path.write_bytes(data)
        load_classifications(path, active)
    result = {}
    for number, row in enumerate(rows, 1):
        check_decision(row)
        if "row_exception" in fields and row["row_exception"] not in {"yes", "no"}:
            raise ValueError("A row_exception marker must be yes or no.")
        if existing and set(PROVENANCE_FIELDS).issubset(fields):
            expected = decision_digest(row)
            if row["decision_value_sha256"] != expected:
                raise ValueError("Existing helper decision values changed without matching provenance; supply an explicit row-exception file instead.")
            if row["decision_origin"] not in {"pending", "group", "row_exception", "existing_row"}:
                raise ValueError("An existing classification has an unsupported decision origin.")
            for name in ("decision_input_sha256", "decision_membership_sha256"):
                if row[name] and not HASH.fullmatch(row[name]):
                    raise ValueError("An existing decision provenance hash is malformed.")
        result[row["correction_id"]] = {**row, "_record": number,
                                        "_has_provenance": set(PROVENANCE_FIELDS).issubset(fields),
                                        "_exception": row.get("row_exception", "yes" if row["mathematical_change"] == "pending" else "no") == "yes"}
    return result


def decision_digest(row: dict) -> str:
    return digest([row[field] for field in MATH_REQUIRED])


def classifications(entries: list[dict], by_member: dict, decisions: dict, previous: dict, exceptions: dict,
                    source_hashes: dict) -> list[dict]:
    output = []
    for template in pending_math_rows(entries, True):
        row = dict(template)
        key = row["correction_id"]
        group = by_member[key]
        row.update({field: group[field] for field in GROUP_REQUIRED[:3]})
        row.update({"decision_origin": "pending", "application_route": "fresh_pending", "decision_input_sha256": "",
                    "decision_input_record": "", "decision_group_id": "", "decision_membership_sha256": "", "row_exception": "no"})
        selected, source = None, None
        if key in exceptions:
            selected, source = exceptions[key], "row_exceptions"
            row.update({"decision_origin": "row_exception", "application_route": "explicit_row_exception", "row_exception": "yes"})
        elif key in previous and (previous[key]["mathematical_change"] in {"yes", "no"} or previous[key]["_exception"]):
            selected, source = previous[key], "existing_classifications"
            row.update({"decision_origin": "existing_row", "application_route": "preserved_existing", "row_exception": "yes" if selected["_exception"] else "no"})
            if selected["_has_provenance"]:
                for field in ("decision_origin", "decision_input_sha256", "decision_input_record", "decision_group_id", "decision_membership_sha256"):
                    row[field] = selected[field]
        elif group["group_id"] in decisions and decisions[group["group_id"]]["mathematical_change"] in {"yes", "no"}:
            selected, source = decisions[group["group_id"]], "group_decisions"
            row.update({"decision_origin": "group", "application_route": "explicit_group_decision",
                        "decision_group_id": group["group_id"], "decision_membership_sha256": group["membership_sha256"]})
        if selected is not None:
            for field in ("mathematical_change", "summary", "reason"):
                row[field] = selected[field]
            if source != "existing_classifications" or not selected["_has_provenance"]:
                row["decision_input_sha256"] = source_hashes[source]
                row["decision_input_record"] = selected["_record"]
        row["decision_value_sha256"] = decision_digest(row)
        output.append(row)
    return output


def make_payloads(tables: dict, summary: dict, *, filter_derived: bool) -> dict[str, bytes]:
    payloads, filtering = {}, []
    for name, (fields, rows) in tables.items():
        if name == "ROW_EXCEPTIONS.tsv" and fields == MATH_REQUIRED and not rows:
            payloads[name] = tsv_bytes(fields, [])
            continue
        presented = []
        for number, row in enumerate(rows, 1):
            output, altered = dict(row), []
            if filter_derived:
                for field in fields:
                    value = row[field]
                    if field not in DISPLAY_FIELDS or not isinstance(value, str):
                        continue
                    filtered = safe_location(value)
                    if filtered != value:
                        output[field] = filtered
                        altered.append(field)
                        filtering.append({"report_file": name, "report_record": number, "field": field,
                                          "original_value_sha256": sha(value.encode()), "filtered_value_sha256": sha(filtered.encode()),
                                          "status": "display only; grouping and fingerprints use original ledger values"})
            output["privacy_filtered_fields"] = ",".join(altered)
            presented.append(output)
        payloads[name] = tsv_bytes(fields + ["privacy_filtered_fields"], presented)
    summary["privacy_filtered_display_fields"] = len(filtering)
    payloads["PRIVACY_FILTERING.tsv"] = tsv_bytes(["report_file", "report_record", "field", "original_value_sha256", "filtered_value_sha256", "status"], filtering)
    payloads["SUMMARY.json"] = (json.dumps(summary, sort_keys=True, indent=2) + "\n").encode()
    report = ["# Interim literal-group mathematical classification support", "", "Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + ".", "",
              "No mathematical decision, summary or reason is generated. Prepare starts every active row and group pending with blank decision prose. Expand copies only explicitly supplied primary group or row decisions. Every output is a fresh snapshot; no live record, source or build is changed.", "",
              "| Measure | Result |", "| --- | ---: |"]
    report += [f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items()]
    report += ["", "## Exact grouping and decision precedence", "",
               "All active promoted-ledger rows are covered, including build rows and all kinds. Withdrawn rows are excluded. Each group is exact kind, old, new equality in the original validated ledger; no whitespace, Unicode, TeX or semantic normalization is used. GROUP_MEMBERS.tsv records each stable R ID, row fingerprint, current ledger position and all original ledger metadata. Display-filtered old/new cells never form group keys.", "",
               "The full group SHA-256 binds the exact three-field tuple. Membership SHA-256 binds that hash and the sorted complete set of stable ID/fingerprint pairs. Every supplied group decision must match current identity and membership, including pending group rows. Added, missing or changed members therefore block reuse until a fresh group snapshot is explicitly reviewed. Ledger reorder alone does not change membership.", "",
               "Precedence is explicit row exception, preserved existing yes/no or protected pending exception, explicit group yes/no, then fresh pending. Yes and no need a supplied reason; yes also needs a supplied summary. Group-pending and omitted groups make no row decision. An explicit pending row exception remains pending even when its group says yes or no. Existing helper provenance and exceptions survive repeat expansion. Legacy existing pending rows without a row_exception marker are conservatively retained as row holds; a pristine pending template should not be passed as an existing decision file unless that is intended.", "",
               "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv retains the existing loader's core schema and appends current group and decision provenance. Decision origin, exact source-file hash, input data-record number and originating group membership distinguish group from row values. ROW_EXCEPTIONS.tsv contains all retained explicit row overrides, including pending. Existing helper decision values are hash-bound; edit through a separate row-exception input when changing them. Explicit new row exceptions may supersede existing values; group decisions cannot.", "",
               "## Privacy, provenance and limits", "",
               "INPUT_HASHES.tsv captures every selected input byte sequence. All inputs are rechecked immediately before exclusive installation; no existing output path is overwritten. Output bytes are privacy-inspected after preparation. With explicit display filtering, each altered informational cell has a marker plus original/filtered hashes in PRIVACY_FILTERING.tsv. Mathematical decisions, reasons, summaries, identity hashes and provenance are never filtered; a privacy finding in decision prose blocks output.", "",
               "This helper verifies promoted annotation format and stable IDs, not the underlying reading or review-event history. It opens only the selected ledger and decision TSVs, never TeX, scans, context files, CHECK_RECORD, review history or build inputs. Identical correction literals can have different mathematical significance in context: grouping is an interface for explicit primary judgment, not evidence that a group deserves one verdict. The existing classification/refresh/final gates are unchanged and are not executed here.", ""]
    payloads["REPORT.md"] = "\n".join(report).encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Prepared output contains a privacy pattern or inspection blocker; no report was installed.")
    return payloads


def run(args) -> dict:
    root = Path(args.root).absolute()
    guard_path(root)
    if not root.is_dir():
        raise ValueError("A regular delivery root is required.")
    root = root.resolve()
    output = relative_path(root, args.output)
    if output.exists() or "interim" not in output.name.casefold() or any(folder == output or folder in output.parents for folder in (root / "sources", root / "pdf", root / "second-reading")):
        raise ValueError("Use a fresh interim output directory outside sources, PDFs and live review state.")
    snapshots, source_hashes, captured = [], {}, {}
    names = {"ledger": args.ledger}
    if args.action == "expand":
        names.update({"group_decisions": args.group_decisions, "existing_classifications": args.existing_classifications, "row_exceptions": args.row_exceptions})
    for role, name in names.items():
        if not name:
            continue
        path = relative_path(root, name)
        if path.suffix != ".tsv":
            raise ValueError("Only explicitly selected TSV inputs are accepted.")
        if path.parent != root and (output == path.parent or path.parent in output.parents):
            raise ValueError("The output must be outside each existing input snapshot directory.")
        data = capture(path)
        snapshots.append((role, path, data))
        captured[role], source_hashes[role] = data, sha(data)
    entries = promoted_entries(captured["ledger"])
    groups, by_member, members = literal_groups(entries)
    decisions = group_decisions(captured["group_decisions"], groups) if "group_decisions" in captured else {}
    previous = row_decisions(captured["existing_classifications"], entries, existing=True) if "existing_classifications" in captured else {}
    exceptions = row_decisions(captured["row_exceptions"], entries, existing=False) if "row_exceptions" in captured else {}
    classified = classifications(entries, by_member, decisions, previous, exceptions, source_hashes)
    for group in groups:
        chosen = decisions.get(group["group_id"])
        if chosen is not None:
            for field in ("mathematical_change", "summary", "reason"):
                group[field] = chosen[field]
    tables = {
        "GROUP_DECISIONS.tsv": (GROUP_FIELDS, groups),
        "GROUP_MEMBERS.tsv": (MEMBER_FIELDS, members),
        "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv": (CLASSIFICATION_FIELDS, classified),
        "ROW_EXCEPTIONS.tsv": (MATH_REQUIRED if args.action == "prepare" else CLASSIFICATION_FIELDS,
                               [row for row in classified if row["row_exception"] == "yes"]),
        "WITHDRAWN_ROWS_EXCLUDED.tsv": (["correction_id", "row_fingerprint", "ledger_record"],
                                         [{"correction_id": entry["id"], "row_fingerprint": entry["fingerprint"], "ledger_record": entry["ledger_record"]} for entry in entries if not entry["active"]]),
        "INPUT_HASHES.tsv": (["role", "file", "bytes", "sha256"], [{"role": role, "file": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": sha(data)} for role, path, data in snapshots]),
    }
    choices, routes = Counter(row["mathematical_change"] for row in classified), Counter(row["application_route"] for row in classified)
    summary = {"operation": args.action, "active_rows": len(classified), "withdrawn_rows_excluded": sum(not entry["active"] for entry in entries),
               "default_kind_active_rows": sum(entry["active"] and entry["row"]["kind"] in MATH_CANDIDATE_KINDS for entry in entries),
               "literal_groups": len(groups), "groups_with_multiple_members": sum(group["member_count"] > 1 for group in groups),
               **{"classifications_" + value: choices[value] for value in ("yes", "no", "pending")},
               **{route + "_rows": routes[route] for route in ("fresh_pending", "explicit_group_decision", "preserved_existing", "explicit_row_exception")},
               "retained_row_exceptions": sum(row["row_exception"] == "yes" for row in classified),
               "retained_pending_exceptions": sum(row["row_exception"] == "yes" and row["mathematical_change"] == "pending" for row in classified)}
    payloads = make_payloads(tables, summary, filter_derived=args.privacy_filter_derived)
    with tempfile.TemporaryDirectory(prefix="math-groups-prepared-", dir=root) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        # Validate compatibility with the existing consumer, against captured
        # active entries only. Its extra informational/provenance fields are inert.
        load_classifications(prepared / "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv", [entry for entry in entries if entry["active"]])
        if any((prepared / name).read_bytes() != data or scan_bytes(name, (prepared / name).read_bytes()) for name, data in payloads.items()):
            raise RuntimeError("Prepared output changed or failed inspection; no report was installed.")
        guard_path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        guard_path(output)
        recheck_snapshots(snapshots)
        output.mkdir()
        installed = []
        try:
            guard_path(output)
            for name in sorted(payloads):
                target = output / name
                os.link(prepared / name, target)
                installed.append(target)
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
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "expand"):
        command = commands.add_parser(action)
        command.add_argument("--ledger", default="CORRECTIONS.tsv", help="Explicit promoted ledger TSV relative to root")
        command.add_argument("--output", required=True, help="Fresh interim directory relative to root")
        command.add_argument("--privacy-filter-derived", action="store_true", help="Mark and hash filtering of display fields; never filter decision prose")
        if action == "expand":
            command.add_argument("--group-decisions", required=True, help="Primary-edited group decision TSV, preserving identity and membership hashes")
            command.add_argument("--existing-classifications", help="Prior per-row decisions to preserve, including marked pending exceptions")
            command.add_argument("--row-exceptions", help="Explicit per-row yes/no/pending overrides; highest priority")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
