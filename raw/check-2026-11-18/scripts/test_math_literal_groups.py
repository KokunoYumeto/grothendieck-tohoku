"""Focused synthetic-only fixtures for explicit literal-group classification."""

from argparse import Namespace
from contextlib import contextmanager, redirect_stdout
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import math_literal_groups as groups


def ledger_row(number, *, page="119", layer="as-printed", kind="translation", old="A", new="B", verdict="confirmed"):
    return {"file": "synthetic-ledger-target.tex", "layer": layer, "printed_page": page, "line": "1", "statement": "synthetic statement",
            "old": old, "new": new, "evidence": "synthetic evidence", "kind": kind,
            "confidence": f"high; second reading {verdict}; R{number:06d}; E{number:06d}"}


def ledger_fixture():
    return [ledger_row(1), ledger_row(2, page="120", layer="English"), ledger_row(3, page="121", old="A "),
            ledger_row(4, page="122", kind="reading"), ledger_row(5, page="", layer="build", kind="structure", old="x", new="y"),
            ledger_row(6, verdict="withdrawn")]


@contextmanager
def fixture(ledger=None):
    with tempfile.TemporaryDirectory(prefix="synthetic-math-groups-") as temporary:
        root = Path(temporary)
        (root / "CORRECTIONS.tsv").write_bytes(groups.tsv_bytes(groups.FIELDS, ledger if ledger is not None else ledger_fixture()))
        args = Namespace(root=root, ledger="CORRECTIONS.tsv", action="prepare", output="groups-interim", privacy_filter_derived=False,
                         group_decisions=None, existing_classifications=None, row_exceptions=None)
        yield root, args


def run(args):
    with redirect_stdout(io.StringIO()):
        return groups.run(args)


