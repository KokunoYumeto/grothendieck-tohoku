"""Propose exact French hunk rebindings from explicit inventory snapshots.

Read-only with respect to every input. Historical decisions are metadata only;
all proposal and diagnostic rows remain pending. No TeX file is opened.
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

from control_word_inventory import BLOCKED_DIRS, read_snapshot, require_safe_name, sha, tsv_bytes
from privacy_guard import privacy_findings, safe_location, scan_bytes


REVIEW_FIELDS = ["hunk_id", "printed_page", "hunk_sha256", "decision", "correction_ids", "reason", "reviewed_utc", "reviewer"]
HUNK_REQUIRED = ["hunk_id", "printed_page", "hunk_sha256", "candidate_correction_ids"]
BINDING_FIELDS = ["correction_id", "ledger_record", "row_fingerprint", "id_source"]
OPTIONAL_MANIFESTS = ["INPUT_HASHES.tsv", "SOURCE_HASHES.tsv", "COMPARISON_SETTINGS.json", "METADATA_RULES.json", "PRIVACY_FILTERING.tsv"]
LOCATOR_FIELDS = ["operation", "dip_file", "dip_start_line", "dip_line_count", "dip_boundary_after_line", "fr_file", "fr_start_line", "fr_line_count", "fr_boundary_after_line"]
HASH = re.compile(r"[0-9a-f]{64}")
HUNK_ID = re.compile(r"D([0-9]+)-[0-9]{3,}")
CORRECTION_ID = re.compile(r"[RL][0-9]{6,}")
POSITIVE = re.compile(r"[1-9][0-9]*")


def table(data: bytes, required: list[str], *, exact: bool = False) -> list[dict]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t", strict=True)
    fields = reader.fieldnames or []
    if (len(fields) != len(set(fields)) or not fields or any(not field for field in fields)
            or (fields != required if exact else not set(required).issubset(fields))):
        raise ValueError("An input TSV has an unsupported or duplicate-column schema; no report was installed.")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("An input TSV has a malformed record; no report was installed.")
    for number, row in enumerate(rows, 1):
        # This is a canonical parsed-record hash, not a claim to preserve its
        # original TSV quoting. INPUT_HASHES retains the complete original bytes.
        row["_record_sha256"] = sha(json.dumps([fields, [row[field] for field in fields]], ensure_ascii=False, separators=(",", ":")).encode())
        row["_record"] = number
        row["_errors"] = []
    return rows


def index(rows: list[dict], field: str) -> dict[str, list[dict]]:
    result = defaultdict(list)
    for row in rows:
        result[row[field]].append(row)
    return result


def record_numbers(rows: list[dict]) -> str:
    return ",".join(str(row["_record"]) for row in rows)


def page_order(row: dict) -> tuple:
    value = row.get("printed_page", "")
    return (int(value) if POSITIVE.fullmatch(str(value)) else float("inf"),
            str(row.get("hunk_id", row.get("historical_hunk_id", ""))),
            int(row.get("prior_review_record", row.get("inventory_record", row.get("record_number", 0))) or 0))


def issue(issues: list[dict], dataset: str, row: dict, field: str, code: str) -> None:
    if code not in row["_errors"]:
        row["_errors"].append(code)
    issues.append({"dataset": dataset, "record_number": row["_record"],
                   "printed_page": row.get("printed_page", ""), "hunk_id": row.get("hunk_id", ""),
                   "correction_id": row.get("correction_id", ""), "field": field, "issue": code,
                   "original_value_sha256": sha(row.get(field, "").encode()), "review_status": "pending"})


def parse_ids(value: str, *, review: bool) -> tuple[list[str] | None, str]:
    if value == "":
        return [], "empty"
    token = r"R[0-9]{6,}" if review else r"[RL][0-9]{6,}"
    if not re.fullmatch(token + r"(?:\s*,\s*" + token + r")*", value):
        return None, "malformed"
    # Only grammar-approved separator whitespace is removed for membership
    # comparison. The original cell and its hash remain historical evidence.
    values = [part.strip() for part in value.split(",")]
    if not all(canonical_correction_id(item) for item in values):
        return None, "malformed"
    return values, "duplicate_ids" if len(values) != len(set(values)) else "valid"


def canonical_correction_id(value: str) -> bool:
    return bool(CORRECTION_ID.fullmatch(value) and int(value[1:]) > 0
                and value == value[0] + f"{int(value[1:]):06d}")


def identity_kind(value: str) -> str:
    if not canonical_correction_id(value):
        return "invalid_identifier"
    return "stable_review_id" if value.startswith("R") else "snapshot_local_ledger_locator"


def validate_hunks(rows: list[dict], dataset: str, issues: list[dict], *, review: bool = False) -> None:
    by_id, by_hash = index(rows, "hunk_id"), index(rows, "hunk_sha256")
    for row in rows:
        match = HUNK_ID.fullmatch(row["hunk_id"])
        if not match:
            issue(issues, dataset, row, "hunk_id", "invalid_hunk_id")
        if not POSITIVE.fullmatch(row["printed_page"]):
            issue(issues, dataset, row, "printed_page", "invalid_printed_page")
        elif match and int(match.group(1)) != int(row["printed_page"]):
            issue(issues, dataset, row, "printed_page", "hunk_id_page_mismatch")
        if not HASH.fullmatch(row["hunk_sha256"]):
            issue(issues, dataset, row, "hunk_sha256", "invalid_hunk_sha256")
        if len(by_id[row["hunk_id"]]) != 1:
            issue(issues, dataset, row, "hunk_id", "duplicate_hunk_id")
        if len(by_hash[row["hunk_sha256"]]) != 1:
            issue(issues, dataset, row, "hunk_sha256", "duplicate_hunk_sha256")
        row["_identity_valid"] = not row["_errors"]
        field = "correction_ids" if review else "candidate_correction_ids"
        row["_ids"], row["_ids_status"] = parse_ids(row[field], review=review)
        if row["_ids_status"] in {"malformed", "duplicate_ids"}:
            issue(issues, dataset, row, field, row["_ids_status"] + "_in_" + field)


def validate_bindings(rows: list[dict], side: str, issues: list[dict]) -> None:
    by_id, by_record = index(rows, "correction_id"), index(rows, "ledger_record")
    for row in rows:
        if not canonical_correction_id(row["correction_id"]):
            issue(issues, side + " bindings", row, "correction_id", "invalid_correction_id")
        if not POSITIVE.fullmatch(row["ledger_record"]):
            issue(issues, side + " bindings", row, "ledger_record", "invalid_ledger_record")
        if not HASH.fullmatch(row["row_fingerprint"]):
            issue(issues, side + " bindings", row, "row_fingerprint", "invalid_row_fingerprint")
        if len(by_id[row["correction_id"]]) != 1:
            issue(issues, side + " bindings", row, "correction_id", "duplicate_correction_id")
        if len(by_record[row["ledger_record"]]) != 1:
            issue(issues, side + " bindings", row, "ledger_record", "duplicate_ledger_record")


def binding_reports(baseline: list[dict], current: list[dict], reviews: list[dict]) -> tuple[list[dict], list[dict], dict]:
    old, new = index(baseline, "correction_id"), index(current, "correction_id")
    references = defaultdict(set)
    for row in reviews:
        for correction_id in row["_ids"] or []:
            references[correction_id].add(row["_record"])
    metadata = [{"inventory_side": side, "binding_record": row["_record"],
                 "identity_kind": identity_kind(row["correction_id"]),
                 **{field: row[field] for field in BINDING_FIELDS if field != "id_source"},
                 "id_source_sha256": sha(row["id_source"].encode()), "canonical_record_sha256": row["_record_sha256"],
                 "validation": ";".join(row["_errors"]) or "valid", "review_status": "pending"}
                for side, rows in (("baseline", baseline), ("current", current)) for row in rows]
    comparisons = []
    for correction_id in sorted(set(old) | set(new) | set(references)):
        before, after = old.get(correction_id, []), new.get(correction_id, [])
        if len(before) > 1 or len(after) > 1 or any("duplicate_ledger_record" in row["_errors"] for row in before + after):
            status = "ambiguous_binding"
        elif any(row["_errors"] for row in before + after):
            status = "invalid_binding"
        elif not before and not after:
            status = "missing_both_bindings"
        elif not before:
            status = "new_current_binding"
        elif not after:
            status = "missing_current_binding"
        elif before[0]["row_fingerprint"] != after[0]["row_fingerprint"]:
            status = "changed_fingerprint"
        else:
            status = "unchanged_fingerprint"
        item = {"correction_id": correction_id, "identity_kind": identity_kind(correction_id), "binding_status": status,
                "referenced_prior_review_records": ",".join(map(str, sorted(references.get(correction_id, set())))),
                "baseline_binding_records": record_numbers(before), "current_binding_records": record_numbers(after),
                "ledger_record_changed": "", "id_source_changed": "", "review_status": "pending"}
        for side, rows in (("baseline", before), ("current", after)):
            item[side + "_ledger_record"] = rows[0]["ledger_record"] if len(rows) == 1 else ""
            item[side + "_row_fingerprint"] = rows[0]["row_fingerprint"] if len(rows) == 1 else ""
            item[side + "_id_source_sha256"] = sha(rows[0]["id_source"].encode()) if len(rows) == 1 else ""
        if len(before) == len(after) == 1:
            item["ledger_record_changed"] = "yes" if before[0]["ledger_record"] != after[0]["ledger_record"] else "no"
            item["id_source_changed"] = "yes" if before[0]["id_source"] != after[0]["id_source"] else "no"
        comparisons.append(item)
    return metadata, comparisons, {row["correction_id"]: row for row in comparisons}


def historical(row: dict, review_input_hash: str) -> dict:
    return {"prior_review_record": row["_record"], "printed_page": row["printed_page"],
            "historical_hunk_id": row["hunk_id"], "hunk_sha256": row["hunk_sha256"],
            "historical_decision": row["decision"], "historical_correction_ids": row["correction_ids"],
            "historical_correction_ids_sha256": sha(row["correction_ids"].encode()),
            "historical_correction_ids_parse_status": row["_ids_status"],
            "historical_reason_sha256": sha(row["reason"].encode()), "historical_reviewed_utc": row["reviewed_utc"],
            "historical_reviewer_sha256": sha(row["reviewer"].encode()),
            "historical_review_record_sha256": row["_record_sha256"],
            "historical_review_input_sha256": review_input_hash, "review_status": "pending"}


def association(row: dict | None, correction_id: str) -> str:
    if row is None:
        return "no_unique_validated_hunk"
    if row["_ids"] is None:
        return "malformed_candidate_field"
    return "listed" if correction_id in row["_ids"] else "not_listed"


def compare(baseline: list[dict], reviews: list[dict], current: list[dict],
            old_bindings: list[dict], new_bindings: list[dict], review_input_hash: str) -> tuple[dict, dict]:
    issues = []
    for rows, dataset, is_review in ((baseline, "baseline hunks", False), (reviews, "prior review", True), (current, "current hunks", False)):
        validate_hunks(rows, dataset, issues, review=is_review)
    validate_bindings(old_bindings, "baseline", issues)
    validate_bindings(new_bindings, "current", issues)
    binding_metadata, bindings, bindings_by_id = binding_reports(old_bindings, new_bindings, reviews)
    old_id, old_hash = index(baseline, "hunk_id"), index(baseline, "hunk_sha256")
    new_id, new_hash = index(current, "hunk_id"), index(current, "hunk_sha256")
    review_by_id = index(reviews, "hunk_id")
    proposals, unmatched_prior, referenced = [], [], []
    matched_baseline, matched_current = set(), set()
    for review in reviews:
        reasons = [code for code in review["_errors"] if code not in {"malformed_in_correction_ids", "duplicate_ids_in_correction_ids"}]
        baseline_rows = old_id.get(review["hunk_id"], [])
        previous, fresh = None, None
        if not baseline_rows:
            reasons.append("missing_baseline_hunk_id")
        elif len(baseline_rows) != 1:
            reasons.append("ambiguous_baseline_hunk_id")
        else:
            candidate = baseline_rows[0]
            for field, code in (("printed_page", "baseline_page_mismatch"), ("hunk_sha256", "baseline_hash_mismatch")):
                if candidate[field] != review[field]:
                    reasons.append(code)
            if not candidate["_identity_valid"]:
                reasons.append("baseline_hunk_identity_not_unique_or_valid")
            if not reasons:
                previous = candidate
        exact_current = new_hash.get(review["hunk_sha256"], [])
        if previous is not None:
            if not exact_current:
                reasons.append("missing_current_exact_hash")
                if new_id.get(review["hunk_id"]):
                    reasons.append("same_current_locator_has_different_hash")
            elif len(exact_current) != 1:
                reasons.append("ambiguous_current_exact_hash")
            elif not exact_current[0]["_identity_valid"]:
                reasons.append("current_hunk_identity_not_unique_or_valid")
            elif exact_current[0]["printed_page"] != previous["printed_page"]:
                reasons.append("current_page_mismatch_for_hash")
            else:
                fresh = exact_current[0]
        reference_checks = []
        for position, correction_id in enumerate(review["_ids"] or [], 1):
            reference_checks.append({"prior_review_record": review["_record"], "printed_page": review["printed_page"],
                                     "historical_hunk_id": review["hunk_id"], "reference_position": position, "correction_id": correction_id,
                                     "historical_correction_ids_sha256": sha(review["correction_ids"].encode()),
                                     "binding_status": bindings_by_id[correction_id]["binding_status"],
                                     "baseline_candidate_association": association(previous, correction_id),
                                     "current_candidate_association": association(fresh, correction_id),
                                     "current_hunk_id": fresh["hunk_id"] if fresh is not None else "", "review_status": "pending"})
        referenced.extend(reference_checks)
        if fresh is not None and not reasons:
            proposals.append({**historical(review, review_input_hash), "baseline_hunk_record": previous["_record"],
                              "current_hunk_record": fresh["_record"], "current_hunk_id": fresh["hunk_id"],
                              "proposal_basis": "unique exact full hash and page; prior identity verified against baseline",
                              "baseline_candidate_correction_ids": previous["candidate_correction_ids"],
                              "current_candidate_correction_ids": fresh["candidate_correction_ids"],
                              "reference_metadata_status": "requires_manual_attention" if review["_ids_status"] in {"malformed", "duplicate_ids"} else "no_referenced_ids" if not review["_ids"] else "parsed",
                              "reference_metadata_attention_count": int(review["_ids_status"] in {"malformed", "duplicate_ids"}),
                              "referenced_binding_attention_count": sum(row["binding_status"] != "unchanged_fingerprint" for row in reference_checks),
                              "referenced_current_candidate_absent_count": sum(row["current_candidate_association"] == "not_listed" for row in reference_checks)})
            matched_baseline.add(previous["_record"])
            matched_current.add(fresh["_record"])
        else:
            unmatched_prior.append({**historical(review, review_input_hash), "baseline_hunk_records": record_numbers(baseline_rows),
                                    "current_exact_hash_records": record_numbers(exact_current), "unmatched_reasons": ";".join(reasons)})
            for code in reasons:
                if code not in review["_errors"]:
                    issue(issues, "prior review", review, "hunk_sha256" if "hash" in code else "hunk_id", code)
    unmatched = {}
    for side, rows, matched, opposite_id, opposite_hash in (
            ("baseline", baseline, matched_baseline, new_id, new_hash),
            ("current", current, matched_current, old_id, old_hash)):
        output = []
        for row in rows:
            if row["_record"] in matched:
                continue
            reasons = list(row["_errors"])
            opposite = opposite_hash.get(row["hunk_sha256"], [])
            if not opposite:
                reasons.append("no_" + ("current" if side == "baseline" else "baseline") + "_exact_hash")
                if opposite_id.get(row["hunk_id"]):
                    reasons.append("same_opposite_locator_has_different_hash")
            elif len(opposite) != 1:
                reasons.append("ambiguous_opposite_exact_hash")
            if side == "baseline" and not review_by_id.get(row["hunk_id"]):
                reasons.append("no_prior_review_for_locator")
            else:
                reasons.append("no_unique_validated_rebinding")
            output.append({"inventory_record": row["_record"], **{field: row[field] for field in HUNK_REQUIRED},
                           **{field: row.get(field, "") for field in LOCATOR_FIELDS},
                           "canonical_record_sha256": row["_record_sha256"], "opposite_exact_hash_records": record_numbers(opposite),
                           "unmatched_reasons": ";".join(reasons), "review_status": "pending"})
        unmatched[side] = output
    history_fields = list(historical(reviews[0], review_input_hash)) if reviews else [
        "prior_review_record", "printed_page", "historical_hunk_id", "hunk_sha256", "historical_decision", "historical_correction_ids",
        "historical_correction_ids_sha256", "historical_correction_ids_parse_status", "historical_reason_sha256", "historical_reviewed_utc",
        "historical_reviewer_sha256", "historical_review_record_sha256", "historical_review_input_sha256", "review_status"]
    unmatched_fields = ["inventory_record", *HUNK_REQUIRED, *LOCATOR_FIELDS, "canonical_record_sha256", "opposite_exact_hash_records", "unmatched_reasons", "review_status"]
    tables = {
        "REBINDING_PROPOSALS.tsv": (history_fields + ["baseline_hunk_record", "current_hunk_record", "current_hunk_id", "proposal_basis", "baseline_candidate_correction_ids", "current_candidate_correction_ids", "reference_metadata_status", "reference_metadata_attention_count", "referenced_binding_attention_count", "referenced_current_candidate_absent_count"], sorted(proposals, key=page_order)),
        "UNMATCHED_PRIOR_REVIEWS.tsv": (history_fields + ["baseline_hunk_records", "current_exact_hash_records", "unmatched_reasons"], sorted(unmatched_prior, key=page_order)),
        "UNMATCHED_BASELINE_HUNKS.tsv": (unmatched_fields, sorted(unmatched["baseline"], key=page_order)),
        "UNMATCHED_CURRENT_HUNKS.tsv": (unmatched_fields, sorted(unmatched["current"], key=page_order)),
        "REFERENCED_ID_CHECKS.tsv": (["prior_review_record", "printed_page", "historical_hunk_id", "reference_position", "correction_id", "historical_correction_ids_sha256", "binding_status", "baseline_candidate_association", "current_candidate_association", "current_hunk_id", "review_status"], sorted(referenced, key=page_order)),
        "ID_BINDING_COMPARISON.tsv": (["correction_id", "identity_kind", "binding_status", "referenced_prior_review_records", "baseline_binding_records", "current_binding_records", "baseline_ledger_record", "current_ledger_record", "baseline_row_fingerprint", "current_row_fingerprint", "baseline_id_source_sha256", "current_id_source_sha256", "ledger_record_changed", "id_source_changed", "review_status"], bindings),
        "BINDING_METADATA.tsv": (["inventory_side", "binding_record", "correction_id", "identity_kind", "ledger_record", "row_fingerprint", "id_source_sha256", "canonical_record_sha256", "validation", "review_status"], binding_metadata),
        "VALIDATION_ISSUES.tsv": (["dataset", "record_number", "printed_page", "hunk_id", "correction_id", "field", "issue", "original_value_sha256", "review_status"], sorted(issues, key=page_order)),
    }
    statuses = Counter(row["binding_status"] for row in bindings)
    summary = {"baseline_hunks": len(baseline), "prior_review_rows": len(reviews), "current_hunks": len(current),
               "unique_exact_rebinding_proposals": len(proposals), "unmatched_prior_reviews": len(unmatched_prior),
               "unmatched_baseline_hunks": len(unmatched["baseline"]), "unmatched_current_hunks": len(unmatched["current"]),
               "validation_issues": len(issues), "referenced_id_checks": len(referenced),
               "malformed_prior_correction_id_fields": sum(row["_ids_status"] == "malformed" for row in reviews),
               "referenced_ids_not_in_current_candidates": sum(row["current_candidate_association"] == "not_listed" for row in referenced),
               **{"bindings_" + status: statuses[status] for status in ("unchanged_fingerprint", "changed_fingerprint", "missing_current_binding", "new_current_binding", "missing_both_bindings", "ambiguous_binding", "invalid_binding")}}
    return tables, summary


def guard_path(path: Path) -> None:
    absolute = path.absolute()
    if ".." in absolute.parts or any(part.casefold() in BLOCKED_DIRS for part in absolute.parts):
        raise ValueError("A selected path passes through a protected context folder or parent traversal.")
    if any(item.is_symlink() for item in (absolute, *absolute.parents)):
        raise ValueError("Selected paths must not pass through symbolic links.")


def relative_path(root: Path, name: str | Path) -> Path:
    raw = str(name)
    require_safe_name(raw)
    path = root / raw
    guard_path(path)
    return path


def capture(path: Path) -> bytes:
    guard_path(path)
    if not path.is_file():
        raise ValueError("A required input is not a regular file.")
    before = path.stat()
    data = read_snapshot(path)
    guard_path(path)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError("An input changed during capture; no report was installed.")
    return data


def recheck_snapshots(snapshots: list[tuple[str, Path, bytes | None]]) -> None:
    for _, path, data in snapshots:
        guard_path(path)
        if data is None:
            if path.exists():
                raise RuntimeError("An optional inventory manifest appeared during the run; no report was installed.")
        elif capture(path) != data:
            raise RuntimeError("An input snapshot changed during the run; no report was installed.")


def payloads_for(tables: dict, summary: dict, *, filter_derived: bool) -> dict[str, bytes]:
    payloads, filtering = {}, []
    for name, (fields, rows) in tables.items():
        presented = []
        for number, row in enumerate(rows, 1):
            output, changed = dict(row), []
            if filter_derived:
                for field, value in row.items():
                    if not isinstance(value, str):
                        continue
                    filtered = safe_location(value)
                    if filtered == value:
                        continue
                    output[field] = filtered
                    changed.append(field)
                    filtering.append({"report_file": name, "report_record": number, "field": field,
                                      "original_value_sha256": sha(value.encode()), "filtered_value_sha256": sha(filtered.encode()),
                                      "privacy_pattern_kinds": ";".join(sorted({kind for _, kind in privacy_findings(value)})),
                                      "status": "explicit presentation filtering; original input unchanged"})
            output["privacy_filtered_fields"] = ",".join(changed)
            presented.append(output)
        payloads[name] = tsv_bytes(fields + ["privacy_filtered_fields"], presented)
    payloads["PRIVACY_FILTERING.tsv"] = tsv_bytes(["report_file", "report_record", "field", "original_value_sha256", "filtered_value_sha256", "privacy_pattern_kinds", "status"], filtering)
    summary["privacy_filtered_metadata_fields"] = len(filtering)
    payloads["SUMMARY.json"] = (json.dumps(summary, indent=2) + "\n").encode()
    report = ["# Interim French hunk rebinding proposals", "", "Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + ".", "",
              "Every review_status is pending. Historical decisions are retained only as historical metadata; this report makes no new decision and writes no review table or other live record.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report += [f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items()]
    report += ["", "## Interpretation and limitations", "",
               "REBINDING_PROPOSALS.tsv requires a unique valid prior hunk identity, exact agreement with the baseline hunk ID, printed page and full SHA-256, and one uniquely identified current hunk with the same full SHA-256 and page. A current hunk ID may differ. Baseline, current and historical duplicate IDs or hashes prevent a proposal for the affected identity. An exact hunk association can coexist with malformed or duplicate historical correction references; those proposals retain an explicit reference metadata attention flag and count, and remain pending.", "",
               "The complete inventory hunk hash binds the page, operation, offsets and raw fragments. No hash is truncated. No fuzzy, content-only or moved-content matching is attempted. Changed offsets alone can leave otherwise similar text unmatched. A reused locator with a different hash is diagnostic only and never establishes a correspondence.", "",
               "UNMATCHED_PRIOR_REVIEWS.tsv accounts for every historical row without a unique proposal. The two UNMATCHED hunk tables also include unreviewed inventory rows. VALIDATION_ISSUES.tsv preserves duplicate, invalid, missing, changed and ambiguous conditions by input record locator and value hash. Record numbers count data rows, starting at one; embedded newlines do not increment them.", "",
               "ID_BINDING_COMPARISON.tsv compares all supplied correction IDs, plus every parsed historical R ID, across the two binding tables. BINDING_METADATA.tsv retains every binding row, including duplicates. Fingerprint changes, missing or new bindings, ledger-record movement and identity-source changes are separate metadata. REFERENCED_ID_CHECKS.tsv preserves reference order and reports whether each historical R ID is still listed among the uniquely matched current hunk's candidates. Neither unchanged fingerprints nor candidate presence validate a correction. Malformed reference fields remain explicitly flagged; no partial IDs are guessed.", "",
               "Correction IDs must use a positive integer with at least six digits and no excess leading zeroes. R identifies a stable review ID. L is explicitly labelled snapshot_local_ledger_locator: comparison of matching L labels and their metadata does not assert stable cross-snapshot identity. Historical correction references accept canonical R IDs only.", "",
               "Historical reason and reviewer prose and binding identity-source prose are represented only by SHA-256. Canonical record hashes bind the header and ordered parsed cells, while INPUT_HASHES.tsv preserves the exact complete input-file hashes, including the historical review table. Original quoting and line endings are bound by file hashes, not reconstructed from record hashes.", "",
               "Only the explicit review TSV, the two inventories' hunk and binding tables, and named optional provenance manifests are read. Manifests are hashed without following their referenced paths. No TeX, scan, correction ledger, review event, page log or readiness record is opened. All supplied input bytes and optional-manifest presence are checked again immediately before exclusive installation.", "",
               "Current inventory freshness is a separate prerequisite: generate it from the intended current source and ledger state before invoking this helper. This utility does not verify inventory hashes against TeX, recompute raw-fragment hashes, authenticate inventory provenance, check scan readings, infer content equivalence, or satisfy an editorial or final-readiness gate. Inventory sidecars, when present, are provenance snapshots only.", "",
               ("Explicit derived-metadata privacy filtering was requested. Every altered presentation cell has a marker and original/filtered hashes in PRIVACY_FILTERING.tsv. Comparison, identity validation and provenance use original captured values; no evidentiary input is rewritten."
                if filter_derived else "Copied metadata is exact. A privacy-pattern finding or inspection blocker aborts installation; no evidentiary value is silently rewritten."), ""]
    payloads["REPORT.md"] = "\n".join(report).encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Prepared report metadata contains a privacy pattern or inspection blocker; no report was installed.")
    return payloads


def run(args) -> dict:
    root = Path(args.root).absolute()
    guard_path(root)
    if not root.is_dir():
        raise ValueError("A regular delivery root directory is required.")
    root = root.resolve()
    baseline_dir = relative_path(root, args.baseline_inventory)
    current_dir = relative_path(root, args.current_inventory)
    review_path = relative_path(root, args.review_table)
    output = relative_path(root, args.output)
    if not baseline_dir.is_dir() or not current_dir.is_dir():
        raise ValueError("Both supplied inventory directories must exist.")
    if review_path.suffix != ".tsv":
        raise ValueError("The explicitly supplied historical review table must be a TSV file.")
    if "interim" not in output.name.casefold():
        raise ValueError("The fresh report directory must have an explicitly interim name.")
    if (output.exists() or output == root or any(folder == output or folder in output.parents
            for folder in [root / "sources", root / "pdf", root / "second-reading", baseline_dir, current_dir])):
        raise ValueError("Use a fresh report directory outside source, PDF, review-state and input-inventory directories; existing paths are never overwritten.")
    snapshots = []
    def remember(role: str, path: Path, *, optional: bool = False) -> bytes | None:
        guard_path(path)
        data = None if optional and not path.exists() else capture(path)
        snapshots.append((role, path, data))
        return data
    inputs = {}
    for side, directory in (("baseline", baseline_dir), ("current", current_dir)):
        inputs[side] = table(remember(side + " hunk inventory", directory / "FRENCH_LAYER_DIFFERENCES.tsv"), HUNK_REQUIRED)
        inputs[side + "_bindings"] = table(remember(side + " ledger ID bindings", directory / "LEDGER_ID_BINDINGS.tsv"), BINDING_FIELDS)
        for name in OPTIONAL_MANIFESTS:
            remember(side + " provenance manifest", directory / name, optional=True)
    review_data = remember("historical review table", review_path)
    reviews = table(review_data, REVIEW_FIELDS, exact=True)
    tables, summary = compare(inputs["baseline"], reviews, inputs["current"], inputs["baseline_bindings"], inputs["current_bindings"], sha(review_data))
    tables["INPUT_HASHES.tsv"] = (["role", "file", "state", "bytes", "sha256"],
                                   [{"role": role, "file": path.relative_to(root).as_posix(),
                                     "state": "present" if data is not None else "absent optional manifest",
                                     "bytes": len(data) if data is not None else "", "sha256": sha(data) if data is not None else ""}
                                    for role, path, data in snapshots])
    payloads = payloads_for(tables, summary, filter_derived=bool(getattr(args, "privacy_filter_derived", False)))
    # Preparation never writes inside an input snapshot or the final directory.
    with tempfile.TemporaryDirectory(prefix="french-rebind-prepared-", dir=root) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        # Validate the bytes actually prepared for installation, not just their
        # in-memory precursors. Any input edit leaves the final path absent.
        if any((prepared / name).read_bytes() != data or scan_bytes(name, (prepared / name).read_bytes()) for name, data in payloads.items()):
            raise RuntimeError("Prepared output changed or failed privacy inspection; no report was installed.")
        guard_path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        guard_path(output)
        recheck_snapshots(snapshots)
        output.mkdir()  # Exclusive reservation, including an existing empty directory.
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
    print(json.dumps({**summary, "report_directory": output.relative_to(root).as_posix(), "review_status": "pending"}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline-inventory", required=True, help="Baseline inventory directory relative to root")
    parser.add_argument("--review-table", required=True, help="Historical review TSV relative to root, with the exact documented schema")
    parser.add_argument("--current-inventory", required=True, help="Fresh current inventory directory relative to root; freshness is a separate prerequisite")
    parser.add_argument("--output", required=True, help="New interim report directory relative to root")
    parser.add_argument("--privacy-filter-derived", action="store_true", help="Explicitly filter presented metadata only, with per-cell markers and original/filtered hashes")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
