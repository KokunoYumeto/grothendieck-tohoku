"""A ledger workbench for explicit, human-supplied second-reading decisions.

No image, source-page file or research context is opened. No decision is
inferred. CORRECTIONS.tsv is read only; exports always go to a separate file.
Stable IDs, original rows and append-only review events live in a sidecar tree.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from final_validate import privacy_findings

FIELDS = ["file", "layer", "printed_page", "line", "statement", "old", "new", "evidence", "kind", "confidence"]
PAGES = list(range(119, 184)) + list(range(185, 222))
PAGE_ORDER = {str(page): index for index, page in enumerate(PAGES)}
PAGE_ORDER[""] = len(PAGES)
REGISTRY_FIELDS = ["review_id", "initial_ledger_record", "registered_utc", "original_fingerprint"] + FIELDS
EVENT_FIELDS = [
    "event_id", "review_id", "utc", "reviewer", "outcome", "confidence",
    "review_evidence", "changes_json", "before_fingerprint", "after_fingerprint",
    "previous_event_hash", "event_hash",
]
INDEX_FIELDS = [
    "review_id", "printed_page", "file", "layer", "line", "statement", "kind",
    "ledger_record", "status", "confidence", "review_evidence", "last_event",
    "original_fingerprint", "reviewed_fingerprint", "current_ledger_fingerprint",
]
STATUS = {"confirm": "confirmed", "amend": "amended", "withdraw": "withdrawn"}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(row: dict) -> str:
    # Confidence is deliberately excluded: first-pass confidence never counts
    # as a second-reading event, and an exported confidence cannot change an ID.
    payload = {field: row[field] for field in FIELDS if field != "confidence"}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def event_hash(event: dict) -> str:
    payload = {field: event[field] for field in EVENT_FIELDS if field != "event_hash"}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def tsv_bytes(fields: list[str], rows: list[dict], header: bool = True) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
    if header:
        writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def read_table(path: Path, fields: list[str] | None = None) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if fields is not None and reader.fieldnames != fields:
            raise ValueError("Unexpected TSV schema in " + path.name)
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Malformed TSV row in " + path.name)
    return rows


def validate_row(row: dict) -> None:
    if set(row) != set(FIELDS) or not all(isinstance(row[field], str) for field in FIELDS):
        raise ValueError("A correction row must contain exactly the requested string-valued columns.")
    if row["printed_page"] not in PAGE_ORDER:
        raise ValueError("Printed page must be 119-183, 185-221, or blank for an unpaged build entry.")


def read_ledger(path: Path) -> tuple[list[dict], str]:
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("The correction ledger changed while being read; retry after that edit completes.")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t")
    if reader.fieldnames != FIELDS:
        raise ValueError("CORRECTIONS.tsv columns do not match the required schema.")
    rows = list(reader)
    for row in rows:
        validate_row(row)
    return rows, hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(prefix="review-write-", dir=path.parent, delete=False) as temporary:
        temporary.write(data)
        temporary.flush()
        os.fsync(temporary.fileno())
        name = Path(temporary.name)
    os.replace(name, path)


def append_bytes(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        view = memoryview(data)
        while view:
            count = os.write(descriptor, view)
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def history_lock(directory: Path, exclusive: bool = False):
    with (directory / "REVIEW_EVENTS.tsv").open("rb") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def project_paths(args) -> tuple[Path, Path, Path]:
    root = args.root.resolve()
    ledger = (root / args.ledger).resolve()
    directory = (root / args.review_dir).resolve()
    if ledger == root or root not in ledger.parents or directory == root or root not in directory.parents:
        raise ValueError("The ledger and review sidecar directory must be inside the delivery tree.")
    return root, ledger, directory


def load_project(directory: Path, ledger: Path) -> tuple[dict, list[dict], list[dict], dict]:
    metadata = {row["key"]: row["value"] for row in read_table(directory / "REVIEW_META.tsv", ["key", "value"])}
    if metadata["ledger_name"] != ledger.name:
        raise ValueError("This review sidecar was initialized for a differently named ledger.")
    registry = read_table(directory / "ROW_REGISTRY.tsv", REGISTRY_FIELDS)
    events = read_table(directory / "REVIEW_EVENTS.tsv", EVENT_FIELDS)
    states = {}
    for entry in registry:
        review_id = entry["review_id"]
        if not re.fullmatch(r"R\d{6,}", review_id) or review_id in states:
            raise ValueError("Invalid or repeated stable review ID.")
        row = {field: entry[field] for field in FIELDS}
        validate_row(row)
        original = fingerprint(row)
        if original != entry["original_fingerprint"]:
            raise ValueError("Original-row fingerprint mismatch for " + review_id)
        states[review_id] = {
            "row": row, "status": "pending", "confidence": "", "review_evidence": "",
            "last_event": "", "original_fingerprint": original,
            "known_fingerprints": {original}, "initial_ledger_record": entry["initial_ledger_record"],
        }
    prior_hash = ""
    for position, event in enumerate(events, 1):
        if event["event_id"] != f"E{position:06d}":
            raise ValueError("Review-event numbering is not continuous.")
        if event["previous_event_hash"] != prior_hash or event_hash(event) != event["event_hash"]:
            raise ValueError("Review-event history hash mismatch at " + event["event_id"])
        review_id = event["review_id"]
        if review_id not in states or event["outcome"] not in STATUS or event["confidence"] not in {"high", "medium", "low"}:
            raise ValueError("Invalid explicit review event " + event["event_id"])
        state = states[review_id]
        if fingerprint(state["row"]) != event["before_fingerprint"]:
            raise ValueError("Review-event input version mismatch for " + review_id)
        changes = json.loads(event["changes_json"])
        state["row"].update(changes)
        validate_row(state["row"])
        if fingerprint(state["row"]) != event["after_fingerprint"]:
            raise ValueError("Review-event output version mismatch for " + review_id)
        state["known_fingerprints"].add(event["after_fingerprint"])
        state.update(status=STATUS[event["outcome"]], confidence=event["confidence"], review_evidence=event["review_evidence"], last_event=event["event_id"])
        prior_hash = event["event_hash"]
    return metadata, registry, events, states


def previous_positions(directory: Path, states: dict) -> dict[int, str]:
    path = directory / "REVIEW_INDEX.tsv"
    if path.is_file():
        rows = read_table(path, INDEX_FIELDS)
        return {int(row["ledger_record"]): row["review_id"] for row in rows if row["ledger_record"] and row["review_id"] in states}
    return {int(state["initial_ledger_record"]): review_id for review_id, state in states.items()}


def align(rows: list[dict], states: dict, previous: dict[int, str], bindings: dict | None = None) -> tuple[dict[str, int], list[int]]:
    by_hash = defaultdict(set)
    for review_id, state in states.items():
        for value in state["known_fingerprints"]:
            by_hash[value].add(review_id)
    row_hashes = {position: fingerprint(row) for position, row in enumerate(rows, 1)}
    assignment, used_records = {}, set()
    for review_id, position in (bindings or {}).items():
        position = int(position)
        if review_id not in states or position not in row_hashes or row_hashes[position] not in states[review_id]["known_fingerprints"]:
            raise ValueError("An explicit ID/record binding does not match a recorded row version.")
        if position in used_records:
            raise ValueError("Two IDs cannot bind to the same ledger record.")
        assignment[review_id] = position
        used_records.add(position)
    for value, review_ids in by_hash.items():
        if len(review_ids) < 2:
            continue
        current_positions = {position for position, row_hash in row_hashes.items() if row_hash == value}
        old_positions = {position for position, review_id in previous.items()
                         if review_id in review_ids and row_hashes.get(position) == value}
        explicit_positions = {position for review_id, position in assignment.items() if review_id in review_ids and row_hashes[position] == value}
        if current_positions != old_positions and current_positions != explicit_positions:
            raise ValueError("Identical registered row versions changed positions; supply explicit stable-ID/record bindings. No duplicate identity is guessed.")
    for position, review_id in previous.items():
        if review_id not in assignment and position not in used_records and position in row_hashes and row_hashes[position] in states[review_id]["known_fingerprints"]:
            assignment[review_id] = position
            used_records.add(position)
    remaining = set(row_hashes) - used_records
    while True:
        progress = False
        for position in sorted(remaining):
            candidates = by_hash[row_hashes[position]] - set(assignment)
            if len(candidates) == 1:
                review_id = next(iter(candidates))
                assignment[review_id] = position
                remaining.remove(position)
                progress = True
        if not progress:
            break
    ambiguous = [position for position in remaining if by_hash[row_hashes[position]] - set(assignment)]
    if ambiguous:
        raise ValueError("Ambiguous duplicate-row alignment at ledger records " + ",".join(map(str, sorted(ambiguous))) + "; use sync --bindings with explicit stable-ID/record pairs.")
    missing = [review_id for review_id, state in states.items() if review_id not in assignment and state["status"] != "withdrawn"]
    if missing:
        raise ValueError("Active registered rows were removed or changed without a recorded amendment/withdrawal: " + ",".join(missing) + ". Record explicit decisions before resynchronizing.")
    return assignment, sorted(remaining)


def sorted_ids(states: dict, assignment: dict) -> list[str]:
    return sorted(states, key=lambda review_id: (PAGE_ORDER[states[review_id]["row"]["printed_page"]], assignment.get(review_id, 10**12), review_id))


def index_rows(rows: list[dict], states: dict, assignment: dict) -> list[dict]:
    result = []
    for review_id in sorted_ids(states, assignment):
        state, position = states[review_id], assignment.get(review_id)
        row = state["row"]
        result.append({
            "review_id": review_id, **{field: row[field] for field in ("printed_page", "file", "layer", "line", "statement", "kind")},
            "ledger_record": position or "", "status": state["status"],
            "confidence": state["confidence"], "review_evidence": state["review_evidence"], "last_event": state["last_event"],
            "original_fingerprint": state["original_fingerprint"], "reviewed_fingerprint": fingerprint(row),
            "current_ledger_fingerprint": fingerprint(rows[position - 1]) if position else "",
        })
    return result


def safe_note(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be supplied explicitly and be nonempty.")
    if privacy_findings(value):
        raise ValueError(label + " contains a possible absolute filesystem path or email address; use a scan/page locator and a nonprivate reviewer label.")
    return value


def initialize(args) -> None:
    root, ledger, directory = project_paths(args)
    if directory.exists():
        raise ValueError("The review directory already exists; use sync, never reinitialize or overwrite its history.")
    reviewer = safe_note(args.reviewer, "Reviewer")
    rows, ledger_hash = read_ledger(ledger)
    timestamp = utc()
    registry = []
    for position, row in enumerate(rows, 1):
        registry.append({"review_id": f"R{position:06d}", "initial_ledger_record": str(position), "registered_utc": timestamp, "original_fingerprint": fingerprint(row), **row})
    metadata = {"created_utc": timestamp, "ledger_name": ledger.name, "initial_ledger_sha256": ledger_hash, "default_reviewer": reviewer,
                "policy": "explicit per-row decisions only; no image reading inferred; correction ledger and TeX sources untouched"}
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="review-init-", dir=directory.parent) as temporary:
        prepared = Path(temporary) / "prepared"
        prepared.mkdir()
        (prepared / "ROW_REGISTRY.tsv").write_bytes(tsv_bytes(REGISTRY_FIELDS, registry))
        (prepared / "REVIEW_EVENTS.tsv").write_bytes(tsv_bytes(EVENT_FIELDS, []))
        (prepared / "REVIEW_META.tsv").write_bytes(tsv_bytes(["key", "value"], [{"key": key, "value": value} for key, value in metadata.items()]))
        _, _, _, states = load_project(prepared, ledger)
        assignment = {entry["review_id"]: int(entry["initial_ledger_record"]) for entry in registry}
        (prepared / "REVIEW_INDEX.tsv").write_bytes(tsv_bytes(INDEX_FIELDS, index_rows(rows, states, assignment)))
        os.rename(prepared, directory)
    print(f"Registered {len(rows)} stable IDs. Every row is pending; no review decision was inferred. CORRECTIONS.tsv is unchanged.")


def synchronize(args) -> None:
    _, ledger, directory = project_paths(args)
    bindings = json.loads(args.bindings.read_text(encoding="utf-8")) if args.bindings else None
    if bindings is not None and not isinstance(bindings, dict):
        raise ValueError("Bindings must be a JSON object mapping stable IDs to ledger-record numbers.")
    with history_lock(directory, exclusive=True):
        _, registry, _, states = load_project(directory, ledger)
        rows, _ = read_ledger(ledger)
        assignment, new_positions = align(rows, states, previous_positions(directory, states), bindings)
        next_id = max((int(review_id[1:]) for review_id in states), default=0) + 1
        additions = []
        for position in new_positions:
            row, review_id = rows[position - 1], f"R{next_id:06d}"
            next_id += 1
            additions.append({"review_id": review_id, "initial_ledger_record": str(position), "registered_utc": utc(), "original_fingerprint": fingerprint(row), **row})
            assignment[review_id] = position
        if additions:
            append_bytes(directory / "ROW_REGISTRY.tsv", tsv_bytes(REGISTRY_FIELDS, additions, header=False))
        _, _, _, states = load_project(directory, ledger)
        atomic_write(directory / "REVIEW_INDEX.tsv", tsv_bytes(INDEX_FIELDS, index_rows(rows, states, assignment)))
    print(f"Synchronized stable IDs; {len(additions)} newly registered rows are pending. No confidence or outcome was inferred.")


def decision_payloads(args) -> list[dict]:
    if args.batch:
        if any((args.review_id, args.outcome, args.confidence, args.evidence, args.changes)):
            raise ValueError("Use either a decision batch or individual decision flags.")
        payload = json.loads(args.batch.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or not payload:
            raise ValueError("A decision batch must be a nonempty JSON array of explicit per-row decisions.")
        return payload
    changes = json.loads(args.changes.read_text(encoding="utf-8")) if args.changes else {}
    return [{"review_id": args.review_id, "outcome": args.outcome, "confidence": args.confidence, "review_evidence": args.evidence, "changes": changes}]


def record_decisions(args) -> None:
    _, ledger, directory = project_paths(args)
    payloads = decision_payloads(args)
    bindings = json.loads(args.bindings.read_text(encoding="utf-8")) if args.bindings else None
    if bindings is not None and not isinstance(bindings, dict):
        raise ValueError("Bindings must be a JSON object mapping stable IDs to ledger-record numbers.")
    with history_lock(directory, exclusive=True):
        metadata, _, history, states = load_project(directory, ledger)
        rows, _ = read_ledger(ledger)
        reviewer_default = args.reviewer or metadata["default_reviewer"]
        additions, prior_hash = [], history[-1]["event_hash"] if history else ""
        for payload in payloads:
            if not isinstance(payload, dict) or set(payload) - {"review_id", "outcome", "confidence", "review_evidence", "reviewer", "changes"}:
                raise ValueError("Unexpected field in explicit decision payload.")
            review_id = payload.get("review_id")
            if review_id not in states:
                raise ValueError("An explicit registered review_id is required for every decision.")
            outcome, confidence = payload.get("outcome"), payload.get("confidence")
            if outcome not in STATUS or confidence not in {"high", "medium", "low"}:
                raise ValueError("Each decision must explicitly give confirm/amend/withdraw and high/medium/low.")
            evidence = safe_note(payload.get("review_evidence"), "Review evidence")
            reviewer = safe_note(payload.get("reviewer") or reviewer_default, "Reviewer")
            changes = payload.get("changes", {})
            if not isinstance(changes, dict) or set(changes) - (set(FIELDS) - {"confidence"}) or not all(isinstance(value, str) for value in changes.values()):
                raise ValueError("Amendments must be string-valued correction-field replacements, excluding confidence.")
            state = states[review_id]
            if outcome == "amend":
                if not changes or all(state["row"][field] == value for field, value in changes.items()):
                    raise ValueError("An amendment must explicitly change at least one correction field.")
            elif changes:
                raise ValueError("Only the amend outcome may contain correction-field changes.")
            before = fingerprint(state["row"])
            amended = {**state["row"], **changes}
            validate_row(amended)
            event = {
                "event_id": f"E{len(history) + len(additions) + 1:06d}", "review_id": review_id,
                "utc": utc(), "reviewer": reviewer, "outcome": outcome, "confidence": confidence,
                "review_evidence": evidence, "changes_json": canonical(changes),
                "before_fingerprint": before, "after_fingerprint": fingerprint(amended),
                "previous_event_hash": prior_hash,
            }
            event["event_hash"] = event_hash(event)
            additions.append(event)
            prior_hash = event["event_hash"]
            state["row"] = amended
            state["known_fingerprints"].add(event["after_fingerprint"])
            state.update(status=STATUS[outcome], confidence=confidence, review_evidence=evidence, last_event=event["event_id"])
        # Align only after applying the explicitly supplied decisions in memory.
        # This also permits an explicit amendment/withdrawal to document a ledger
        # edit the reviewer has already made. Unexplained edits still fail.
        assignment, unregistered = align(rows, states, previous_positions(directory, states), bindings)
        # Validate the entire batch before appending any event. Prior events and
        # original registry rows are never rewritten or deleted.
        append_bytes(directory / "REVIEW_EVENTS.tsv", tsv_bytes(EVENT_FIELDS, additions, header=False))
        atomic_write(directory / "REVIEW_INDEX.tsv", tsv_bytes(INDEX_FIELDS, index_rows(rows, states, assignment)))
    print(f"Recorded {len(additions)} explicit review events. CORRECTIONS.tsv and all TeX sources are unchanged by this command.")
    if unregistered:
        print(f"{len(unregistered)} unregistered ledger records remain pending; run sync to assign their stable IDs.")


def selected_page(value: str | None) -> str | None:
    if value is None:
        return None
    if value in {"build", "unpaged"}:
        return ""
    if value not in PAGE_ORDER or value == "":
        raise ValueError("Use a supplied printed page or build/unpaged.")
    return value


def report(args) -> None:
    _, ledger, directory = project_paths(args)
    with history_lock(directory):
        _, _, history, states = load_project(directory, ledger)
        rows, _ = read_ledger(ledger)
        assignment, unregistered = align(rows, states, previous_positions(directory, states))
        page = selected_page(getattr(args, "page", None))
        ids = sorted_ids(states, assignment)
        if page is not None:
            ids = [review_id for review_id in ids if states[review_id]["row"]["printed_page"] == page]
        if args.action == "status":
            groups = []
            for printed in list(map(str, PAGES)) + [""]:
                subset = [review_id for review_id in ids if states[review_id]["row"]["printed_page"] == printed]
                if subset:
                    groups.append({"printed_page": printed or "build/unpaged", **dict(Counter(states[review_id]["status"] for review_id in subset))})
            print(json.dumps({"totals": dict(Counter(states[review_id]["status"] for review_id in ids)), "unregistered_pending_records": unregistered, "groups": groups}, ensure_ascii=False, indent=2))
        elif args.action == "pending":
            selected = [entry for entry in index_rows(rows, states, assignment) if entry["status"] == "pending" and (page is None or entry["printed_page"] == page)]
            fields = ["review_id", "printed_page", "file", "layer", "line", "statement", "kind", "ledger_record", "status"]
            sys.stdout.write(tsv_bytes(fields, [{field: entry[field] for field in fields} for entry in selected]).decode())
            if unregistered:
                print("Unregistered pending ledger records; run sync: " + ",".join(map(str, unregistered)), file=sys.stderr)
        else:
            if args.action == "show":
                if args.review_id not in states:
                    raise ValueError("Unknown stable review ID.")
                ids = [args.review_id]
            elif args.pending_only:
                ids = [review_id for review_id in ids if states[review_id]["status"] == "pending"]
            output = []
            for review_id in ids:
                state = states[review_id]
                item = {"review_id": review_id, "ledger_record": assignment.get(review_id), "status": state["status"],
                        "review_confidence": state["confidence"], "review_evidence": state["review_evidence"], "correction": state["row"]}
                if args.action == "show":
                    item["history"] = [event for event in history if event["review_id"] == review_id]
                output.append(item)
            print(json.dumps(output, ensure_ascii=False, indent=2))


def export_reviewed(args) -> None:
    root, ledger, directory = project_paths(args)
    destination = (root / args.output).resolve()
    if destination == ledger or directory == destination or directory in destination.parents or root not in destination.parents:
        raise ValueError("Export must be a separate file inside the delivery tree, outside the review sidecar; it cannot overwrite CORRECTIONS.tsv.")
    if destination.suffix.lower() != ".tsv" or (root / "sources") in destination.parents or (root / "pdf") in destination.parents:
        raise ValueError("A reviewed export must be a TSV outside the source and PDF trees.")
    if destination.exists():
        raise ValueError("The export filename already exists; choose a new filename to preserve it.")
    with history_lock(directory):
        _, _, _, states = load_project(directory, ledger)
        rows, _ = read_ledger(ledger)
        assignment, unregistered = align(rows, states, previous_positions(directory, states))
        pending = [review_id for review_id, state in states.items() if state["status"] == "pending"]
        if pending or unregistered:
            raise ValueError(f"Export refused: {len(pending)} registered pending rows and {len(unregistered)} unregistered pending records remain.")
        output, mapping = [], []
        for review_id in sorted_ids(states, assignment):
            state = states[review_id]
            if state["status"] == "withdrawn" and args.withdrawn == "omit":
                mapping.append({"review_id": review_id, "export_record": "", "status": "withdrawn; omitted from active export", "last_event": state["last_event"], "row_fingerprint": fingerprint(state["row"])})
                continue
            row = dict(state["row"])
            if args.confidence_format == "annotated":
                row["confidence"] = f"{state['confidence']}; second reading {state['status']}; {review_id}; {state['last_event']}"
            else:
                row["confidence"] = state["confidence"]
            output.append(row)
            mapping.append({"review_id": review_id, "export_record": str(len(output)), "status": state["status"], "last_event": state["last_event"], "row_fingerprint": fingerprint(row)})
        map_path = destination.with_name(destination.stem + ".review-map.tsv")
        if map_path.exists():
            raise ValueError("The corresponding review-map export already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(tsv_bytes(FIELDS, output))
        with map_path.open("xb") as stream:
            stream.write(tsv_bytes(["review_id", "export_record", "status", "last_event", "row_fingerprint"], mapping))
    print(f"Exported {len(output)} reviewed rows with the original {len(FIELDS)} columns to {destination.name}. CORRECTIONS.tsv is unchanged. Source edits are not performed or verified by this workbench.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ledger", type=Path, default=Path("CORRECTIONS.tsv"))
    parser.add_argument("--review-dir", type=Path, default=Path("second-reading"))
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="Assign stable IDs; all imported rows start pending")
    init.add_argument("--reviewer", required=True)
    sync = commands.add_parser("sync", help="Register genuinely new rows and update positions; never infer a decision")
    sync.add_argument("--bindings", type=Path, help="Optional JSON stable-ID to ledger-record mapping for ambiguous duplicates")
    commands.add_parser("status", help="Report counts in printed order, with unpaged build entries last")
    pending = commands.add_parser("pending", help="Report every pending stable ID and any unregistered records")
    pending.add_argument("--page")
    page = commands.add_parser("page", help="Show registered correction data for one printed page; no images are opened")
    page.add_argument("--page", required=True)
    page.add_argument("--pending-only", action="store_true")
    show = commands.add_parser("show", help="Show one registered row and its complete prior event history")
    show.add_argument("--id", dest="review_id", required=True)
    decide = commands.add_parser("decide", help="Record explicit decisions, individually or as an explicit per-row batch")
    decide.add_argument("--id", dest="review_id")
    decide.add_argument("--outcome", choices=tuple(STATUS))
    decide.add_argument("--confidence", choices=("high", "medium", "low"))
    decide.add_argument("--evidence")
    decide.add_argument("--reviewer")
    decide.add_argument("--changes", type=Path, help="JSON file of explicitly supplied correction-field replacements for an amendment")
    decide.add_argument("--batch", type=Path, help="JSON array; every entry must specify an ID, outcome, confidence and review_evidence")
    decide.add_argument("--bindings", type=Path, help="Optional explicit stable-ID/record bindings if duplicate row versions make alignment ambiguous")
    export = commands.add_parser("export", help="Write a separate reviewed ledger copy; refuse while any row remains pending")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--withdrawn", choices=("omit", "retain"), required=True, help="Explicit choice: active ledger omits withdrawals; historical ledger may retain labeled rows")
    export.add_argument("--confidence-format", choices=("annotated", "plain"), default="annotated")
    args = parser.parse_args()
    if args.action == "init":
        initialize(args)
    elif args.action == "sync":
        synchronize(args)
    elif args.action == "decide":
        record_decisions(args)
    elif args.action == "export":
        export_reviewed(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