def table(root, name, directory="groups-interim"):
    with (root / directory / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_decisions(root, rows):
    (root / "GROUP_DECISIONS.primary.tsv").write_bytes(groups.tsv_bytes(list(rows[0]) if rows else groups.GROUP_FIELDS, rows))


def expand_args(args, output="expanded-interim"):
    return Namespace(**{**vars(args), "action": "expand", "group_decisions": "GROUP_DECISIONS.primary.tsv", "output": output})


class LiteralGroupFixtures(unittest.TestCase):
    def test_exact_groups_complete_membership_and_pending_templates(self):
        with fixture() as (root, args):
            original_capture = groups.capture
            def only_selected_tables(path):
                self.assertEqual(path.suffix, ".tsv")
                return original_capture(path)
            with patch.object(groups, "capture", side_effect=only_selected_tables):
                summary = run(args)
            self.assertEqual((summary["active_rows"], summary["literal_groups"], summary["withdrawn_rows_excluded"]), (5, 4, 1))
            grouped = table(root, "GROUP_DECISIONS.tsv")
            repeated = next(row for row in grouped if row["member_count"] == "2")
            self.assertEqual(repeated["printed_pages"], "119,120")
            self.assertEqual(repeated["layers"], "English,as-printed")
            self.assertEqual(repeated["correction_ids"], "R000001,R000002")
            self.assertEqual(repeated["group_id"], "G" + groups.digest(["translation", "A", "B"]))
            self.assertEqual(len(table(root, "GROUP_MEMBERS.tsv")), 5)
            self.assertIn("evidence", table(root, "GROUP_MEMBERS.tsv")[0])
            for row in grouped + table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv"):
                self.assertEqual((row["mathematical_change"], row["summary"], row["reason"]), ("pending", "", ""))
            self.assertEqual(table(root, "ROW_EXCEPTIONS.tsv"), [])
            with (root / args.output / "ROW_EXCEPTIONS.tsv").open(newline="") as stream:
                exception_fields = next(csv.reader(stream, delimiter="\t"))
            self.assertEqual(exception_fields, groups.MATH_REQUIRED)
            self.assertTrue(all(row["row_exception"] == "no" for row in table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv")))
            repeated.update(mathematical_change="no", reason="Explicit synthetic group reason")
            write_decisions(root, grouped)
            expanded = expand_args(args)
            expanded.existing_classifications = "groups-interim/MATHEMATICAL_CHANGE_CLASSIFICATION.tsv"
            self.assertEqual(run(expanded)["classifications_no"], 2)
            pending = next(row for row in table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv") if row["correction_id"] == "R000002")
            exception = {field: pending[field] for field in exception_fields}
            exception["reason"] = "Explicit synthetic pending hold from the prepared core template"
            (root / "ROW_EXCEPTIONS.primary.tsv").write_bytes(groups.tsv_bytes(exception_fields, [exception]))
            held = expand_args(args, "expanded-with-template-interim")
            held.row_exceptions = "ROW_EXCEPTIONS.primary.tsv"
            held_result = run(held)
            self.assertEqual((held_result["classifications_no"], held_result["retained_pending_exceptions"]), (1, 1))

    def test_explicit_decisions_precedence_and_repeat_exception_preservation(self):
        with fixture() as (root, args):
            run(args)
            decision_rows = table(root, "GROUP_DECISIONS.tsv")
            for row in decision_rows:
                if row["kind"] == "translation" and row["old"] == "A ":
                    row.update(mathematical_change="no", reason="Explicit synthetic group no reason")
                elif row["kind"] != "structure":
                    row.update(mathematical_change="yes", summary="Explicit synthetic group summary", reason="Explicit synthetic group yes reason")
            write_decisions(root, decision_rows)
            pending = {row["correction_id"]: row for row in table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv")}
            existing = {field: pending["R000001"][field] for field in groups.MATH_REQUIRED}
            existing.update(mathematical_change="no", reason="Existing synthetic row reason")
            exception = {field: pending["R000002"][field] for field in groups.MATH_REQUIRED}
            exception.update(reason="Explicit synthetic pending hold")
            (root / "existing.tsv").write_bytes(groups.tsv_bytes(groups.MATH_REQUIRED, [existing]))
            (root / "exceptions.tsv").write_bytes(groups.tsv_bytes(groups.MATH_REQUIRED, [exception]))
            expanded = expand_args(args)
            expanded.existing_classifications, expanded.row_exceptions = "existing.tsv", "exceptions.tsv"
            summary = run(expanded)
            self.assertEqual((summary["classifications_yes"], summary["classifications_no"], summary["classifications_pending"]), (1, 2, 2))
            rows = {row["correction_id"]: row for row in table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv", expanded.output)}
            self.assertEqual(rows["R000001"]["reason"], existing["reason"])
            self.assertEqual(rows["R000002"]["mathematical_change"], "pending")
            self.assertEqual(rows["R000002"]["row_exception"], "yes")
            self.assertEqual(rows["R000004"]["summary"], "Explicit synthetic group summary")
            self.assertEqual(rows["R000004"]["decision_origin"], "group")
            repeated = expand_args(args, "repeat-interim")
            repeated.existing_classifications = (Path(expanded.output) / "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv").as_posix()
            run(repeated)
            repeated_rows = {row["correction_id"]: row for row in table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv", repeated.output)}
            for key in rows:
                for field in groups.MATH_REQUIRED + ["row_exception", "decision_origin", "decision_input_sha256", "decision_group_id", "decision_membership_sha256"]:
                    self.assertEqual(repeated_rows[key][field], rows[key][field])
            self.assertEqual(table(root, "ROW_EXCEPTIONS.tsv", repeated.output)[0]["correction_id"], "R000002")
            # A legacy unmarked pending row is conservatively retained as a hold.
            (root / "legacy.tsv").write_bytes(groups.tsv_bytes(groups.MATH_REQUIRED, [{field: pending["R000001"][field] for field in groups.MATH_REQUIRED}]))
            legacy = expand_args(args, "legacy-interim")
            legacy.existing_classifications = "legacy.tsv"
            run(legacy)
            first = table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv", legacy.output)[0]
            self.assertEqual((first["mathematical_change"], first["row_exception"]), ("pending", "yes"))

    def test_stale_memberships_and_row_fingerprints_cannot_inherit(self):
        for change in ("new_member", "missing_member", "changed_fingerprint"):
            with self.subTest(change=change), fixture() as (root, args):
                run(args)
                decisions = table(root, "GROUP_DECISIONS.tsv")
                decisions[0].update(mathematical_change="no", reason="Explicit synthetic reason")
                write_decisions(root, decisions)
                current = ledger_fixture()
                if change == "new_member":
                    current.append(ledger_row(7))
                elif change == "missing_member":
                    current.pop(1)
                else:
                    current[1]["evidence"] = "changed synthetic evidence"
                (root / "CORRECTIONS.tsv").write_bytes(groups.tsv_bytes(groups.FIELDS, current))
                with self.assertRaisesRegex(ValueError, "membership"):
                    run(expand_args(args))
                self.assertFalse((root / "expanded-interim").exists())
        with fixture() as (root, args):
            run(args)
            original = (root / "CORRECTIONS.tsv").read_bytes()
            write_decisions(root, table(root, "GROUP_DECISIONS.tsv"))
            # Reordering the exact same ID/fingerprint pairs leaves memberships valid.
            (root / "CORRECTIONS.tsv").write_bytes(groups.tsv_bytes(groups.FIELDS, list(reversed(ledger_fixture()))))
            self.assertEqual(run(expand_args(args))["active_rows"], 5)
            (root / "CORRECTIONS.tsv").write_bytes(original)
            invalid = {field: table(root, "MATHEMATICAL_CHANGE_CLASSIFICATION.tsv")[0][field] for field in groups.MATH_REQUIRED}
            invalid["row_fingerprint"] = "f" * 64
            (root / "stale.tsv").write_bytes(groups.tsv_bytes(groups.MATH_REQUIRED, [invalid]))
            expanded = expand_args(args, "stale-row-interim")
            expanded.row_exceptions = "stale.tsv"
            with self.assertRaisesRegex(ValueError, "changed after manual classification"):
                run(expanded)

    def test_decision_requirements_duplicate_inputs_and_promoted_identity(self):
        for choice, summary, reason in (("yes", "", "reason"), ("no", "", ""), ("yes", "summary", ""), ("YES", "summary", "reason")):
            with self.subTest(choice=choice, summary=summary, reason=reason), fixture() as (root, args):
                run(args)
                decisions = table(root, "GROUP_DECISIONS.tsv")
                decisions[0].update(mathematical_change=choice, summary=summary, reason=reason)
                write_decisions(root, decisions)
                with self.assertRaises(ValueError):
                    run(expand_args(args))
        with fixture() as (root, args):
            run(args)
            decisions = table(root, "GROUP_DECISIONS.tsv")
            write_decisions(root, decisions + [decisions[0]])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                run(expand_args(args))
        for confidence in ("high", "high; second reading confirmed; R000000; E000001", "high; second reading confirmed; L000001; E000001"):
            with self.subTest(confidence=confidence), fixture([{**ledger_row(1), "confidence": confidence}]) as (root, args):
                with self.assertRaises(ValueError):
                    run(args)

    def test_privacy_display_filtering_never_defines_groups_or_rewrites_decisions(self):
        private_a, private_b = "first" + "@" + "example.invalid", "second" + "@" + "example.invalid"
        with fixture([ledger_row(1, old=private_a), ledger_row(2, old=private_b)]) as (root, args):
            original = (root / "CORRECTIONS.tsv").read_bytes()
            with self.assertRaisesRegex(RuntimeError, "privacy pattern"):
                run(args)
            args.privacy_filter_derived = True
            self.assertEqual(run(args)["literal_groups"], 2)
            decision_rows = table(root, "GROUP_DECISIONS.tsv")
            self.assertEqual(decision_rows[0]["old"], decision_rows[1]["old"])
            self.assertNotEqual(decision_rows[0]["group_id"], decision_rows[1]["group_id"])
            self.assertTrue(table(root, "PRIVACY_FILTERING.tsv"))
            decision_rows[0].update(mathematical_change="no", reason="Explicit synthetic reason")
            write_decisions(root, decision_rows)
            summary = run(expand_args(args))
            self.assertEqual((summary["classifications_no"], summary["classifications_pending"]), (1, 1))
            self.assertEqual((root / "CORRECTIONS.tsv").read_bytes(), original)
            decision_rows[0]["reason"] = private_a
            write_decisions(root, decision_rows)
            with self.assertRaisesRegex(ValueError, "never filtered"):
                run(expand_args(args, "private-decision-interim"))

    def test_input_immutability_guards_and_snapshot_rechecks(self):
        with fixture() as (root, args):
            original = (root / "CORRECTIONS.tsv").read_bytes()
            run(args)
            self.assertEqual((root / "CORRECTIONS.tsv").read_bytes(), original)
            with self.assertRaises(ValueError):
                run(args)
            for name in ("notes/new-interim", "sources/new-interim", "../new-interim"):
                with self.subTest(output=name):
                    args.output = name
                    with self.assertRaises(ValueError):
                        run(args)
            args.output = "changed-interim"
            (root / "linked.tsv").symlink_to(root / "CORRECTIONS.tsv")
            args.ledger = "linked.tsv"
            with self.assertRaisesRegex(ValueError, "symbolic"):
                run(args)
            args.ledger = "CORRECTIONS.tsv"
            recheck = groups.recheck_snapshots
            def changed(snapshots):
                (root / "CORRECTIONS.tsv").write_bytes(original + b"\n")
                recheck(snapshots)
            with patch.object(groups, "recheck_snapshots", side_effect=changed), self.assertRaisesRegex(RuntimeError, "changed"):
                run(args)
            self.assertFalse((root / args.output).exists())
            (root / "CORRECTIONS.tsv").write_bytes(original)
            original_link, linked = groups.os.link, []
            def failed_install(source, target):
                linked.append(target)
                if len(linked) == 2:
                    raise OSError("synthetic interrupted installation")
                return original_link(source, target)
            with patch.object(groups.os, "link", side_effect=failed_install), self.assertRaisesRegex(OSError, "synthetic"):
                run(args)
            self.assertFalse((root / args.output).exists())
            self.assertEqual((root / "CORRECTIONS.tsv").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
