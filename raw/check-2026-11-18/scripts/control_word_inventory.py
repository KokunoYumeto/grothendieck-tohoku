"""Inventory static TeX control-word candidates against an original source ZIP.

This is a lexical comparison, never a TeX validity check or a page reading.
Reports contain command names, counts and source coordinates, not excerpts.
No source is changed and no build, macro expansion or external input occurs.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from privacy_guard import privacy_findings, safe_location, scan_bytes

BLOCKED_DIRS = frozenset({"programme", "notes", "stacks"})
VERBATIM_ENVS = frozenset({"verbatim", "verbatim*", "Verbatim", "Verbatim*", "BVerbatim", "LVerbatim", "SaveVerbatim", "lstlisting", "minted", "comment"})
DECLARATIONS = frozenset({"newcommand", "renewcommand", "providecommand", "DeclareRobustCommand", "NewDocumentCommand", "RenewDocumentCommand", "ProvideDocumentCommand", "DeclareDocumentCommand", "DeclareMathOperator", "def", "gdef", "edef", "xdef", "let", "futurelet"})
SYNTAX_SIGNALS = frozenset({"catcode", "makeatletter", "makeatother", "ExplSyntaxOn", "ExplSyntaxOff", "csname", "endcsname"})


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def letter(character: str) -> bool:
    return "A" <= character <= "Z" or "a" <= character <= "z"


def coordinates(offset: int, starts: list[int]) -> tuple[int, int]:
    line = bisect_right(starts, offset)
    return line, offset - starts[line - 1] + 1


def skip_space_comments(text: str, offset: int) -> int:
    while offset < len(text):
        if text[offset].isspace():
            offset += 1
        elif text[offset] == "%":
            end = text.find("\n", offset)
            offset = len(text) if end < 0 else end
        else:
            break
    return offset


def lex_control_words(data: bytes, include_declarations: bool = False,
                      include_comment_ranges: bool = False) -> dict:
    """Read UTF-8 with ASCII letter catcodes; skip only documented literals."""
    text = data.decode("utf-8-sig")
    starts = [0] + [match.end() for match in re.finditer("\n", text)]
    occurrences, skipped, notes, comments = [], [], [], []
    offset = 0
    while offset < len(text):
        character = text[offset]
        if character == "%":
            end = text.find("\n", offset)
            end = len(text) if end < 0 else end
            skipped.append((offset, end))
            if include_comment_ranges:
                comments.append((offset, end))
            offset = end
            continue
        if character != "\\":
            offset += 1
            continue
        if offset + 1 >= len(text):
            offset += 1
            continue
        if not letter(text[offset + 1]):
            # A control symbol consumes its next character, including a second
            # backslash or a percent sign. A later third backslash starts anew.
            offset += 2
            continue
        end = offset + 2
        while end < len(text) and letter(text[end]):
            end += 1
        name = text[offset + 1:end]
        line, column = coordinates(offset, starts)
        occurrences.append({"command": name, "line": line, "column": column, "offset": offset, "end": end})
        if name in SYNTAX_SIGNALS:
            notes.append({"line": line, "kind": "syntax signal", "command": name,
                          "detail": "This lexical scan does not interpret catcode changes or constructed command names."})
        if name == "verb":
            delimiter_at = end + (1 if end < len(text) and text[end] == "*" else 0)
            if delimiter_at >= len(text) or text[delimiter_at] in "\r\n":
                notes.append({"line": line, "kind": "inline literal boundary", "command": name,
                              "detail": "No same-line delimiter was available; no literal body was skipped."})
                offset = end
                continue
            delimiter = text[delimiter_at]
            line_end = text.find("\n", delimiter_at)
            line_end = len(text) if line_end < 0 else line_end
            close = text.find(delimiter, delimiter_at + 1, line_end)
            literal_end = line_end if close < 0 else close + 1
            skipped.append((end, literal_end))
            if close < 0:
                notes.append({"line": line, "kind": "inline literal boundary", "command": name,
                              "detail": "No closing delimiter was found before line end; the remainder of that line was treated as literal."})
            offset = literal_end
            continue
        if name == "begin":
            argument = skip_space_comments(text, end)
            match = re.match(r"\{([A-Za-z][A-Za-z0-9*_-]*)\}", text[argument:])
            if match and match.group(1) in VERBATIM_ENVS:
                environment = match.group(1)
                body_start = argument + match.end()
                marker = "\\end{" + environment + "}"
                close = text.find(marker, body_start)
                literal_end = len(text) if close < 0 else close
                skipped.append((end, literal_end))
                if close < 0:
                    notes.append({"line": line, "kind": "environment literal boundary", "command": name,
                                  "detail": "No matching literal end marker was found; the remainder of the file was treated as literal."})
                offset = literal_end
                continue
        offset = end

    declarations = []
    if include_declarations:
        masked = list(text)
        for first, last in skipped:
            for position in range(first, last):
                if masked[position] not in "\r\n":
                    masked[position] = " "
        visible = "".join(masked)
        for occurrence in occurrences:
            if occurrence["command"] not in DECLARATIONS:
                continue
            position = occurrence["end"]
            while position < len(visible) and visible[position].isspace():
                position += 1
            if position < len(visible) and visible[position] == "*":
                position += 1
                while position < len(visible) and visible[position].isspace():
                    position += 1
            braced = position < len(visible) and visible[position] == "{"
            if braced:
                position += 1
                while position < len(visible) and visible[position].isspace():
                    position += 1
            match = re.match(r"\\([A-Za-z]+)", visible[position:])
            if not match or match.group(1) in {"csname", "endcsname"}:
                continue
            after = position + match.end()
            if braced:
                while after < len(visible) and visible[after].isspace():
                    after += 1
                if after >= len(visible) or visible[after] != "}":
                    continue
            line, column = coordinates(position, starts)
            declarations.append({"command": match.group(1), "declaration_form": occurrence["command"],
                                 "declaration_line": occurrence["line"], "name_line": line, "name_column": column})
    result = {"occurrences": occurrences, "counts": Counter(item["command"] for item in occurrences),
              "declarations": declarations, "notes": notes,
              "lines": data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))}
    if include_comment_ranges:
        result["comment_ranges"] = comments
    return result


def blocked(name: str) -> bool:
    return any(part.casefold() in BLOCKED_DIRS for part in PurePosixPath(name).parts[:-1])


def require_safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or re.match(r"^[A-Za-z]:", name)
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or path.as_posix() != name or privacy_findings(name)):
        raise ValueError("A source filename is unsafe or contains a possible private locator; no report was installed.")
    return name


def current_files(sources: Path) -> dict[str, Path]:
    if not sources.is_dir() or sources.is_symlink():
        raise ValueError("A regular sources directory is required.")
    result = {}
    for directory, directories, filenames in os.walk(sources, followlinks=False):
        base = Path(directory)
        directories[:] = sorted(name for name in directories if name.casefold() not in BLOCKED_DIRS and not (base / name).is_symlink())
        for filename in sorted(filenames):
            path = base / filename
            if path.suffix.lower() != ".tex" or path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(sources).as_posix()
            require_safe_name(relative)
            result[relative] = path
    return dict(sorted(result.items()))


def read_snapshot(path: Path) -> bytes:
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("An input changed while being read; no report was installed.")
    return data


def file_hash(path: Path) -> tuple[int, str]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("An input changed while being hashed; no report was installed.")
    return after.st_size, digest.hexdigest()


def original_files(path: Path) -> dict[str, bytes]:
    result = {}
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            name = entry.filename
            is_symlink = ((entry.external_attr >> 16) & 0o170000) == 0o120000
            if entry.is_dir() or is_symlink or PurePosixPath(name).suffix.lower() != ".tex" or blocked(name):
                continue
            require_safe_name(name)
            if name in result:
                raise ValueError("The original source ZIP contains a duplicate TeX member name.")
            result[name] = archive.read(entry)
    return dict(sorted(result.items()))


def tsv_bytes(fields: list[str], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def compare(current: dict[str, bytes], original: dict[str, bytes], include_declarations: bool) -> tuple[dict, dict]:
    old_lex = {name: lex_control_words(data) for name, data in original.items()}
    new_lex = {name: lex_control_words(data, include_declarations) for name, data in current.items()}
    old_global, new_global = Counter(), Counter()
    for item in old_lex.values():
        old_global.update(item["counts"])
    for item in new_lex.values():
        new_global.update(item["counts"])
    counts, candidates, occurrences, splits, declarations, notes, files, hashes = [], [], [], [], [], [], [], []
    for side, dataset in (("original", original), ("current", current)):
        for name, data in dataset.items():
            hashes.append({"side": side, "file": name if side == "original" else "sources/" + name, "bytes": len(data), "sha256": sha(data)})
    candidate_files = defaultdict(set)
    for name, fresh in new_lex.items():
        previous = old_lex.get(name, {"counts": Counter(), "lines": 0})
        old_counts, new_counts = previous["counts"], fresh["counts"]
        occurrence_map, declaration_map = defaultdict(list), defaultdict(list)
        for item in fresh["occurrences"]:
            occurrence_map[item["command"]].append(item)
        for item in fresh["declarations"]:
            declaration_map[item["command"]].append(item)
            declarations.append({"file": "sources/" + name, **item, "interpretation": "literal declaration form only; candidate remains subject to manual review"})
        notes.extend({"side": "current", "file": "sources/" + name, **item} for item in fresh["notes"])
        local_candidates = 0
        for command in sorted(set(old_counts) | set(new_counts)):
            old_count, new_count = old_counts[command], new_counts[command]
            status = "new to file" if new_count and not old_count else "removed from file" if old_count and not new_count else "increased" if new_count > old_count else "decreased" if new_count < old_count else "unchanged"
            counts.append({"file": "sources/" + name, "original_member": name if name in original else "", "command": command,
                           "original_count": old_count, "current_count": new_count, "delta": new_count - old_count,
                           "status": status, "count_increase_candidate": "yes" if new_count > old_count else "no"})
            if new_count <= old_count:
                continue
            local_candidates += 1
            candidate_id = f"C{len(candidates) + 1:06d}"
            globally_new = not old_global[command]
            prefix_names = sorted((prefix for prefix in old_global if command.startswith(prefix) and len(prefix) < len(command)), key=lambda prefix: (-len(prefix), prefix))
            candidates.append({"candidate_id": candidate_id, "file": "sources/" + name, "original_member": name if name in original else "",
                               "command": command, "original_count": old_count, "current_count": new_count, "delta": new_count - old_count,
                               "new_to_file": "yes" if not old_count else "no", "globally_new": "yes" if globally_new else "no",
                               "current_lines": ",".join(str(line) for line in sorted({item["line"] for item in occurrence_map[command]})),
                               "possible_original_prefix_splits": ";".join(prefix + "+" + command[len(prefix):] for prefix in prefix_names),
                               "explicit_declaration_forms": len(declaration_map[command]) if include_declarations else "",
                               "review_status": "candidate only; no validity or editorial verdict"})
            candidate_files[command].add(name)
            occurrences.extend({"candidate_id": candidate_id, "file": "sources/" + name, "command": command,
                                "line": item["line"], "column": item["column"]} for item in occurrence_map[command])
            splits.extend({"candidate_id": candidate_id, "file": "sources/" + name, "command": command,
                           "known_original_prefix": prefix, "remaining_letters": command[len(prefix):],
                           "prefix_original_global_count": old_global[prefix], "prefix_original_file_count": old_counts[prefix],
                           "interpretation": "possible lexical merge only; not a proposed correction"} for prefix in prefix_names)
        files.append({"file": "sources/" + name, "original_member": name if name in original else "", "status": "matched" if name in original else "current file absent from original ZIP",
                      "original_lines": previous["lines"], "current_lines": fresh["lines"], "original_control_word_occurrences": sum(old_counts.values()),
                      "current_control_word_occurrences": sum(new_counts.values()), "candidate_names": local_candidates})
    for name, item in old_lex.items():
        notes.extend({"side": "original", "file": name, **note} for note in item["notes"])
        if name not in current:
            files.append({"file": "", "original_member": name, "status": "original-only TeX member; contributes to original global vocabulary",
                          "original_lines": item["lines"], "current_lines": 0, "original_control_word_occurrences": sum(item["counts"].values()),
                          "current_control_word_occurrences": 0, "candidate_names": 0})
    global_rows = [{"command": command, "original_count": old_global[command], "current_count": new_global[command],
                    "delta": new_global[command] - old_global[command], "globally_new": "yes" if new_global[command] and not old_global[command] else "no",
                    "current_candidate_files": len(candidate_files[command])} for command in sorted(set(old_global) | set(new_global))]
    tables = {
        "CONTROL_WORD_COUNTS.tsv": (["file", "original_member", "command", "original_count", "current_count", "delta", "status", "count_increase_candidate"], counts),
        "CANDIDATES.tsv": (["candidate_id", "file", "original_member", "command", "original_count", "current_count", "delta", "new_to_file", "globally_new", "current_lines", "possible_original_prefix_splits", "explicit_declaration_forms", "review_status"], candidates),
        "CANDIDATE_OCCURRENCES.tsv": (["candidate_id", "file", "command", "line", "column"], occurrences),
        "POSSIBLE_PREFIX_SPLITS.tsv": (["candidate_id", "file", "command", "known_original_prefix", "remaining_letters", "prefix_original_global_count", "prefix_original_file_count", "interpretation"], splits),
        "GLOBAL_COMMANDS.tsv": (["command", "original_count", "current_count", "delta", "globally_new", "current_candidate_files"], global_rows),
        "GLOBALLY_NEW_COMMANDS.tsv": (["command", "original_count", "current_count", "delta", "globally_new", "current_candidate_files"], [row for row in global_rows if row["globally_new"] == "yes"]),
        "FILE_SUMMARY.tsv": (["file", "original_member", "status", "original_lines", "current_lines", "original_control_word_occurrences", "current_control_word_occurrences", "candidate_names"], files),
        "SOURCE_HASHES.tsv": (["side", "file", "bytes", "sha256"], hashes),
        "LEXICAL_NOTES.tsv": (["side", "file", "line", "kind", "command", "detail"], notes),
    }
    if include_declarations:
        tables["CURRENT_DECLARATIONS.tsv"] = (["file", "command", "declaration_form", "declaration_line", "name_line", "name_column", "interpretation"], declarations)
    summary = {"current_tex_files": len(current), "original_tex_members": len(original), "same_path_matches": len(set(current) & set(original)),
               "globally_new_command_names": sum(row["globally_new"] == "yes" for row in global_rows), "file_command_candidates": len(candidates),
               "current_candidate_occurrences": len(occurrences), "possible_prefix_splits": len(splits),
               "explicit_declaration_forms_collected": len(declarations) if include_declarations else None, "lexical_notes": len(notes)}
    return tables, summary


def recheck_snapshot(sources: Path, current: dict[str, bytes], archive_path: Path, archive_hash: tuple[int, str]) -> None:
    again = current_files(sources)
    if set(again) != set(current):
        raise RuntimeError("The current TeX file set changed; no report was installed.")
    if any(file_hash(path) != (len(current[name]), sha(current[name])) for name, path in again.items()):
        raise RuntimeError("A current TeX source changed; no report was installed.")
    if file_hash(archive_path) != archive_hash:
        raise RuntimeError("The original source ZIP changed; no report was installed.")


def run(args) -> dict:
    root = args.root.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise ValueError("The delivery root cannot be inside a protected context folder.")
    if args.output.is_absolute() or any(part.casefold() in BLOCKED_DIRS for part in args.output.parts):
        raise ValueError("Use a new relative report-directory name outside protected context folders.")
    require_safe_name(args.output.as_posix())
    cursor = root
    for part in args.output.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("The report path must not pass through a symbolic link.")
    output = (root / args.output).resolve()
    protected = [root / "sources", root / "pdf"]
    if output == root or root not in output.parents or any(output == folder or folder in output.parents for folder in protected):
        raise ValueError("The new report directory must be inside the delivery tree and outside sources and PDFs.")
    if output.exists():
        raise ValueError("The report directory already exists; no report is overwritten.")
    sources = root / "sources"
    current_paths = current_files(sources)
    if not current_paths:
        raise ValueError("No eligible current TeX source files were found.")
    archive_path = args.original_sources.resolve()
    if any(part.casefold() in BLOCKED_DIRS for part in archive_path.parts[:-1]):
        raise ValueError("The original source ZIP cannot be opened from a protected context folder.")
    archive_hash = file_hash(archive_path)
    original = original_files(archive_path)
    if not original:
        raise ValueError("No eligible original TeX source members were found.")
    current = {name: read_snapshot(path) for name, path in current_paths.items()}
    tables, summary = compare(current, original, args.include_declarations)
    source_rows = tables["SOURCE_HASHES.tsv"][1]
    source_set_hash = sha(json.dumps(source_rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    input_rows = [{"role": "original source ZIP", "file": safe_location(archive_path.name), "bytes": archive_hash[0], "sha256": archive_hash[1]},
                  {"role": "combined original/current source inventory", "file": "SOURCE_HASHES.tsv logical rows", "bytes": "", "sha256": source_set_hash}]
    tables["INPUT_HASHES.tsv"] = (["role", "file", "bytes", "sha256"], input_rows)
    report = ["# Static TeX control-word candidate inventory", "", "Generated " + utc() + ".", "",
              "This interim mechanical inventory makes no validity, reading, translation or editorial decision. No source was changed and no TeX build was run.", "",
              "| Measure | Count |", "| --- | ---: |"]
    report.extend(f"| {key.replace('_', ' ')} | {value if value is not None else 'not collected'} |" for key, value in summary.items())
    report.extend(["", "## Interpretation", "",
                   "CANDIDATES.tsv lists each current file/command pair whose lexical count exceeds the same-path original count. Missing original files have a zero baseline. CANDIDATE_OCCURRENCES.tsv lists every current occurrence of each candidate, including existing occurrences and literal declaration-name tokens; it does not identify which individual occurrence was added. Coordinates are one-based physical LF lines and character columns.", "",
                   "GLOBALLY_NEW_COMMANDS.tsv uses the vocabulary of all eligible original TeX members, including original-only files. POSSIBLE_PREFIX_SPLITS.tsv lists all proper prefixes that were control words in the original vocabulary. A split is only a possible merged-word candidate; it is neither a correction nor proof that the longer word is invalid.", "",
                   "Explicit declaration forms, when requested, are metadata only. A declared candidate is retained with the same review status. Declaration syntax does not establish execution, correctness or intended use.", "",
                   "The scan uses ASCII letters for control words, consumes escaped control symbols, skips percent comments, simple verb/verb-star bodies, and literal bodies of the documented common verbatim environments. It does not expand macros, follow input commands, interpret catcode changes, understand custom literal macros or reconstruct csname-generated commands. It is not a full TeX parser. LEXICAL_NOTES.tsv records observed syntax signals and incomplete recognized literal boundaries; it cannot enumerate every limitation.", "",
                   "The original ZIP is matched by exact relative member name. No container-prefix or basename matching is guessed. Source filenames under programme, notes or stacks directories and symbolic links are not opened. Reports contain command names and structural metadata only, with no prose or formula excerpts.", "",
                   "SOURCE_HASHES.tsv binds every lexically inspected member and current source. INPUT_HASHES.tsv also binds the complete original ZIP and combined source-inventory rows. All snapshot inputs were checked again before this new directory was installed. Candidate IDs belong to this snapshot.", ""])
    payloads = {name: tsv_bytes(fields, rows) for name, (fields, rows) in tables.items()}
    payloads["REPORT.md"] = "\n".join(report).encode("utf-8")
    if any(scan_bytes(name, data) for name, data in payloads.items()):
        raise RuntimeError("Generated metadata contains a privacy pattern or inspection blocker; no report was installed.")
    with tempfile.TemporaryDirectory(prefix="control-word-inventory-", dir=root.parent) as temporary:
        prepared = Path(temporary)
        for name, data in payloads.items():
            (prepared / name).write_bytes(data)
        recheck_snapshot(sources, current, archive_path, archive_hash)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir()  # Exclusive reservation: never replace an existing report.
        installed = []
        try:
            for name in sorted(payloads):
                target = output / name
                os.link(prepared / name, target)
                installed.append(target)
        except BaseException:
            for path in installed:
                path.unlink()
            output.rmdir()
            raise
    print(json.dumps({**summary, "report_directory": output.relative_to(root).as_posix(), "review_status": "all candidates require manual review"}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--original-sources", type=Path, required=True, help="Supplied source ZIP; only eligible TeX member contents are lexically inspected")
    parser.add_argument("--output", type=Path, required=True, help="New interim report directory relative to the delivery root")
    parser.add_argument("--include-declarations", action="store_true", help="Report simple literal current declaration forms as metadata; never clears a candidate")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
