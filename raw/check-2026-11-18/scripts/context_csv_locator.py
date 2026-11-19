"""Mechanical CSV iteration with positional fields and physical line locators.

No dictionaries are built from column names: duplicate and empty headers remain
visible, and surplus fields retain their one-based position. No content is
normalized or semantically interpreted. UTF-8 is required; a UTF-8 BOM is
recorded as encoding metadata and omitted from the first header field.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class CsvRecord:
    record_number: int
    physical_start_line: int
    physical_end_line: int
    fields: tuple[str, ...]

    def positional_fields(self, headers: tuple[str, ...]) -> list[dict]:
        """Bind fields by position; an absent header/value is represented by None."""
        return [
            {
                "position": index + 1,
                "header": headers[index] if index < len(headers) else None,
                "value": self.fields[index] if index < len(self.fields) else None,
            }
            for index in range(max(len(headers), len(self.fields)))
        ]

    def as_dict(self, headers: tuple[str, ...]) -> dict:
        """Return the search helper's positional, locator-bearing record form."""
        return {
            "logical_record": self.record_number,
            "physical_line_start": self.physical_start_line,
            "physical_line_end": self.physical_end_line,
            "fields": self.positional_fields(headers),
        }

    def metadata(self, header_count: int) -> dict:
        serialized = json.dumps(
            self.fields, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return {
            "record_number": self.record_number,
            "physical_start_line": self.physical_start_line,
            "physical_end_line": self.physical_end_line,
            "field_count": len(self.fields),
            "field_count_matches_header": len(self.fields) == header_count,
            "blank_record": not self.fields,
            "fields_sha256": hashlib.sha256(serialized).hexdigest(),
        }


class CsvLocator:
    """Read one immutable byte snapshot and iterate its exact parsed fields.

    Logical record numbers are one-based after the first parsed CSV record,
    which is the header. Blank CSV records count as logical data records.
    Physical line numbers are one-based and recognize LF, CRLF, and lone CR,
    including those inside quoted fields. A malformed input raises csv.Error;
    no rows after that error are invented or recovered.
    """

    def __init__(self, raw: bytes):
        self.byte_size = len(raw)
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.utf8_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig", errors="strict")
        self.physical_lines = tuple(io.StringIO(text, newline=""))
        self.physical_line_count = len(self.physical_lines)
        self.headers: tuple[str, ...] = ()
        self.header_physical_start_line: int | None = None
        self.header_physical_end_line: int | None = None
        reader = csv.reader(self.physical_lines, strict=True)
        try:
            self.headers = tuple(next(reader))
        except StopIteration:
            return
        self.header_physical_start_line = 1
        self.header_physical_end_line = reader.line_num

    @classmethod
    def from_path(cls, path: str | Path) -> "CsvLocator":
        return cls(Path(path).read_bytes())

    def records(self) -> Iterator[CsvRecord]:
        reader = csv.reader(self.physical_lines, strict=True)
        try:
            next(reader)
        except StopIteration:
            return
        previous_end = reader.line_num
        for record_number, fields in enumerate(reader, start=1):
            record = CsvRecord(
                record_number=record_number,
                physical_start_line=previous_end + 1,
                physical_end_line=reader.line_num,
                fields=tuple(fields),
            )
            previous_end = reader.line_num
            yield record

    def metadata(self, relative_file: str) -> tuple[dict, list[dict]]:
        """Return only headers, hashes, counts and locators, never data values."""
        header_counts = Counter(self.headers)
        duplicate_headers = [
            {"header": value, "positions": [i + 1 for i, h in enumerate(self.headers) if h == value]}
            for value, count in header_counts.items()
            if count > 1
        ]
        locators = []
        malformed = None
        try:
            for record in self.records():
                locators.append(record.metadata(len(self.headers)))
        except csv.Error as exc:
            # csv.Error contains a parser description, not the source field.
            malformed = {"message": str(exc), "after_complete_data_records": len(locators)}
        summary = {
            "relative_file": relative_file,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "encoding": "utf-8",
            "utf8_bom": self.utf8_bom,
            "physical_line_count": self.physical_line_count,
            "headers": list(self.headers),
            "header_field_count": len(self.headers),
            "header_physical_start_line": self.header_physical_start_line,
            "header_physical_end_line": self.header_physical_end_line,
            "data_record_count": len(locators),
            "multiline_data_record_count": sum(r["physical_end_line"] > r["physical_start_line"] for r in locators),
            "blank_data_record_count": sum(r["blank_record"] for r in locators),
            "duplicate_headers": duplicate_headers,
            "empty_header_positions": [i + 1 for i, h in enumerate(self.headers) if h == ""],
            "field_count_mismatch_records": [r["record_number"] for r in locators if not r["field_count_matches_header"]],
            "malformed_csv": malformed,
        }
        return summary, locators


def iter_csv_records(path: str | Path) -> Iterator[dict]:
    """Yield data records with fields [{position, header, value}, ...].

    This adapter retains raw parsed values for a scratch index or immediate
    search. It does not apply privacy masking. The caller must mask any selected
    values before including them in returned search results or delivery files.
    """
    table = CsvLocator.from_path(path)
    for record in table.records():
        yield record.as_dict(table.headers)
