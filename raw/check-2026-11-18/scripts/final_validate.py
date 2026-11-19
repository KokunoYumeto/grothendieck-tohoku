"""Inspect delivery structure, privacy and build provenance without editing text.

Run this only when the page audit is ready for final validation. A passing
report is a mechanical result, not a certificate of readings, translations,
proof checks, notes, or visual PDF review.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import zipfile

from build_report import PRINTED_PAGES, completed_pages
from checkpoint import inventory
from check_events_gate import (EVENT_INPUT_NAMES, EVENT_POLICY_PATH, EVENT_TABLE_PATH,
                               evaluate_event_snapshot, read_event_input, recheck_event_inputs)
from privacy_guard import (VALIDATION_REPORT_NAMES, privacy_findings, safe_location, scan_archive_set,
                           scan_bytes, scan_text, unsafe_member)

PRIVACY_FIELDS = ["file", "line_or_pdf_page", "kind", "scope", "finding_id", "file_sha256", "source_offset_start", "source_offset_end", "match_sha256", "classification", "preservation_basis"]
CORRECTION_FIELDS = ["file", "layer", "printed_page", "line", "statement", "old", "new", "evidence", "kind", "confidence"]
REQUIRED = ["CORRECTIONS.tsv", "CHECK_RECORD.md", "CHECK_EVENTS.tsv", "NOTES.md", "PDF_CHECK.md", "README.md", "progress.log"]
CONFIDENCE_ANNOTATION = re.compile(
    r"(?P<degree>high|medium|low)[ \t]*;[ \t]*"
    r"second reading (?P<verdict>confirmed|amended|withdrawn)[ \t]*;[ \t]*"
    r"(?P<review_id>R[0-9]{6,})[ \t]*;[ \t]*(?P<event_id>E[0-9]{6,})"
)


def confidence_annotation(value: object) -> dict[str, str] | None:
    """Parse explicit exporter metadata; never infer a review or its correctness."""
    if not isinstance(value, str):
        return None
    match = CONFIDENCE_ANNOTATION.fullmatch(value.strip(" \t"))
    if match is None:
        return None
    result = match.groupdict()
    for key in ("review_id", "event_id"):
        identifier = result[key]
        digits = identifier[1:]
        if not digits.lstrip("0") or (len(digits) > 6 and digits.startswith("0")):
            return None
    return result


def confidence_checks(rows: list[dict]) -> list[tuple[str, bool, str]]:
    """Return format/identity checks without inspecting correction literals."""
    parsed = [confidence_annotation(row.get("confidence")) for row in rows]
    invalid = [position for position, item in enumerate(parsed, 1) if item is None]
    sample = ", ".join(map(str, invalid[:20])) or "none"
    if len(invalid) > 20:
        sample += ", ..."
    repeated = {}
    for key in ("review_id", "event_id"):
        counts = Counter(item[key] for item in parsed if item is not None)
        repeated[key] = sum(count > 1 for count in counts.values())
    return [
        ("explicit-second-reading-confidence", not invalid,
         f"Rows without a recognized degree, explicit confirmed/amended/withdrawn second-reading verdict, and canonical positive R/E IDs: {len(invalid)}. "
         f"Logical ledger records, first 20: {sample}. This checks metadata, not the reading or event-history binding."),
        ("unique-second-reading-identifiers", not any(repeated.values()),
         f"Repeated annotated row IDs: {repeated['review_id']}; repeated last-event IDs: {repeated['event_id']}. Each retained ledger row must identify its own row and explicit review event."),
    ]


def table(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        return reader.fieldnames or [], list(reader)


def heading_pages(text: str) -> list[int]:
    """Read canonical page records, preserving duplicates, order and outsiders.

    Addendum titles can mention a page without opening another page record.
    A literal fenced example is not a record. The exact canonical heading
    grammar is the one emitted by the record writer.
    """
    result = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]))
            continue
        match = re.fullmatch(r"#{2,3}[ \t]+Printed page[ \t]+([0-9]+)(?:[ \t]+#+)?[ \t]*", line)
        if match:
            result.append(int(match[1]))
    return result

def original_frontmatter_checks(root: Path, original_zip: Path) -> list[tuple[str, bool, str]]:
    results = []
    with zipfile.ZipFile(original_zip) as original:
        for filename in ("README.md", "README.fr.md"):
            target = root / "sources" / filename
            same = target.is_file() and target.read_bytes() == original.read(filename)
            results.append(("unchanged-source-" + filename, same, "Exact byte comparison with supplied source README; any change requires review."))
        for layer in ("dip", "fr", "en"):
            filename = f"main-{layer}.tex"
            old = original.read("main-fr.tex" if layer == "dip" else filename)
            target = root / "sources" / filename
            if not target.is_file():
                results.append(("frontmatter-" + layer, False, "Main file is missing."))
                continue
            new = target.read_bytes()
            old_match = re.search(rb"\\input\{(?:fr|en)[/]p\d{3}\.tex\}", old)
            new_match = re.search(rb"\\input\{(?:dip|fr|en)[/]p\d{3}\.tex\}", new)
            same = bool(old_match and new_match and old[:old_match.start()] == new[:new_match.start()])
            results.append(("frontmatter-" + layer, same, "Exact comparison through the first page input; unchanged prefix preserves the supplied front matter and its credits."))
    return results


def preserved_source_regions(root: Path, original_zip: Path | None) -> dict:
    """Locate byte-identical protected regions; never infer a credit reading."""
    regions = {}
    if original_zip is None:
        return regions
    with zipfile.ZipFile(original_zip) as original:
        for filename in ("README.md", "README.fr.md"):
            path = root / "sources" / filename
            old = original.read(filename)
            if path.is_file() and path.read_bytes() == old:
                regions["sources/" + filename] = (len(old.decode("utf-8-sig")), "Complete source README is byte-identical to the supplied original; this region is required to remain unchanged.", len(old), hashlib.sha256(old).hexdigest())
        for layer in ("dip", "fr", "en"):
            original_layer = "fr" if layer == "dip" else layer
            old = original.read(f"main-{original_layer}.tex")
            path = root / "sources" / f"main-{layer}.tex"
            if not path.is_file():
                continue
            new = path.read_bytes()
            old_match = re.search(rb"\\input\{(?:fr|en)[/]p\d{3}\.tex\}", old)
            new_match = re.search(rb"\\input\{(?:dip|fr|en)[/]p\d{3}\.tex\}", new)
            if old_match and new_match and old[:old_match.start()] == new[:new_match.start()]:
                prefix = new[:new_match.start()]
                regions[f"sources/main-{layer}.tex"] = (len(prefix.decode("utf-8-sig")), "Main-file prefix through the first page input is byte-identical to the supplied original front matter; no credit or rights text was altered.", len(prefix), hashlib.sha256(prefix).hexdigest())
    return regions


def inspect(root: Path, original_zip: Path | None, phase: str | None, archive_path: Path | list[Path] | None) -> tuple[list[dict], list[dict], list[dict]]:
    checks, private, files = [], [], []
    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": safe_location(name), "status": "pass" if passed else "fail", "detail": safe_location(detail)})
    members, excluded = inventory(root)
    protected_regions = preserved_source_regions(root, original_zip)
    hashes = {}
    event_inputs = {name: None for name in EVENT_INPUT_NAMES}
    for member in members:
        data = read_event_input(root, member.relative) if member.relative in EVENT_INPUT_NAMES else member.path.read_bytes()
        if data is None:
            raise RuntimeError("An included event input disappeared; rerun validation.")
        if member.relative in EVENT_INPUT_NAMES:
            if len(data) != member.size:
                raise RuntimeError("An event input changed size after inventory; rerun validation.")
            event_inputs[member.relative] = data
        digest = hashlib.sha256(data).hexdigest()
        hashes[member.relative] = digest
        files.append({"file": safe_location(member.relative), "bytes": member.size, "sha256": digest, "status": "included"})
        found = scan_text(member.relative, member.relative, scope="included filename", location="filename") + scan_bytes(member.relative, data)
        if unsafe_member(member.relative):
            add("safe-delivery-name-" + member.relative, False, "A returned filename is not a safe relative POSIX member name.")
        for item in found:
            item.update(classification="privacy finding or inspection blocker", preservation_basis="")
            region = protected_regions.get(member.relative)
            if (region and hashlib.sha256(data[:region[2]]).hexdigest() == region[3]
                    and item["scope"] == "file content" and isinstance(item["source_offset_end"], int)
                    and item["source_offset_end"] <= region[0]):
                item.update(classification="preserved-source credit/rights conflict", preservation_basis=region[1])
            private.append(item)
    for relative, size, reason in excluded:
        files.append({"file": safe_location(relative), "bytes": size, "sha256": "", "status": "excluded: " + safe_location(reason)})
    for item in evaluate_event_snapshot(event_inputs[EVENT_TABLE_PATH], event_inputs[EVENT_POLICY_PATH]):
        add(item["check"], item["status"] == "pass", item["detail"])
    for filename in REQUIRED:
        path = root / filename
        add("required-" + filename, path.is_file() and path.stat().st_size > 0, "Required deliverable exists and is nonempty.")
    for layer in ("dip", "fr", "en"):
        expected = {f"p{page}.tex" for page in PRINTED_PAGES}
        actual = {path.name for path in (root / "sources" / layer).glob("p*.tex")}
        add("page-file-set-" + layer, actual == expected, f"Expected 102 page files; found {len(actual)}. Missing: {', '.join(sorted(expected - actual)) or 'none'}. Extra: {', '.join(sorted(actual - expected)) or 'none'}.")
        add("main-file-" + layer, (root / "sources" / f"main-{layer}.tex").is_file(), "Standalone main file is present.")
        add("final-pdf-" + layer, (root / "pdf" / f"main-{layer}.pdf").is_file(), "Final PDF is present.")
    add("ordered-page-completion", completed_pages(root) == PRINTED_PAGES, "progress.log must contain all 102 page-completion entries exactly once and in printed order.")
    record = root / "CHECK_RECORD.md"
    if record.is_file():
        pages = heading_pages(record.read_text(encoding="utf-8"))
        add("page-record-sections", pages == PRINTED_PAGES, f"Detected {len(pages)} canonical printed-page sections at heading level two or three outside code fences. This checks headings, not the adequacy of the comparisons described in them.")
    corrections = root / "CORRECTIONS.tsv"
    if corrections.is_file():
        fields, rows = table(corrections)
        add("correction-schema", fields == CORRECTION_FIELDS, "Columns must match the requested correction-ledger schema and order.")
        missing_evidence = [index for index, row in enumerate(rows, 2) if not row.get("evidence", "").strip()]
        add("correction-evidence-present", not missing_evidence, f"Rows with empty evidence: {len(missing_evidence)}. Evidence presence does not establish its adequacy.")
        unfinished = [index for index, row in enumerate(rows, 2) if re.search(r"first[ -]reading|pending|provisional|not yet", row.get("confidence") or "", re.I)]
        add("no-explicitly-provisional-confidence", not unfinished, f"Rows still explicitly marked provisional or awaiting rereading: {len(unfinished)}. This does not infer that a second reading occurred.")
        for name, passed, detail in confidence_checks(rows):
            add(name, passed, detail)
    for filename in ("NOTES.md", "PDF_CHECK.md"):
        path = root / filename
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            placeholders = bool(re.search(r"\bplaceholder\b|\bnot yet (?:started|performed|written|reviewed)\b", text, re.I))
            add("no-obvious-placeholder-" + filename, not placeholders, "Searches explicit placeholder wording only; substantive completion needs the primary reviewer's judgment.")
    if original_zip is not None:
        for name, passed, detail in original_frontmatter_checks(root, original_zip):
            add(name, passed, detail)
    else:
        add("original-credit-comparison-requested", False, "Supply --original-sources to compare the original READMEs and main-file front matter. No credit preservation is certified without that comparison.")
    report_root = root / "build-reports"
    if phase:
        candidates = [report_root / phase]
    else:
        candidates = sorted((path.parent for path in report_root.glob("*/SUMMARY.tsv")), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    current_tex = {name.removeprefix("sources/"): value for name, value in hashes.items() if name.startswith("sources/") and name.endswith(".tex")}
    selected = None
    for candidate in candidates:
        hash_table = candidate / "SOURCE_HASHES.tsv"
        if not hash_table.is_file() or not (candidate / "SUMMARY.tsv").is_file():
            continue
        _, entries = table(hash_table)
        recorded = {row["file"]: row["sha256"] for row in entries}
        if recorded == current_tex:
            selected = candidate
            break
    add("build-matches-current-tex", selected is not None, "A build phase must have hashes for the exact current TeX sources.")
    if selected:
        _, entries = table(selected / "SUMMARY.tsv")
        by_layer = {row["layer"]: row for row in entries}
        for layer in ("dip", "fr", "en"):
            row = by_layer.get(layer, {})
            passed = (row.get("exit_codes") == "0,0" and row.get("limit_passed") == "yes"
                      and int(row.get("errors_final_pass", "1")) == 0
                      and float(row.get("max_overfull_pt", "inf")) <= 2.0)
            add("final-build-" + layer, passed, f"Phase {selected.name}: two successful passes, zero final-pass errors, and maximum overflow at most 2 pt are required.")
            delivered_hash = hashes.get(f"pdf/main-{layer}.pdf")
            add("pdf-matches-built-" + layer, bool(delivered_hash and row.get("pdf_sha256") == delivered_hash), "Delivered PDF hash must match the selected build-phase PDF.")
    if archive_path is not None:
        paths = [archive_path] if isinstance(archive_path, Path) else archive_path
        archived = {}
        archive_findings = scan_archive_set(paths, inventory_out=archived)
        for item in archive_findings:
            item.update(classification="archive privacy finding or inspection blocker", preservation_basis="")
        private.extend(archive_findings)
        add("archive-privacy-and-structure", not archive_findings, f"Archive-set inspection found {len(archive_findings)} privacy or structural blockers. Every textual member, generated manifest, member name and ZIP/member comment was examined; chunked files were reconstructed.")
        actual = archived.get("files", {})
        missing, extra = set(hashes) - set(actual), set(actual) - set(hashes)
        mismatches = [name for name in set(hashes) & set(actual) if hashes[name] != actual[name]["sha256"]]
        add("archive-current-deliverables", not missing and not extra and not mismatches, f"Missing current deliverables: {len(missing)}; unexpected logical files: {len(extra)}; differing contents: {len(mismatches)}. All validation reports are included in this exact byte comparison.")
        manifest = archived.get("file_list_rows", [])
        included_rows = [row for row in manifest if row.get("status") == "included"]
        manifest_by_name = {row.get("path"): row for row in included_rows}
        manifest_ok = len(included_rows) == len(manifest_by_name) and set(manifest_by_name) == set(actual)
        manifest_ok = manifest_ok and all(row.get("sha256") == actual[name]["sha256"] and row.get("bytes") == str(actual[name]["bytes"]) for name, row in manifest_by_name.items())
        add("archive-manifest-binding", manifest_ok, "The generated file list must identify every logical deliverable once with its exact byte count and SHA-256.")
        info = archived.get("archive_info", {})
        add("archive-final-kind-and-parts", info.get("kind") == "final" and info.get("archive_count") == str(len(paths)), "The generated archive information must declare final delivery and the exact supplied part count.")
    conflicts = [item for item in private if item["classification"] == "preserved-source credit/rights conflict"]
    ordinary = [item for item in private if item not in conflicts]
    add("privacy", not ordinary, f"Found {len(ordinary)} recognizable privacy occurrences or inspection blockers outside protected original regions. Reports contain safe locations and hashes, never sensitive matches. No source is redacted automatically.")
    add("privacy-source-credit-conflicts", not conflicts, f"Found {len(conflicts)} privacy-pattern conflicts in byte-identical protected source regions. They are reported separately, never silently waived or removed. A conflict blocks final packaging until resolved explicitly by the primary reviewer.")
    recheck_event_inputs(root, event_inputs)
    return checks, private, files


def write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_reports(destination: Path, checks: list[dict], private: list[dict], files: list[dict]) -> None:
    conflicts = [row for row in private if row.get("classification") == "preserved-source credit/rights conflict"]
    ordinary = [row for row in private if row not in conflicts]
    write_rows(destination / "FINAL_VALIDATION_CHECKS.tsv", ["check", "status", "detail"], checks)
    write_rows(destination / "FINAL_VALIDATION_PRIVACY.tsv", PRIVACY_FIELDS, ordinary)
    write_rows(destination / "FINAL_VALIDATION_CREDIT_CONFLICTS.tsv", PRIVACY_FIELDS, conflicts)
    write_rows(destination / "FINAL_VALIDATION_INVENTORY.tsv", ["file", "bytes", "sha256", "status"], files)
    failed = [row for row in checks if row["status"] == "fail"]
    content = (
        "# Mechanical final validation\n\n"
        + datetime.now(timezone.utc).strftime("Run at %Y-%m-%dT%H:%M:%SZ.\n\n")
        + f"Checks: {len(checks)}; failed checks: {len(failed)}; ordinary privacy findings or inspection blockers: {len(ordinary)}; protected-source conflicts: {len(conflicts)}.\n\n"
        "This report checks file structure, explicit completion markers, privacy patterns, "
        "selected unchanged front matter, and recorded build provenance. It does not "
        "certify scan readings, translation fidelity, literal correctness, correction justifications, "
        "proof checks, note completeness, or visual review of the PDFs.\n\n"
        "Privacy scanning examines all declared or detected textual files regardless of extension, "
        "included filenames, extracted PDF text and textual PDF metadata/objects. PDF attachments "
        "are an inspection blocker. Binary image contents are not OCRed. Pattern detection does "
        "not claim to identify every obfuscated private reference. A possible path may be notation "
        "or a regular expression and needs manual assessment. Nothing is automatically changed "
        "in sources, mathematical records, credits or rights notices.\n\n"
        "Findings in byte-identical protected source README/front-matter regions are written "
        "separately to FINAL_VALIDATION_CREDIT_CONFLICTS.tsv. They remain unresolved constraints, "
        "not automatic permission to alter or disclose credits. Both privacy checks must pass "
        "for final packaging. Reports retain safe locators and hashes without copying sensitive matches.\n\n"
        "The inventory records selected deliverables. The five exact generated validation-report "
        "names are omitted only from the preflight's stale-inventory comparison, because a report "
        "cannot hash its own final bytes. Those files are still scanned, freshly hashed by preflight, "
        "packaged, and checked byte for byte in a later read-only archive validation.\n\n"
        "An archive-set check scans every textual member, generated manifest, member name, ZIP "
        "comment and member comment. Split logical files are reconstructed before inspection. "
        "It also checks exact current-file membership/hashes and the generated manifest bindings.\n\n"
        "## Checks needing attention\n\n"
        + ("\n".join("- " + row["check"] + ": " + row["detail"] for row in failed) if failed else "No mechanical failure was found.")
        + "\n"
    )
    (destination / "FINAL_VALIDATION.md").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--original-sources", type=Path, help="Supplied original source ZIP; used only for credit/front-matter comparisons")
    parser.add_argument("--final-phase", help="Specific build-report phase to verify")
    parser.add_argument("--archive", type=Path, action="append", help="Already-created final ZIP part; repeat for every part. Archive checks are read-only by default")
    parser.add_argument("--report-dir", type=Path, help="Optional report destination; archive-check reports must be outside the delivery tree")
    args = parser.parse_args()
    root = args.root.resolve()
    checks, private, files = inspect(root, args.original_sources, args.final_phase, args.archive)
    destination = args.report_dir.resolve() if args.report_dir else (None if args.archive else root)
    if destination is not None:
        if args.archive and (destination == root or root in destination.parents):
            raise ValueError("Archive-check reports must be outside the delivered tree so packaged report bytes remain unchanged.")
        destination.mkdir(parents=True, exist_ok=True)
        write_reports(destination, checks, private, files)
        generated_findings = []
        for name in VALIDATION_REPORT_NAMES:
            generated_findings.extend(scan_bytes(name, (destination / name).read_bytes()))
        for item in generated_findings:
            item.update(classification="generated report privacy finding or inspection blocker", preservation_basis="")
        private.extend(generated_findings)
        checks.append({"check": "generated-validation-report-privacy", "status": "fail" if generated_findings else "pass",
                       "detail": f"The five newly generated reports were inspected; findings or blockers: {len(generated_findings)}."})
        write_reports(destination, checks, private, files)
        if any(scan_bytes(name, (destination / name).read_bytes()) for name in VALIDATION_REPORT_NAMES):
            raise RuntimeError("A generated validation report still contains a privacy pattern; final preflight will refuse it.")
    failed = [row for row in checks if row["status"] == "fail"]
    print(f"Mechanical validation: {len(checks)} checks, {len(failed)} failures, {len(private)} privacy findings or inspection blockers. " + ("Reports written." if destination else "Read-only archive check; no report or source was changed."))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
