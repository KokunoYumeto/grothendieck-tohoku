"""Create an immutable lexical proof-cue snapshot of the diplomatic page files.

The output supplies literal leads and structural locators only. It makes no
proof, editorial, scan-reading, completeness, or correctness determination.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile

from control_word_inventory import (
    BLOCKED_DIRS, coordinates, file_hash, read_snapshot, require_safe_name, sha, tsv_bytes, utc,
)
from privacy_guard import safe_location, scan_bytes
from proof_cue_lex import CUE_PATTERNS, LIMITATIONS, scan_page

PAGES = list(range(119, 184)) + list(range(185, 222))
PAGE_RANK = {page: rank for rank, page in enumerate(PAGES)}
LOCATION_FIELDS = [
    "file", "layer", "printed_page", "line", "column", "end_line", "end_column",
    "offset", "end_offset", "scope", "source_sha256",
]
ANCHOR_CONTEXT_FIELDS = [
    "preceding_anchor_id", "preceding_anchor_file", "preceding_anchor_page",
    "preceding_anchor_line", "preceding_anchor_literal",
]
HEADING_CONTEXT_FIELDS = [
    "preceding_numbered_heading_id", "preceding_numbered_heading_file",
    "preceding_numbered_heading_page", "preceding_numbered_heading_line",
    "preceding_numbered_heading_literal", "preceding_numbered_heading_number",
]
CUE_FIELDS = [
    "cue_id", "family", *LOCATION_FIELDS, "literal_cue", "literal_cue_sha256",
    "fragment_id", "fragment_start_line", "fragment_end_line", "paragraph_fragment",
    "paragraph_fragment_sha256", "fragment_completeness", "fragment_limitation",
    *ANCHOR_CONTEXT_FIELDS, *HEADING_CONTEXT_FIELDS,
    "privacy_filtered_fields", "review_status",
]
FRAGMENT_FIELDS = [
    "fragment_id", *LOCATION_FIELDS, "paragraph_fragment", "paragraph_fragment_sha256",
    "completeness", "left_boundary", "right_boundary", "limitation",
    "privacy_filtered_fields", "review_status",
]
ANCHOR_FIELDS = [
    "anchor_id", *LOCATION_FIELDS, "literal_source", "argument_literal",
    "argument_sha256", "argument_offset", "argument_end_offset",
    "privacy_filtered_fields", "review_status",
]
HEADING_FIELDS = [
    "heading_id", *LOCATION_FIELDS, "literal_type", "literal_label", "literal_number",
    "numbered", "literal_source", "literal_source_sha256", "recognition_rule",
    *ANCHOR_CONTEXT_FIELDS, "privacy_filtered_fields", "review_status",
]
NOTE_FIELDS = [
    "note_id", *LOCATION_FIELDS, "kind", "detail", "privacy_filtered_fields", "review_status",
]


def source_paths(root: Path) -> dict[str, Path]:
    sources, directory = root / "sources", root / "sources/dip"
    if sources.is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("Regular source and diplomatic page directories are required.")
    result = {}
    for page in PAGES:
        path = directory / f"p{page:03d}.tex"
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"A regular diplomatic page file is required for printed page {page}.")
        result[path.relative_to(root).as_posix()] = path
    recognized = {p.name for p in directory.glob("p*.tex") if re.fullmatch(r"p[0-9]{3}\.tex", p.name)}
    if recognized != {f"p{page:03d}.tex" for page in PAGES}:
        raise ValueError("Diplomatic page filenames do not match the required 102-page set.")
    return result


def clean_record(row: dict) -> dict:
    result = dict(row)
    filtered = []
    for key, value in row.items():
        if isinstance(value, str):
            result[key] = safe_location(value)
            if result[key] != value:
                filtered.append(key)
    result["privacy_filtered_fields"] = ",".join(filtered)
    return result


def location(item: dict, metadata: dict) -> dict:
    return {**metadata, **{key: item.get(key, "") for key in LOCATION_FIELDS if key not in metadata}}


def active(item: dict) -> bool:
    return item.get("scope") == "active"


def position(item: dict) -> tuple[int, int]:
    return PAGE_RANK[int(item["printed_page"])], int(item["offset"])


def preceding(item: dict, events: list[dict], keys: list[tuple[int, int]]) -> dict | None:
    index = bisect_left(keys, position(item)) - 1
    return events[index] if index >= 0 else None


def anchor_context(item: dict | None) -> dict:
    if item is None:
        return dict.fromkeys(ANCHOR_CONTEXT_FIELDS, "")
    return dict(zip(ANCHOR_CONTEXT_FIELDS, [
        item["anchor_id"], item["file"], item["printed_page"], item["line"], item["argument_literal"],
    ]))


def heading_context(item: dict | None) -> dict:
    if item is None:
        return dict.fromkeys(HEADING_CONTEXT_FIELDS, "")
    return dict(zip(HEADING_CONTEXT_FIELDS, [
        item["heading_id"], item["file"], item["printed_page"], item["line"],
        item["literal_source"], item["literal_number"],
    ]))


def bounded_nonactive_fragment(text: str, item: dict, metadata: dict, identifier: str) -> dict:
    """Retain source-line context without interpreting nonactive paragraphs."""
    first, last = int(item["offset"]), int(item["end_offset"])
    left = text.rfind("\n", 0, first) + 1
    right = text.find("\n", last)
    right = len(text) if right < 0 else right
    limitation = "Nonactive or uncertain lexical scope: only bounded raw source-line context is supplied; paragraph boundaries are not asserted."
    if right - left > 640:
        if last - first > 640:
            left = right = first
        else:
            left = max(left, min(first - (640 - (last - first)) // 2, right - 640))
            right = left + 640
    if text[left:right].strip() and text[left:right].strip() == text.strip():
        left, right = first, last
        if text[left:right].strip() == text.strip():
            left = right = first
    raw = text[left:right]
    starts = [0] + [match.end() for match in re.finditer("\n", text)]
    line, column = coordinates(left, starts)
    end_line, end_column = coordinates(right, starts)
    return {
        **metadata, "fragment_id": identifier, "line": line, "column": column,
        "end_line": end_line, "end_column": end_column, "offset": left, "end_offset": right,
        "scope": item["scope"], "paragraph_fragment": raw,
        "paragraph_fragment_sha256": sha(raw.encode("utf-8")),
        "completeness": "bounded_nonactive_source_lines" if raw else "omitted_nonactive_context",
        "left_boundary": "source-line or bounded-window start",
        "right_boundary": "source-line or bounded-window end", "limitation": limitation,
        "review_status": "pending primary review",
    }


def inventory_bytes(snapshot: dict[str, bytes]) -> tuple[dict, dict]:
    cues, fragments, anchors, headings, notes, sources = [], [], [], [], [], []
    for name, data in snapshot.items():
        match = re.fullmatch(r"sources/dip/p([0-9]{3})\.tex", name)
        if not match or int(match.group(1)) not in PAGE_RANK:
            raise ValueError("An input member is outside the diplomatic page-source scope.")
        page = int(match.group(1))
        text = data.decode("utf-8-sig")
        scan = scan_page(text)
        metadata = {"file": name, "layer": "dip", "printed_page": page, "source_sha256": sha(data)}
        referenced = {row["fragment_id"] for row in scan["cues"]}
        fragment_lookup = {}
        for number, item in enumerate(scan["fragments"], 1):
            if item["fragment_id"] not in referenced:
                continue
            raw = item["fragment"]
            fragment = {
                **location(item, metadata), "fragment_id": f"P{page:03d}-{number:04d}",
                "paragraph_fragment": raw, "paragraph_fragment_sha256": sha(raw.encode("utf-8")),
                "completeness": item["completeness"], "left_boundary": item["left_boundary"],
                "right_boundary": item["right_boundary"], "limitation": item["limitation"],
                "review_status": "pending primary review",
            }
            if raw.strip() and raw.strip() == text.strip():
                fragment["paragraph_fragment"] = ""
                fragment["completeness"] = "omitted whole-page span"
                fragment["limitation"] += "; whole-page guard withheld the fragment"
            fragment_lookup[item["fragment_id"]] = fragment
            fragments.append(fragment)
        for number, item in enumerate(scan["anchors"], 1):
            anchors.append({
                **location(item, metadata), "anchor_id": f"A{page:03d}-{number:04d}",
                "literal_source": item["matched"], "argument_literal": item["argument"],
                "argument_sha256": sha(item["argument"].encode("utf-8")),
                "argument_offset": item["argument_offset"], "argument_end_offset": item["argument_end_offset"],
                "review_status": "pending primary review",
            })
        for number, item in enumerate(scan["headings"], 1):
            headings.append({
                **location(item, metadata), "heading_id": f"H{page:03d}-{number:04d}",
                "literal_type": item["heading_type"], "literal_label": item["label"],
                "literal_number": item["number"], "numbered": "yes" if item["numbered"] else "no",
                "literal_source": item["matched"], "literal_source_sha256": sha(item["matched"].encode("utf-8")),
                "recognition_rule": item["rule"], "review_status": "pending primary review",
            })
        fallback_fragments = {}
        for number, item in enumerate(scan["cues"], 1):
            fragment = fragment_lookup.get(item["fragment_id"])
            if fragment is None:
                if item["scope"] == "active":
                    raise ValueError("An active lexical cue has no fragment binding.")
                fragment = bounded_nonactive_fragment(text, item, metadata, f"P{page:03d}-X{number:04d}")
                key = (fragment["offset"], fragment["end_offset"], fragment["scope"])
                if key in fallback_fragments:
                    fragment = fallback_fragments[key]
                else:
                    fallback_fragments[key] = fragment
                    fragments.append(fragment)
            cues.append({
                **location(item, metadata), "cue_id": f"C{page:03d}-{number:04d}", "family": item["family"],
                "literal_cue": item["matched"], "literal_cue_sha256": sha(item["matched"].encode("utf-8")),
                "fragment_id": fragment["fragment_id"], "fragment_start_line": fragment["line"],
                "fragment_end_line": fragment["end_line"], "paragraph_fragment": fragment["paragraph_fragment"],
                "paragraph_fragment_sha256": fragment["paragraph_fragment_sha256"],
                "fragment_completeness": fragment["completeness"], "fragment_limitation": fragment["limitation"],
                "review_status": "pending primary review",
            })
        for number, item in enumerate(scan["notes"], 1):
            notes.append({**location(item, metadata), "note_id": f"N{page:03d}-{number:04d}",
                          "kind": item["kind"], "detail": item["detail"], "review_status": "pending primary review"})
        sources.append({"file": name, "printed_page": page, "bytes": len(data),
                        "lines": data.count(b"\n") + int(bool(data) and not data.endswith(b"\n")), "sha256": sha(data)})
    for rows in [cues, fragments, anchors, headings, notes]:
        rows.sort(key=lambda row: (*position(row), str(row.get("family", ""))))
    active_anchors = [row for row in anchors if active(row)]
    numbered_headings = [row for row in headings if active(row) and row["numbered"] == "yes"]
    anchor_keys, heading_keys = list(map(position, active_anchors)), list(map(position, numbered_headings))
    for row in headings:
        row.update(anchor_context(preceding(row, active_anchors, anchor_keys)))
    for row in cues:
        row.update(anchor_context(preceding(row, active_anchors, anchor_keys)))
        row.update(heading_context(preceding(row, numbered_headings, heading_keys)))
    cues, fragments, anchors, headings, notes = [
        [clean_record(row) for row in rows] for rows in [cues, fragments, anchors, headings, notes]
    ]
    candidates = [row for row in cues if row["scope"] in {"active", "uncertain"}]
    comments = [row for row in cues if row["scope"] == "comment"]
    literals = [row for row in cues if row["scope"] == "literal_or_verbatim"]
    numbered = [row for row in headings if row["scope"] == "active" and row["numbered"] == "yes"]
    page_rows = []
    for page in PAGES:
        local_cues = [row for row in cues if row["printed_page"] == page]
        page_rows.append({"printed_page": page, "file": f"sources/dip/p{page:03d}.tex",
                          "present": "yes" if any(s["printed_page"] == page for s in sources) else "no",
                          "cue_candidates": sum(row["scope"] in {"active", "uncertain"} for row in local_cues),
                          "comment_cues": sum(row["scope"] == "comment" for row in local_cues),
                          "literal_cues": sum(row["scope"] == "literal_or_verbatim" for row in local_cues),
                          "active_anchors": sum(row["printed_page"] == page and active(row) for row in anchors),
                          "numbered_heading_candidates": sum(row["printed_page"] == page for row in numbered),
                          "review_status": "pending primary review"})
    family_rows = []
    for pattern in CUE_PATTERNS:
        family = pattern["family"]
        local = [row for row in cues if row["family"] == family]
        family_rows.append({"family": family, "label": pattern["label"], "raw_matches": len(local),
                            "cue_candidates": sum(row["scope"] in {"active", "uncertain"} for row in local),
                            "comment_matches": sum(row["scope"] == "comment" for row in local),
                            "literal_matches": sum(row["scope"] == "literal_or_verbatim" for row in local)})
    tables = {
        "CUES.tsv": (CUE_FIELDS, candidates), "COMMENT_CUES.tsv": (CUE_FIELDS, comments),
        "LITERAL_CUES.tsv": (CUE_FIELDS, literals), "ALL_CUE_MATCHES.tsv": (CUE_FIELDS, cues),
        "PARAGRAPH_FRAGMENTS.tsv": (FRAGMENT_FIELDS, fragments),
        "LAYER_TARGETS.tsv": (ANCHOR_FIELDS, anchors), "HEADING_CANDIDATES.tsv": (HEADING_FIELDS, headings),
        "NUMBERED_HEADINGS.tsv": (HEADING_FIELDS, numbered), "LEXICAL_NOTES.tsv": (NOTE_FIELDS, notes),
        "PAGE_COVERAGE.tsv": (list(page_rows[0]), page_rows),
        "FAMILY_COUNTS.tsv": (list(family_rows[0]), family_rows),
        "SOURCE_HASHES.tsv": (["file", "printed_page", "bytes", "lines", "sha256"], sources),
    }
    summary = {
        "generated_utc": utc(), "source_files": len(sources), "expected_source_files": len(PAGES),
        "raw_cue_matches": len(cues), "cue_candidates": len(candidates), "comment_cues": len(comments),
        "literal_cues": len(literals), "candidate_pages": len({row["printed_page"] for row in candidates}),
        "paragraph_fragments": len(fragments), "active_layer_targets": len(active_anchors),
        "all_layer_targets": len(anchors), "typed_heading_candidates": len(headings),
        "active_numbered_heading_candidates": len(numbered), "lexical_notes": len(notes),
        "fragment_completeness_counts": dict(Counter(row["completeness"] for row in fragments)),
        "privacy_filtered_records": sum(bool(row["privacy_filtered_fields"]) for group in [cues, fragments, anchors, headings, notes] for row in group),
        "review_status": "pending primary review; lexical leads only",
    }
    return tables, summary


def recheck(root: Path, snapshot: dict[str, bytes]) -> None:
    paths = source_paths(root)
    if set(paths) != set(snapshot) or any(
        file_hash(path) != (len(snapshot[name]), sha(snapshot[name])) for name, path in paths.items()
    ):
        raise RuntimeError("The diplomatic source snapshot changed; no report was installed.")


def run(args) -> dict:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside a protected context folder.")
    if args.output.is_absolute() or "interim" not in args.output.name.casefold():
        raise ValueError("Use a fresh relative output directory explicitly named interim.")
    require_safe_name(args.output.as_posix())
    if any(part.casefold() in BLOCKED_DIRS for part in args.output.parts):
        raise ValueError("The output cannot be placed inside a protected context folder.")
    cursor = root
    for part in args.output.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("The output path must not traverse a symbolic link.")
    output = (root / args.output).resolve()
    if output == root or root not in output.parents or any(
        output == root / name or root / name in output.parents for name in ("sources", "pdf", "scripts", "second-reading")
    ):
        raise ValueError("Use a new report directory outside sources, PDFs, scripts and review state.")
    if output.exists():
        raise ValueError("The interim snapshot already exists and will not be overwritten.")
    paths = source_paths(root)
    snapshot = {name: read_snapshot(path) for name, path in paths.items()}
    tables, summary = inventory_bytes(snapshot)
    rules = {"cue_patterns": CUE_PATTERNS, "limitations": LIMITATIONS,
             "nearest_locator_rule": "strictly preceding lexical start position in printed-page order; active LayerTarget or active numbered heading; no semantic association",
             "coordinates": "one-based decoded-character line/column; zero-based offsets; both end coordinates and end offsets are exclusive",
             "nonactive_fragment_rule": "bounded raw source-line context up to 640 characters; no paragraph boundary claim; whole-page context withheld",
             "scope": "only sources/dip leaf page files; all review statuses pending"}
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads["RULES.json"] = (json.dumps(rules, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    source_set_hash = sha(payloads["SOURCE_HASHES.tsv"])
    payloads["INPUT_HASHES.tsv"] = tsv_bytes(["role", "file", "sha256"], [
        {"role": "diplomatic source inventory", "file": "SOURCE_HASHES.tsv", "sha256": source_set_hash},
        {"role": "literal and structural rules", "file": "RULES.json", "sha256": sha(payloads["RULES.json"])},
    ])
    payloads["SUMMARY.json"] = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    report = ["# Interim proof-cue leads", "", "Generated " + summary["generated_utc"] + ".", "",
              "This is a lexical lead inventory for the primary reviewer. It does not establish that a proof is omitted, deferred, supplied, valid, needed or checked. It is not a complete inventory of author claims. Every status remains pending.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items() if isinstance(value, int))
    report += ["", "## Tables", "",
               "CUES.tsv contains active or uncertain lexical matches; COMMENT_CUES.tsv and LITERAL_CUES.tsv retain other scopes separately. ALL_CUE_MATCHES.tsv is their union. Each cue carries its literal match, source hash, file-local paragraph fragment and its boundaries/limitations, plus the strictly preceding active LayerTarget and recognized numbered-heading locator across the printed-page stream.", "",
               "PARAGRAPH_FRAGMENTS.tsv deduplicates only fragments referenced by a cue. LAYER_TARGETS.tsv records every recognized explicit LayerTarget argument, not only labels that appear to name statements. HEADING_CANDIDATES.tsv includes recognized typed heading candidates; NUMBERED_HEADINGS.tsv is the active subset with an explicitly parsed literal number. No anchor-to-statement identity is inferred.", "",
               "PAGE_COVERAGE.tsv includes all 102 printed pages, including zero-cue pages. FAMILY_COUNTS.tsv and RULES.json expose every exact matching pattern. SOURCE_HASHES.tsv and INPUT_HASHES.tsv bind the captured inputs. Snapshot IDs are local to this inventory and are not ledger review IDs.", "",
               "## Limits and preservation", "",
               "A complete fragment means a lexical file-local paragraph block, not a claim that the author's paragraph starts or ends there. Paragraphs may continue across page files. Bounded or withheld fragments are explicitly marked. Whole pages are never emitted as paragraph fragments. Macro expansion, TeX execution, semantic prose classification and proof assessment are not performed.", "",
               "Returned source-derived fields are privacy-filtered if the existing privacy patterns match. Such fields are marked; hashes bind their original literal values. The source files and credits are never changed. A filtered fragment is not byte-for-byte literal display.", "",
               "Only diplomatic leaf page files are read. No original scans, other source layers, main files, preamble, ledger, review events or protected context folders are read by this helper. The 102-file set and all source hashes are rechecked before exclusive installation; prior snapshots remain unchanged.", "",
               "Additional lexical limits:", ""]
    report.extend("- " + str(item) for item in LIMITATIONS)
    report.append("")
    payloads["REPORT.md"] = "\n".join(report).encode("utf-8")
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Generated metadata has a privacy finding; no snapshot was installed.")
    with tempfile.TemporaryDirectory(prefix="proof-cue-inventory-", dir=root.parent) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        recheck(root, snapshot)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir()
        installed = []
        try:
            for name in sorted(payloads):
                path = output / name
                os.link(prepared / name, path)
                installed.append(path)
        except BaseException:
            for path in installed:
                path.unlink()
            output.rmdir()
            raise
    print(json.dumps({**summary, "report_directory": output.relative_to(root).as_posix()}, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
