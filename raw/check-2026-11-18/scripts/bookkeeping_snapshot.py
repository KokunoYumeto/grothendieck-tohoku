"""Create an interim ledger/structure snapshot without making review decisions.

Only exact ledger equality, recorded identifiers, counts, byte hashes and source
line-break counts are used. No source wording or image is interpreted. Existing
records and the review sidecar are read only.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from literal_binding_report import source_locator
from privacy_guard import safe_location, scan_bytes
from refresh_check_record import KINDS, LAYERS, PAGE_HEADING, SOURCE_RANGE, tsv_data
from second_reading import FIELDS, PAGES, align, fingerprint, load_project, previous_positions, read_ledger


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_rows(rows: list[dict]) -> list[dict]:
    return [{key: safe_location(value) if isinstance(value, str) else value for key, value in row.items()} for row in rows]


def create_snapshot(args) -> dict:
    root = args.root.resolve()
    output = (root / args.output).resolve()
    if root not in output.parents or output.exists() or "interim" not in output.name.lower():
        raise ValueError("Choose a new interim-named report directory inside the delivery tree.")
    if any(output == root / tree or root / tree in output.parents for tree in ("sources", "pdf", "second-reading")):
        raise ValueError("Snapshot output cannot be inside a source, PDF or review-history tree.")
    inputs = {}
    def read(path):
        data = path.read_bytes()
        inputs[path] = data
        return data
    ledger = root / "CORRECTIONS.tsv"
    read(ledger)
    rows, ledger_hash = read_ledger(ledger)
    if digest(inputs[ledger]) != ledger_hash:
        raise RuntimeError("The ledger changed while snapshot preparation began.")
    directory = (root / args.review_dir).resolve()
    states, assignment, history = {}, {}, []
    if directory.is_dir():
        for name in ("REVIEW_META.tsv", "ROW_REGISTRY.tsv", "REVIEW_EVENTS.tsv", "REVIEW_INDEX.tsv"):
            path = directory / name
            if path.is_file():
                read(path)
        _, _, history, states = load_project(directory, ledger)
        assignment, unregistered = align(rows, states, previous_positions(directory, states))
    else:
        unregistered = list(range(1, len(rows) + 1))
    id_by_record = {position: review_id for review_id, position in assignment.items()}
    identifiers = {position: id_by_record.get(position, f"L{position:06d}") for position in range(1, len(rows) + 1)}
    bindings = [{"review_id": review_id, "export_record": position, "status": states[review_id]["status"],
                 "last_event": states[review_id]["last_event"], "row_fingerprint": fingerprint(rows[position - 1])}
                for review_id, position in sorted(assignment.items(), key=lambda item: item[1])]
    # This map records existing identities/statuses for mechanical reports. It
    # is not a reviewed ledger export and does not change any pending outcome.
    locators, locator_cache = {}, {}
    for position, row in enumerate(rows, 1):
        key = (row["file"], row["layer"], row["printed_page"])
        if key not in locator_cache:
            _, _, name, _ = source_locator(root, row)
            locator_cache[key] = name or row["file"]
        locators[position] = locator_cache[key]
    exact, pairs = defaultdict(list), defaultdict(list)
    noops = []
    for position, row in enumerate(rows, 1):
        exact[tuple(row[field] for field in FIELDS)].append(position)
        pairs[(locators[position], row["layer"], row["printed_page"], row["old"], row["new"])].append(position)
        if row["old"] == row["new"]:
            noops.append({"correction_id": identifiers[position], "ledger_record": position, "file": locators[position], "printed_page": row["printed_page"], "kind": row["kind"], "literal_characters": len(row["new"]), "row_fingerprint": fingerprint(row)})
    def grouped(source, prefix):
        result = []
        for positions in source.values():
            if len(positions) < 2:
                continue
            first = rows[positions[0] - 1]
            result.append({"group_id": f"{prefix}{len(result) + 1:05d}", "file": locators[positions[0]], "printed_page": first["printed_page"],
                           "layer": first["layer"], "records": len(positions), "correction_ids": ",".join(identifiers[p] for p in positions),
                           "ledger_records": ",".join(map(str, positions)), "old_sha256": digest(first["old"].encode()), "new_sha256": digest(first["new"].encode()),
                           "interpretation": "manual bookkeeping review only; multiplicity may be intentional"})
        return result
    duplicates, repeated = grouped(exact, "DUP"), grouped(pairs, "PAIR")
    prior_new, chains = defaultdict(list), []
    for position, row in enumerate(rows, 1):
        name = locators[position]
        if row["old"] and row["old"] != row["new"]:
            for prior in prior_new[(name, row["old"])]:
                before = rows[prior - 1]
                reversal = before["old"] == row["new"]
                chains.append({"earlier_id": identifiers[prior], "earlier_record": prior, "later_id": identifiers[position], "later_record": position,
                               "file": name, "printed_page": row["printed_page"], "relation": "exact reversal candidate" if reversal else "exact earlier-new/later-old candidate",
                               "shared_literal_sha256": digest(row["old"].encode()), "shared_literal_characters": len(row["old"]),
                               "interpretation": "record order and equality do not establish edit chronology or the same source occurrence"})
        if row["new"] and row["new"] != row["old"]:
            prior_new[(name, row["new"])].append(position)
    page_counts = []
    for page in [str(page) for page in PAGES] + [""]:
        selected = [row for row in rows if row["printed_page"] == page]
        counts = Counter(row["layer"] for row in selected)
        page_counts.append({"printed_page": page or "build/unpaged", "rows": len(selected),
                            **{layer: counts[layer] for layer in LAYERS},
                            "explicitly_pending_confidence": sum(bool(re.search(r"first[ -]reading|pending|provisional|not yet", row["confidence"], re.I)) for row in selected)})
    structure = []
    def status(check, passed, detail):
        structure.append({"check": check, "status": "pass" if passed else "flag", "detail": detail})
    progress = read(root / "progress.log").decode("utf-8")
    completed = [int(page) for page in re.findall(r"(?m)^page (\d{3}) done\s", progress)]
    status("ordered-completion-markers", completed == PAGES, f"Found {len(completed)} entries; expected 102 once each in printed order. This does not verify the reading.")
    source_metadata, line_counts = [], {}
    for layer in ("dip", "fr", "en"):
        expected = {f"p{page}.tex" for page in PAGES}
        paths = {path.name: path for path in (root / "sources" / layer).glob("p*.tex")}
        status("page-file-set-" + layer, set(paths) == expected, f"Expected 102 files; found {len(paths)}; missing {len(expected - set(paths))}; extra {len(set(paths) - expected)}.")
        empty = 0
        for name, path in sorted(paths.items()):
            data = read(path)
            lines = data.count(b"\n") + bool(data and not data.endswith(b"\n"))
            empty += not data
            relative = path.relative_to(root).as_posix()
            line_counts[relative] = lines
            source_metadata.append({"file": relative, "bytes": len(data), "physical_lines": lines, "sha256": digest(data)})
        status("nonempty-page-files-" + layer, not empty, f"Empty page files: {empty}.")
    record = read(root / "CHECK_RECORD.md").decode("utf-8")
    headings = list(PAGE_HEADING.finditer(record))
    status("ordered-check-record-headings", [int(item.group(1)) for item in headings] == PAGES, f"Found {len(headings)} page headings; narrative and timestamps were not assessed.")
    metadata_flags = []
    for index, heading in enumerate(headings):
        page = heading.group(1)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(record)
        section = record[heading.end():end]
        selected = [row for row in rows if row["printed_page"] == page]
        layers, kinds = Counter(row["layer"] for row in selected), Counter(row["kind"] for row in selected)
        count_lines = re.findall(r"(?m)^- Corrections in this pass: ([^\r\n]*)", section)
        if len(count_lines) != 1:
            metadata_flags.append({"printed_page": page, "component": "counts", "field": "count-line multiplicity", "recorded": len(count_lines), "current": 1})
        else:
            layer_text, _, kind_text = count_lines[0].partition(". Kinds: ")
            for layer in LAYERS:
                found = re.search(re.escape(layer) + r": (\d+)", layer_text)
                if found and int(found.group(1)) != layers[layer]:
                    metadata_flags.append({"printed_page": page, "component": "counts", "field": layer, "recorded": found.group(1), "current": layers[layer]})
            for kind in KINDS:
                found = re.search(re.escape(kind) + r": (\d+)", kind_text)
                value = int(found.group(1)) if found else 0
                if value != kinds[kind]:
                    metadata_flags.append({"printed_page": page, "component": "kind counts", "field": kind, "recorded": value, "current": kinds[kind]})
        source_lines = re.findall(r"(?m)^- Sources compared: ([^\r\n]*)", section)
        ranges = list(SOURCE_RANGE.finditer(source_lines[0])) if len(source_lines) == 1 else []
        if len(ranges) != 3:
            metadata_flags.append({"printed_page": page, "component": "source ranges", "field": "range multiplicity", "recorded": len(ranges), "current": 3})
        for item in ranges:
            name = f"sources/{item['tree']}/p{item['page']}.tex"
            value = line_counts.get(name, "missing")
            if item["first"] != "1" or item["page"] != page or item["last"] != str(value):
                metadata_flags.append({"printed_page": page, "component": "source ranges", "field": name, "recorded": item["first"] + "–" + item["last"], "current": "1–" + str(value)})
    status("review-sidecar-coverage", not unregistered and len(assignment) == len(rows), f"Aligned IDs: {len(assignment)}; unregistered current ledger records: {len(unregistered)}; existing review events: {len(history)}. No outcome was changed.")
    totals = {"ledger_rows": len(rows), "stable_id_bindings": len(bindings), "existing_review_events": len(history),
              "review_status_counts": dict(Counter(state["status"] for state in states.values())), "unregistered_records": unregistered,
              "exact_duplicate_groups": len(duplicates), "rows_in_exact_duplicate_groups": sum(row["records"] for row in duplicates),
              "repeated_literal_pair_groups": len(repeated), "exact_chain_candidates": len(chains),
              "exact_reversal_candidates": sum(row["relation"] == "exact reversal candidate" for row in chains), "old_equals_new_rows": len(noops),
              "structural_flags": sum(row["status"] == "flag" for row in structure), "check_record_metadata_flags": len(metadata_flags),
              "source_files_counted": len(source_metadata)}
    if any(path.read_bytes() != data for path, data in inputs.items()):
        raise RuntimeError("An input changed during the bookkeeping snapshot; no report was installed.")
    input_hashes = [{"file": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": digest(data)} for path, data in inputs.items() if root in path.parents]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bookkeeping-snapshot-", dir=output.parent) as temporary:
        prepared = Path(temporary) / "prepared"; prepared.mkdir()
        group_fields = ["group_id", "file", "printed_page", "layer", "records", "correction_ids", "ledger_records", "old_sha256", "new_sha256", "interpretation"]
        tables = [
            ("ROW_ID_BINDINGS.tsv", ["review_id", "export_record", "status", "last_event", "row_fingerprint"], bindings),
            ("EXACT_DUPLICATE_ROWS.tsv", group_fields, duplicates), ("REPEATED_LITERAL_PAIRS.tsv", group_fields, repeated),
            ("EXACT_CHAIN_CANDIDATES.tsv", ["earlier_id", "earlier_record", "later_id", "later_record", "file", "printed_page", "relation", "shared_literal_sha256", "shared_literal_characters", "interpretation"], chains),
            ("OLD_EQUALS_NEW.tsv", ["correction_id", "ledger_record", "file", "printed_page", "kind", "literal_characters", "row_fingerprint"], noops),
            ("PAGE_COUNTS.tsv", ["printed_page", "rows", *LAYERS, "explicitly_pending_confidence"], page_counts),
            ("STRUCTURAL_CHECKS.tsv", ["check", "status", "detail"], structure),
            ("CHECK_RECORD_METADATA_FLAGS.tsv", ["printed_page", "component", "field", "recorded", "current"], metadata_flags),
            ("SOURCE_METADATA.tsv", ["file", "bytes", "physical_lines", "sha256"], source_metadata),
            ("INPUT_HASHES.tsv", ["file", "bytes", "sha256"], input_hashes),
        ]
        for name, fields, values in tables:
            (prepared / name).write_bytes(tsv_data(fields, safe_rows(values)))
        (prepared / "SUMMARY.json").write_text(json.dumps({"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "stage": "interim bookkeeping only", **totals}, indent=2) + "\n", encoding="utf-8")
        text = "# Interim bookkeeping snapshot\n\nNo reading decision, scan inspection, source edit or review-state change was performed. Exact duplicate rows, repeated literal pairs and exact chains are candidates for manual bookkeeping review; they may represent intentional repeated occurrences or later edits. Old-equals-new rows may document retained decisions. None is automatically removed or confirmed.\n\nROW_ID_BINDINGS.tsv copies current aligned stable IDs and statuses into a fingerprint-bound report map. It is not a reviewed ledger export. Structural checks assess names, markers, counts and byte-level line ranges; they do not assess narrative adequacy or literal correctness. CHECK_RECORD_METADATA_FLAGS.tsv reports differences from the current ledger/source snapshot without changing the record.\n\nSource files were used only for byte hashes and physical LF counts. No source wording was displayed or interpreted. All input hashes were rechecked before installing this new report directory.\n"
        (prepared / "REPORT.md").write_text(text, encoding="utf-8")
        if any(scan_bytes(path.name, path.read_bytes()) for path in prepared.iterdir()):
            raise ValueError("A generated bookkeeping report contains a privacy pattern; no report was installed.")
        output.mkdir()
        for path in prepared.iterdir():
            os.link(path, output / path.name)
    result = {"report_directory": output.relative_to(root).as_posix(), **totals}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, default=Path("second-reading"))
    create_snapshot(parser.parse_args())


if __name__ == "__main__":
    main()
