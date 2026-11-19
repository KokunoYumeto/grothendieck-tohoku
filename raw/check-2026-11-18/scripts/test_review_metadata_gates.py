"""Exercise review-metadata gates using disposable synthetic fixtures only.

Run this file directly. It never locates or opens the edition's live ledger,
sources, review sidecar, scans, PDFs, build reports or research context.
"""

from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import checkpoint
import final_validate
from privacy_guard import VALIDATION_REPORT_NAMES
from refresh_check_record import load_rows
import second_reading


def row(confidence: str, number: int = 1) -> dict:
    result = dict.fromkeys(second_reading.FIELDS, "")
    result.update(
        file="sources/dip/p119.tex", layer="as-printed", printed_page="119",
        line=str(number), statement=f"synthetic fixture {number}", old="alpha",
        new="beta", evidence="Synthetic mechanical fixture; no scan reading.",
        kind="typesetting", confidence=confidence,
    )
    return result


def annotation(degree: str = "high", verdict: str = "confirmed",
               review_id: str = "R000001", event_id: str = "E000001") -> str:
    return f"{degree}; second reading {verdict}; {review_id}; {event_id}"


def write_tsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.write_bytes(second_reading.tsv_bytes(fields, rows))


def tree_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


class ReviewMetadataGates(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="review-metadata-fixture-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ledger(self, rows: list[dict]) -> None:
        write_tsv(self.root / "CORRECTIONS.tsv", second_reading.FIELDS, rows)

    def map_for(self, value: dict, *, status: str = "confirmed",
                event: str | None = "E000001", review_id: str = "R000001",
                fingerprint: str | None = None) -> Path:
        fields = ["review_id", "export_record", "status", "row_fingerprint"]
        entry = {"review_id": review_id, "export_record": "1", "status": status,
                 "row_fingerprint": fingerprint or second_reading.fingerprint(value)}
        if event is not None:
            fields.insert(3, "last_event")
            entry["last_event"] = event
        path = self.root / "synthetic.review-map.tsv"
        write_tsv(path, fields, [entry])
        return path

    def test_all_degrees_and_explicit_verdicts(self) -> None:
        for degree in ("high", "medium", "low"):
            for verdict in ("confirmed", "amended", "withdrawn"):
                with self.subTest(degree=degree, verdict=verdict):
                    parsed = final_validate.confidence_annotation(annotation(degree, verdict))
                    self.assertEqual(parsed, {"degree": degree, "verdict": verdict,
                                              "review_id": "R000001", "event_id": "E000001"})
        self.assertIsNotNone(final_validate.confidence_annotation(
            "\tlow \t; second reading amended\t; R1000000 ; E1000001 "))
        # Canonical padding is checked without a bounded integer conversion.
        self.assertIsNotNone(final_validate.confidence_annotation(
            annotation(review_id="R" + "9" * 5000)))

    def test_reject_incomplete_or_ambiguous_cells(self) -> None:
        invalid = [
            None, "", " ", "high", "medium", "low", "reviewed",
            "high; second reading confirmed", "high; confirmed; R000001; E000001",
            "certain; second reading confirmed; R000001; E000001",
            "high; second reading confirm; R000001; E000001",
            "high; second reading pending; R000001; E000001",
            "high; second reading confirmed; E000001; R000001",
            "high; second reading confirmed; R1; E000001",
            "high; second reading confirmed; R000000; E000001",
            "high; second reading confirmed; R000001; E000000",
            "high; second reading confirmed; R0000001; E000001",
            "high; second reading confirmed; R000001; E0000001",
            annotation() + "; R000002", annotation() + "; E000002",
            annotation() + "; pending", annotation() + " trailing text",
            annotation() + "\n", "\n" + annotation(),
            annotation().replace("; ", ";\n", 1),
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(final_validate.confidence_annotation(value))

    def test_final_inspect_uses_strict_gate_and_preserves_old_gate(self) -> None:
        for confidence, explicit, provisional in (
            ("high", "fail", "pass"),
            ("high; first reading pending", "fail", "fail"),
            (annotation("low", "withdrawn"), "pass", "pass"),
        ):
            with self.subTest(confidence=confidence):
                self.ledger([row(confidence)])
                before = tree_hashes(self.root)
                checks, _, _ = final_validate.inspect(self.root, None, None, None)
                statuses = {item["check"]: item["status"] for item in checks}
                self.assertEqual(statuses["explicit-second-reading-confidence"], explicit)
                self.assertEqual(statuses["no-explicitly-provisional-confidence"], provisional)
                self.assertEqual(before, tree_hashes(self.root))

    def test_row_and_event_ids_are_unique(self) -> None:
        cases = [
            [row(annotation()), row(annotation(event_id="E000002"), 2)],
            [row(annotation()), row(annotation(review_id="R000002"), 2)],
        ]
        for rows in cases:
            checks = {name: passed for name, passed, _ in final_validate.confidence_checks(rows)}
            self.assertTrue(checks["explicit-second-reading-confidence"])
            self.assertFalse(checks["unique-second-reading-identifiers"])

    def test_invalid_record_locations_do_not_copy_cell_content(self) -> None:
        secret_marker = "synthetic-unrecognized-cell"
        checks = final_validate.confidence_checks([row(annotation()), row(secret_marker, 2)])
        detail = checks[0][2]
        self.assertIn("Logical ledger records, first 20: 2.", detail)
        self.assertNotIn(secret_marker, detail)

    def test_current_map_verdicts_and_no_map_counts(self) -> None:
        for verdict in ("confirmed", "amended", "withdrawn"):
            with self.subTest(verdict=verdict):
                value = row(annotation(verdict=verdict))
                self.ledger([value])
                mapping = self.map_for(value, status=verdict)
                before = tree_hashes(self.root)
                direct = load_rows(self.root, None)
                mapped = load_rows(self.root, mapping)
                self.assertEqual(direct, mapped)
                self.assertEqual(mapped[0]["active"], verdict != "withdrawn")
                self.assertEqual(before, tree_hashes(self.root))

    def test_stale_status_cannot_override_annotated_verdict(self) -> None:
        value = row(annotation(event_id="E000003"))
        self.ledger([value])
        mapping = self.map_for(value, status="withdrawn", event="E000003")
        self.assertTrue(load_rows(self.root, None)[0]["active"])
        before = tree_hashes(self.root)
        with self.assertRaisesRegex(ValueError, "status disagrees"):
            load_rows(self.root, mapping)
        self.assertEqual(before, tree_hashes(self.root))

    def test_stale_last_event_cannot_override_same_content(self) -> None:
        value = row(annotation(event_id="E000003"))
        self.ledger([value])
        mapping = self.map_for(value, event="E000002")
        with self.assertRaisesRegex(ValueError, "last event disagrees"):
            load_rows(self.root, mapping)

    def test_missing_map_event_is_rejected_for_annotated_row(self) -> None:
        value = row(annotation())
        self.ledger([value])
        mapping = self.map_for(value, event=None)
        with self.assertRaisesRegex(ValueError, "last event disagrees"):
            load_rows(self.root, mapping)

    def test_existing_id_and_content_binding_gates_remain(self) -> None:
        value = row(annotation())
        self.ledger([value])
        mapping = self.map_for(value, review_id="R000002")
        with self.assertRaisesRegex(ValueError, "disagree"):
            load_rows(self.root, mapping)
        mapping = self.map_for(value, fingerprint="0" * 64)
        with self.assertRaisesRegex(ValueError, "does not match"):
            load_rows(self.root, mapping)

    def test_pre_promotion_plain_map_remains_available_but_cannot_pass_final(self) -> None:
        value = row("high")
        self.ledger([value])
        mapping = self.map_for(value, status="withdrawn")
        self.assertFalse(load_rows(self.root, mapping)[0]["active"])
        checks = {name: passed for name, passed, _ in final_validate.confidence_checks([value])}
        self.assertFalse(checks["explicit-second-reading-confidence"])

    def test_map_status_is_normalized_and_validated_once(self) -> None:
        value = row("low")
        self.ledger([value])
        mapping = self.map_for(value, status=" withdrawn ")
        self.assertFalse(load_rows(self.root, mapping)[0]["active"])
        mapping = self.map_for(value, status="pending")
        self.assertTrue(load_rows(self.root, mapping)[0]["active"])
        mapping = self.map_for(value, status="synthetic-unknown-status")
        with self.assertRaisesRegex(ValueError, "unrecognized status"):
            load_rows(self.root, mapping)

    def test_final_preflight_requires_current_confidence_checks(self) -> None:
        for name in VALIDATION_REPORT_NAMES:
            (self.root / name).write_text("Synthetic report.\n", encoding="utf-8")
        write_tsv(self.root / "FINAL_VALIDATION_INVENTORY.tsv", ["file", "bytes", "sha256", "status"], [])
        checks = [{"check": name, "status": "pass", "detail": "Synthetic check."}
                  for name in ("privacy", "privacy-source-credit-conflicts")]

        def preflight() -> dict:
            write_tsv(self.root / "FINAL_VALIDATION_CHECKS.tsv", ["check", "status", "detail"], checks)
            members, excluded = checkpoint.inventory(self.root)
            return checkpoint.validation_preflight(self.root, members, excluded)

        with self.assertRaisesRegex(RuntimeError, "confidence"):
            preflight()
        checks.append({"check": "explicit-second-reading-confidence", "status": "pass", "detail": "Synthetic check."})
        with self.assertRaisesRegex(RuntimeError, "review-identifier"):
            preflight()
        checks.append({"check": "unique-second-reading-identifiers", "status": "pass", "detail": "Synthetic check."})
        self.assertEqual(set(preflight()), set(VALIDATION_REPORT_NAMES))
        checks[-1]["status"] = "fail"
        with self.assertRaisesRegex(RuntimeError, "every recorded"):
            preflight()

    def test_real_exporter_annotated_retain_is_accepted_and_preserves_history(self) -> None:
        cases = [(degree, outcome) for degree in ("high", "medium", "low")
                 for outcome in ("confirm", "amend", "withdraw")]
        self.ledger([row("high; first reading pending", number)
                     for number in range(1, len(cases) + 1)])
        common = dict(root=self.root, ledger=Path("CORRECTIONS.tsv"), review_dir=Path("second-reading"))
        decisions = []
        for number, (degree, outcome) in enumerate(cases, 1):
            item = {"review_id": f"R{number:06d}", "outcome": outcome,
                    "confidence": degree, "review_evidence": "Synthetic explicit decision; no image reading."}
            if outcome == "amend":
                item["changes"] = {"statement": f"synthetic amended record {number}"}
            decisions.append(item)
        batch = self.root / "fixture-decisions.json"
        batch.write_text(json.dumps(decisions), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            second_reading.initialize(Namespace(**common, reviewer="Synthetic reviewer"))
            second_reading.record_decisions(Namespace(**common, batch=batch, review_id=None,
                outcome=None, confidence=None, evidence=None, changes=None, bindings=None, reviewer=None))
            before = tree_hashes(self.root)
            second_reading.export_reviewed(Namespace(**common, output=Path("CORRECTIONS.reviewed.tsv"),
                withdrawn="retain", confidence_format="annotated"))
        after = tree_hashes(self.root)
        self.assertTrue(all(after[name] == digest for name, digest in before.items()))
        exported, _ = second_reading.read_ledger(self.root / "CORRECTIONS.reviewed.tsv")
        self.assertEqual(len(exported), 9)
        self.assertTrue(all(passed for _, passed, _ in final_validate.confidence_checks(exported)))
        target = self.root / "synthetic-promoted-ledger"
        target.mkdir()
        write_tsv(target / "CORRECTIONS.tsv", second_reading.FIELDS, exported)
        entries = load_rows(target, self.root / "CORRECTIONS.reviewed.review-map.tsv")
        self.assertEqual(sum(entry["active"] for entry in entries), 6)
        with (self.root / "second-reading" / "REVIEW_EVENTS.tsv").open(encoding="utf-8", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream, delimiter="\t"))), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
