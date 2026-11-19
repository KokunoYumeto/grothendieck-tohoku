"""Inventory plain C/O/U/V/Z tokens in recognized lexical math, dip pages only.

This is a pending lexical inventory, never a reading or correctness judgment.
It reads no scan, ledger, review history, main file, preamble or context folder.
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
    BLOCKED_DIRS, VERBATIM_ENVS, coordinates, file_hash, lex_control_words,
    read_snapshot, require_safe_name, sha, skip_space_comments, tsv_bytes, utc,
)
from math_font_context import (
    INHERITING_ENVS, INNER_MATH_ENVS, OUTER_MATH_ENVS, TEXT_BODY_ENVS,
    balanced_end, scan_font_context, token,
)
from privacy_guard import safe_location, scan_bytes

PAGES = list(range(119, 184)) + list(range(185, 222))
PAGE_RANK = {page: index for index, page in enumerate(PAGES)}
CAPITALS = "COUVZ"
FONT_WRAPPERS = frozenset({
    "mathrm", "mathbf", "mathit", "mathsf", "mathtt", "mathnormal",
    "mathcal", "mathscr", "mathfrak", "mathbb", "mathbbm", "mathds",
    "mathbbold", "boldsymbol", "bm", "pmb", "mathbfit", "mathbfsf",
    "mathbfsfit", "mathsfbf", "mathsfit", "operatorname", "operatornamewithlimits",
})
FONT_DECLARATIONS = frozenset({
    "rm", "bf", "it", "sf", "tt", "cal", "mit", "rmfamily", "sffamily",
    "ttfamily", "bfseries", "mdseries", "itshape", "upshape", "normalfont",
    "boldmath", "unboldmath", "mathversion", "font", "usefont", "selectfont",
})
REFERENCE_ARGUMENTS = frozenset({
    "label", "LayerTarget", "ref", "eqref", "pageref", "autoref", "nameref",
    "cref", "Cref", "vref", "Vref", "cite", "citep", "citet", "citealp",
    "citeauthor", "citeyear", "index", "glossary", "bibitem", "url", "path",
    "input", "include", "includegraphics",
})
KNOWN_ENVS = INHERITING_ENVS | INNER_MATH_ENVS | OUTER_MATH_ENVS | TEXT_BODY_ENVS | VERBATIM_ENVS
DISPOSITIONS = ("candidate", "wrapped", "reference_argument", "text", "skipped", "uncertain")
MATCH_FIELDS = [
    "match_id", "file", "printed_page", "line", "column", "capital", "disposition",
    "reason", "lexical_mode", "context_category", "context_name", "context_caveat",
    "source_context", "source_line_sha256", "context_privacy_filtered",
    "context_truncated", "source_context_limit", "review_status",
]


def contains(intervals: list[tuple[int, int, str]], offset: int) -> str:
    return next((reason for first, last, reason in intervals if first <= offset < last), "")


def argument(text: str, after: int) -> tuple[int, int] | None:
    first = skip_space_comments(text, after)
    if first >= len(text):
        return None
    if text[first] == "{":
        last = balanced_end(text, first)
        return (first, last) if last is not None else None
    if text[first] in "}$":
        return None
    _, _, last = token(text, first)
    return first, last


def exclusion_masks(text: str, scan: dict, lexical: dict) -> tuple[dict, list[dict]]:
    """Supplement existing context probes with literal font/reference masks.

    Only explicit argument spans are interpreted. Unsupported parser states
    are retained as uncertain, never promoted to recognized-math candidates.
    """
    masks = {"wrapped": [], "reference_argument": [], "uncertain": [], "literal": []}
    notes, environments = [], []
    starts = [0] + [item.end() for item in re.finditer("\n", text)]
    reference_commands = {
        (item["line"], item["column"])
        for item in scan["occurrences"] if item["token_role"] != "invocation token"
    }

    def note(at: int, name: str, detail: str) -> None:
        line, column = coordinates(at, starts)
        notes.append({"line": line, "column": column, "kind": "capital exclusion uncertainty",
                      "syntax_name": name, "detail": detail})

    for item in lexical["occurrences"]:
        at, end, name = item["offset"], item["end"], item["command"]
        if contains(masks["literal"], at) or (item["line"], item["column"]) in reference_commands:
            continue
        if name in {"string", "meaning"}:
            first = skip_space_comments(text, end)
            if first < len(text):
                _, _, last = token(text, first)
                masks["literal"].append((first, last, "literal token reference"))
            continue
        if name in {"detokenize", "unexpanded"}:
            body = argument(text, end)
            if body and text[body[0]] == "{":
                masks["literal"].append((*body, "literal argument"))
            continue
        if name in {"let", "futurelet"}:
            first = skip_space_comments(text, end)
            if first < len(text):
                _, _, last = token(text, first)
                masks["literal"].append((first, last, "assignment target"))
                if name == "let":
                    first = skip_space_comments(text, last)
                    if text[first:first + 1] == "=":
                        first = skip_space_comments(text, first + 1)
                    if first < len(text):
                        _, _, last = token(text, first)
                        masks["literal"].append((first, last, "literal alias source"))
            continue
        if name in {"begin", "end"}:
            first = skip_space_comments(text, end)
            match = re.match(r"\{([A-Za-z][A-Za-z0-9*_-]*)\}", text[first:])
            if match:
                environment = match.group(1)
                after = first + match.end()
                if name == "begin":
                    environments.append((environment, at, environment not in KNOWN_ENVS))
                else:
                    index = next((i for i in range(len(environments) - 1, -1, -1)
                                  if environments[i][0] == environment), None)
                    if index is not None:
                        for old_name, begin, unknown in environments[index:]:
                            if unknown:
                                masks["uncertain"].append((begin, after, "unrecognized environment " + old_name))
                        del environments[index:]
            continue
        if name in FONT_WRAPPERS:
            first = skip_space_comments(text, end)
            if name == "operatorname" and text[first:first + 1] == "*":
                first += 1
            body = argument(text, first)
            if body:
                masks["wrapped"].append((*body, "explicit font/operator argument of " + name))
            else:
                masks["uncertain"].append((at, len(text), "unrecognized font argument of " + name))
                note(at, name, "No balanced group or single argument token was recognized; later capitals remain uncertain.")
        elif name in REFERENCE_ARGUMENTS:
            first = skip_space_comments(text, end)
            if text[first:first + 1] == "*":
                first = skip_space_comments(text, first + 1)
            while text[first:first + 1] == "[":
                last = balanced_end(text, first)
                if last is None:
                    masks["uncertain"].append((at, len(text), "unbalanced reference optional argument"))
                    note(at, name, "The optional reference argument is unbalanced; later capitals remain uncertain.")
                    break
                masks["reference_argument"].append((first, last, "reference optional argument of " + name))
                first = skip_space_comments(text, last)
            body = argument(text, first)
            if body:
                masks["reference_argument"].append((*body, "reference/label argument of " + name))
            else:
                masks["uncertain"].append((at, len(text), "unrecognized reference argument of " + name))
                note(at, name, "No explicit reference argument was recognized; later capitals remain uncertain.")
        elif name in FONT_DECLARATIONS:
            masks["uncertain"].append((at, len(text), "font declaration scope is not executed: " + name))
            note(at, name, "Declaration-style font state is not executed; subsequent otherwise-math capitals remain uncertain.")
    for name, first, unknown in environments:
        if unknown:
            masks["uncertain"].append((first, len(text), "unclosed unrecognized environment " + name))
    # These notes signal boundaries or execution that the probe parser does not
    # settle. A whole-file demotion deliberately favors no false math certainty.
    safe_note_kinds = {"single-token argument", "unrecognized environment mode"}
    unsafe = [item for item in scan["notes"] if item["kind"] not in safe_note_kinds]
    if unsafe:
        masks["uncertain"].append((0, len(text), "file has unresolved lexical boundary/execution notes"))
    return masks, notes


def short_context(text: str, offset: int, starts: list[int], width: int) -> dict:
    line, column = coordinates(offset, starts)
    first = starts[line - 1]
    last = text.find("\n", first)
    original = text[first:len(text) if last < 0 else last].removesuffix("\r")
    safe = safe_location(original)
    # Filter the whole line before cropping, so a cropped private token cannot
    # escape recognition merely because its beginning or end was truncated.
    center = min(column - 1, max(0, len(safe) - 1))
    start = max(0, min(center - width // 2, max(0, len(safe) - width)))
    finish = min(len(safe), start + width)
    return {"source_context": ("…" if start else "") + safe[start:finish] + ("…" if finish < len(safe) else ""),
            "source_line_sha256": sha(original.encode("utf-8")),
            "context_privacy_filtered": "yes" if safe != original else "no",
            "context_truncated": "yes" if start or finish < len(safe) else "no",
            "source_context_limit": width}


def scan_page(data: bytes, context_chars: int = 120) -> tuple[list[dict], list[dict]]:
    if not 40 <= context_chars <= 240:
        raise ValueError("Context width must be between 40 and 240 decoded characters.")
    text = data.decode("utf-8-sig")
    offsets = {match.start() for match in re.finditer("[" + CAPITALS + "]", text)}
    scan = scan_font_context(data, offsets)
    probes = {item["offset"]: item for item in scan["probes"]}
    masks, extra_notes = exclusion_masks(text, scan, lex_control_words(data))
    starts = [0] + [item.end() for item in re.finditer("\n", text)]
    rows = []
    for at in sorted(offsets):
        probe = probes[at]
        line, column = coordinates(at, starts)
        mode = probe.get("observed_mode", "")
        category = probe["context_category"]
        if not probe["visited"] or contains(masks["literal"], at):
            disposition, reason = "skipped", "comment, control-word name, literal reference, or other skipped syntax"
        elif contains(masks["reference_argument"], at):
            disposition, reason = "reference_argument", contains(masks["reference_argument"], at)
        elif mode == "text":
            disposition, reason = "text", "recognized text or file-entry text assumption"
        elif mode != "math" or category != "recognized math":
            disposition, reason = "uncertain", "probe does not establish a recognized nondeferred math context"
        elif contains(masks["uncertain"], at):
            disposition, reason = "uncertain", contains(masks["uncertain"], at)
        elif contains(masks["wrapped"], at):
            disposition, reason = "wrapped", contains(masks["wrapped"], at)
        else:
            disposition, reason = "candidate", "plain literal capital in recognized lexical math"
        rows.append({"line": line, "column": column, "capital": text[at],
                     "disposition": disposition, "reason": reason,
                     "lexical_mode": "unknown" if disposition == "uncertain" else mode,
                     "context_category": "uncertain context" if disposition == "uncertain" else category,
                     "context_name": probe.get("context_name", ""),
                     "context_caveat": probe.get("context_caveat", ""),
                     **short_context(text, at, starts, context_chars),
                     "review_status": "pending manual review; no correctness decision"})
    return rows, scan["notes"] + extra_notes


def inventory_bytes(snapshot: dict[str, bytes], context_chars: int = 120) -> tuple[dict, dict]:
    matches, notes, hashes = [], [], []
    for name, data in sorted(snapshot.items()):
        match = re.fullmatch(r"sources/dip/p([0-9]{3})\.tex", name)
        if match is None or int(match.group(1)) not in PAGE_RANK:
            raise ValueError("Only the 102 named diplomatic page files are eligible snapshot inputs.")
        page = int(match.group(1))
        rows, page_notes = scan_page(data, context_chars)
        matches.extend({"file": name, "printed_page": page, **row} for row in rows)
        notes.extend({"file": name, "printed_page": page, **row} for row in page_notes)
        hashes.append({"file": name, "bytes": len(data), "sha256": sha(data)})
    matches.sort(key=lambda row: (PAGE_RANK[row["printed_page"]], row["line"], row["column"]))
    for index, row in enumerate(matches, 1):
        row["match_id"] = f"PC{index:06d}"
    counts = Counter((row["printed_page"], row["capital"], row["disposition"]) for row in matches)
    coverage, matrix = [], []
    for page in PAGES:
        present = f"sources/dip/p{page}.tex" in snapshot
        totals = {key: sum(counts[page, capital, key] for capital in CAPITALS) for key in DISPOSITIONS}
        coverage.append({"printed_page": page, "file": f"sources/dip/p{page}.tex",
                         "source_present": "yes" if present else "no", "raw_capitals": sum(totals.values()) if present else "",
                         **{key: value if present else "" for key, value in totals.items()},
                         "candidate_presence": ("nonzero" if totals["candidate"] else "zero") if present else "not inventoried"})
        for capital in CAPITALS:
            matrix.append({"printed_page": page, "capital": capital, "source_present": "yes" if present else "no",
                           **{key: counts[page, capital, key] if present else "" for key in DISPOSITIONS}})
    candidates = [row for row in matches if row["disposition"] == "candidate"]
    uncertain = [row for row in matches if row["disposition"] == "uncertain"]
    excluded = [row for row in matches if row["disposition"] not in {"candidate", "uncertain"}]
    tables = {
        "CANDIDATES.tsv": (MATCH_FIELDS, candidates),
        "UNCERTAIN_MATCHES.tsv": (MATCH_FIELDS, uncertain),
        "EXCLUDED_RAW_MATCHES.tsv": (MATCH_FIELDS, excluded),
        "ALL_RAW_MATCHES.tsv": (MATCH_FIELDS, matches),
        "PAGE_COVERAGE.tsv": (["printed_page", "file", "source_present", "raw_capitals", *DISPOSITIONS, "candidate_presence"], coverage),
        "PAGE_CAPITAL_COUNTS.tsv": (["printed_page", "capital", "source_present", *DISPOSITIONS], matrix),
        "SOURCE_HASHES.tsv": (["file", "bytes", "sha256"], hashes),
        "LEXICAL_NOTES.tsv": (["file", "printed_page", "line", "column", "kind", "syntax_name", "detail"], notes),
    }
    summary = {"expected_page_files": len(PAGES), "source_files": len(snapshot), "raw_capitals": len(matches),
               "candidates": len(candidates), "uncertain_matches": len(uncertain), "excluded_raw_matches": len(excluded),
               "candidate_pages": len({row["printed_page"] for row in candidates}),
               "zero_candidate_present_pages": sum(row["candidate_presence"] == "zero" for row in coverage),
               "missing_pages": len(PAGES) - len(snapshot), "lexical_notes": len(notes),
               "privacy_filtered_contexts": sum(row["context_privacy_filtered"] == "yes" for row in matches)}
    return tables, summary


def source_paths(root: Path) -> dict[str, Path]:
    sources, directory = root / "sources", root / "sources/dip"
    if any(path.is_symlink() or not path.is_dir() for path in (sources, directory)):
        raise ValueError("Regular source and diplomatic-page directories are required.")
    expected = {f"p{page}.tex" for page in PAGES}
    actual = {path.name: path for path in directory.iterdir() if path.suffix == ".tex"}
    if set(actual) != expected or any(path.is_symlink() or not path.is_file() for path in actual.values()):
        raise ValueError("The diplomatic layer must contain exactly the 102 expected regular page TeX files.")
    return {f"sources/dip/p{page}.tex": actual[f"p{page}.tex"] for page in PAGES}


def recheck(root: Path, snapshot: dict[str, bytes]) -> None:
    paths = source_paths(root)
    if set(paths) != set(snapshot) or any(file_hash(path) != (len(snapshot[name]), sha(snapshot[name])) for name, path in paths.items()):
        raise RuntimeError("The diplomatic source snapshot changed; no report was installed.")


def checked_output(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or "interim" not in relative.name.casefold():
        raise ValueError("Use a fresh relative report-directory name containing interim.")
    require_safe_name(relative.as_posix())
    if any(part.casefold() in BLOCKED_DIRS | {"sources", "pdf", "second-reading"} for part in relative.parts):
        raise ValueError("The report must be outside source, PDF, review-state and protected context directories.")
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("The report path must not pass through a symbolic link.")
    output = cursor.resolve()
    if root not in output.parents or output.exists():
        raise ValueError("The report directory must be new and inside the delivery tree.")
    return output


def run(args) -> dict:
    raw_root = args.root.absolute()
    if any(part.casefold() in BLOCKED_DIRS for part in raw_root.parts):
        raise ValueError("The delivery root cannot pass through a protected context folder.")
    if any(path.is_symlink() for path in [raw_root, *raw_root.parents]):
        raise ValueError("The delivery root must not pass through a symbolic link.")
    root = raw_root.resolve()
    if not root.is_dir():
        raise ValueError("A regular delivery root is required.")
    output = checked_output(root, args.output)
    snapshot = {name: read_snapshot(path) for name, path in source_paths(root).items()}
    tables, summary = inventory_bytes(snapshot, args.context_chars)
    rules = {"capitals": CAPITALS, "layer": "dip", "printed_pages": PAGES,
             "font_wrappers": sorted(FONT_WRAPPERS), "font_declarations_uncertain": sorted(FONT_DECLARATIONS),
             "reference_argument_commands": sorted(REFERENCE_ARGUMENTS), "source_context_limit": args.context_chars,
             "context_requirement": "visited probe, math mode, recognized math category, no supplemental uncertainty or wrapper/reference mask",
             "uncertainty_policy": "Unknown environments are masked locally; unresolved parser boundary/execution notes demote otherwise-math tokens throughout the file. Font declarations demote following otherwise-math tokens."}
    rules_payload = (json.dumps(rules, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    source_payload = tsv_bytes(*tables["SOURCE_HASHES.tsv"])
    tables["INPUT_HASHES.tsv"] = (["role", "file", "sha256"], [
        {"role": "diplomatic source snapshot", "file": "SOURCE_HASHES.tsv", "sha256": sha(source_payload)},
        {"role": "literal inventory rules", "file": "RULES.json", "sha256": sha(rules_payload)},
    ])
    report = ["# Pending plain math-capital inventory", "", "Generated " + utc() + ".", "",
              "All findings are pending lexical candidates. No correctness, font choice, scan reading or source correction is inferred.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value} |" for key, value in summary.items())
    report.extend(["", "## Interpretation", "",
        "CANDIDATES.tsv contains plain literal C/O/U/V/Z character tokens only where the existing context probe reports recognized math and the supplemental masks find no known font wrapper, label/reference argument or unresolved context. It is ordered by printed page, source line and decoded-character column. Adjacent letters are separate math-character candidates; no word or notation meaning is inferred.", "",
        "UNCERTAIN_MATCHES.tsv retains otherwise relevant raw letters in unresolved or deferred contexts. EXCLUDED_RAW_MATCHES.tsv retains known wrapped, reference-argument, text and skipped-syntax matches. ALL_RAW_MATCHES.tsv accounts for every literal target letter, including letters inside control-word names or comments. Every raw letter has exactly one disposition. A zero candidate count is not a claim that the page has no such notation or no errors.", "",
        "PAGE_COVERAGE.tsv has all 102 printed pages, and PAGE_CAPITAL_COUNTS.tsv has all 102 by 5 capital combinations, including explicit zero counts. Missing inputs are refused by the command. SOURCE_HASHES.tsv and INPUT_HASHES.tsv bind the current bytes and rules. Snapshot match IDs are locators, not stable review or correction IDs.", "",
        "Source contexts are short same-line excerpts, cropped after filtering the entire line for recognized private paths/emails. Any filtering is marked; source_line_sha256 identifies the original decoded line without its CR/LF ending. Coordinates refer to original text. A filtered or truncated context may not display the target token. Excerpts are derived report fields; source bytes are never changed. Every generated payload was privacy-scanned before installation.", "",
        "This is static lexical TeX, not macro expansion. Each file starts in assumed text mode. Known direct font commands use balanced groups or a single TeX argument token, including intervening comments. Nested wrapper content is conservatively excluded. Declaration-style fonts, unsupported boundaries/execution, unknown environments, custom macros/fonts, catcode changes and cross-file state limit coverage; uncertainty is reported instead of being called recognized math. No preamble or custom definition is loaded.", "",
        "Only the 102 regular leaf files in sources/dip are opened. No source ZIP, scan, main, preamble, ledger, review history or context folder is read. The source set/hashes are rechecked immediately before exclusive installation in a fresh interim directory. Existing reports and all inputs remain unchanged. See scripts/PLAIN_MATH_CAPITALS.md for usage and limits.", ""])
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads.update({"RULES.json": rules_payload, "SUMMARY.json": (json.dumps(summary, sort_keys=True, indent=2) + "\n").encode(),
                     "REPORT.md": "\n".join(report).encode()})
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Generated reports contain a privacy finding or inspection blocker; no report was installed.")
    with tempfile.TemporaryDirectory(prefix="plain-capitals-", dir=root.parent) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        recheck(root, snapshot)
        output = checked_output(root, args.output)
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
    parser.add_argument("--output", type=Path, required=True, help="Fresh relative interim report directory")
    parser.add_argument("--context-chars", type=int, default=120, help="Same-line context width, 40 to 240; default 120")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
