"""Shared mechanical privacy inspection for delivery files and archive sets.

Only findings and safe locators are returned. Source bytes are never rewritten.
Text detection is independent of filename suffix; binary images are not OCRed.
"""

from __future__ import annotations

import ast
import codecs
from contextlib import ExitStack
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
import tokenize
import zipfile

from privacy_syntax import (editorial_slash_not_path, extra_tex_morphism,
                            serialized_hom_newline, verified_pdf_charset)

VALIDATION_REPORT_NAMES = frozenset({
    "FINAL_VALIDATION.md", "FINAL_VALIDATION_CHECKS.tsv", "FINAL_VALIDATION_PRIVACY.tsv",
    "FINAL_VALIDATION_INVENTORY.tsv", "FINAL_VALIDATION_CREDIT_CONFLICTS.tsv",
})
GENERATED_ARCHIVE_NAMES = frozenset({"FILE_LIST.tsv", "ARCHIVE_INFO.tsv", "CHECKPOINT_INFO.tsv", "CHUNKS.tsv"})
EMAIL = re.compile(r"(?<![\w.+-])[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
LOCAL_URI = re.compile(r'''\bf(?:ile):/+[^\s<>"'`,;]+''', re.I)
WINDOWS_PATH = re.compile(r'''(?<![\w\\])[A-Za-z]:[\\/][^\s()\[\]{}<>"'`,;]+''')
UNC_PATH = re.compile(r'''(?<!\\)(?P<unc_slash>\\{1,2})(?P=unc_slash)[A-Za-z0-9_.-]+(?P=unc_slash)[A-Za-z0-9_.-][^\s<>"'`,;]+''')
NETWORK_PATH = re.compile(r'''(?<![:/])//[A-Za-z0-9_.-]+/[^\s<>"'`,;]+''')
POSIX_PATH = re.compile(r'''(?<![\w./\\*?\)\]\}])(?<!<layer>)/(?!/)[\w.~\-][^\s()\[\]{}<>"'`,;]*''')
PATTERNS = [(EMAIL, "email address"), (LOCAL_URI, "local-file URI"),
            (WINDOWS_PATH, "possible absolute filesystem path"), (UNC_PATH, "possible network filesystem path"),
            (NETWORK_PATH, "possible network filesystem path"), (POSIX_PATH, "possible absolute filesystem path")]
# A typed TeX morphism can start with the same letter-colon-backslash bytes as
# a drive path. Require the complete small mathematical expression, including
# its arrow and target, rather than exempting a control-word prefix. The two
# backslash widths cover literal TeX and one JSON/Python escaping layer.
_TEX_FONT = r"(?:mathbf|mathrm|mathcal|mathbb|mathfrak|overline|bar)"
_TEX_ARGUMENT = r"(?:\{[A-Za-z]\}|[A-Za-z])'{0,3}"
_TEX_MORPHISM = re.compile(
    r"[A-Za-z]:(?P<slash>\\{1,2})" + _TEX_FONT + r"[ \t]*" + _TEX_ARGUMENT
    + r"[ \t]*(?P=slash)(?:to|rightarrow|longrightarrow)[ \t]*"
    + r"(?:(?P=slash)" + _TEX_FONT + r"[ \t]*)?" + _TEX_ARGUMENT
)
_TEX_LIMIT_INDEX = re.compile(r"(?P<slash>\\{1,2})(?P=slash)[A-Za-z](?P=slash)in[ \t]+[A-Za-z]")
TEXT_SUFFIXES = frozenset({".tex", ".sty", ".cls", ".ldf", ".cfg", ".ini", ".bib", ".bst", ".md", ".tsv", ".csv", ".py", ".sh", ".txt", ".log", ".json", ".jsonl", ".yaml", ".yml", ".html", ".htm", ".xml", ".svg", ".js", ".mjs", ".ts", ".css", ".toml", ".rst", ".ipynb"})
BINARY_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"II*\x00", b"MM\x00*", b"RIFF", b"PK\x03\x04", b"\x1f\x8b", b"\x7fELF")
READ_SIZE = 1024 * 1024
MAX_LINE_CHARS = 4 * 1024 * 1024


