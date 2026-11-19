"""Package complete hourly checkpoints or the final delivery archive.

Creation is separate from persistence: the caller must save every resulting
ZIP successfully, then name its first part as --previous on the next run.
No source text is transformed. Archive members use delivery-relative names.
Final packaging additionally requires current successful validation and scans
every completed ZIP part before installation. Hourly checkpoint gates remain
independent of final validation.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

MAX_BYTES = 500_000_000             # Strict decimal limit, below 512 MiB.
CHUNK_BYTES = 480_000_000           # Leaves room for ZIP and manifest overhead.
BUFFER_BYTES = 1024 * 1024
EXCLUDED_DIRS = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cache", "input", "upload", "tmp", "scratch", "scans", "renders",
    "rendered", "tex-runtime", "checkpoints", "__split__",
}
IMAGE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif", ".ppm", ".pgm",
}
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".7z")
TEX_CACHE_SUFFIXES = (
    ".aux", ".toc", ".out", ".log", ".fls", ".fdb_latexmk",
    ".synctex.gz", ".nav", ".snm", ".vrb",
)


@dataclass
class Member:
    path: Path
    relative: str
    size: int
    mtime_ns: int


@dataclass
class Piece:
    member: Member
    stored: str
    offset: int
    size: int
    part: int = 0
    sha256: str = ""


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_parse(value: str) -> datetime:
    value = value.strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("An explicit UTC timezone is required.")
    return result.astimezone(timezone.utc)


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Unsafe archive-relative member name.")
    return path


def exclusion(relative: str) -> str | None:
    path = PurePosixPath(relative)
    name = path.name.lower()
    if any(part in EXCLUDED_DIRS for part in path.parts[:-1]):
        return "cache, input, render, runtime or earlier-checkpoint directory"
    if name == ".ds_store" or name.endswith((".pyc", ".pyo", ".bak", "~")):
        return "cache or backup"
    if name.endswith(ARCHIVE_SUFFIXES):
        return "archive; earlier archives are never nested"
    if name in {"tohoku_part_i_printed_pp119-183.pdf", "tohoku_part_ii_printed_pp185-221.pdf"}:
        return "attached original scan"
    if path.suffix.lower() in IMAGE_SUFFIXES and path.parts[0] != "problem-images":
        return "rendered image outside explicit problem-images folder"
    if path.parts[0] == "sources" and name.endswith(TEX_CACHE_SUFFIXES):
        return "generated TeX auxiliary or unsanitized build log"
    if len(path.parts) == 2 and path.parts[0] == "sources" and name.startswith("main-") and name.endswith(".pdf"):
        return "duplicate build PDF; delivery PDFs belong in pdf"
    return None


def inventory(root: Path) -> tuple[list[Member], list[tuple[str, int, str]]]:
    included, excluded = [], []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative in {"FILE_LIST.tsv", "CHECKPOINT_INFO.tsv", "ARCHIVE_INFO.tsv", "CHUNKS.tsv"}:
            # Metadata extracted during a restoration is regenerated below;
            # manifests are not recursively included as source deliverables.
            continue
        if path.is_symlink():
            excluded.append((relative, 0, "symbolic link; no external target included"))
            continue
        if not path.is_file():
            continue
        stat = path.stat()
        reason = exclusion(relative)
        if reason:
            excluded.append((relative, stat.st_size, reason))
        else:
            safe_relative(relative)
            included.append(Member(path, relative, stat.st_size, stat.st_mtime_ns))
    return included, excluded


def tsv(fields: list[str], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _report_table(data: bytes, required: set[str]) -> list[dict]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t")
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not required.issubset(fields):
        raise RuntimeError("A generated validation report has an unexpected TSV schema.")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise RuntimeError("A generated validation report contains a malformed TSV row.")
    return rows


def _member_snapshot(member: Member, retain_bytes: bool = False) -> tuple[str, bytes | None]:
    before = member.path.stat()
    if member.path.is_symlink() or (before.st_size, before.st_mtime_ns) != (member.size, member.mtime_ns):
        raise RuntimeError("A deliverable changed before the validation preflight; rerun validation.")
    digest = hashlib.sha256()
    payload = bytearray() if retain_bytes else None
    with member.path.open("rb") as stream:
        for block in iter(lambda: stream.read(BUFFER_BYTES), b""):
            digest.update(block)
            if payload is not None:
                payload.extend(block)
    after = member.path.stat()
    if member.path.is_symlink() or (after.st_size, after.st_mtime_ns) != (member.size, member.mtime_ns):
        raise RuntimeError("A deliverable changed during the validation preflight; rerun validation.")
    return digest.hexdigest(), bytes(payload) if payload is not None else None


def require_final_deliverables(root: Path) -> None:
    required = ["CORRECTIONS.tsv", "CHECK_RECORD.md", "CHECK_EVENTS.tsv", "NOTES.md", "PDF_CHECK.md", "README.md", "progress.log"]
    required += [f"sources/main-{layer}.tex" for layer in ("dip", "fr", "en")]
    required += [f"pdf/main-{layer}.pdf" for layer in ("dip", "fr", "en")]
    missing = [name for name in required if not (root / name).is_file() or (root / name).stat().st_size == 0]
    if missing:
        raise RuntimeError("Final packaging requires all final deliverables; missing: " + ", ".join(missing))
    pages = [int(value) for value in re.findall(r"(?m)^page (\d{3}) done\s", (root / "progress.log").read_text(encoding="utf-8"))]
    expected = list(range(119, 184)) + list(range(185, 222))
    if pages != expected:
        raise RuntimeError("Final packaging requires all 102 ordered page-completion entries.")


def validation_preflight(root: Path, members: list[Member], excluded: list[tuple[str, int, str]]) -> dict[str, str]:
    """Bind final packaging to successful reports and an unchanged inventory.

    Only the exact generated root report names are exempt from their own stale
    inventory comparison. They are still required, scanned, hashed and packaged.
    This function reads current files but writes no report or archive.
    """
    from privacy_guard import VALIDATION_REPORT_NAMES, privacy_findings, safe_location, scan_bytes
    from check_events_gate import (EVENT_CHECK_NAMES, EVENT_INPUT_NAMES, EVENT_POLICY_PATH,
                                   EVENT_TABLE_PATH, evaluate_event_snapshot, recheck_event_inputs)

    report_names = set(VALIDATION_REPORT_NAMES)
    indexed = {member.relative: member for member in members}
    if len(indexed) != len(members):
        raise RuntimeError("The current delivery inventory contains duplicate member names.")
    if any(name not in indexed or indexed[name].size == 0 for name in report_names):
        raise RuntimeError("Final packaging requires every generated validation report, nonempty and included.")
    if not EVENT_INPUT_NAMES.issubset(indexed):
        raise RuntimeError("Final packaging requires the event table and its explicit approved policy in the current inventory.")
    if any(privacy_findings(member.relative) for member in members):
        raise RuntimeError("An included member name contains a possible private path or email address.")
    if any(privacy_findings(safe_location(relative)) for relative, _, _ in excluded):
        raise RuntimeError("An excluded-file locator could not be made privacy-safe for the manifest.")

    hashes, reports = {}, {}
    for name in sorted(report_names):
        hashes[name], data = _member_snapshot(indexed[name], retain_bytes=True)
        reports[name] = data
        findings = scan_bytes(name, data)
        if findings:
            raise RuntimeError(f"Generated validation reports contain {len(findings)} privacy findings; rerun validation after review.")

    checks = _report_table(reports["FINAL_VALIDATION_CHECKS.tsv"], {"check", "status", "detail"})
    check_names = [row["check"] for row in checks]
    if not checks or any(not name for name in check_names) or len(check_names) != len(set(check_names)):
        raise RuntimeError("Final validation checks must be nonempty and uniquely named.")
    if any(row["status"] != "pass" for row in checks):
        raise RuntimeError("Final packaging requires every recorded final-validation check to pass.")
    required_checks = {
        "privacy", "privacy-source-credit-conflicts",
        "explicit-second-reading-confidence", "unique-second-reading-identifiers",
    }
    required_checks.update(EVENT_CHECK_NAMES)
    if not required_checks.issubset(check_names):
        raise RuntimeError("Final validation must include passing privacy, protected-source-conflict, explicit second-reading confidence, unique review-identifier and all eight mechanical event checks.")

    rows = _report_table(reports["FINAL_VALIDATION_INVENTORY.tsv"], {"file", "bytes", "sha256", "status"})
    recorded, included_names = {}, set()
    for row in rows:
        if row["status"] != "included":
            if not row["status"].startswith("excluded:"):
                raise RuntimeError("The validation inventory contains an unrecognized inclusion status.")
            continue
        name = row["file"]
        if not name or name in included_names or safe_relative(name).as_posix() != name:
            raise RuntimeError("The validation inventory contains a duplicate or invalid included filename.")
        included_names.add(name)
        if name in report_names:
            continue
        if not re.fullmatch(r"\d+", row["bytes"]) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise RuntimeError("The validation inventory contains an invalid size or SHA-256 digest.")
        recorded[name] = (int(row["bytes"]), row["sha256"])
    expected_names = set(indexed) - report_names
    if set(recorded) != expected_names:
        raise RuntimeError("The current included-file set differs from the validation inventory; rerun validation.")
    event_inputs = {name: None for name in EVENT_INPUT_NAMES}
    for name in sorted(expected_names):
        hashes[name], data = _member_snapshot(indexed[name], retain_bytes=name in EVENT_INPUT_NAMES)
        if name in EVENT_INPUT_NAMES:
            event_inputs[name] = data
    if any(recorded[name] != (indexed[name].size, hashes[name]) for name in expected_names):
        raise RuntimeError("Current deliverable sizes or hashes differ from the validation inventory; rerun validation.")
    event_checks = evaluate_event_snapshot(event_inputs[EVENT_TABLE_PATH], event_inputs[EVENT_POLICY_PATH])
    if any(item["status"] != "pass" for item in event_checks):
        raise RuntimeError("Current event-table and policy snapshots do not pass all eight mechanical event checks.")
    recheck_event_inputs(root, event_inputs)
    return hashes


def preflight(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if not root.is_dir():
        raise RuntimeError("The delivery root does not exist.")
    members, excluded = inventory(root)
    require_final_deliverables(root)
    hashes = validation_preflight(root, members, excluded)
    print(json.dumps({
        "kind": "final-preflight", "validation": "passed",
        "included_files": len(members), "excluded_files": len(excluded),
        "hashed_files": len(hashes), "uncompressed_bytes": sum(member.size for member in members),
        "archives_created": 0,
    }, indent=2))


def previous_record(path: Path | None) -> tuple[dict, dict]:
    if path is None:
        return {}, {}
    with zipfile.ZipFile(path) as archive:
        info_rows = list(csv.DictReader(io.StringIO(archive.read("CHECKPOINT_INFO.tsv").decode()), delimiter="\t"))
        file_rows = list(csv.DictReader(io.StringIO(archive.read("FILE_LIST.tsv").decode()), delimiter="\t"))
    info = {row["key"]: row["value"] for row in info_rows}
    files = {row["path"]: row for row in file_rows if row["status"] == "included"}
    return info, files


def plan(members: list[Member]) -> list[list[Piece]]:
    pieces = []
    for index, member in enumerate(members, 1):
        count = max(1, math.ceil(member.size / CHUNK_BYTES))
        for segment in range(count):
            offset = segment * CHUNK_BYTES
            size = min(CHUNK_BYTES, member.size - offset)
            stored = member.relative if count == 1 else f"__split__/{index:08d}.part{segment + 1:04d}"
            pieces.append(Piece(member, stored, offset, size))
    # Conservative allowance for manifest rows and ZIP metadata. The actual
    # completed ZIP size is also checked before any final archive is installed.
    reserve = 1_000_000 + sum(2048 + 8 * len(p.stored.encode()) for p in pieces)
    if reserve >= MAX_BYTES // 4:
        raise RuntimeError("Manifest is unexpectedly large; review this inventory.")
    groups, group, used = [], [], reserve
    for piece in pieces:
        estimate = piece.size + math.ceil(piece.size / 16384) * 8 + 512 + 2 * len(piece.stored.encode())
        if group and used + estimate >= MAX_BYTES:
            groups.append(group)
            group, used = [], 1024
        if used + estimate >= MAX_BYTES:
            raise RuntimeError("A segment exceeds the conservative per-ZIP budget.")
        group.append(piece)
        piece.part = len(groups) + 1
        used += estimate
    if group:
        groups.append(group)
    return groups


def write_piece(archive: zipfile.ZipFile, piece: Piece, complete_hashes: dict) -> None:
    member = piece.member
    before = member.path.stat()
    if (before.st_size, before.st_mtime_ns) != (member.size, member.mtime_ns):
        raise RuntimeError(f"File changed during checkpoint: {member.relative}")
    digest = hashlib.sha256()
    whole = complete_hashes.setdefault(member.relative, hashlib.sha256())
    with member.path.open("rb") as source, archive.open(piece.stored, "w", force_zip64=True) as destination:
        source.seek(piece.offset)
        remaining = piece.size
        while remaining:
            block = source.read(min(BUFFER_BYTES, remaining))
            if not block:
                raise RuntimeError(f"File shortened during checkpoint: {member.relative}")
            digest.update(block)
            whole.update(block)
            destination.write(block)
            remaining -= len(block)
    after = member.path.stat()
    if (after.st_size, after.st_mtime_ns) != (member.size, member.mtime_ns):
        raise RuntimeError(f"File changed during checkpoint: {member.relative}")
    piece.sha256 = digest.hexdigest()


def create(args: argparse.Namespace) -> None:
    final = getattr(args, "action", "create") == "final"
    root = args.root.resolve()
    if not root.is_dir():
        raise RuntimeError("The delivery root does not exist.")
    destination = (args.destination or root.parent).resolve()
    if destination == root or root in destination.parents:
        raise RuntimeError("Delivery archives must be outside the delivery tree.")
    if not final and args.number < 1:
        raise RuntimeError("Checkpoint numbers start at 1.")
    previous_info, previous_files = previous_record(args.previous)
    if not final and args.number > 1 and not previous_info:
        raise RuntimeError("Supply --previous for the last successfully saved checkpoint.")
    if not final and previous_info and int(previous_info["number"]) + 1 != args.number:
        raise RuntimeError("Checkpoint numbering must increase by exactly one.")
    started = utc_parse(args.started_utc)
    due = None if final else started + timedelta(hours=args.number)
    if not final and previous_info:
        due = max(due, utc_parse(previous_info["created_utc"]) + timedelta(hours=1))
    now = datetime.now(timezone.utc)
    members, excluded = inventory(root)
    if not members:
        raise RuntimeError("The delivery tree contains no includable files.")
    groups = plan(members)
    prefix = "TOHOKU_CHECK" if final else f"TOHOKU_CHECK_checkpoint_{args.number:02d}"
    names = [prefix + ".zip"] if len(groups) == 1 else [f"{prefix}_part{i + 1}.zip" for i in range(len(groups))]
    summary = {
        "kind": "final" if final else "checkpoint",
        "number": args.number, "due_utc": utc_text(due) if due else "",
        "current_utc": utc_text(now), "due": now >= due if due else None,
        "included_files": len(members), "excluded_files": len(excluded),
        "uncompressed_bytes": sum(member.size for member in members),
        "archives": names,
    }
    if args.dry_run:
        # Inventory and stat only: no content hashing, no writes, no ZIPs.
        print(json.dumps(summary, indent=2))
        return
    if due is not None and now < due:
        raise RuntimeError("The next hourly checkpoint is not due until " + utc_text(due))
    preflight_hashes = None
    if final:
        require_final_deliverables(root)
        preflight_hashes = validation_preflight(root, members, excluded)
        summary["validation_preflight"] = "passed"
        existing = [path for path in destination.glob("TOHOKU_CHECK*.zip") if re.fullmatch(r"TOHOKU_CHECK(?:_part\d+)?\.zip", path.name)]
    else:
        existing = list(destination.glob(prefix + "*.zip"))
    if existing:
        raise RuntimeError("A ZIP with this delivery name already exists; it will not be overwritten.")
    from privacy_guard import safe_location

    destination.mkdir(parents=True, exist_ok=True)
    whole_hashes = {}
    pieces = [piece for group in groups for piece in group]
    with tempfile.TemporaryDirectory(prefix="checkpoint-package-", dir=destination) as temporary:
        temporary = Path(temporary)
        for name, group in zip(names, groups):
            with zipfile.ZipFile(temporary / name, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
                for piece in group:
                    write_piece(archive, piece, whole_hashes)
        if final and {name: digest.hexdigest() for name, digest in whole_hashes.items()} != preflight_hashes:
            raise RuntimeError("Packaged bytes differ from the final-validation preflight snapshot; no final ZIP was installed.")
        rows = []
        for member in members:
            digest = whole_hashes[member.relative].hexdigest()
            relevant = [piece for piece in pieces if piece.member is member]
            prior = previous_files.get(member.relative, {})
            unchanged = prior.get("sha256") == digest
            rows.append({
                "path": member.relative, "bytes": member.size,
                "sha256": digest, "status": "included",
                "archives": ";".join(dict.fromkeys(names[piece.part - 1] for piece in relevant)),
                "unchanged_reference": safe_location(prior.get("archives", "")) if unchanged else "",
                "reason": "complete current deliverable; included even when unchanged",
            })
        for relative, size, reason in excluded:
            rows.append({
                "path": safe_location(relative), "bytes": size, "sha256": "",
                "status": "excluded", "archives": "", "unchanged_reference": "",
                "reason": reason,
            })
        info = {
            "kind": "final" if final else "checkpoint",
            "number": "" if final else str(args.number), "created_utc": utc_text(now),
            "started_utc": utc_text(started), "due_utc": utc_text(due) if due else "",
            "previous_successfully_saved_checkpoint": safe_location(args.previous.name) if args.previous else "",
            "snapshot_policy": "complete deliverables; no unchanged deliverable omitted",
            "archive_count": str(len(names)), "size_limit_bytes_exclusive": str(MAX_BYTES),
            "verification": "ZIP CRC and manifest SHA-256 checked after writing",
        }
        with zipfile.ZipFile(temporary / names[0], "a", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as first:
            first.writestr("FILE_LIST.tsv", tsv(["path", "bytes", "sha256", "status", "archives", "unchanged_reference", "reason"], rows))
            info_name = "ARCHIVE_INFO.tsv" if final else "CHECKPOINT_INFO.tsv"
            first.writestr(info_name, tsv(["key", "value"], [{"key": key, "value": value} for key, value in info.items()]))
            split = [piece for piece in pieces if piece.stored.startswith("__split__/")]
            if split:
                first.writestr("CHUNKS.tsv", tsv(["path", "stored", "offset", "bytes", "sha256", "archive"], [
                    {"path": piece.member.relative, "stored": piece.stored, "offset": piece.offset,
                     "bytes": piece.size, "sha256": piece.sha256, "archive": names[piece.part - 1]}
                    for piece in split
                ]))
        for index, name in enumerate(names, 1):
            path = temporary / name
            if path.stat().st_size >= MAX_BYTES:
                raise RuntimeError("Archive exceeds the strict 500 MB limit: " + name)
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("ZIP integrity verification failed: " + name)
                for piece in groups[index - 1]:
                    digest = hashlib.sha256()
                    with archive.open(piece.stored) as stream:
                        for block in iter(lambda: stream.read(BUFFER_BYTES), b""):
                            digest.update(block)
                    if digest.hexdigest() != piece.sha256:
                        raise RuntimeError("Archive content hash mismatch: " + piece.member.relative)
        if final:
            from privacy_guard import scan_archive_set

            expected_members = {name: {piece.stored for piece in group} for name, group in zip(names, groups)}
            expected_members[names[0]].update({"FILE_LIST.tsv", info_name})
            if split:
                expected_members[names[0]].add("CHUNKS.tsv")
            findings = scan_archive_set([temporary / name for name in names], expected_members=expected_members)
            if findings:
                raise RuntimeError(f"Final archive privacy scan found {len(findings)} findings; no final ZIP was installed. " + json.dumps(findings, ensure_ascii=False))
            summary["archive_privacy_scan"] = "passed"
        # Install only completed, verified files, using exclusive creation.
        # Earlier checkpoint ZIPs are never overwritten, renamed or deleted.
        for name in names:
            os.link(temporary / name, destination / name)
        summary["archive_bytes"] = {name: (destination / name).stat().st_size for name in names}
    print(json.dumps(summary, indent=2))


def restore_chunks(args: argparse.Namespace) -> None:
    root = args.directory.resolve()
    with (root / "CHUNKS.tsv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    grouped = {}
    for row in rows:
        grouped.setdefault(row["path"], []).append(row)
    for relative, chunks in grouped.items():
        destination = root.joinpath(*safe_relative(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            offset = 0
            for chunk in sorted(chunks, key=lambda item: int(item["offset"])):
                if int(chunk["offset"]) != offset:
                    raise RuntimeError("Non-contiguous chunks for " + relative)
                source = root.joinpath(*safe_relative(chunk["stored"]).parts)
                digest, count = hashlib.sha256(), 0
                with source.open("rb") as stream:
                    for block in iter(lambda: stream.read(BUFFER_BYTES), b""):
                        output.write(block)
                        digest.update(block)
                        count += len(block)
                if count != int(chunk["bytes"]) or digest.hexdigest() != chunk["sha256"]:
                    raise RuntimeError("Chunk verification failed for " + relative)
                offset += count
        print("Restored", relative)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    pack = subparsers.add_parser("create", help="Create an hourly checkpoint, never an early or duplicate one")
    pack.add_argument("--number", type=int, required=True)
    final = subparsers.add_parser("final", help="Create TOHOKU_CHECK.zip after completion; final delivery is not an hourly checkpoint")
    final.set_defaults(number=None)
    for command in (pack, final):
        command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
        command.add_argument("--destination", type=Path, help="Output directory outside the delivery tree")
        command.add_argument("--previous", type=Path, help="First ZIP of the last checkpoint whose persistence succeeded")
        command.add_argument("--started-utc", default="2026-11-18T12:30:14Z")
        command.add_argument("--dry-run", action="store_true", help="List metadata only; never hash, write or create a ZIP")
    check = subparsers.add_parser("preflight", help="Verify final prerequisites and current successful validation without creating an archive")
    check.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    restore = subparsers.add_parser("restore-chunks", help="Reassemble oversized files after extracting all ZIP parts")
    restore.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.action in {"create", "final"}:
        create(args)
    elif args.action == "preflight":
        preflight(args)
    else:
        restore_chunks(args)


if __name__ == "__main__":
    main()
