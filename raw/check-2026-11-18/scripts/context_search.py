"""Mechanically index supplied context and return bounded, privacy-safe matches.

Only authorized programme/Stacks HTML, CSV and manifest/status text are read.
JavaScript is never executed. Parsed values belong in an external scratch cache;
the index report contains only hashes, schemas, counts and source locators.
Search results carry no claim about mathematical truth or later-work relations.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import hashlib
import html
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re

from context_csv_locator import CsvLocator
from privacy_guard import safe_location, scan_bytes


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def text_value(value):
    return value if isinstance(value, str) else compact(value)


def safe_tree(value):
    if isinstance(value, str):
        return safe_location(value)
    if isinstance(value, list):
        return [safe_tree(item) for item in value]
    if isinstance(value, dict):
        return {safe_location(key): safe_tree(item) for key, item in value.items()}
    return value


def tsv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, delimiter="\t", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def install(output, payloads):
    if output.exists():
        raise ValueError("Output already exists; use a fresh directory.")
    if any(scan_bytes(name, raw) for name, raw in payloads.items()):
        raise ValueError("Prepared output has a privacy finding; no report installed.")
    output.mkdir(parents=True)
    for name, raw in payloads.items():
        (output / name).write_bytes(raw)


def source_inputs(root):
    paths = sorted({*(root / "programme").rglob("*.html"),
                    *(root / "programme").rglob("*.htm"),
                    *(root / "stacks").rglob("*.csv"),
                    *(root / "programme").rglob("*.md"),
                    *(root / "stacks").rglob("*.md"),
                    *([root / "README.md"] if (root / "README.md").is_file() else [])})
    if not paths:
        raise ValueError("No authorized context inputs found.")
    for path in paths:
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError("A context input escapes the selected context tree.")
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in paths}


def markdown_records(source):
    """Split exact text at blank lines, headings and list-item starts."""
    rows, pending = [], []
    offset = 0

    def flush():
        if not pending:
            return
        start_line, start_offset, _ = pending[0]
        end_line, end_offset, last = pending[-1]
        rows.append({"kind": "markdown_text", "logical_record": len(rows) + 1,
            "physical_line_start": start_line, "physical_line_end": end_line,
            "character_start": start_offset, "character_end": end_offset + len(last),
            "anchor_ids": [], "html_tag": "",
            "fields": [{"position": 1, "name": "text", "value": "".join(part[2] for part in pending)}]})
        pending.clear()

    for number, line in enumerate(source.splitlines(keepends=True), 1):
        if not line.strip():
            flush()
        else:
            heading = bool(re.match(r"^#{1,6}[ \t]+", line))
            item = bool(re.match(r"^[ \t]*(?:[-*+]|[0-9]+[.)])[ \t]+", line))
            if heading or item:
                flush()
            pending.append((number, offset, line))
            if heading:
                flush()
        offset += len(line)
    flush()
    return rows


def notes_context_status(root, captured):
    """Report observed absence with the literal supplied README marker."""
    present = (root / "notes").exists()
    status = {"directory_name": "notes", "directory_present": present,
              "status": "present; contents outside this index" if present else "absent"}
    raw = captured.get("README.md")
    if raw is None:
        status["manifest_evidence"] = None
        return status
    source = raw.decode("utf-8-sig")
    lines = source.splitlines()
    start = next((index for index, line in enumerate(lines) if re.match(r"^[ \t]*-[ \t]+`notes/`:", line)), None)
    end = None if start is None else next((index for index in range(start, min(start + 8, len(lines)))
            if re.match(r"^[ \t]*-[ \t]+none:", lines[index])), None)
    if end is not None:
        status["status"] = "present despite supplied none marker" if present else "absent; supplied README explicitly records none"
        status["manifest_evidence"] = {"source_file": "README.md", "source_sha256": sha(raw),
            "physical_line_start": start + 1, "physical_line_end": end + 1,
            "text": "\n".join(lines[start:end + 1]),
            "logical_records": [row["logical_record"] for row in markdown_records(source)
                if row["physical_line_end"] >= start + 1 and row["physical_line_start"] <= end + 1]}
    else:
        status["manifest_evidence"] = None
    return status


@dataclass
class Element:
    tag: str
    start: int
    end: int
    parent: object
    attrs: list = field(default_factory=list)


class StaticHTML(HTMLParser):
    """Keep text outside script/style with enclosing block and anchor locators."""

    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
    BLOCK = frozenset({"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "pre", "figcaption", "dt", "dd", "label", "option", "button", "summary"})
    FALLBACK = frozenset({"div", "section", "article", "header", "footer", "nav", "a"})

    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.starts = [0] + [match.end() for match in re.finditer("\n", source)]
        self.root = Element("document", 0, len(source), None)
        self.stack = [self.root]
        self.blocks = {}
        self.unmatched_end_tags = Counter()
        self.anchor_count = 0

    def source_position(self):
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.source_position()
        node = Element(tag, start, start + len(self.get_starttag_text()), self.stack[-1], attrs)
        self.anchor_count += sum(key == "id" for key, value in attrs)
        if tag not in self.VOID:
            self.stack.append(node)
        elif tag in {"br", "hr"}:
            self.add_text("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        end = self.source.find(">", self.source_position()) + 1
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                for node in self.stack[index:]:
                    node.end = end
                del self.stack[index:]
                return
        self.unmatched_end_tags[tag] += 1

    def add_text(self, value):
        if any(node.tag in {"script", "style"} for node in self.stack):
            return
        block = next((node for node in reversed(self.stack) if node.tag in self.BLOCK), None)
        block = block or next((node for node in reversed(self.stack) if node.tag in self.FALLBACK), self.root)
        key = block.start, block.tag
        if key not in self.blocks:
            self.blocks[key] = [block, []]
        self.blocks[key][1].append(value)

    def handle_data(self, data):
        self.add_text(data)

    def handle_entityref(self, name):
        self.add_text(html.unescape("&" + name + ";"))

    def handle_charref(self, name):
        self.add_text(html.unescape("&#" + name + ";"))

    def records(self):
        self.feed(self.source)
        self.close()
        for node in self.stack[1:]:
            node.end = len(self.source)
        records = []
        for node, parts in sorted(self.blocks.values(), key=lambda item: item[0].start):
            value = "".join(parts)
            if not value.strip():
                continue
            ancestors, current = [], node
            while current is not None:
                ancestors.append(current)
                current = current.parent
            anchors = [value for ancestor in reversed(ancestors) for key, value in ancestor.attrs if key == "id" and value is not None]
            records.append({"kind": "html_static", "logical_record": len(records) + 1,
                "physical_line_start": bisect_right(self.starts, node.start),
                "physical_line_end": bisect_right(self.starts, max(node.start, node.end - 1)),
                "character_start": node.start, "character_end": node.end,
                "anchor_ids": anchors, "html_tag": node.tag,
                "fields": [{"position": 1, "name": "text", "value": value}]})
        return records


def data_rows(source):
    """Decode literal JSON only; retain each DATA.rows item's source span."""
    matches = list(re.finditer(r"\b(?:const|let|var)\s+DATA\s*=\s*", source))
    if len(matches) != 1:
        raise ValueError("Expected exactly one literal DATA assignment in programme HTML.")
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(source, matches[0].end())
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise ValueError("DATA.rows is not a literal JSON array.")
    starts = [0] + [match.end() for match in re.finditer("\n", source)]

    def whitespace(index):
        while index < len(source) and source[index].isspace():
            index += 1
        return index

    index = whitespace(matches[0].end()) + 1
    rows_start = None
    while True:
        index = whitespace(index)
        if source[index] == "}":
            break
        key, index = decoder.raw_decode(source, index)
        index = whitespace(index)
        if source[index] != ":":
            raise ValueError("Malformed DATA object boundary.")
        index = whitespace(index + 1)
        if key == "rows":
            rows_start = index
        _, index = decoder.raw_decode(source, index)
        index = whitespace(index)
        if source[index] == ",":
            index += 1
    if rows_start is None or source[rows_start] != "[":
        raise ValueError("Missing DATA.rows source span.")
    index, records = rows_start + 1, []
    while True:
        index = whitespace(index)
        if source[index] == "]":
            break
        start = index
        item, index = decoder.raw_decode(source, start)
        if not isinstance(item, dict):
            raise ValueError("A DATA.rows record is not an object.")
        records.append({"kind": "html_DATA.rows", "logical_record": len(records) + 1,
            "physical_line_start": bisect_right(starts, start),
            "physical_line_end": bisect_right(starts, max(start, index - 1)),
            "character_start": start, "character_end": index,
            "anchor_ids": ["DATA.rows"], "html_tag": "",
            "fields": [{"position": number, "name": key, "value": field_value}
                       for number, (key, field_value) in enumerate(item.items(), 1)]})
        index = whitespace(index)
        if source[index] == ",":
            index += 1
    if [dict((field["name"], field["value"]) for field in row["fields"]) for row in records] != value["rows"]:
        raise ValueError("DATA.rows source-span reconstruction differs from its literal JSON.")
    return records, {"DATA_keys": list(value), "DATA_rows": len(records),
                     "DATA_physical_line_start": bisect_right(starts, matches[0].end()),
                     "DATA_physical_line_end": bisect_right(starts, end - 1)}