def _mathematical_term_ends(text: str, end: int) -> bool:
    remainder = text[end:]
    if not remainder:
        return True
    # A filename, drive qualifier, extra component or unrecognized control
    # sequence after the target keeps the original filesystem finding active.
    if remainder[0].isalnum() or remainder[0] in "_/:":
        return False
    if remainder.startswith(".") and len(remainder) > 1 and not remainder[1].isspace():
        return False
    if remainder.startswith("\\"):
        return bool(re.match(r"\\{1,2}(?:qquad|quad)(?![A-Za-z])|\\{1,2}[)\]]", remainder))
    return True


def _tex_morphism_not_path(text: str, match: re.Match) -> bool:
    """Recognize a narrow TeX token grammar, never a filename-prefix waiver."""
    typed = _TEX_MORPHISM.match(text, match.start())
    return typed is not None and _mathematical_term_ends(text, typed.end())


def _tex_limit_index_not_path(text: str, match: re.Match) -> bool:
    # In a limit index, an arrow followed by an array line break and i-in-I
    # can resemble a network path. Require both the preceding TeX arrow and
    # the complete single-letter membership expression, with no path suffix.
    if not re.search(r"\\{1,2}(?:longrightarrow|rightarrow|to)[ \t]*$", text[:match.start()]):
        return False
    typed = _TEX_LIMIT_INDEX.match(text, match.start())
    return typed is not None and _mathematical_term_ends(text, typed.end())


def _printed_word_seam_not_path(text: str, match: re.Match) -> bool:
    # These exact editorial word-division descriptions are neither file names
    # nor path prefixes. Keep all longer components and all other words under
    # the ordinary path rule, and require explicit seam/division context.
    before = text[:match.start()]
    pairs = (("coho-", chr(47) + "mologiques"),
             ("immédi-", chr(47) + "atement"),
             (r"imm\u00e9di-", chr(47) + "atement"),
             ("immé-", chr(47) + "atement"),
             (r"imm\u00e9-", chr(47) + "atement"))
    if not any(before.endswith(left) and match.group(0) == right for left, right in pairs):
        return False
    context = text[max(0, match.start() - 60):match.end() + 60]
    return bool(re.search(r"\b(?:seam|division)\b", context))


def _flattened_quotient_not_path(text: str, match: re.Match) -> bool:
    # One supplied context field flattens an indexed-set quotient into plain
    # text. Require its exact left expression and following sentence boundary;
    # a standalone root name or any longer path remains a finding.
    return (match.group(0) == chr(47) + "G"
            and re.search(r"\bI n\+1[ \t]+$", text[:match.start()]) is not None
            and re.match(r"[ \t]+\.[ \t]+In the second product\b", text[match.end():]) is not None)


def _not_a_filesystem_path(expression: re.Pattern, text: str, match: re.Match) -> bool:
    return ((expression is WINDOWS_PATH and
             (_tex_morphism_not_path(text, match) or extra_tex_morphism(text, match, _mathematical_term_ends)))
            or (expression is UNC_PATH and
                (_tex_limit_index_not_path(text, match) or serialized_hom_newline(text, match)))
            or (expression is POSIX_PATH and
                (_printed_word_seam_not_path(text, match) or editorial_slash_not_path(text, match, _mathematical_term_ends)
                 or _flattened_quotient_not_path(text, match))))


def _pattern_matches(expression: re.Pattern, text: str):
    for match in expression.finditer(text):
        if _not_a_filesystem_path(expression, text, match):
            continue
        yield match


def safe_location(value: str) -> str:
    value = str(value)
    for expression, kind in PATTERNS:
        replacement = "<redacted-email>" if kind == "email address" else "<local>"
        value = expression.sub(
            lambda match: match.group(0) if _not_a_filesystem_path(expression, value, match) else replacement,
            value,
        )
    return value


def privacy_findings(text: str) -> list[tuple[int, str]]:
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        for expression, kind in PATTERNS:
            if next(_pattern_matches(expression, line), None) is not None:
                item = (number, kind)
                if item not in result:
                    result.append(item)
    return result


def finding(name: str, location: str, kind: str, *, scope: str = "file content", file_sha256: str = "", start: int | str = "", end: int | str = "", match_digest: str = "") -> dict:
    identity = "\0".join(map(str, [name, location, kind, scope, file_sha256, start, end, match_digest]))
    return {"file": safe_location(name), "line_or_pdf_page": str(location), "kind": kind, "scope": scope,
            "finding_id": hashlib.sha256(identity.encode()).hexdigest(), "file_sha256": file_sha256,
            "source_offset_start": start, "source_offset_end": end, "match_sha256": match_digest}


