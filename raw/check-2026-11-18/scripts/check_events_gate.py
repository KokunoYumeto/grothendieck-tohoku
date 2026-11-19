"""Mechanical FINAL checks over exact CHECK_EVENTS and approved-policy bytes.

This adapter reads no file during evaluation and emits no event prose. It reuses
the inventory's strict TSV parser and lexical reference rules. A refutation row
is selected only by exact equality of its type cell to REFUTATION_TYPE. The
historical inventory's case-insensitive marker search is deliberately not used.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from check_events_inventory import (
    EVENT_FIELDS, ID_LEFT, ID_RIGHT, REFERENCE_RULES, find_references, parse_events,
)
from control_word_inventory import BLOCKED_DIRS, read_snapshot

EVENT_TABLE_PATH = "CHECK_EVENTS.tsv"
EVENT_POLICY_PATH = "validation-policy/check-events-policy.json"
EVENT_INPUT_NAMES = frozenset({EVENT_TABLE_PATH, EVENT_POLICY_PATH})
EVENT_CHECK_NAMES = (
    "check-events-schema",
    "check-events-tsv",
    "check-events-required-fields",
    "check-events-exact-duplicates",
    "check-events-literal-types",
    "check-events-refutation-id-bindings",
    "check-events-reference-presence-policy",
    "check-events-policy-approved",
)
ALLOWED_EVENT_TYPES = (
    "targeted proof check",
    "independent re-proof",
    "computation or formal certificate",
    "used and rechecked in this run",
    "carried as background without fault found",
    "refuted, with the refined statement's id",
)
REFUTATION_TYPE = ALLOWED_EVENT_TYPES[-1]
EXPLICIT_ID_RULE = "explicit statement-ID introducer"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate policy key.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON constant in policy.")


def _load_policy(data: bytes) -> dict:
    """Require the approved literal contract; accept no permissive defaults."""
    policy = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant)
    if not isinstance(policy, dict):
        raise ValueError("Policy must be an object.")
    allowed = policy.get("allowed_event_types")
    if (not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed)
            or len(allowed) != len(ALLOWED_EVENT_TYPES) or set(allowed) != set(ALLOWED_EVENT_TYPES)):
        raise ValueError("Policy must name the six exact approved event types.")
    exact = {
        "required_fields": EVENT_FIELDS,
        "refutation_marker_fields": ["type"],
        "refutation_marker_pattern": "^" + REFUTATION_TYPE + "$",
        "reference_fields": ["outcome"],
        "identifier_rules": REFERENCE_RULES,
        "exact_declared_id_left_boundary": ID_LEFT,
        "exact_declared_id_right_boundary": ID_RIGHT,
        "catalog_basis": "exact CHECK_EVENTS.statement_id values; no external catalogue implied",
        "duplicate_policy": "block exact parsed-value duplicates for manual resolution",
    }
    if any(policy.get(name) != value for name, value in exact.items()):
        raise ValueError("Policy differs from the approved mechanical contract.")
    for name in ("approved", "reference_rules_reviewed", "include_exact_declared_id_mentions",
                 "require_reference_in_marker_rows"):
        if policy.get(name) is not True:
            raise ValueError("Policy approval and reference requirements must be explicit true values.")
    return policy


def _binding_detail(events: bytes | None, policy: bytes | None) -> str:
    def digest(data: bytes | None) -> str:
        return hashlib.sha256(data).hexdigest() if data is not None else "missing"
    return ("CHECK_EVENTS_sha256=" + digest(events) + "; policy_sha256=" + digest(policy)
            + "; exact canonical type equality; no semantic or completeness judgment.")


def _fail_all(detail: str, events: bytes | None, policy: bytes | None) -> list[dict]:
    return [{"check": name, "status": "fail", "detail": detail + (
        " " + _binding_detail(events, policy) if name == "check-events-policy-approved" else "")}
        for name in EVENT_CHECK_NAMES]


def _references(outcome: str, catalog: dict[str, list[int]], policy: dict) -> list[dict]:
    found = find_references(outcome, catalog, policy)
    # Tokens introduced with an actual ID word must bind even without the digit
    # and punctuation shape used to screen ambiguous lexical candidates. The
    # broader "refined statement:" form keeps the approved shape filter.
    # Use the approved introducer expression verbatim, preserving every capture.
    rule = next(rule for rule in policy["identifier_rules"] if rule["name"] == EXPLICIT_ID_RULE)
    seen = {(item["start"], item["end"], item["reference"]) for item in found}
    for match in re.finditer(rule["pattern"], outcome, re.IGNORECASE):
        if re.search(r"\bid\b", outcome[match.start():match.start("id")], re.IGNORECASE) is None:
            continue
        first, last = match.span("id")
        value = match.group("id")
        if (first, last, value) not in seen:
            found.append({"reference": value, "start": first, "end": last, "rule": EXPLICIT_ID_RULE})
            seen.add((first, last, value))
    return found


def evaluate_event_snapshot(events: bytes | None, policy_data: bytes | None) -> list[dict]:
    """Return all eight fixed checks, failing closed on unavailable inputs.

    Values are never normalized. Output contains only fixed descriptions,
    counts and input hashes. Required-field presence is not an adequacy check.
    """
    if events is None or policy_data is None:
        return _fail_all("Both the event table and explicit approved policy are required.", events, policy_data)
    try:
        policy = _load_policy(policy_data)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return _fail_all("The supplied policy is malformed, unapproved or outside the exact approved contract.", events, policy_data)
    parsed = parse_events(events)
    rows = parsed["rows"]
    schema_ok = parsed["header"] == EVENT_FIELDS
    tsv_ok = bool(parsed["parse_complete"] and not parsed["malformed"] and rows)
    complete = schema_ok and tsv_ok
    missing = sum(row["values"][field] is None or not row["values"][field].strip()
                  for row in rows for field in EVENT_FIELDS)
    duplicates = sum(count > 1 for count in Counter(tuple(row["cells"]) for row in rows).values())
    unapproved = len({row["values"]["type"] for row in rows
                      if row["values"]["type"] not in ALLOWED_EVENT_TYPES})
    catalog = defaultdict(list)
    for row in rows:
        value = row["values"]["statement_id"]
        if value is not None and value.strip():
            catalog[value].append(row["event_record"])
    selected = [row for row in rows if row["values"]["type"] == REFUTATION_TYPE]
    unbound, without_reference, occurrences = 0, 0, 0
    for row in selected:
        refs = _references(row["values"]["outcome"] or "", catalog, policy)
        occurrences += len(refs)
        without_reference += not refs
        unbound += sum(item["reference"] not in catalog for item in refs)
    results = (
        (schema_ok, "Exact five-column header order is required."),
        (tsv_ok, f"Strict complete TSV with at least one event; malformed records or parse errors: {len(parsed['malformed'])}."),
        (complete and missing == 0, f"Missing or blank required cells: {missing}; parsed values are not normalized."),
        (complete and duplicates == 0, f"Exact parsed-value duplicate groups: {duplicates}; repeated IDs or dates alone are permitted."),
        (complete and unapproved == 0, f"Distinct literal types outside the six approved values: {unapproved}."),
        (complete and unbound == 0, f"Exact-type selected rows: {len(selected)}; reference occurrences: {occurrences}; unmatched literal catalog references: {unbound}. Tokens introduced with an explicit ID word also require binding."),
        (complete and without_reference == 0, f"Exact-type selected rows without an extracted reference: {without_reference}; every selected row requires a reference."),
        (True, "Approved exact policy contract. " + _binding_detail(events, policy_data)),
    )
    return [{"check": name, "status": "pass" if passed else "fail", "detail": detail}
            for name, (passed, detail) in zip(EVENT_CHECK_NAMES, results)]


def read_event_input(root: Path, name: str) -> bytes | None:
    """Read only one fixed input, refusing symlinks and protected directories."""
    if name not in EVENT_INPUT_NAMES:
        raise ValueError("Only the fixed event table and policy paths are permitted.")
    if root.is_symlink() or any(part.casefold() in BLOCKED_DIRS for part in root.parts):
        raise RuntimeError("The event-input root is not permitted.")
    path = root
    for part in Path(name).parts:
        path = path / part
        if path.is_symlink():
            raise RuntimeError("A fixed event input or its directory is a symlink.")
    if not path.exists():
        return None
    if not path.is_file():
        raise RuntimeError("A fixed event input is not a regular file.")
    before = path.stat()
    data = read_snapshot(path)
    after = path.stat()
    if path.is_symlink() or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError("An event input changed while being read; rerun validation.")
    return data


def recheck_event_inputs(root: Path, captured: dict[str, bytes | None]) -> None:
    """Bind validation to the same two byte snapshots used in its inventory."""
    if set(captured) != EVENT_INPUT_NAMES:
        raise RuntimeError("The event-input snapshot is incomplete.")
    for name in sorted(EVENT_INPUT_NAMES):
        if read_event_input(root, name) != captured[name]:
            raise RuntimeError("An event table or policy changed during validation; rerun validation.")