def make_index(args):
    root, cache, output = args.context_root.resolve(), args.cache.resolve(), args.output.resolve()
    delivery = Path(__file__).resolve().parents[1]
    if cache == delivery or delivery in cache.parents or root == cache or root in cache.parents:
        raise ValueError("The parsed-content cache must be outside delivery and supplied context.")
    if output == root or root in output.parents or output == cache or output in cache.parents or cache in output.parents:
        raise ValueError("The report must be separate from supplied context and the parsed-content cache.")
    if cache.exists() or output.exists():
        raise ValueError("Use fresh cache and report directories.")
    captured = source_inputs(root)
    records, files = [], []
    for name, raw in captured.items():
        digest = sha(raw)
        if name.endswith(".csv"):
            table = CsvLocator(raw)
            metadata, _ = table.metadata(name)
            if metadata["malformed_csv"]:
                raise ValueError("A CSV failed strict parsing; no index installed.")
            selected = []
            for row in table.records():
                fields = [{"position": item["position"], "name": item["header"], "value": item["value"]}
                          for item in row.positional_fields(table.headers)]
                selected.append({"kind": "csv", "logical_record": row.record_number,
                    "physical_line_start": row.physical_start_line, "physical_line_end": row.physical_end_line,
                    "character_start": "", "character_end": "", "anchor_ids": [], "html_tag": "", "fields": fields})
        elif name.endswith(".md"):
            source = raw.decode("utf-8-sig", errors="strict")
            selected = markdown_records(source)
            metadata = {"relative_file": name, "sha256": digest, "byte_size": len(raw),
                "physical_line_count": len(source.splitlines()), "encoding": "utf-8",
                "markdown_text_records": len(selected), "headers": ["text"]}
        else:
            source = raw.decode("utf-8-sig", errors="strict")
            static = StaticHTML(source)
            static_records = static.records()
            literal_records, data_metadata = data_rows(source)
            selected = static_records + literal_records
            metadata = {"relative_file": name, "sha256": digest, "byte_size": len(raw),
                "physical_line_count": len(source.splitlines()), "encoding": "utf-8",
                "static_text_records": len(static_records), "anchor_count": static.anchor_count,
                "unmatched_end_tags": dict(static.unmatched_end_tags), **data_metadata}
        for record in selected:
            record["source_file"] = name
            record["source_sha256"] = digest
            record["record_id"] = name + "#" + record["kind"] + ":" + str(record["logical_record"])
            for value in record["fields"]:
                value["value_sha256"] = sha(compact(value["value"]).encode())
            record["fields_sha256"] = sha(compact(record["fields"]).encode())
        records.extend(selected)
        files.append(metadata)
    raw_cache = ("\n".join(compact(record) for record in records) + "\n").encode()
    manifest = {"schema": "supplied-context-search-v2", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records), "record_counts_by_kind": dict(Counter(row["kind"] for row in records)),
        "source_files": files, "cache_records_sha256": sha(raw_cache),
        "logical_record_convention": "One-based per source and record kind; CSV records follow the header and include blank records.",
        "physical_line_convention": "One-based, inclusive. CSV supports LF, CRLF and CR; HTML source locators use LF lines.",
        "character_offset_convention": "HTML offsets are zero-based Unicode code-point positions in UTF-8-decoded text, end exclusive.",
        "field_hash_convention": "value_sha256 hashes the exact parsed value serialized as compact UTF-8 JSON with ensure_ascii=False; fields_sha256 hashes the ordered field objects, including their positions, names and value hashes.",
        "static_text_convention": "Text and entities outside script/style, grouped by nearest text block; anchors are enclosing id attributes; br/hr become newlines.",
        "markdown_text_convention": "Exact text blocks split at blank lines, headings and list-item starts; no Markdown is executed or followed.",
        "json_convention": "Only literal JSON DATA.rows is decoded; other DATA keys are schema metadata, not searched.",
        "page_search_convention": "Literal numeric token search in fields explicitly named by the primary; no page-range expansion or page-field inference.",
        "notes_context_status": notes_context_status(root, captured),
        "interpretation_status": "Mechanical retrieval only; every note comparison remains pending primary review."}
    locators = [{key: row[key] for key in ("source_file", "source_sha256", "record_id", "kind", "logical_record",
                 "physical_line_start", "physical_line_end", "character_start", "character_end", "fields_sha256")}
                | {"anchor_ids": compact(row["anchor_ids"]), "html_tag": row["html_tag"],
                   "field_names": compact([value["name"] for value in row["fields"]])} for row in records]
    safe_manifest, safe_locators = safe_tree(manifest), safe_tree(locators)
    safe_manifest["privacy_masked_metadata"] = safe_manifest != manifest or safe_locators != locators
    payloads = {"INDEX_SUMMARY.json": json_bytes(safe_manifest),
                "RECORD_LOCATORS.tsv": tsv_bytes(list(safe_locators[0]), safe_locators),
                "REPORT.md": ("# Supplied context: mechanical index\n\n"
                    "This report contains schemas, source hashes, counts, locators and the narrow README evidence for the notes-directory status. Other parsed context values stay in an external scratch cache. No supplied context file is copied into delivery.\n\n"
                    "Use the context_search.py query command for a named note and explicit literal terms, anchors or page fields. Each selected field retains its original-value hash; returned snippets are privacy masked. No match means only that the exact query did not match this indexed scope. No mathematical or later-work verdict is inferred.\n\n"
                    "All Stacks CSV fields are preserved by position, including duplicate names or absent fields. HTML static text excludes script and style content. DATA.rows is decoded as literal JSON without running JavaScript; other DATA keys are outside the search scope. The supplied context README and programme/Stacks Markdown status, map and README files are indexed as exact text blocks. HTML record spans cover the enclosing text block; DATA.rows spans cover the individual JSON object.\n").encode()}
    if source_inputs(root) != captured:
        raise ValueError("A supplied input changed while indexing; no index installed.")
    if any(scan_bytes(name, raw) for name, raw in payloads.items()):
        raise ValueError("Index metadata has a privacy finding; no index installed.")
    cache.mkdir(parents=True)
    (cache / "records.jsonl").write_bytes(raw_cache)
    (cache / "manifest.json").write_bytes(json_bytes(manifest))
    install(output, payloads)
    return {"source_files": len(files), "records": len(records), "counts_by_kind": manifest["record_counts_by_kind"],
            "privacy_masked_metadata": safe_manifest["privacy_masked_metadata"], "cache_records_sha256": sha(raw_cache)}


