"""Refresh mechanical CHECK_RECORD metadata after final second-read promotion.

Only ledger counts, numeric source-line ranges and a marked summary block
can change. Narrative, verdicts and reading timestamps are protected. Page
files are used only to count physical line breaks; no wording or TeX is read
for an editorial decision. Mathematical significance is never inferred.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile

from second_reading import FIELDS, PAGES, fingerprint
import second_reading as review_workbench
from final_validate import confidence_annotation, privacy_findings
from control_word_inventory import BLOCKED_DIRS, read_snapshot, require_safe_name
from privacy_guard import safe_location, scan_bytes

LAYERS = ["as-printed", "corrected", "English", "build"]
KINDS = ["reading", "misprint of the original", "translation", "typesetting", "structure"]
READING_LAYERS = ["as-printed", "corrected", "English"]
PAGE_ORDER = {str(page): index for index, page in enumerate(PAGES)}
PAGE_ORDER[""] = len(PAGES)
MATH_CANDIDATE_KINDS = {"misprint of the original", "translation"}
MATH_REQUIRED = ["correction_id", "row_fingerprint", "mathematical_change", "summary", "reason"]
MATH_FIELDS = MATH_REQUIRED + ["ledger_record", "file", "layer", "printed_page", "line", "statement", "kind", "old", "new"]
BEGIN = "<!-- TOHOKU_MECHANICAL_SUMMARY_BEGIN -->"
END = "<!-- TOHOKU_MECHANICAL_SUMMARY_END -->"
PAGE_HEADING = re.compile(r"(?m)^#{2,3}\s+(?:Printed\s+)?(?:page|p\.)\s*(\d{3})\b[^\r\n]*(?:\r?\n|$)", re.I)
COUNT_LINE = re.compile(r"(?m)^(?P<label>- Corrections in this pass: )(?P<layers>[^\r\n]*?)(?P<separator>\. Kinds: )(?P<kinds>[^\r\n]*?)\.(?P<eol>\r?\n|$)")
SOURCES_LINE = re.compile(r"(?m)^- Sources compared: [^\r\n]*(?:\r?\n|$)")
SOURCE_RANGE = re.compile(r"(?P<prefix>`sources/(?P<tree>dip|fr|en)/p(?P<page>\d{3})\.tex`, lines )(?P<first>\d+)(?P<dash>[–-])(?P<last>\d+)")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tsv_data(fields: list[str], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def read_tsv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields, rows = reader.fieldnames or [], list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Malformed TSV record in " + path.name)
    return fields, rows


def load_rows(root: Path, review_map: Path | None) -> list[dict]:
    fields, rows = read_tsv(root / "CORRECTIONS.tsv")
    if fields != FIELDS:
        raise ValueError("The live correction ledger does not have the required column schema and order.")
    mapping = {}
    if review_map:
        map_fields, entries = read_tsv(review_map)
        if not {"review_id", "export_record", "status"}.issubset(map_fields):
            raise ValueError("The supplied review map lacks its required columns.")
        for entry in entries:
            if entry["export_record"]:
                position = int(entry["export_record"])
                if position in mapping:
                    raise ValueError("A review map cannot assign two IDs to one ledger record.")
                mapping[position] = entry
    result, seen = [], set()
    for position, row in enumerate(rows, 1):
        if row["layer"] not in LAYERS or row["kind"] not in KINDS or row["printed_page"] not in PAGE_ORDER:
            raise ValueError("Unrecognized layer, kind or printed page at ledger record " + str(position))
        ids = re.findall(r"\bR\d{6,}\b", row["confidence"])
        if len(set(ids)) > 1:
            raise ValueError("Multiple review IDs occur in one confidence cell.")
        mapped = mapping.get(position, {})
        map_status = mapped.get("status", "").split(";", 1)[0].strip()
        if mapped and map_status not in {"pending", "confirmed", "amended", "withdrawn"}:
            raise ValueError("The supplied review map has an unrecognized status at record " + str(position))
        if ids and mapped and ids[0] != mapped["review_id"]:
            raise ValueError("Confidence annotation and explicit review map disagree.")
        if mapped.get("row_fingerprint") and mapped["row_fingerprint"] != fingerprint(row):
            raise ValueError("The supplied review map does not match the current correction content at record " + str(position))
        annotation = confidence_annotation(row["confidence"])
        if mapped and annotation:
            if map_status != annotation["verdict"]:
                raise ValueError("The supplied review-map status disagrees with the current confidence verdict at record " + str(position))
            if mapped.get("last_event", "") != annotation["event_id"]:
                raise ValueError("The supplied review-map last event disagrees with the current confidence annotation at record " + str(position))
        correction_id = ids[0] if ids else mapped.get("review_id", f"L{position:06d}")
        if not re.fullmatch(r"[RL]\d{6,}", correction_id):
            raise ValueError("A correction locator must be a generated review ID or ledger-record ID.")
        if correction_id in seen:
            raise ValueError("Correction IDs must be unique; provide the matching review export map if needed.")
        seen.add(correction_id)
        explicitly_withdrawn = bool(re.search(r";\s*second reading withdrawn\s*(?:;|$)", row["confidence"], re.I))
        explicitly_withdrawn |= map_status == "withdrawn"
        result.append({"id": correction_id, "ledger_record": position, "fingerprint": fingerprint(row), "active": not explicitly_withdrawn, "row": row})
    return result


def row_order(entry: dict) -> tuple:
    return PAGE_ORDER[entry["row"]["printed_page"]], entry["ledger_record"]


def load_classifications(path: Path | None, entries: list[dict]) -> dict:
    if path is None:
        return {}
    fields, rows = read_tsv(path)
    if not set(MATH_REQUIRED).issubset(fields):
        raise ValueError("Mathematical classification input lacks required columns.")
    current = {entry["id"]: entry for entry in entries}
    result = {}
    for row in rows:
        correction_id = row["correction_id"]
        if correction_id in result or correction_id not in current:
            raise ValueError("Duplicate or stale mathematical-classification ID: " + correction_id)
        if row["row_fingerprint"] != current[correction_id]["fingerprint"]:
            raise ValueError("The correction changed after manual classification: " + correction_id)
        choice = row["mathematical_change"].strip().lower()
        if choice not in {"yes", "no", "pending"}:
            raise ValueError("Mathematical change must be explicitly yes, no, or pending.")
        if choice in {"yes", "no"} and not row["reason"].strip():
            raise ValueError("An explicit yes/no mathematical classification needs a reason: " + correction_id)
        if choice == "yes" and not row["summary"].strip():
            raise ValueError("A mathematical change needs a reviewer-supplied one-line summary: " + correction_id)
        if privacy_findings(row["summary"] + "\n" + row["reason"]):
            raise ValueError("A mathematical summary/reason contains a possible private path or email address.")
        result[correction_id] = {"choice": choice, "summary": row["summary"], "reason": row["reason"]}
    return result


def pending_math_rows(entries: list[dict], all_kinds: bool = False) -> list[dict]:
    selected = sorted((entry for entry in entries if entry["active"] and (all_kinds or entry["row"]["kind"] in MATH_CANDIDATE_KINDS)), key=row_order)
    rows = []
    for entry in selected:
        row = entry["row"]
        rows.append({"correction_id": entry["id"], "row_fingerprint": entry["fingerprint"],
                     "mathematical_change": "pending", "summary": "", "reason": "",
                     "ledger_record": entry["ledger_record"],
                     **{field: row[field] for field in MATH_FIELDS if field in row}})
    return rows


def prepare_math(args) -> None:
    root = args.root.resolve()
    entries = load_rows(root, args.review_map)
    output = (root / args.output).resolve()
    if output == root / "CORRECTIONS.tsv" or root not in output.parents or (root / "sources") in output.parents:
        raise ValueError("The classification template must be a separate file inside the delivery tree, outside sources.")
    rows = pending_math_rows(entries, args.all_kinds)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(tsv_data(MATH_FIELDS, rows))
    print(f"Prepared {len(rows)} pending manual classification rows in {output.name}. No mathematical significance was inferred.")


def prepare_math_interim(args) -> None:
    """Create pending templates from captured, verified effective review rows."""
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside protected context folders.")
    if args.review_map:
        raise ValueError("The effective-state inventory uses verified review history, not an export map.")
    for relative in (args.output, args.review_dir):
        if relative.is_absolute():
            raise ValueError("Use paths relative to the delivery root.")
        require_safe_name(relative.as_posix())
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if part.casefold() in BLOCKED_DIRS or cursor.is_symlink():
                raise ValueError("Interim inputs and outputs cannot pass through symlinks or protected context folders.")
    output, directory = (root / args.output).resolve(), (root / args.review_dir).resolve()
    if "interim" not in output.name.casefold() or output.exists():
        raise ValueError("Use a fresh output directory explicitly containing interim.")
    if any(output == root / name or root / name in output.parents for name in ("sources", "pdf", "second-reading")) or output == directory or directory in output.parents:
        raise ValueError("The report must be outside sources, PDFs and review state.")
    if any(directory == root / name or root / name in directory.parents for name in ("sources", "pdf")):
        raise ValueError("The review directory cannot point into sources or PDFs.")
    ledger = root / "CORRECTIONS.tsv"
    paths = {"CORRECTIONS.tsv": ledger}
    paths.update({args.review_dir.as_posix() + "/" + name: directory / name for name in
                  ("REVIEW_META.tsv", "ROW_REGISTRY.tsv", "REVIEW_EVENTS.tsv", "REVIEW_INDEX.tsv")})
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ValueError("Every required ledger/review input must be a regular file.")
    # The existing shared lock is read-only. It prevents a history/index write
    # midway through capture without creating any live lock or state file.
    with review_workbench.history_lock(directory):
        captured = {name: read_snapshot(path) for name, path in paths.items()}
    with tempfile.TemporaryDirectory(prefix="math-review-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_review = snapshot_root / "second-reading"
        snapshot_review.mkdir()
        snapshot_ledger = snapshot_root / "CORRECTIONS.tsv"
        snapshot_ledger.write_bytes(captured["CORRECTIONS.tsv"])
        for name in ("REVIEW_META.tsv", "ROW_REGISTRY.tsv", "REVIEW_EVENTS.tsv", "REVIEW_INDEX.tsv"):
            (snapshot_review / name).write_bytes(captured[args.review_dir.as_posix() + "/" + name])
        _, registry, events, states = review_workbench.load_project(snapshot_review, snapshot_ledger)
        ledger_rows, _ = review_workbench.read_ledger(snapshot_ledger)
        assignment, unregistered = review_workbench.align(ledger_rows, states, review_workbench.previous_positions(snapshot_review, states))
        expected_index = [{field: str(value) for field, value in row.items()}
                          for row in review_workbench.index_rows(ledger_rows, states, assignment)]
        actual_index = review_workbench.read_table(snapshot_review / "REVIEW_INDEX.tsv", review_workbench.INDEX_FIELDS)
        if actual_index != expected_index:
            raise ValueError("The captured review index is stale or disagrees with verified current history/row alignment.")
    entries, projection = [], []
    for review_id in review_workbench.sorted_ids(states, assignment):
        state, position = states[review_id], assignment.get(review_id)
        row = dict(state["row"])
        entry = {"id": review_id, "ledger_record": position or "", "fingerprint": fingerprint(row),
                 "active": state["status"] != "withdrawn", "row": row}
        entries.append(entry)
        projection.append({"correction_id": review_id, "ledger_record": position or "", "review_status": state["status"],
                           "last_review_event": state["last_event"], "file": row["file"], "layer": row["layer"],
                           "printed_page": row["printed_page"], "line": row["line"], "kind": row["kind"],
                           "current_ledger_fingerprint": fingerprint(ledger_rows[position - 1]) if position else "",
                           "effective_row_fingerprint": entry["fingerprint"],
                           "classification_scope": "default misprint/translation kinds" if row["kind"] in MATH_CANDIDATE_KINDS else "broader all-active-kinds scope",
                           "mathematical_change": "" if not entry["active"] else "pending"})
    all_pending = pending_math_rows(entries, True)
    default_pending = pending_math_rows(entries, False)
    unpaged_pending = [row for row in projection if row["review_status"] == "pending" and not row["printed_page"]]
    withdrawn = [row for row in projection if row["review_status"] == "withdrawn"]
    unregistered_rows = []
    for position in unregistered:
        row = ledger_rows[position - 1]
        unregistered_rows.append({"ledger_record": position, "file": row["file"], "layer": row["layer"],
                                  "printed_page": row["printed_page"], "line": row["line"], "kind": row["kind"],
                                  "row_fingerprint": fingerprint(row), "review_status": "pending; no stable R ID assigned",
                                  "default_kind_candidate": "yes" if row["kind"] in MATH_CANDIDATE_KINDS else "no",
                                  "mathematical_change": "pending"})
    counts = Counter(state["status"] for state in states.values())
    grouping = Counter((entry["row"]["printed_page"], entry["row"]["layer"], entry["row"]["kind"], states[entry["id"]]["status"]) for entry in entries)
    group_rows = [{"printed_page": key[0], "layer": key[1], "kind": key[2], "review_status": key[3], "rows": count}
                  for key, count in sorted(grouping.items(), key=lambda item: (PAGE_ORDER[item[0][0]], *item[0][1:]))]
    summary = {"registered_review_rows": len(states), "current_ledger_rows": len(ledger_rows), "review_events_verified": len(events),
               "active_registered_rows": len(all_pending), "withdrawn_rows_excluded": len(withdrawn),
               "default_kind_pending_classifications": len(default_pending), "broader_all_active_pending_classifications": len(all_pending),
               "pending_review_rows": counts["pending"], "unpaged_pending_review_rows": len(unpaged_pending),
               "unpaged_pending_build_rows": sum(row["layer"] == "build" for row in unpaged_pending),
               "unregistered_pending_ledger_rows": len(unregistered),
               "unregistered_unpaged_pending_rows": sum(not row["printed_page"] for row in unregistered_rows),
               "all_current_ledger_rows_have_stable_ids": not unregistered,
               "classification_yes_decisions": 0, "classification_no_decisions": 0}
    projection_fields = ["correction_id", "ledger_record", "review_status", "last_review_event", "file", "layer", "printed_page", "line", "kind",
                         "current_ledger_fingerprint", "effective_row_fingerprint", "classification_scope", "mathematical_change"]
    tables = {
        "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv": (MATH_FIELDS, all_pending),
        "DEFAULT_KIND_CANDIDATES.tsv": (MATH_FIELDS, default_pending),
        "ROW_PROJECTION.tsv": (projection_fields, projection),
        "UNPAGED_PENDING_REVIEW_ROWS.tsv": (projection_fields, unpaged_pending),
        "WITHDRAWN_ROWS_EXCLUDED.tsv": (projection_fields, withdrawn),
        "UNREGISTERED_PENDING_ROWS.tsv": (["ledger_record", "file", "layer", "printed_page", "line", "kind", "row_fingerprint", "review_status", "default_kind_candidate", "mathematical_change"], unregistered_rows),
        "GROUP_COUNTS.tsv": (["printed_page", "layer", "kind", "review_status", "rows"], group_rows),
        "INPUT_HASHES.tsv": (["file", "bytes", "sha256"], [{"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in captured.items()]),
    }
    payloads, filtered_fields = {}, []
    for name, (fields, rows) in tables.items():
        presented = []
        for number, row in enumerate(rows, 1):
            result, changed = dict(row), []
            if args.privacy_filter_derived:
                for field, value in row.items():
                    if not isinstance(value, str):
                        continue
                    safe = safe_location(value)
                    if safe != value:
                        result[field] = safe
                        changed.append(field)
                        filtered_fields.append({"report_file": name, "record_locator": safe_location(str(row.get("correction_id") or row.get("ledger_record") or number)),
                                                "field": field, "original_value_sha256": hashlib.sha256(value.encode()).hexdigest(),
                                                "filtered_value_sha256": hashlib.sha256(safe.encode()).hexdigest(),
                                                "status": "presentation filtering only; effective row fingerprint uses original fields"})
            if name in {"MATHEMATICAL_CHANGE_CLASSIFICATION.tsv", "DEFAULT_KIND_CANDIDATES.tsv"}:
                result["privacy_filtered_fields"] = ",".join(changed)
            presented.append(result)
        output_fields = fields + ["privacy_filtered_fields"] if name in {"MATHEMATICAL_CHANGE_CLASSIFICATION.tsv", "DEFAULT_KIND_CANDIDATES.tsv"} else fields
        payloads[name] = tsv_data(output_fields, presented)
    summary["privacy_filtered_derived_fields"] = len(filtered_fields)
    payloads["PRIVACY_FILTERING.tsv"] = tsv_data(["report_file", "record_locator", "field", "original_value_sha256", "filtered_value_sha256", "status"], filtered_fields)
    report = ["# Interim pending mathematical-change classification inventory", "", "Generated " + utc() + ".", "",
              "This is a read-only projection of explicitly recorded review events, with no mathematical interpretation or classification. Every candidate classification is pending; every summary and reason is empty. No source page, scan, CHECK_RECORD or context folder was read.", "",
              "| Measure | Result |", "| --- | ---: |"]
    report += [f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items()]
    report += ["", "## Candidate scopes and effective rows", "",
               "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv includes every nonwithdrawn registered effective row, covering the optional all-active-kinds classification gate. DEFAULT_KIND_CANDIDATES.tsv is the subset whose effective kind is literally misprint of the original or translation, covering the default required scope. The subset supplies no additional decisions; choose one scope for later manual classification rather than maintaining conflicting copies.", "",
               "The verified workbench replay supplies stable R IDs, amendment fields and explicit withdrawals. A still-pending review row remains included, explicitly marked in ROW_PROJECTION.tsv; its classification is also pending. ROW_PROJECTION.tsv records current/effective fingerprints and the last explicit review event. Withdrawn rows are excluded from both classification templates and retained only in WITHDRAWN_ROWS_EXCLUDED.tsv as metadata.", "",
               "Unregistered ledger records, if any, have no assigned stable ID and are listed separately in UNREGISTERED_PENDING_ROWS.tsv. Their presence makes registered-only candidate coverage incomplete; this utility does not register or decide them. UNPAGED_PENDING_REVIEW_ROWS.tsv includes every registered pending row without a printed page, including build rows; unregistered unpaged records remain in their separate table.", "",
               "## Fingerprints and later promotion", "",
               "The row fingerprint covers the nine correction fields other than confidence. Annotated export and byte-preserving promotion retain it when effective fields remain unchanged. Later amendments to wording, evidence, kind or locators invalidate the old binding. Classification decisions are never carried onto a different fingerprint automatically. Input hashes bind the ledger and all four review sidecar files; the captured index is checked against replayed history and current alignment.", "",
               "This interim inventory neither exports nor promotes CORRECTIONS.tsv. It does not execute refresh or a final gate. After all review rows are explicitly resolved, use the documented annotated-retain export and reviewed promotion workflow. Then validate manual classifications against the promoted ledger, preview refresh, and only subsequently apply an authorized refresh. See scripts/MATH_CLASSIFICATION_INTERIM.md and scripts/SECOND_READING_PROMOTION.md.", "",
               "## Privacy and limits", "",
               ("Explicit derived-field privacy filtering is enabled. Marked presentation fields are replaced only after effective-row fingerprints and selection are computed. PRIVACY_FILTERING.tsv records their original/filtered hashes. A filtered informational old/new field is not the full original literal; inspect its effective review row when supplying a decision. No source, credit, ledger or history byte is rewritten."
                if args.privacy_filter_derived else "Presentation fields are exact; any privacy finding blocks installation without rewriting an excerpt."), "",
               "All prepared output files are privacy-scanned, and the captured inputs are checked again before exclusive installation. Previous snapshots remain unchanged. Group counts and kind-based candidate membership do not establish mathematical significance, completeness of proof checking or correctness of an editorial change.", ""]
    payloads["REPORT.md"] = "\n".join(report).encode()
    payloads["SUMMARY.json"] = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("A prepared inventory has a privacy pattern or inspection blocker; no report was installed.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="math-inventory-", dir=output.parent) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        with review_workbench.history_lock(directory):
            if any(read_snapshot(paths[name]) != data for name, data in captured.items()):
                raise RuntimeError("A ledger or review input changed during projection; no report was installed.")
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


def count_source_lines(path: Path) -> int:
    # Count bytes, not words, formulas or TeX structure. LF is the physical
    # line boundary used by these source files; a final unterminated line counts.
    count, size, last = 0, 0, b""
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            count += block.count(b"\n")
            size += len(block)
            last = block[-1:]
    return count + (1 if size and last != b"\n" else 0)


def validate_count_field(text: str, allowed: list[str]) -> None:
    if text in {"", "none (0)"}:
        return
    seen = set()
    for pair in text.split(", "):
        name, separator, value = pair.rpartition(": ")
        if not separator or name not in allowed or not value.isdigit() or name in seen:
            raise ValueError("A count metadata line contains unexpected prose or syntax; it was not changed.")
        seen.add(name)


def strip_summary(text: str) -> str:
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("Malformed or duplicated managed summary markers.")
    if BEGIN not in text:
        return text
    pattern = re.compile(r"(?ms)^" + re.escape(BEGIN) + r"\r?\n.*?^" + re.escape(END) + r"(?:\r?\n){1,2}")
    result, count = pattern.subn("", text)
    if count != 1:
        raise ValueError("The managed summary block could not be isolated safely.")
    return result


def protected_content(text: str) -> str:
    text = strip_summary(text)
    text = COUNT_LINE.sub(lambda match: match["label"] + "<COUNTS>" + match["separator"] + "<KINDS>." + match["eol"], text)
    def protect_sources(match):
        return SOURCE_RANGE.sub(lambda item: item["prefix"] + item["first"] + item["dash"] + "<LINE_COUNT>", match.group(0))
    return SOURCES_LINE.sub(protect_sources, text)


def update_pages(text: str, entries: list[dict], root: Path) -> tuple[str, dict]:
    headings = list(PAGE_HEADING.finditer(text))
    if [int(match.group(1)) for match in headings] != PAGES:
        raise ValueError("CHECK_RECORD must contain all 102 printed-page sections once and in order before refresh.")
    active = [entry for entry in entries if entry["active"]]
    by_page = {str(page): [entry["row"] for entry in active if entry["row"]["printed_page"] == str(page)] for page in PAGES}
    pieces, ranges_changed, count_lines_changed = [text[:headings[0].start()]], 0, 0
    for index, heading in enumerate(headings):
        page = heading.group(1)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.start():end]
        source_matches = list(SOURCES_LINE.finditer(section))
        count_matches = list(COUNT_LINE.finditer(section))
        if len(source_matches) != 1 or len(count_matches) != 1:
            raise ValueError("Exactly one source-range line and one count line are required in page " + page)
        source_match, count_match = source_matches[0], count_matches[0]
        validate_count_field(count_match["layers"], LAYERS)
        validate_count_field(count_match["kinds"], KINDS)
        ranges = list(SOURCE_RANGE.finditer(source_match.group(0)))
        if len(ranges) != 3 or {item["tree"] for item in ranges} != {"dip", "fr", "en"} or any(item["page"] != page or item["first"] != "1" for item in ranges):
            raise ValueError("Unexpected source-range structure in page " + page)
        line_counts = {tree: count_source_lines(root / "sources" / tree / f"p{page}.tex") for tree in ("dip", "fr", "en")}
        if any(value == 0 for value in line_counts.values()):
            raise ValueError("An empty source file cannot be given a checked line range.")
        ranges_changed += sum(int(item["last"]) != line_counts[item["tree"]] for item in ranges)
        source_text = SOURCE_RANGE.sub(lambda item: item["prefix"] + item["first"] + item["dash"] + str(line_counts[item["tree"]]), source_match.group(0))
        rows = by_page[page]
        layer_counts = Counter(row["layer"] for row in rows)
        kind_counts = Counter(row["kind"] for row in rows)
        layer_text = ", ".join(f"{layer}: {layer_counts[layer]}" for layer in LAYERS)
        kind_text = ", ".join(f"{kind}: {kind_counts[kind]}" for kind in KINDS if kind_counts[kind]) or "none (0)"
        count_text = count_match["label"] + layer_text + count_match["separator"] + kind_text + "." + count_match["eol"]
        count_lines_changed += count_text != count_match.group(0)
        edits = [(source_match.start(), source_match.end(), source_text), (count_match.start(), count_match.end(), count_text)]
        for start, finish, replacement in sorted(edits, reverse=True):
            section = section[:start] + replacement + section[finish:]
        pieces.append(section)
    return "".join(pieces), {"page_sections": len(PAGES), "source_ranges_changed": ranges_changed, "count_lines_changed": count_lines_changed}


def one_line(value: str) -> str:
    return " ".join(value.splitlines()).strip()


def summary_block(entries: list[dict], classifications: dict, timestamp: str, eol: str) -> tuple[str, dict]:
    active = [entry for entry in entries if entry["active"]]
    matrix = Counter((entry["row"]["layer"], entry["row"]["kind"]) for entry in active)
    candidates = [entry for entry in active if entry["row"]["kind"] in MATH_CANDIDATE_KINDS]
    missing_candidates = [entry["id"] for entry in candidates if classifications.get(entry["id"], {}).get("choice", "pending") == "pending"]
    unclassified_all = [entry["id"] for entry in active if classifications.get(entry["id"], {}).get("choice", "pending") == "pending"]
    math_yes = [entry for entry in sorted(active, key=row_order) if classifications.get(entry["id"], {}).get("choice") == "yes"]
    zero_pages = {layer: sum(not any(entry["row"]["layer"] == layer and entry["row"]["printed_page"] == str(page) for entry in active) for page in PAGES) for layer in READING_LAYERS}
    lines = [BEGIN, "", "## Mechanical totals after second reading", "",
             f"Metadata refreshed {timestamp}. Counts and source-line ranges refer to the current ledger and source files. Original narratives, verdicts and completion timestamps are preserved; this refresh asserts no new reading or proof check.", "",
             f"Active correction rows: **{len(active)}**. Explicitly withdrawn rows excluded from these counts: **{len(entries) - len(active)}**. Active rows without a printed page: **{sum(not entry['row']['printed_page'] for entry in active)}**.", "",
             "Counts are ledger rows, not inferred token or occurrence counts.", "",
             "| Layer | Reading | Original misprint | Translation | Typesetting | Structure | Total |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for layer in LAYERS:
        values = [matrix[layer, kind] for kind in KINDS]
        lines.append("| " + layer + " | " + " | ".join(map(str, values + [sum(values)])) + " |")
    values = [sum(matrix[layer, kind] for layer in LAYERS) for kind in KINDS]
    lines += ["| **Total** | " + " | ".join(map(str, values + [sum(values)])) + " |", "",
              "### Pages with no recorded change", "",
              "| Layer | Pages with no active correction row | Pages with at least one active correction row |",
              "| --- | ---: | ---: |"]
    for layer in READING_LAYERS:
        lines.append(f"| {layer} | {zero_pages[layer]} | {len(PAGES) - zero_pages[layer]} |")
    lines += ["", "These counts cover all 102 supplied printed pages and do not infer a scan-reading result from an empty ledger subset.", "",
              "### Changes to mathematics: explicit manual classifications", "",
              f"Rows explicitly classified as mathematical changes: **{len(math_yes)}**. Pending classifications among original-misprint/translation candidates: **{len(missing_candidates)}**. Active rows of any kind without an explicit yes/no classification: **{len(unclassified_all)}**.", "",
              "The list contains only reviewer-supplied yes decisions. An unlisted or unclassified row is not automatically judged mathematically immaterial. Other correction kinds can be included by an explicit manual classification.", ""]
    if math_yes:
        for entry in math_yes:
            row, decision = entry["row"], classifications[entry["id"]]
            location = "printed p. " + row["printed_page"] if row["printed_page"] else "unpaged build entry"
            statement = "; statement " + one_line(row["statement"]) if row["statement"] else ""
            printed_line = "; printed line " + one_line(row["line"]) if row["line"] else ""
            if privacy_findings(row["file"] + "\n" + row["statement"]):
                raise ValueError("A mathematical-change locator contains a possible private path or email address.")
            lines.append(f"- {entry['id']} — {location}{statement}{printed_line}; {row['layer']}; `{row['file']}`: {one_line(decision['summary'])} Manual reason: {one_line(decision['reason'])}")
    else:
        lines.append("No active row is currently supplied with an explicit yes classification. This does not establish that no mathematical change exists.")
    if missing_candidates:
        lines += ["", "Pending original-misprint/translation candidate IDs: " + ", ".join(missing_candidates) + "."]
    lines += ["", END, "", ""]
    stats = {"active_rows": len(active), "withdrawn_rows_excluded": len(entries) - len(active), "zero_change_pages": zero_pages,
             "explicit_math_changes": len(math_yes), "pending_math_candidates": len(missing_candidates), "unclassified_active_rows": len(unclassified_all)}
    return eol.join(lines), stats


def insert_summary(text: str, block: str) -> str:
    text = strip_summary(text)
    title = re.match(r"\A(?:\ufeff)?# [^\r\n]*(?:\r?\n)", text)
    if not title:
        raise ValueError("CHECK_RECORD must start with its existing level-one title.")
    position = title.end()
    if text.startswith("\r\n", position):
        position += 2
    elif text.startswith("\n", position):
        position += 1
    return text[:position] + block + text[position:]


def refresh_text(root: Path, original: str, entries: list[dict], classifications: dict, timestamp: str) -> tuple[str, dict]:
    updated, stats = update_pages(original, entries, root)
    eol = "\r\n" if "\r\n" in original else "\n"
    block, totals = summary_block(entries, classifications, timestamp, eol)
    updated = insert_summary(updated, block)
    if protected_content(original) != protected_content(updated):
        raise RuntimeError("Protected narrative/timestamp content would change; refresh aborted.")
    return updated, {**stats, **totals, "protected_narrative_unchanged": True}


def refresh(args) -> None:
    root = args.root.resolve()
    progress = (root / "progress.log").read_bytes().decode("utf-8")
    if [int(value) for value in re.findall(r"(?m)^page (\d{3}) done\s", progress)] != PAGES:
        raise ValueError("Refresh is deferred until all 102 ordered page-completion entries exist.")
    entries = load_rows(root, args.review_map)
    unfinished = [entry["id"] for entry in entries if entry["active"] and re.search(r"first[ -]reading|pending|provisional|not yet", entry["row"]["confidence"], re.I)]
    if unfinished:
        raise ValueError("The promoted ledger still explicitly marks unfinished second readings: " + ",".join(unfinished))
    classifications = load_classifications(args.math_classifications, entries)
    record = root / "CHECK_RECORD.md"
    before = record.read_bytes()
    updated, stats = refresh_text(root, before.decode("utf-8"), entries, classifications, utc())
    if args.require_math_complete and stats["pending_math_candidates"]:
        raise ValueError("Explicit mathematical classifications are still pending for original-misprint/translation candidates.")
    if args.require_all_math_classified and stats["unclassified_active_rows"]:
        raise ValueError("Some active correction rows still lack an explicit mathematical yes/no classification.")
    if args.write or args.output:
        destination = record if args.write else (root / args.output).resolve()
        if root not in destination.parents or (root / "sources") in destination.parents or destination == root / "CORRECTIONS.tsv":
            raise ValueError("The refreshed report must remain inside the delivery tree and outside source files/ledger.")
        if args.output and (destination == record or destination.exists()):
            raise ValueError("A preview needs a new filename; use --write for the protected in-place refresh.")
        if record.read_bytes() != before:
            raise RuntimeError("CHECK_RECORD changed during preparation; no update was written.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.write:
            with tempfile.NamedTemporaryFile(prefix="record-refresh-", dir=root, delete=False) as stream:
                stream.write(updated.encode("utf-8")); stream.flush(); os.fsync(stream.fileno()); temporary = Path(stream.name)
            os.replace(temporary, record)
        else:
            with destination.open("xb") as stream:
                stream.write(updated.encode("utf-8"))
        stats["output"] = destination.name
    else:
        stats["output"] = "none; preview statistics only"
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--review-map", type=Path, help="Matching second-reading export map, useful if confidence cells omit stable review IDs")
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare-math", help="Create pending manual classifications; never classify significance automatically")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--all-kinds", action="store_true", help="Include every active row; default candidates are original misprints and translations")
    interim = commands.add_parser("prepare-math-interim", help="Read-only effective-review projection with pending-only default and all-active classification tables")
    interim.add_argument("--output", type=Path, required=True, help="Fresh relative directory explicitly containing interim")
    interim.add_argument("--review-dir", type=Path, default=Path("second-reading"))
    interim.add_argument("--privacy-filter-derived", action="store_true", help="Explicitly filter privacy patterns only in derived presentation fields, with original hashes and markers")
    refresh_command = commands.add_parser("refresh", help="Refresh numeric metadata; default prints statistics without writing")
    refresh_command.add_argument("--math-classifications", type=Path)
    mode = refresh_command.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--output", type=Path, help="Write a separate preview copy instead of updating CHECK_RECORD.md")
    refresh_command.add_argument("--require-math-complete", action="store_true", help="Require explicit yes/no for all original-misprint and translation candidates")
    refresh_command.add_argument("--require-all-math-classified", action="store_true", help="Require an explicit yes/no for every active row of every kind")
    args = parser.parse_args()
    if args.action == "prepare-math":
        prepare_math(args)
    elif args.action == "prepare-math-interim":
        prepare_math_interim(args)
    else:
        refresh(args)


if __name__ == "__main__":
    main()
