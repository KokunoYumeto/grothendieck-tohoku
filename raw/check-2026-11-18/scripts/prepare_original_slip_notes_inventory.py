"""Prepare exact pending-notes metadata; make no reading or note judgment.

Only the promoted ledger, an explicitly selected French inventory/review and
optional supplied primary link decisions are read. No context or scan is opened.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import re

from math_literal_groups import promoted_entries
from privacy_guard import scan_bytes


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parsed(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")), delimiter="\t")
    fields = reader.fieldnames or []
    if not fields or len(fields) != len(set(fields)):
        raise ValueError("Missing or duplicate input columns.")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Malformed input TSV row.")
    return fields, rows


def tsv(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--french-inventory", required=True)
    parser.add_argument("--primary-links")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    def relative(name):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Use a delivery-relative path.")
        target = root / path
        if target.is_symlink() or root not in target.resolve().parents:
            raise ValueError("Input or output escapes the delivery tree.")
        return target

    output = relative(args.output)
    if output.exists() or "interim" not in output.name or output.parent != root:
        raise ValueError("Use a fresh, top-level interim report directory.")
    names = {
        "ledger": "CORRECTIONS.tsv",
        "French primary review": "FRENCH_LAYER_REVIEW.tsv",
        "French inventory": (Path(args.french_inventory) / "FRENCH_LAYER_DIFFERENCES.tsv").as_posix(),
    }
    if args.primary_links:
        names["supplied primary links"] = args.primary_links
    captured = {role: (name, relative(name).read_bytes()) for role, name in names.items()}
    ledger_fields, _ = parsed(captured["ledger"][1])
    entries = promoted_entries(captured["ledger"][1])
    by_id = {entry["id"]: entry for entry in entries}
    if len(by_id) != len(entries):
        raise ValueError("Duplicate stable correction identity.")
    active = [entry for entry in entries if entry["active"]]
    slips = [entry for entry in active if entry["row"]["kind"] == "misprint of the original"]
    _, reviews = parsed(captured["French primary review"][1])
    hunk_fields, hunks = parsed(captured["French inventory"][1])
    review_by_id = {row["hunk_id"]: row for row in reviews}
    hunk_by_id = {row["hunk_id"]: row for row in hunks}
    if len(review_by_id) != len(reviews) or len(hunk_by_id) != len(hunks) or set(review_by_id) != set(hunk_by_id):
        raise ValueError("French hunk/review identity sets do not match exactly.")
    references, enriched_hunks, linked_hunks = [], [], defaultdict(list)
    for hunk in hunks:
        review = review_by_id[hunk["hunk_id"]]
        if (hunk["printed_page"], hunk["hunk_sha256"]) != (review["printed_page"], review["hunk_sha256"]):
            raise ValueError("French review page/hash binding is stale.")
        enriched_hunks.append({**hunk, **{"primary_" + key: review[key] for key in
            ("decision", "correction_ids", "reason", "reviewed_utc", "reviewer")},
            "notes_drafting_status": "pending primary notes drafting"})
        ids = review["correction_ids"].split(",") if review["correction_ids"] else []
        for position, rid in enumerate(ids, 1):
            if not re.fullmatch(r"R[0-9]{6,}", rid) or rid not in by_id:
                raise ValueError("Unresolved explicit French correction reference.")
            entry = by_id[rid]
            references.append({"hunk_id": hunk["hunk_id"], "printed_page": hunk["printed_page"],
                "hunk_sha256": hunk["hunk_sha256"], "reference_position": position,
                "correction_id": rid, "row_fingerprint": entry["fingerprint"],
                "ledger_record": entry["ledger_record"], "ledger_activity": "active" if entry["active"] else "withdrawn",
                **{"ledger_" + key: value for key, value in entry["row"].items()},
                "notes_drafting_status": "pending primary notes drafting"})
            linked_hunks[rid].append(hunk["hunk_id"])

    buckets = defaultdict(list)
    for entry in slips:
        row = entry["row"]
        buckets[tuple(row[key] for key in ("printed_page", "old", "new", "evidence"))].append(entry)
    members, groups, cross_layer_pairs = [], [], 0
    for key, bucket in buckets.items():
        merge = len(bucket) == 2 and Counter(entry["row"]["layer"] for entry in bucket) == Counter({"corrected": 1, "English": 1})
        selected = [bucket] if merge else [[entry] for entry in bucket]
        cross_layer_pairs += int(merge)
        for batch in selected:
            ids = sorted(entry["id"] for entry in batch)
            identity = json.dumps([key, ids], ensure_ascii=False, separators=(",", ":")).encode()
            gid = "NS" + sha(identity)
            groups.append({"notes_group_id": gid, **dict(zip(("printed_page", "old", "new", "evidence"), key)),
                "member_count": len(batch), "correction_ids": ",".join(ids),
                "grouping_basis": "exact same-page old/new/evidence; one French and one English row" if merge else "singleton; no cross-layer merge",
                "notes_drafting_status": "pending primary notes drafting"})
            for entry in batch:
                members.append({"notes_group_id": gid, "correction_id": entry["id"],
                    "row_fingerprint": entry["fingerprint"], "ledger_record": entry["ledger_record"],
                    **entry["row"], "explicit_french_hunk_references": ",".join(linked_hunks.get(entry["id"], [])),
                    "notes_drafting_status": "pending primary notes drafting"})
    members.sort(key=lambda row: int(row["correction_id"][1:]))
    if {row["correction_id"] for row in members} != {entry["id"] for entry in slips} or len(members) != len(slips):
        raise ValueError("Original-slip row coverage is not exact.")

    counts = []
    for scope, selected in (("all active ledger rows", active), ("active original-slip rows", slips)):
        for (layer, kind), count in sorted(Counter((entry["row"]["layer"], entry["row"]["kind"]) for entry in selected).items()):
            counts.append({"scope": scope, "layer": layer, "kind": kind, "rows": count})
    verdict_counts = Counter(row["decision"] for row in reviews)
    summary = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ledger_rows": len(entries), "active_rows": len(active), "withdrawn_rows_excluded": len(entries) - len(active),
        "original_slip_rows": len(slips), "original_slip_groups": len(groups), "exact_cross_layer_pairs": cross_layer_pairs,
        "original_slip_rows_by_layer": dict(Counter(entry["row"]["layer"] for entry in slips)),
        "French_hunks": len(hunks), "French_hunks_with_primary_verdict": len(reviews),
        "French_hunk_reference_rows": len(references), "French_hunk_reference_unique_ids": len({row["correction_id"] for row in references}),
        "French_references_to_withdrawn_rows": sum(row["ledger_activity"] == "withdrawn" for row in references),
        "original_slip_rows_without_explicit_French_hunk_reference": sum(not linked_hunks.get(entry["id"]) for entry in slips),
        "French_primary_verdict_counts": dict(verdict_counts),
        "French_metadata_only_by_exact_explicit_verdict": verdict_counts["nonprinting layer metadata"],
        "notes_drafting_status": "pending for every row, group and hunk; no note drafted"}
    payloads = {
        "ORIGINAL_SLIP_ROWS.tsv": tsv(list(members[0]), members),
        "ORIGINAL_SLIP_EXACT_GROUPS.tsv": tsv(list(groups[0]), groups),
        "FRENCH_REVIEW_HUNKS.tsv": tsv(list(enriched_hunks[0]), enriched_hunks),
        "FRENCH_HUNK_CORRECTION_REFERENCES.tsv": tsv(list(references[0]), references),
        "COUNTS_BY_LAYER_AND_KIND.tsv": tsv(["scope", "layer", "kind", "rows"], counts),
        "FRENCH_PRIMARY_VERDICT_COUNTS.tsv": tsv(["decision", "hunks"], [{"decision": key, "hunks": value} for key, value in verdict_counts.items()]),
        "INPUT_HASHES.tsv": tsv(["role", "file", "bytes", "sha256"], [{"role": role, "file": name, "bytes": len(data), "sha256": sha(data)} for role, (name, data) in captured.items()]),
    }
    if "supplied primary links" in captured:
        fields, links = parsed(captured["supplied primary links"][1])
        for link in links:
            if hunk_by_id[link["hunk_id"]]["hunk_sha256"] != link["hunk_sha256"] or by_id[link["correction_id"]]["fingerprint"] != link["row_fingerprint"]:
                raise ValueError("Supplied primary link has a stale hunk or correction fingerprint.")
        payloads["SUPPLIED_PRIMARY_LINK_DECISIONS.tsv"] = tsv(fields, links)
        summary["supplied_primary_link_decisions"] = len(links)
    payloads["SUMMARY.json"] = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode()
    payloads["REPORT.md"] = (
        "# Original-slip notes inventory: drafting pending\n\n"
        "This is an exact metadata inventory for the primary notes writer. No note, proof judgment, scan reading, semantic merger or new original-slip verdict is supplied. No context folder or scan was opened.\n\n"
        "ORIGINAL_SLIP_ROWS.tsv preserves each active ledger row whose existing kind is misprint of the original, its stable R ID/current fingerprint and every ledger field. ORIGINAL_SLIP_EXACT_GROUPS.tsv merges only an exact same-page old/new/evidence pair consisting of one corrected-French row and one English row; all other rows remain singletons. Statements and locators remain exact in the member table.\n\n"
        "FRENCH_REVIEW_HUNKS.tsv retains every selected inventory fragment and every existing primary verdict/reason. Its inventory review_status is historical mechanical metadata; primary_decision is the existing primary verdict. All notes_drafting_status fields remain pending. FRENCH_HUNK_CORRECTION_REFERENCES.tsv preserves every explicit reference, with its current row fingerprint and complete ledger fields. No absent literal candidate or unlinked ledger row is treated as an editorial verdict.\n\n"
        "The metadata-only count uses only the exact existing decision label nonprinting layer metadata. Other decision labels are reported separately and are not reclassified. Any supplied primary link decisions are copied with their existing hashes and reasons; they do not constitute a blanket decision on other links.\n\n"
        "INPUT_HASHES.tsv binds the exact inputs. No evidence or decision prose is privacy-filtered; an inspection finding blocks report installation. Source text, ledger, French review and CHECK_RECORD are not edited.\n"
    ).encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise ValueError("Prepared inventory has a privacy finding or inspection blocker.")
    if any(relative(name).read_bytes() != data for name, data in captured.values()):
        raise ValueError("An input changed during preparation; no report installed.")
    output.mkdir()
    for name, data in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({**summary, "output": output.relative_to(root).as_posix()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
