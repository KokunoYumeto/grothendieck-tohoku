"""Report exact correction-ledger replacement bindings without editorial decisions.

Only byte-level literal occurrence, locator metadata and explicit ledger markers
are examined. Every absence, brace diagnostic and later-record association is a
manual-review flag. No source, ledger, reading history or existing report changes.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile

from build_report import sanitize_text
from final_validate import privacy_findings
from refresh_check_record import load_rows, read_tsv, tsv_data

LAYER_TREES = {"as-printed": "dip", "corrected": "fr", "English": "en"}
INHERITED_MARKER = "Inherited correction retained:"
FILE_URI = re.compile(r"\bfile:/{2,3}[^\s<>\"']+", re.I)
UNC_PATH = re.compile(r"(?<!\\)\\\\[A-Za-z0-9_.-]+\\[^\s<>\"']+")
SHARE_PATH = re.compile(r"(?<![:/])//[A-Za-z0-9_.-]+/[^\s<>\"']+")
ROW_FIELDS = [
    "correction_id", "ledger_record", "row_fingerprint", "file", "source_file", "layer", "printed_page", "line", "kind", "confidence",
    "ledger_activity", "inherited_marker", "source_status", "source_sha256", "source_bytes", "source_lines", "new_status",
    "new_characters", "new_utf8_bytes", "new_occurrences", "new_locations", "old_occurrences",
    "new_double_open", "new_double_close", "old_double_open", "old_double_close", "brace_collapsed_new_occurrences",
    "brace_collapsed_new_locations", "later_record_candidate_ids", "review_flags", "privacy_redacted_fields",
]
DETAIL_FIELDS = ROW_FIELDS + ["statement", "evidence", "old", "new", "brace_collapsed_new_diagnostic"]
LATER_FIELDS = ["correction_id", "ledger_record", "candidate_id", "candidate_ledger_record", "source_file", "literal_relation", "candidate_new_status", "candidate_activity", "candidate_only"]
GROUP_FIELDS = ["dimension", "value", "rows", "present", "absent", "empty_new", "unresolved_source", "inherited", "inherited_with_doubled_braces", "inherited_doubled_braces_new_absent", "absent_with_brace_collapse_present"]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_text(value: str) -> str:
    value = FILE_URI.sub("<redacted-local-file-uri>", value)
    value = UNC_PATH.sub("<redacted-network-path>", value)
    value = SHARE_PATH.sub("<redacted-network-path>", value)
    return sanitize_text(value)


def safe_row(row: dict) -> dict:
    result, redacted = {}, []
    for field, value in row.items():
        changed = safe_text(value) if isinstance(value, str) else value
        result[field] = changed
        if changed != value:
            redacted.append(field)
    if "privacy_redacted_fields" in row:
        prior = row["privacy_redacted_fields"]
        result["privacy_redacted_fields"] = ",".join(filter(None, [prior, *redacted]))
    return result


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(path: Path) -> bytes:
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("An input changed while being read; rerun the report after that edit.")
    return data


def source_locator(root: Path, row: dict) -> tuple[str, Path | None, str, list[str]]:
    value = row["file"]
    if not value or "\\" in value or PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        return "unsafe or empty source locator", None, "", ["unresolved-source-locator"]
    parts = PurePosixPath(value).parts
    if not parts:
        return "empty normalized source locator", None, "", ["unresolved-source-locator"]
    if ".." in parts:
        return "parent traversal source locator", None, "", ["unresolved-source-locator"]
    if parts[0] == "sources":
        relative = PurePosixPath(*parts)
    elif parts[0] in {"dip", "fr", "en"}:
        relative = PurePosixPath("sources", *parts)
    elif len(parts) == 1 and re.fullmatch(r"p\d{3}\.tex", parts[0]):
        if row["layer"] not in LAYER_TREES:
            return "page basename without a reading-layer binding", None, "", ["unresolved-source-locator"]
        relative = PurePosixPath("sources", LAYER_TREES[row["layer"]], parts[0])
    elif len(parts) == 1:
        relative = PurePosixPath("sources", parts[0])
    else:
        return "unrecognized source locator form", None, "", ["unresolved-source-locator"]
    display = relative.as_posix()
    if relative.suffix != ".tex":
        return "non-TeX source locator not opened", None, display, ["unsupported-source-type"]
    path = root.joinpath(*relative.parts).resolve()
    if (root / "sources").resolve() not in path.parents:
        return "source locator resolves outside source tree", None, display, ["unresolved-source-locator"]
    flags = []
    tree = relative.parts[1] if len(relative.parts) >= 3 else None
    if tree in {"dip", "fr", "en"} and row["layer"] in LAYER_TREES and tree != LAYER_TREES[row["layer"]]:
        flags.append("source-tree-and-ledger-layer-disagree")
    page = re.fullmatch(r"p(\d{3})\.tex", relative.name)
    if page and row["printed_page"] and page.group(1) != row["printed_page"]:
        flags.append("source-filename-and-printed-page-disagree")
    if not path.is_file():
        return "source file missing", path, display, flags + ["source-file-missing"]
    return "read exact source bytes", path, display, flags


def literal_occurrences(data: bytes, value: str, line_ends: list[int], limit: int) -> tuple[int | str, str]:
    if not value:
        return "", ""
    literal = value.encode("utf-8")
    count = data.count(literal)
    locations, offset = [], 0
    for _ in range(min(count, limit)):
        position = data.find(literal, offset)
        if position < 0:
            break
        first = bisect_right(line_ends, position - 1) + 1
        last = bisect_right(line_ends, position + len(literal) - 2) + 1
        locations.append(str(first) if first == last else f"{first}–{last}")
        offset = position + len(literal)
    return count, ";".join(locations)


def bind_row(entry: dict, source: dict, source_name: str, locator_flags: list[str], limit: int) -> dict:
    row = entry["row"]
    old, new = row["old"], row["new"]
    collapsed = new.replace("{{", "{").replace("}}", "}")
    inherited = INHERITED_MARKER in row["evidence"]
    flags = list(locator_flags)
    result = {
        "correction_id": entry["id"], "ledger_record": entry["ledger_record"], "row_fingerprint": entry["fingerprint"],
        **{field: row[field] for field in ("file", "layer", "printed_page", "line", "kind", "confidence")},
        "source_file": source_name, "ledger_activity": "active or not explicitly withdrawn" if entry["active"] else "explicitly withdrawn",
        "inherited_marker": "yes; exact audit.inherited evidence marker" if inherited else "no exact marker",
        "source_status": source["status"], "source_sha256": source.get("sha256", ""), "source_bytes": source.get("bytes", ""), "source_lines": source.get("lines", ""),
        "new_status": "unresolved source", "new_characters": len(new), "new_utf8_bytes": len(new.encode("utf-8")),
        "new_occurrences": "", "new_locations": "", "old_occurrences": "",
        "new_double_open": new.count("{{"), "new_double_close": new.count("}}"),
        "old_double_open": old.count("{{"), "old_double_close": old.count("}}"),
        "brace_collapsed_new_occurrences": "", "brace_collapsed_new_locations": "", "later_record_candidate_ids": "",
        "review_flags": "", "privacy_redacted_fields": "",
        "statement": row["statement"], "evidence": row["evidence"], "old": old, "new": new,
        "brace_collapsed_new_diagnostic": collapsed if collapsed != new else "",
    }
    if "data" in source:
        data, line_ends = source["data"], source["line_ends"]
        result["new_occurrences"], result["new_locations"] = literal_occurrences(data, new, line_ends, limit)
        result["old_occurrences"], _ = literal_occurrences(data, old, line_ends, 0)
        if not new:
            result["new_status"] = "empty new; no presence test"
        elif result["new_occurrences"]:
            result["new_status"] = "present"
        else:
            result["new_status"] = "absent"
            flags.append("nonempty-new-literal-absent")
        if collapsed != new:
            result["brace_collapsed_new_occurrences"], result["brace_collapsed_new_locations"] = literal_occurrences(data, collapsed, line_ends, limit)
            if result["new_status"] == "absent" and result["brace_collapsed_new_occurrences"]:
                flags.append("one-pass-brace-collapse-occurs-diagnostic-only")
    elif not new:
        result["new_status"] = "empty new; unresolved source"
    if inherited and any(result[field] for field in ("new_double_open", "new_double_close", "old_double_open", "old_double_close")):
        flags.append("inherited-row-has-doubled-braces-review-binding")
    result["review_flags"] = ";".join(flags)
    return result


def later_candidates(rows: list[dict], entries: list[dict]) -> list[dict]:
    by_source = defaultdict(list)
    entry_by_record = {entry["ledger_record"]: entry for entry in entries}
    for row in rows:
        if row["source_file"]:
            by_source[row["source_file"]].append(row)
    associations = []
    for row in rows:
        if row["new_status"] != "absent":
            continue
        new = entry_by_record[row["ledger_record"]]["row"]["new"]
        found = []
        for later in by_source[row["source_file"]]:
            if later["ledger_record"] <= row["ledger_record"]:
                continue
            old = entry_by_record[later["ledger_record"]]["row"]["old"]
            if not old:
                continue
            relation = "missing new literal is contained in later record old" if new in old else "later record old is contained in missing new literal" if old in new else ""
            if relation:
                found.append(later["correction_id"])
                associations.append({"correction_id": row["correction_id"], "ledger_record": row["ledger_record"],
                                     "candidate_id": later["correction_id"], "candidate_ledger_record": later["ledger_record"],
                                     "source_file": row["source_file"], "literal_relation": relation,
                                     "candidate_new_status": later["new_status"], "candidate_activity": later["ledger_activity"],
                                     "candidate_only": "yes; later record order and literal overlap do not prove a subsequent edit"})
        row["later_record_candidate_ids"] = ",".join(found)
    return associations


def metrics(rows: list[dict]) -> dict:
    inherited = [row for row in rows if row["inherited_marker"].startswith("yes;")]
    doubled = [row for row in inherited if any(row[field] for field in ("new_double_open", "new_double_close", "old_double_open", "old_double_close"))]
    return {"rows": len(rows), "present": sum(row["new_status"] == "present" for row in rows),
            "absent": sum(row["new_status"] == "absent" for row in rows),
            "empty_new": sum(row["new_characters"] == 0 for row in rows),
            "unresolved_source": sum(row["source_status"] != "read exact source bytes" for row in rows),
            "inherited": len(inherited), "inherited_with_doubled_braces": len(doubled),
            "inherited_doubled_braces_new_absent": sum(row["new_status"] == "absent" for row in doubled),
            "absent_with_brace_collapse_present": sum(row["new_status"] == "absent" and bool(row["brace_collapsed_new_occurrences"]) for row in rows)}


def report(args) -> dict:
    root = args.root.resolve()
    output = (root / args.output).resolve()
    if output == root or root not in output.parents or any(output == root / name or (root / name) in output.parents for name in ("sources", "pdf", "second-reading")):
        raise ValueError("Output must be a new report directory inside the delivery tree, outside source, PDF and review-history trees.")
    if output.exists():
        raise ValueError("The report directory already exists; choose a new name to preserve it.")
    if args.max_locations < 0:
        raise ValueError("Maximum source locations cannot be negative.")
    if safe_text(output.relative_to(root).as_posix()) != output.relative_to(root).as_posix():
        raise ValueError("The output directory name contains a recognizable private path or email pattern.")
    ledger_path = root / "CORRECTIONS.tsv"
    ledger_data = snapshot(ledger_path)
    map_data = snapshot(args.review_map) if args.review_map else None
    entries = load_rows(root, args.review_map)
    if args.review_map:
        _, bindings = read_tsv(args.review_map)
        current = {entry["ledger_record"]: entry for entry in entries}
        for binding in bindings:
            if not binding["export_record"]:
                continue
            entry = current.get(int(binding["export_record"]))
            if entry is None:
                raise ValueError("The review map references a missing current ledger record.")
            if not binding.get("row_fingerprint") and binding["review_id"] not in re.findall(r"\bR\d{6,}\b", entry["row"]["confidence"]):
                raise ValueError("A plain-confidence review map must bind the row by fingerprint; use its current export map or omit the map.")
    cache, source_names, rows = {}, {}, []
    for entry in entries:
        status, path, name, flags = source_locator(root, entry["row"])
        if path is not None and status == "read exact source bytes":
            if path not in cache:
                data = snapshot(path)
                cache[path] = {"status": status, "data": data, "sha256": digest(data), "bytes": len(data),
                               "lines": data.count(b"\n") + bool(data and not data.endswith(b"\n")),
                               "line_ends": [index for index, value in enumerate(data) if value == 10]}
            source = cache[path]
            source_names[name] = source
        else:
            source = {"status": status}
        rows.append(bind_row(entry, source, name, flags, args.max_locations))
    associations = later_candidates(rows, entries)
    if snapshot(ledger_path) != ledger_data or (args.review_map and snapshot(args.review_map) != map_data):
        raise RuntimeError("The correction ledger or review map changed during the report; no report was installed. Rerun against the next snapshot.")
    for path, data in cache.items():
        if snapshot(path) != data["data"]:
            raise RuntimeError("An indicated source changed during the report; no report was installed. Rerun against the next snapshot.")
    groups = []
    for dimension in ("layer", "kind", "printed_page", "inherited_marker", "ledger_activity"):
        values = sorted({row[dimension] for row in rows}, key=lambda value: (not bool(value), value))
        for value in values:
            selected = [row for row in rows if row[dimension] == value]
            groups.append({"dimension": dimension, "value": value or "(unpaged)", **metrics(selected)})
    totals = {**metrics(rows), "source_files_read": len(cache), "rows_with_new_doubled_braces": sum(bool(row["new_double_open"] or row["new_double_close"]) for row in rows),
              "absent_with_later_record_candidates": sum(row["new_status"] == "absent" and bool(row["later_record_candidate_ids"]) for row in rows),
              "later_record_candidate_associations": len(associations), "flagged_rows": sum(bool(row["review_flags"]) for row in rows),
              "stable_review_ids": sum(entry["id"].startswith("R") for entry in entries),
              "snapshot_ledger_record_ids": sum(entry["id"].startswith("L") for entry in entries)}
    source_hashes = [{"file": name, "bytes": source["bytes"], "lines": source["lines"], "sha256": source["sha256"]} for name, source in sorted(source_names.items())]
    input_hashes = [{"role": "correction ledger", "file": "CORRECTIONS.tsv", "bytes": len(ledger_data), "sha256": digest(ledger_data)}]
    if map_data is not None:
        input_hashes.append({"role": "explicit review export map", "file": "review-map input", "bytes": len(map_data), "sha256": digest(map_data)})
    protected_rows = [safe_row(row) for row in rows]
    totals["rows_with_report_field_redactions"] = sum(bool(row["privacy_redacted_fields"]) for row in protected_rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="literal-bindings-", dir=output.parent) as temporary:
        prepared = Path(temporary) / "prepared"
        prepared.mkdir()
        subsets = [
            ("ROW_BINDINGS.tsv", ROW_FIELDS, [{field: row[field] for field in ROW_FIELDS} for row in protected_rows]),
            ("ABSENT_NEW_LITERALS.tsv", DETAIL_FIELDS, [row for row in protected_rows if row["new_status"] == "absent"]),
            ("INHERITED_DOUBLED_BRACES.tsv", DETAIL_FIELDS, [row for row in protected_rows if row["inherited_marker"].startswith("yes;") and any(row[field] for field in ("new_double_open", "new_double_close", "old_double_open", "old_double_close"))]),
            ("FLAGGED_ROWS.tsv", DETAIL_FIELDS, [row for row in protected_rows if row["review_flags"]]),
            ("LATER_RECORD_CANDIDATES.tsv", LATER_FIELDS, [safe_row(row) for row in associations]),
            ("GROUPS.tsv", GROUP_FIELDS, [safe_row(row) for row in groups]),
            ("SOURCE_HASHES.tsv", ["file", "bytes", "lines", "sha256"], [safe_row(row) for row in source_hashes]),
            ("INPUT_HASHES.tsv", ["role", "file", "bytes", "sha256"], input_hashes),
        ]
        for filename, fields, values in subsets:
            (prepared / filename).write_bytes(tsv_data(fields, values))
        (prepared / "SUMMARY.json").write_text(json.dumps({"generated_utc": utc(), "totals": totals, "scope": "mechanical literal bindings only; all flags require manual review"}, indent=2) + "\n", encoding="utf-8")
        prose = ["# Correction replacement-literal bindings", "", "Generated " + utc() + ".", "",
                 "This report performs exact UTF-8 byte comparisons against the indicated source files. It contains no scan reading, visual verification, mathematical assessment or conclusion that an absent literal is an incorrect correction. Later edits, restructuring, deletion and a ledger binding issue can all explain absence.", "",
                 "| Measure | Count |", "| --- | ---: |"]
        prose += [f"| {key.replace('_', ' ')} | {value} |" for key, value in totals.items()]
        prose += ["", "## Interpretation", "",
                  "ABSENT_NEW_LITERALS.tsv lists only nonempty replacement literals that do not occur anywhere in the indicated source snapshot. Empty new fields are reported separately as having no presence test; they are not failed replacements. An occurrence proves presence only, not that the intended occurrence or source line was changed correctly.", "",
                  "INHERITED_DOUBLED_BRACES.tsv selects the exact evidence marker written by audit.inherited and literal doubled opening or closing braces in either old or new. Adjacent braces may be legitimate TeX. The one-pass diagnostic replaces each nonoverlapping {{ with { and }} with } in the replacement literal, then tests that variant mechanically. Even when the variant occurs, this is not a proposed amendment or a decision about correct grouping.", "",
                  "LATER_RECORD_CANDIDATES.tsv lists later ledger records for the same indicated source whose old field has exact substring containment with a missing new field. Record order is not proof of edit chronology; short overlapping literals may be incidental. These are candidate explanations only, and no row is withdrawn, confirmed or amended.", "",
                  "ROW_BINDINGS.tsv includes every row, including explicitly withdrawn rows, with their activity labelled. GROUPS.tsv groups the results by layer, kind, printed page, explicit inherited marker and activity. L-prefixed IDs are one-based ledger-record locators for this snapshot; R-prefixed IDs come from explicit second-reading annotations or a fingerprint-bound map.", "",
                  "Source locations use physical LF line boundaries, with at most " + str(args.max_locations) + " occurrences shown per tested literal. Counts are nonoverlapping exact occurrences. The line metadata recorded in CORRECTIONS is retained for manual reference and is not interpreted as an exact binding constraint.", "",
                  "SOURCE_HASHES.tsv and INPUT_HASHES.tsv bind the results to their byte snapshots. The input bytes are rechecked before installation; concurrent changes abort the report. Re-run with a new output directory after subsequent edits or final promotion.", "",
                  "Matching uses the original ledger strings before privacy filtering. Recognizable email, local path and local-file URI patterns are redacted only in generated report fields, with the affected fields identified. The original ledger and sources are untouched. Hashes identify the unsanitized input snapshots. Pattern filtering does not claim exhaustive privacy detection.", "",
                  "No source, ledger, review history, progress log, CHECK_RECORD section or existing report was changed. Every flag remains pending manual review.", ""]
        (prepared / "REPORT.md").write_text("\n".join(prose), encoding="utf-8")
        for path in prepared.iterdir():
            if privacy_findings(path.read_text(encoding="utf-8")):
                raise ValueError("A generated report still contains a recognizable privacy pattern; no report was installed.")
        output.mkdir()
        installed = []
        try:
            for path in prepared.iterdir():
                target = output / path.name
                os.link(path, target)
                installed.append(target)
        except BaseException:
            for path in installed:
                path.unlink()
            output.rmdir()
            raise
    result = {"report_directory": output.relative_to(root).as_posix(), **totals, "manual_review_status": "every flag remains undecided"}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="New report directory relative to the delivery root")
    parser.add_argument("--review-map", type=Path, help="Matching second-reading export map if stable IDs need it")
    parser.add_argument("--max-locations", type=int, default=5)
    report(parser.parse_args())


if __name__ == "__main__":
    main()
