"""Create a page-sorted interim terminology recurrence candidate inventory.

Only literal/regular-expression matches and lexical TeX contexts are reported.
No spelling, translation, mathematics or scan reading is judged. Source files,
correction ledgers, review state and existing snapshots remain unchanged.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile

from control_word_inventory import (
    BLOCKED_DIRS, coordinates, file_hash, read_snapshot, require_safe_name, sha,
    tsv_bytes, utc,
)
from math_font_context import scan_font_context
from privacy_guard import safe_location, scan_bytes

PAGES = list(range(119, 184)) + list(range(185, 222))
PAGE_RANK = {page: index for index, page in enumerate(PAGES)}
LAYER_RANK = {"dip": 0, "fr": 1, "en": 2}
LEFT, RIGHT = r"(?<![\w\\])", r"(?!\w)"
SEPARATOR = r"(?:[ \t\r\n~]+|[ \t]*-[ \t]*)"
ENGLISH_TERMS = [
    ("en_direct_limits", "direct limit(s)", "direct" + SEPARATOR + "limits?"),
    ("en_inverse_limits", "inverse limit(s)", "inverse" + SEPARATOR + "limits?"),
    ("en_direct_systems", "direct system(s)", "direct" + SEPARATOR + "systems?"),
    ("en_inverse_systems", "inverse system(s)", "inverse" + SEPARATOR + "systems?"),
    ("en_flabby", "flabby", "flabby"),
    ("en_schemes", "scheme(s) in lexical text or uncertain context", "schemes?"),
    ("en_boundary_elements", "boundary element(s)", "boundary" + SEPARATOR + "elements?"),
    ("en_boundary_homomorphisms", "boundary homomorphism(s)", "boundary" + SEPARATOR + "homomorphisms?"),
    ("en_positive_degrees", "positive degree(s)", "positive" + SEPARATOR + "degrees?"),
]
FRENCH_TERMS = [
    ("fr_coefficients", "coefficients"),
    ("fr_du_homomorphisme", "du homomorphisme"),
    ("fr_de_homomorphisme", "de homomorphisme"),
]
PATTERNS = [
    {"family": family, "label": label, "language": "English", "layers": "en",
     "pattern": LEFT + expression + RIGHT, "flags": "IGNORECASE; Unicode word boundaries",
     "context_rule": "text or uncertain contexts; recognized math excluded" if family == "en_schemes"
                     else "all visited lexical contexts; skipped material excluded"}
    for family, label, expression in ENGLISH_TERMS
] + [
    {"family": family, "label": literal, "language": "French", "layers": "dip,fr",
     "pattern": LEFT + re.escape(literal) + RIGHT, "flags": "case-sensitive; Unicode word boundaries",
     "context_rule": "all visited lexical contexts; skipped material excluded"}
    for family, literal in FRENCH_TERMS
]
PATTERN_RANK = {row["family"]: index for index, row in enumerate(PATTERNS)}
MATCH_FIELDS = [
    "match_id", "family", "layer", "file", "printed_page", "line", "end_line",
    "column", "end_column", "matched_token", "source_line", "source_line_sha256",
    "lexical_mode", "context_category", "context_name", "context_caveat",
    "file_has_lexical_notes", "source_line_privacy_filtered", "disposition",
    "exclusion_reason", "review_status",
]


def source_paths(root: Path) -> dict[str, Path]:
    result = {}
    sources = root / "sources"
    if sources.is_symlink() or not sources.is_dir():
        raise ValueError("A regular source directory is required.")
    for layer in LAYER_RANK:
        directory = sources / layer
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Regular dip, fr and en page directories are required.")
        for path in sorted(directory.glob("p*.tex")):
            if path.is_symlink() or not path.is_file():
                continue
            match = re.fullmatch(r"p([0-9]{3})\.tex", path.name)
            if not match:
                continue
            page = int(match.group(1))
            if page not in PAGE_RANK:
                raise ValueError("A page filename is outside the documented printed-page order.")
            name = path.relative_to(root).as_posix()
            require_safe_name(name)
            result[name] = path
    return dict(sorted(result.items()))


def match_context(start: dict, end: dict) -> tuple[str, str, str, str, str]:
    if not start["visited"] or not end["visited"]:
        return "", "skipped lexical material or syntax", "", "", "skipped lexical material or syntax"
    names = list(dict.fromkeys([start["context_name"], end["context_name"]]))
    caveats = list(dict.fromkeys(value for value in [start["context_caveat"], end["context_caveat"]] if value))
    if (start["observed_mode"], start["context_category"], start["context_name"]) != (
        end["observed_mode"], end["context_category"], end["context_name"]
    ):
        return "unknown", "mixed lexical contexts", "; ".join(names), "; ".join(caveats + ["match endpoints have different lexical contexts"]), ""
    return start["observed_mode"], start["context_category"], start["context_name"], "; ".join(caveats), ""


def inventory_bytes(snapshot: dict[str, bytes]) -> tuple[dict, dict]:
    matches, notes, sources, files = [], [], [], []
    for name, data in snapshot.items():
        path_match = re.fullmatch(r"sources/(dip|fr|en)/p([0-9]{3})\.tex", name)
        if path_match is None:
            raise ValueError("A snapshot member is not an eligible relative page-source name.")
        layer, page = path_match.group(1), int(path_match.group(2))
        text = data.decode("utf-8-sig")
        starts = [0] + [item.end() for item in re.finditer("\n", text)]
        raw = []
        for pattern in PATTERNS:
            if layer not in pattern["layers"].split(","):
                continue
            flags = re.IGNORECASE if pattern["language"] == "English" else 0
            for found in re.finditer(pattern["pattern"], text, flags):
                raw.append((pattern, found))
        offsets = {position for _, found in raw for position in (found.start(), found.end() - 1)}
        scan = scan_font_context(data, offsets)
        probes = {item["offset"]: item for item in scan["probes"]}
        metadata = {"file": name, "layer": layer, "printed_page": page}
        for pattern, found in raw:
            first_line, column = coordinates(found.start(), starts)
            end_line, end_column = coordinates(found.end() - 1, starts)
            line_start = starts[first_line - 1]
            line_end = starts[end_line] if end_line < len(starts) else len(text)
            source_line = text[line_start:line_end].rstrip("\r\n")
            filtered_line = safe_location(source_line)
            mode, category, context_name, caveat, excluded = match_context(
                probes[found.start()], probes[found.end() - 1]
            )
            if not excluded and pattern["family"] == "en_schemes" and mode == "math":
                excluded = "recognized math context; prose scheme filter"
            matches.append({
                **metadata, "family": pattern["family"], "line": first_line,
                "end_line": end_line, "column": column, "end_column": end_column,
                "matched_token": found.group(), "source_line": filtered_line,
                "source_line_sha256": sha(source_line.encode("utf-8")),
                "lexical_mode": mode, "context_category": category,
                "context_name": context_name, "context_caveat": caveat,
                "file_has_lexical_notes": "yes" if scan["notes"] else "no",
                "source_line_privacy_filtered": "yes" if filtered_line != source_line else "no",
                "disposition": "excluded raw match" if excluded else "candidate",
                "exclusion_reason": excluded,
                "review_status": "not assessed; raw match retained" if excluded else "pending manual review",
            })
        notes.extend({**metadata, **item} for item in scan["notes"])
        sources.append({"file": name, "bytes": len(data), "sha256": sha(data)})
        files.append({**metadata, "lines": scan["lines"], "raw_matches": len(raw), "lexical_notes": len(scan["notes"])})
    matches.sort(key=lambda row: (PAGE_RANK[int(row["printed_page"])], LAYER_RANK[row["layer"]],
                                  row["line"], row["column"], PATTERN_RANK[row["family"]]))
    for number, row in enumerate(matches, 1):
        row["match_id"] = f"T{number:06d}"
    candidates = [row for row in matches if row["disposition"] == "candidate"]
    excluded = [row for row in matches if row["disposition"] != "candidate"]
    family_rows = []
    for pattern in PATTERNS:
        for layer in pattern["layers"].split(","):
            selected = [row for row in matches if row["family"] == pattern["family"] and row["layer"] == layer]
            retained = [row for row in selected if row["disposition"] == "candidate"]
            family_rows.append({"family": pattern["family"], "label": pattern["label"], "layer": layer,
                                "raw_matches": len(selected), "candidates": len(retained),
                                "excluded_raw_matches": len(selected) - len(retained),
                                "candidate_pages": len({row["printed_page"] for row in retained})})
    page_counts = Counter((row["printed_page"], row["layer"], row["family"], row["disposition"]) for row in matches)
    page_rows = [
        {"printed_page": page, "layer": layer, "family": family, "disposition": disposition, "count": count}
        for (page, layer, family, disposition), count in sorted(page_counts.items(),
            key=lambda item: (PAGE_RANK[int(item[0][0])], LAYER_RANK[item[0][1]], PATTERN_RANK[item[0][2]], item[0][3]))
    ]
    files.sort(key=lambda row: (PAGE_RANK[int(row["printed_page"])], LAYER_RANK[row["layer"]]))
    notes.sort(key=lambda row: (PAGE_RANK[int(row["printed_page"])], LAYER_RANK[row["layer"]], row["line"], row["column"]))
    inventory_rows = [{"layer": layer, "expected_page_files": len(PAGES),
                       "present_page_files": sum(row["layer"] == layer for row in files),
                       "missing_printed_pages": ",".join(str(page) for page in PAGES
                           if f"sources/{layer}/p{page}.tex" not in snapshot)} for layer in LAYER_RANK]
    tables = {
        "CANDIDATES.tsv": (MATCH_FIELDS, candidates),
        "ENGLISH_CANDIDATES.tsv": (MATCH_FIELDS, [row for row in candidates if row["layer"] == "en"]),
        "FRENCH_CANDIDATES.tsv": (MATCH_FIELDS, [row for row in candidates if row["layer"] in {"dip", "fr"}]),
        "EXCLUDED_RAW_MATCHES.tsv": (MATCH_FIELDS, excluded),
        "ALL_RAW_MATCHES.tsv": (MATCH_FIELDS, matches),
        "FAMILY_COUNTS.tsv": (["family", "label", "layer", "raw_matches", "candidates", "excluded_raw_matches", "candidate_pages"], family_rows),
        "PAGE_COUNTS.tsv": (["printed_page", "layer", "family", "disposition", "count"], page_rows),
        "FILE_SUMMARY.tsv": (["file", "layer", "printed_page", "lines", "raw_matches", "lexical_notes"], files),
        "SOURCE_HASHES.tsv": (["file", "bytes", "sha256"], sources),
        "SOURCE_INVENTORY.tsv": (["layer", "expected_page_files", "present_page_files", "missing_printed_pages"], inventory_rows),
        "PATTERNS.tsv": (["family", "label", "language", "layers", "pattern", "flags", "context_rule"], PATTERNS),
        "LEXICAL_NOTES.tsv": (["file", "layer", "printed_page", "line", "column", "kind", "syntax_name", "detail"], notes),
    }
    summary = {
        "source_files": len(snapshot), "raw_matches": len(matches), "candidates": len(candidates),
        "excluded_raw_matches": len(excluded), "candidate_pages": len({row["printed_page"] for row in candidates}),
        "candidates_by_layer": dict(sorted(Counter(row["layer"] for row in candidates).items())),
        "source_line_fields_privacy_filtered": sum(row["source_line_privacy_filtered"] == "yes" for row in matches),
        "lexical_notes": len(notes),
    }
    return tables, summary


def recheck(root: Path, snapshot: dict[str, bytes]) -> None:
    paths = source_paths(root)
    if set(paths) != set(snapshot):
        raise RuntimeError("The eligible page-file set changed; no report was installed.")
    if any(file_hash(path) != (len(snapshot[name]), sha(snapshot[name])) for name, path in paths.items()):
        raise RuntimeError("A page source changed after the snapshot; no report was installed.")


def run(args) -> dict:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside a protected context folder.")
    if args.output.is_absolute() or "interim" not in args.output.name.casefold():
        raise ValueError("Use a new relative report-directory name explicitly containing interim.")
    require_safe_name(args.output.as_posix())
    if any(part.casefold() in BLOCKED_DIRS for part in args.output.parts):
        raise ValueError("The report cannot be placed inside a protected context folder.")
    cursor = root
    for part in args.output.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("The report path must not pass through a symbolic link.")
    output = (root / args.output).resolve()
    if output == root or root not in output.parents or any(
        output == root / name or root / name in output.parents for name in ("sources", "pdf")
    ):
        raise ValueError("The report must be inside the delivery tree and outside source/PDF trees.")
    if output.exists():
        raise ValueError("The interim report already exists; snapshots are never overwritten.")
    paths = source_paths(root)
    if not paths:
        raise ValueError("No eligible current page sources were found.")
    snapshot = {name: read_snapshot(path) for name, path in paths.items()}
    tables, summary = inventory_bytes(snapshot)
    source_rows = tables["SOURCE_HASHES.tsv"][1]
    source_set_hash = sha(json.dumps(source_rows, sort_keys=True, separators=(",", ":")).encode())
    pattern_payload = tsv_bytes(*tables["PATTERNS.tsv"])
    tables["INPUT_HASHES.tsv"] = (["role", "file", "sha256"], [
        {"role": "page-source inventory", "file": "SOURCE_HASHES.tsv logical rows", "sha256": source_set_hash},
        {"role": "exact matching rules", "file": "PATTERNS.tsv", "sha256": sha(pattern_payload)},
    ])
    report = ["# Interim recurrence candidates", "", "Generated " + utc() + ".", "",
              "This read-only inventory makes no diagnosis or correctness decision. All candidates remain pending manual review by the primary reviewer. It does not inspect scans, build PDFs or change any source, ledger or review state.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items() if key != "candidates_by_layer")
    report.extend(["", "## Counts by family and layer", "",
                   "| Family | Layer | Candidates | Excluded raw matches | Candidate pages |", "| --- | --- | ---: | ---: | ---: |"])
    report.extend(f"| {row['label']} | {row['layer']} | {row['candidates']} | {row['excluded_raw_matches']} | {row['candidate_pages']} |"
                  for row in tables["FAMILY_COUNTS.tsv"][1])
    report.extend(["", "## Scope and interpretation", "",
                   "PATTERNS.tsv records every exact regular expression, case rule, layer selection and context rule. English patterns allow singular/plural forms, case variation and documented whitespace, nonbreaking-space tilde or hyphen separators. The French patterns are bounded, case-sensitive literal coefficients, du homomorphisme and de homomorphisme; their internal spaces are literal single spaces.", "",
                   "CANDIDATES.tsv is sorted by printed page, then diplomatic/corrected/English layer, source line and column. ENGLISH_CANDIDATES.tsv and FRENCH_CANDIDATES.tsv provide separate views. Exact matched tokens and their complete surrounding source line are included; a match crossing a line break includes all surrounding source lines from its start to end. Coordinates are one-based decoded-character positions, with end coordinates inclusive.", "",
                   "Raw matches whose endpoint tokens are skipped as comments, literals or TeX syntax are retained in EXCLUDED_RAW_MATCHES.tsv. The English scheme(s) family also excludes recognized math context. Text mode alone is not proof of prose: custom macro arguments, names and deferred definitions can require manual assessment. Unknown or mixed contexts remain candidates. ALL_RAW_MATCHES.tsv preserves every pattern match, including exclusions, without a correctness verdict.", "",
                   "Source-line fields are exact apart from removing the final line ending and privacy-pattern filtering when needed. A filtered field is explicitly marked, and source_line_sha256 binds the original decoded line span. Source bytes themselves remain unchanged. No private local path or email match is deliberately copied into a returned report.", "",
                   "No macro expansion or formatting normalization is performed. Patterns can miss phrases interrupted by TeX commands, discretionary hyphens or other spellings. Each file begins in assumed text mode; custom environments, catcodes and cross-input math state are not executed. The lexical notes and all raw matches are available for manual context. This report cannot establish terminology consistency or absence of errors.", "",
                   "Only leaf page files in sources/dip, sources/fr and sources/en are opened. Protected context folders, symbolic links, main files, preambles, source ZIPs and scans are not read. The eligible file set and all source hashes were rechecked before exclusive installation of this new interim directory.", ""])
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads["REPORT.md"] = "\n".join(report).encode("utf-8")
    payloads["SUMMARY.json"] = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Generated reports have a privacy pattern or inspection blocker; no report was installed.")
    with tempfile.TemporaryDirectory(prefix="recurrence-inventory-", dir=root.parent) as temporary:
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
    print(json.dumps({**summary, "report_directory": output.relative_to(root).as_posix()}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True, help="Fresh relative directory explicitly named interim")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