def scan_text(text: str, name: str, *, scope: str = "file content", location: str | None = None, file_sha256: str = "", base_offset: int = 0, start_line: int = 1) -> list[dict]:
    findings, offset = [], base_offset
    for number, line in enumerate(text.splitlines(keepends=True), start_line):
        for expression, kind in PATTERNS:
            for match in _pattern_matches(expression, line):
                findings.append(finding(name, location or str(number), kind, scope=scope, file_sha256=file_sha256,
                                        start=offset + match.start(), end=offset + match.end(),
                                        match_digest=hashlib.sha256(match.group(0).encode()).hexdigest()))
        offset += len(line)
    return findings


def text_encoding(prefix: bytes, name: str) -> tuple[str | None, str]:
    suffix = PurePosixPath(name).suffix.lower()
    known = suffix in TEXT_SUFFIXES
    if not prefix:
        return "utf-8", "empty text"
    for marker, encoding in ((codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                             (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"), (codecs.BOM_UTF8, "utf-8-sig")):
        if prefix.startswith(marker):
            return encoding, "byte-order mark"
    if any(prefix.startswith(marker) for marker in BINARY_MAGIC):
        return ("utf-8", "binary signature in declared text") if known else (None, "binary signature")
    if b"\x00" in prefix:
        sample = prefix[:min(len(prefix), 4096)]
        candidates = []
        for width, encodings in ((4, ("utf-32-le", "utf-32-be")), (2, ("utf-16-le", "utf-16-be"))):
            aligned = sample[:len(sample) - len(sample) % width]
            for encoding in encodings:
                try:
                    decoded = aligned.decode(encoding)
                except UnicodeError:
                    continue
                if decoded and sum(character.isprintable() or character in "\r\n\t\f" for character in decoded) / len(decoded) > 0.98:
                    ascii_ratio = sum(character.isascii() and (character.isprintable() or character in "\r\n\t\f") for character in decoded) / len(decoded)
                    candidates.append((ascii_ratio, encoding))
        if candidates:
            candidates.sort(reverse=True)
            if candidates[0][0] >= 0.20 and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.10):
                return candidates[0][1], "Unicode text detected without byte-order mark"
            return None, "ambiguous Unicode encoding requires manual inspection"
        return ("utf-8", "NUL bytes in declared text") if known else (None, "binary NUL bytes")
    try:
        # The prefix may end inside a valid UTF-8 sequence.
        decoded = codecs.getincrementaldecoder("utf-8")().decode(prefix, final=False)
        encoding = "utf-8"
    except UnicodeError:
        decoded, encoding = prefix.decode("cp1252", errors="replace"), "cp1252"
    printable = sum(character.isprintable() or character in "\r\n\t\f" for character in decoded) / max(1, len(decoded))
    if not known and printable < 0.92:
        return None, "binary control-byte proportion"
    return encoding, "declared or detected text"


def scan_pdf(stream, name: str, file_sha256: str) -> list[dict]:
    findings = []
    try:
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject, TextStringObject
        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            return [finding(name, "PDF", "encrypted PDF could not be privacy-inspected", file_sha256=file_sha256)]
        for number, page in enumerate(reader.pages, 1):
            findings.extend(scan_text(page.extract_text() or "", name, location=f"PDF page {number}", file_sha256=file_sha256))
        # Traverse textual PDF objects: Info, annotations, URI destinations,
        # strings in attachment name trees and XMP metadata streams are covered.
        seen, count, charset_cache = set(), 0, {}
        def walk(value, depth=0, key="", parent=None):
            nonlocal count
            if depth > 150 or count > 500_000:
                raise ValueError("PDF object inspection limit exceeded")
            if isinstance(value, IndirectObject):
                reference = (value.idnum, value.generation)
                value = value.get_object()
                # A string reused in metadata and a font descriptor must be
                # inspected in both typed contexts. Only containers need the
                # cycle guard; string objects have no recursive children.
                if not isinstance(value, TextStringObject):
                    if reference in seen:
                        return
                    seen.add(reference)
            count += 1
            if isinstance(value, TextStringObject):
                text_value = str(value)
                detected = scan_text(text_value, name, scope="PDF textual object", location="PDF metadata/object", file_sha256=file_sha256)
                if verified_pdf_charset(text_value, key, parent, charset_cache):
                    # Remove only the one whole-value slash-path occurrence.
                    # All other pattern families and all other strings remain inspected.
                    digest = hashlib.sha256(text_value.encode()).hexdigest()
                    detected = [item for item in detected if not (
                        item["kind"] == "possible absolute filesystem path"
                        and item["source_offset_start"] == 0
                        and item["source_offset_end"] == len(text_value)
                        and item["match_sha256"] == digest)]
                findings.extend(detected)
            elif isinstance(value, DictionaryObject):
                if isinstance(value, StreamObject) and str(value.get("/" + "Type", "")) == "/" + "Metadata":
                    data = value.get_data()
                    encoding, _ = text_encoding(data[:65536], "metadata.xml")
                    findings.extend(scan_text(data.decode(encoding or "utf-8", errors="replace"), name, scope="PDF XMP metadata", location="PDF metadata/object", file_sha256=file_sha256))
                if isinstance(value, StreamObject) and str(value.get("/" + "Type", "")) == "/" + "EmbeddedFile":
                    findings.append(finding(name, "PDF embedded attachment", "embedded attachment requires separate privacy review", file_sha256=file_sha256))
                for child_key, item in value.items():
                    walk(item, depth + 1, str(child_key), value)
            elif isinstance(value, ArrayObject):
                for item in value:
                    walk(item, depth + 1, key, parent)
        walk(reader.trailer)
    except Exception as exc:
        findings.append(finding(name, "PDF", "PDF privacy inspection failed: " + type(exc).__name__, file_sha256=file_sha256))
    return findings


def scan_stream(name: str, stream, *, file_sha256: str = "") -> list[dict]:
    stream.seek(0)
    prefix = stream.read(65536)
    stream.seek(0)
    if prefix.startswith(b"%PDF-") or PurePosixPath(name).suffix.lower() == ".pdf":
        return scan_pdf(stream, name, file_sha256)
    encoding, classification = text_encoding(prefix, name)
    if classification == "ambiguous Unicode encoding requires manual inspection":
        return [finding(name, "text decoding", classification, file_sha256=file_sha256)]
    if encoding is None:
        return []
    if classification in {"binary signature in declared text", "NUL bytes in declared text"}:
        return [finding(name, "text decoding", classification, file_sha256=file_sha256)]
    if PurePosixPath(name).suffix.lower() == ".py":
        # In valid Python, a Path division operator is executable syntax, not
        # a literal local pathname. Preserve checks on every string/comment and
        # every email match; malformed Python falls back to plain text scanning.
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        if size <= 16 * READ_SIZE:
            try:
                text = stream.read().decode(encoding)
                ast.parse(text)
                offsets, position = [0], 0
                for line in text.splitlines(keepends=True):
                    position += len(line)
                    offsets.append(position)
                spans = []
                for token in tokenize.generate_tokens(io.StringIO(text).readline):
                    if token.type in {tokenize.STRING, tokenize.COMMENT}:
                        spans.append((offsets[token.start[0] - 1] + token.start[1], offsets[token.end[0] - 1] + token.end[1]))
                found = scan_text(text, name, file_sha256=file_sha256)
                return [item for item in found if item["kind"] == "email address" or any(first <= item["source_offset_start"] and item["source_offset_end"] <= last for first, last in spans)]
            except (UnicodeError, SyntaxError, tokenize.TokenError, IndexError):
                stream.seek(0)
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    pending, offset, line_number, findings = "", 0, 1, []
    try:
        while True:
            chunk = stream.read(READ_SIZE)
            pending += decoder.decode(chunk, final=not chunk)
            cut = pending.rfind("\n") + 1
            if cut:
                complete, pending = pending[:cut], pending[cut:]
                findings.extend(scan_text(complete, name, file_sha256=file_sha256, base_offset=offset, start_line=line_number))
                line_number += len(complete.splitlines())
                offset += len(complete)
            if len(pending) > MAX_LINE_CHARS:
                findings.append(finding(name, str(line_number), "text line exceeds privacy inspection limit", file_sha256=file_sha256))
                return findings
            if not chunk:
                findings.extend(scan_text(pending, name, file_sha256=file_sha256, base_offset=offset, start_line=line_number))
                break
    except UnicodeError:
        findings.append(finding(name, str(line_number), "text decoding failed during privacy inspection", file_sha256=file_sha256))
    return findings


def scan_bytes(name: str, data: bytes) -> list[dict]:
    return scan_stream(name, io.BytesIO(data), file_sha256=hashlib.sha256(data).hexdigest())


def unsafe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name
            or bool(PureWindowsPath(name).drive) or any(ord(character) < 32 or ord(character) == 127 for character in name))


def scan_archive_set(paths: list[Path], *, expected_members: dict[str, set[str]] | None = None, inventory_out: dict | None = None) -> list[dict]:
    """Inspect every supplied ZIP part, including manifests and logical chunks.

    A missing part, malformed chunk map, duplicate/unexpected member, encrypted
    entry or uninspectable textual file is a finding, never a silent exemption.
    """
    findings, archives, infos, chunk_tables, stored_names = [], {}, {}, [], set()
    logical_inventory, manifest_rows, archive_info = {}, [], {}
    with ExitStack() as stack:
        for path in paths:
            if path.name in archives:
                findings.append(finding(path.name, "archive name", "duplicate archive basename", scope="archive metadata"))
                continue
            findings.extend(scan_text(path.name, path.name, scope="archive filename", location="archive filename"))
            try:
                archive = stack.enter_context(zipfile.ZipFile(path))
            except Exception as exc:
                findings.append(finding(path.name, "ZIP", "archive could not be read: " + type(exc).__name__, scope="archive metadata"))
                continue
            archives[path.name] = archive
            if path.stat().st_size >= 500_000_000:
                findings.append(finding(path.name, "ZIP", "archive is not below the exclusive size limit", scope="archive metadata"))
            try:
                bad = archive.testzip()
                if bad is not None:
                    findings.append(finding(bad, "ZIP CRC", "archive CRC failure", scope="archive metadata"))
            except Exception as exc:
                findings.append(finding(path.name, "ZIP CRC", "archive integrity check failed: " + type(exc).__name__, scope="archive metadata"))
            findings.extend(scan_text(archive.comment.decode("utf-8", errors="replace"), path.name, scope="ZIP comment", location="ZIP comment"))
            names = [item.filename for item in archive.infolist()]
            if len(names) != len(set(names)):
                findings.append(finding(path.name, "ZIP members", "duplicate stored member name", scope="archive metadata"))
            expected = expected_members.get(path.name) if expected_members is not None else None
            if expected_members is not None and expected is None:
                findings.append(finding(path.name, "ZIP members", "archive part was not expected", scope="archive metadata"))
            if expected is not None and set(names) != expected:
                findings.append(finding(path.name, "ZIP members", "stored member set differs from expected complete snapshot", scope="archive metadata"))
            for info in archive.infolist():
                name = info.filename
                if name in stored_names:
                    findings.append(finding(name, "ZIP members", "duplicate stored name across the archive set", scope="archive metadata"))
                stored_names.add(name)
                findings.extend(scan_text(name, name, scope="archive member name", location="member name"))
                if unsafe_member(name):
                    findings.append(finding(name, "member name", "unsafe archive member name", scope="archive metadata"))
                if info.flag_bits & 1:
                    findings.append(finding(name, "ZIP member", "encrypted member cannot be privacy-inspected", scope="archive metadata"))
                    continue
                findings.extend(scan_text(info.comment.decode("utf-8", errors="replace"), name, scope="ZIP member comment", location="member comment"))
                # Unicode path/comment extra fields can contain a second name.
                extra = info.extra
                while len(extra) >= 4:
                    identifier = int.from_bytes(extra[:2], "little")
                    size = int.from_bytes(extra[2:4], "little")
                    payload, extra = extra[4:4 + size], extra[4 + size:]
                    if len(payload) != size:
                        findings.append(finding(name, "ZIP extra field", "truncated ZIP extra field", scope="archive metadata"))
                        break
                    if identifier in {0x7075, 0x6375}:
                        findings.extend(scan_text(payload[5:].decode("utf-8", errors="replace"), name, scope="ZIP Unicode name/comment extra field", location="member extra field"))
                key = (path.name, name)
                infos[key] = info
                if info.is_dir():
                    continue
                if name == "CHUNKS.tsv":
                    try:
                        data = archive.read(info)
                        chunk_tables.append(list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t")))
                    except Exception as exc:
                        findings.append(finding(name, "chunk manifest", "chunk manifest could not be parsed: " + type(exc).__name__, scope="archive metadata"))
                if name in {"FILE_LIST.tsv", "ARCHIVE_INFO.tsv"}:
                    try:
                        table = list(csv.DictReader(io.StringIO(archive.read(info).decode("utf-8"), newline=""), delimiter="\t"))
                        if name == "FILE_LIST.tsv":
                            manifest_rows.extend(table)
                        else:
                            archive_info.update({row["key"]: row["value"] for row in table})
                    except Exception as exc:
                        findings.append(finding(name, "generated manifest", "manifest could not be parsed: " + type(exc).__name__, scope="archive metadata"))
                if name.startswith("__split__/"):
                    continue
                try:
                    with archive.open(info) as source, tempfile.SpooledTemporaryFile(max_size=8 * READ_SIZE) as logical:
                        digest = hashlib.sha256()
                        while True:
                            block = source.read(READ_SIZE)
                            if not block:
                                break
                            logical.write(block)
                            digest.update(block)
                        findings.extend(scan_stream(name, logical, file_sha256=digest.hexdigest()))
                        if name not in GENERATED_ARCHIVE_NAMES:
                            logical_inventory[name] = {"bytes": info.file_size, "sha256": digest.hexdigest()}
                except Exception as exc:
                    findings.append(finding(name, "ZIP member", "member privacy inspection failed: " + type(exc).__name__))
        if expected_members is not None and set(expected_members) != set(archives):
            findings.append(finding("archive set", "ZIP parts", "expected archive parts are missing or duplicated", scope="archive metadata"))
        grouped, used = {}, set()
        if len(chunk_tables) > 1:
            findings.append(finding("CHUNKS.tsv", "chunk manifest", "multiple chunk manifests are ambiguous", scope="archive metadata"))
        for table in chunk_tables:
            for row in table:
                if set(row) != {"path", "stored", "offset", "bytes", "sha256", "archive"} or any(value is None for value in row.values()):
                    findings.append(finding("CHUNKS.tsv", "chunk manifest", "malformed chunk mapping row", scope="archive metadata"))
                    continue
                name = row["path"]
                if unsafe_member(name):
                    findings.append(finding(name, "logical chunk name", "unsafe reconstructed member name", scope="archive metadata"))
                    continue
                grouped.setdefault(name, []).append(row)
        for name, chunks in grouped.items():
            findings.extend(scan_text(name, name, scope="reconstructed member name", location="logical name"))
            if name in stored_names:
                findings.append(finding(name, "reconstructed member", "logical file appears both whole and chunked", scope="archive metadata"))
            try:
                ordered = sorted(chunks, key=lambda row: int(row["offset"]))
                with tempfile.SpooledTemporaryFile(max_size=8 * READ_SIZE) as logical:
                    offset, whole = 0, hashlib.sha256()
                    for row in ordered:
                        key = (row["archive"], row["stored"])
                        if key in used or key not in infos or not row["stored"].startswith("__split__/") or int(row["offset"]) != offset or int(row["bytes"]) < 0:
                            raise ValueError("missing, duplicate or noncontiguous chunk")
                        used.add(key)
                        count, digest = 0, hashlib.sha256()
                        with archives[key[0]].open(infos[key]) as source:
                            while True:
                                block = source.read(READ_SIZE)
                                if not block:
                                    break
                                logical.write(block)
                                whole.update(block)
                                digest.update(block)
                                count += len(block)
                        if count != int(row["bytes"]) or digest.hexdigest() != row["sha256"]:
                            raise ValueError("chunk bytes or hash mismatch")
                        offset += count
                    findings.extend(scan_stream(name, logical, file_sha256=whole.hexdigest()))
                    logical_inventory[name] = {"bytes": offset, "sha256": whole.hexdigest()}
            except Exception as exc:
                findings.append(finding(name, "reconstructed member", "chunk reconstruction or privacy inspection failed: " + type(exc).__name__))
        unbound = {key for key in infos if key[1].startswith("__split__/")} - used
        if unbound:
            findings.append(finding("archive set", "chunk manifest", "stored chunks are absent from the verified logical-file map", scope="archive metadata"))
    if inventory_out is not None:
        inventory_out.update({"files": logical_inventory, "file_list_rows": manifest_rows, "archive_info": archive_info,
                              "generated_names": sorted(stored_names & GENERATED_ARCHIVE_NAMES)})
    return findings