def literal_match(text, term, case_sensitive=False):
    return term in text if case_sensitive else term.casefold() in text.casefold()


def token_match(text, token):
    return re.search(r"(?<![A-Za-z0-9_-])" + re.escape(token) + r"(?![A-Za-z0-9_-])", text, re.I) is not None


def select_record(record, args):
    if args.source and not any(fnmatch.fnmatchcase(record["source_file"], pattern) for pattern in args.source):
        return None
    if args.kind and record["kind"] not in args.kind:
        return None
    selected = [field for field in record["fields"] if not args.field or field["name"] in args.field]
    term_hits = {term: [field["position"] for field in selected if literal_match(text_value(field["value"]), term, args.case_sensitive)] for term in args.term}
    if term_hits and not (all(term_hits.values()) if args.match == "all" else any(term_hits.values())):
        return None
    anchor_positions, anchor_ids = [], []
    for anchor in args.anchor:
        matches = [field["position"] for field in selected if token_match(text_value(field["value"]), anchor)]
        matched_ids = [value for value in record["anchor_ids"] if value == anchor]
        if not matches and not matched_ids:
            return None
        anchor_positions.extend(matches)
        anchor_ids.extend(matched_ids)
    page_positions = []
    for page in args.page:
        matches = [field["position"] for field in record["fields"] if field["name"] in args.page_field
                   and re.search(r"(?<![0-9])" + re.escape(page) + r"(?![0-9])", text_value(field["value"]))]
        if not matches:
            return None
        page_positions.extend(matches)
    positions = set(anchor_positions + page_positions + [position for values in term_hits.values() for position in values])
    positions.update(field["position"] for field in record["fields"] if field["name"] in args.show_field)
    result = {key: record[key] for key in record if key != "fields"}
    result["primary_comparison"] = "pending primary review"
    result["matched_anchor_ids"] = anchor_ids
    result["fields"] = []
    for field in record["fields"]:
        if field["position"] not in positions:
            continue
        original = text_value(field["value"])
        masked = safe_location(original)
        if args.full_fields or len(masked) <= args.snippet_chars:
            excerpt, truncated = masked, False
        else:
            candidates = [masked.casefold().find(value.casefold()) for value in [*args.term, *args.anchor, *args.page] if value]
            at = min((value for value in candidates if value >= 0), default=0)
            start = max(0, at - args.snippet_chars // 3)
            end = min(len(masked), start + args.snippet_chars)
            excerpt = ("…" if start else "") + masked[start:end] + ("…" if end < len(masked) else "")
            truncated = True
        result["fields"].append({"position": field["position"], "name": field["name"],
            "value_sha256": field["value_sha256"], "text": excerpt,
            "privacy_masked": masked != original, "snippet_truncated": truncated,
            "matching_terms": [term for term, positions_for_term in term_hits.items() if field["position"] in positions_for_term],
            "anchor_match": field["position"] in anchor_positions, "page_match": field["position"] in page_positions})
    return safe_tree(result)


def query(args):
    if not args.term and not args.anchor and not args.page:
        raise ValueError("Supply at least one explicit term, anchor or page.")
    if args.page and not args.page_field:
        raise ValueError("Page queries require explicitly named page fields.")
    if any(not re.fullmatch(r"[0-9]+", page) for page in args.page):
        raise ValueError("A page query must be a literal integer token.")
    if args.limit < 1 or args.snippet_chars < 40:
        raise ValueError("Use a positive result limit and at least 40 snippet characters.")
    root = args.context_root.resolve()
    output, cache = args.output.resolve(), args.cache.resolve()
    if output == root or root in output.parents or output == cache or cache in output.parents:
        raise ValueError("Search results must be separate from supplied context and the parsed-content cache.")
    manifest = json.loads((args.cache / "manifest.json").read_text())
    raw_cache = (args.cache / "records.jsonl").read_bytes()
    if sha(raw_cache) != manifest["cache_records_sha256"]:
        raise ValueError("Scratch cache hash differs from its manifest.")
    captured = source_inputs(root)
    expected = {item["relative_file"]: item["sha256"] for item in manifest["source_files"]}
    if {name: sha(raw) for name, raw in captured.items()} != expected:
        raise ValueError("Supplied context changed; prepare a fresh index before searching.")
    if manifest.get("notes_context_status") != notes_context_status(root, captured):
        raise ValueError("The notes-directory status changed; prepare a fresh index.")
    found = []
    for line in raw_cache.decode().splitlines():
        record = json.loads(line)
        match = select_record(record, args)
        if match is not None:
            found.append(match)
    selected = found[:args.limit]
    summary = safe_tree({"note_id": args.note_id, "terms": args.term, "term_combination": args.match,
        "anchors": args.anchor, "pages": args.page, "page_fields": args.page_field,
        "search_fields": args.field, "shown_fields": args.show_field, "source_patterns": args.source,
        "case_sensitive": args.case_sensitive, "full_fields": args.full_fields,
        "matched_records": len(found), "returned_records": len(selected), "results_truncated": len(found) > len(selected),
        "privacy_masked_fields": sum(field["privacy_masked"] for row in selected for field in row["fields"]),
        "snippet_truncated_fields": sum(field["snippet_truncated"] for row in selected for field in row["fields"]),
        "cache_records_sha256": manifest["cache_records_sha256"],
        "notes_context_status": manifest.get("notes_context_status"),
        "source_hashes": expected, "primary_comparison": "pending primary review",
        "scope_limit": "Literal retrieval only. No page-field semantics, page-range expansion or mathematical relation is inferred."})
    flat = []
    fields = ["note_id", "source_file", "source_sha256", "record_id", "kind", "logical_record", "physical_line_start", "physical_line_end",
              "character_start", "character_end", "anchor_ids", "field_position", "field_name", "value_sha256", "text", "privacy_masked", "snippet_truncated", "primary_comparison"]
    for row in selected:
        for value in row["fields"] or [{}]:
            flat.append({key: row[key] for key in fields if key in row}
                | {"note_id": safe_location(args.note_id), "anchor_ids": compact(row["anchor_ids"]),
                   "field_position": value.get("position", ""), "field_name": value.get("name", ""),
                   **{key: value.get(key, "") for key in ("value_sha256", "text", "privacy_masked", "snippet_truncated")}})
    if source_inputs(root) != captured:
        raise ValueError("A supplied source changed during the query; no results installed.")
    install(args.output.resolve(), {"SEARCH_SUMMARY.json": json_bytes(summary), "SEARCH_RESULTS.json": json_bytes(selected),
                                  "SEARCH_RESULTS.tsv": tsv_bytes(fields, flat)})
    return {key: summary[key] for key in ("note_id", "matched_records", "returned_records", "results_truncated", "privacy_masked_fields")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index", help="Create external parsed cache and content-free index metadata.")
    search = sub.add_parser("query", help="Return bounded literal matches for primary review.")
    for command in (index, search):
        command.add_argument("--context-root", type=Path, required=True)
        command.add_argument("--cache", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    search.add_argument("--note-id", required=True)
    search.add_argument("--term", action="append", default=[])
    search.add_argument("--anchor", action="append", default=[])
    search.add_argument("--page", action="append", default=[])
    search.add_argument("--page-field", action="append", default=[])
    search.add_argument("--field", action="append", default=[])
    search.add_argument("--show-field", action="append", default=[])
    search.add_argument("--source", action="append", default=[])
    search.add_argument("--kind", action="append", choices=("csv", "html_static", "html_DATA.rows", "markdown_text"), default=[])
    search.add_argument("--match", choices=("all", "any"), default="all")
    search.add_argument("--case-sensitive", action="store_true")
    search.add_argument("--full-fields", action="store_true")
    search.add_argument("--snippet-chars", type=int, default=260)
    search.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    try:
        result = make_index(args) if args.command == "index" else query(args)
    except (ValueError, OSError, csv.Error, UnicodeError) as exc:
        parser.exit(2, safe_location(type(exc).__name__ + ": " + str(exc)) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
