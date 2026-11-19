"""Six focused synthetic fixture groups; never opens a live edition input."""

from argparse import Namespace
from contextlib import contextmanager, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import french_layer_rebind as rebind


def hunk(page=119, number=1, start=0, new="synthetic corrected\n", ids="R000001"):
    old = "synthetic diplomatic\n"
    digest = rebind.sha(json.dumps([page, "replace", start, start + 1, start, start + 1, old, new], ensure_ascii=False, separators=(",", ":")).encode())
    return {"hunk_id": f"D{page}-{number:03d}", "printed_page": str(page), "hunk_sha256": digest,
            "candidate_correction_ids": ids, "operation": "replace", "dip_file": f"sources/dip/p{page}.tex",
            "dip_start_line": str(start + 1), "dip_line_count": "1", "dip_boundary_after_line": "",
            "fr_file": f"sources/fr/p{page}.tex", "fr_start_line": str(start + 1), "fr_line_count": "1", "fr_boundary_after_line": "",
            "dip_fragment": old, "fr_fragment": new}


def review(item, ids="R000001"):
    return {**{field: item[field] for field in ("hunk_id", "printed_page", "hunk_sha256")},
            "decision": "synthetic historical decision", "correction_ids": ids,
            "reason": "synthetic reason prose omitted from the output", "reviewed_utc": "2026-01-01T00:00:00Z", "reviewer": "synthetic reviewer"}


def binding(correction_id="R000001", record="1", value="synthetic row", source="synthetic index"):
    return {"correction_id": correction_id, "ledger_record": str(record), "row_fingerprint": rebind.sha(value.encode()), "id_source": source}


@contextmanager
def fixture(baseline=None, current=None, reviews=None, before=None, after=None):
    baseline = baseline if baseline is not None else [hunk()]
    current = current if current is not None else [dict(row) for row in baseline]
    reviews = reviews if reviews is not None else [review(row) for row in baseline]
    before = before if before is not None else [binding()]
    after = after if after is not None else [dict(row) for row in before]
    with tempfile.TemporaryDirectory(prefix="synthetic-rebind-") as temporary:
        root = Path(temporary)
        for name, rows, bindings in (("baseline", baseline, before), ("current", current, after)):
            (root / name).mkdir()
            fields = list(hunk())
            (root / name / "FRENCH_LAYER_DIFFERENCES.tsv").write_bytes(rebind.tsv_bytes(fields, rows))
            (root / name / "LEDGER_ID_BINDINGS.tsv").write_bytes(rebind.tsv_bytes(rebind.BINDING_FIELDS, bindings))
        (root / "FRENCH_LAYER_REVIEW.tsv").write_bytes(rebind.tsv_bytes(rebind.REVIEW_FIELDS, reviews))
        args = Namespace(root=root, baseline_inventory="baseline", current_inventory="current", review_table="FRENCH_LAYER_REVIEW.tsv", output="result-interim", privacy_filter_derived=False)
        yield root, args


def run(args):
    with redirect_stdout(io.StringIO()):
        return rebind.run(args)


def rows(root, name, output="result-interim"):
    with (root / output / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


class RebindingFixtures(unittest.TestCase):
    def test_exact_hash_provenance_order_and_pending_only(self):
        baseline = [hunk(121), hunk(119)]
        current = [dict(baseline[0]), {**baseline[1], "hunk_id": "D119-004"}]
        reviews = [review(baseline[0], ""), review(baseline[1], "R000002, R000001")]
        bindings = [binding(), binding("R000002", "2", "second synthetic row")]
        with fixture(baseline, current, reviews, bindings, bindings) as (root, args):
            review_bytes = (root / args.review_table).read_bytes()
            original_capture = rebind.capture
            def allowed_capture(path):
                self.assertIn(path.suffix, {".tsv", ".json"})
                return original_capture(path)
            with patch.object(rebind, "capture", side_effect=allowed_capture):
                summary = run(args)
            self.assertEqual(summary["unique_exact_rebinding_proposals"], 2)
            proposed = rows(root, "REBINDING_PROPOSALS.tsv")
            self.assertEqual([row["printed_page"] for row in proposed], ["119", "121"])
            self.assertEqual(proposed[0]["current_hunk_id"], "D119-004")
            self.assertEqual(proposed[0]["historical_correction_ids"], "R000002, R000001")
            self.assertEqual(proposed[0]["historical_review_input_sha256"], rebind.sha(review_bytes))
            self.assertEqual(proposed[0]["historical_reason_sha256"], rebind.sha(reviews[1]["reason"].encode()))
            refs = rows(root, "REFERENCED_ID_CHECKS.tsv")
            self.assertEqual([row["correction_id"] for row in refs], ["R000002", "R000001"])
            for path in (root / args.output).glob("*.tsv"):
                for row in rows(root, path.name):
                    if "review_status" in row:
                        self.assertEqual(row["review_status"], "pending")
            combined = b"".join(path.read_bytes() for path in (root / args.output).iterdir())
            self.assertNotIn(reviews[0]["reason"].encode(), combined)
            self.assertNotIn(reviews[0]["reviewer"].encode(), combined)

    def test_changed_missing_and_invalid_prior_identity(self):
        baseline = [hunk(number=1), hunk(number=2, start=4), hunk(number=3, start=8)]
        current = [hunk(number=1, start=1), hunk(number=2, start=4, new="changed synthetic fragment\n"), hunk(number=4, start=12)]
        with fixture(baseline, current) as (root, args):
            summary = run(args)
            self.assertEqual(summary["unique_exact_rebinding_proposals"], 0)
            self.assertEqual(summary["unmatched_prior_reviews"], 3)
            self.assertEqual(summary["unmatched_baseline_hunks"], 3)
            self.assertEqual(summary["unmatched_current_hunks"], 3)
            self.assertIn("same_current_locator_has_different_hash", rows(root, "UNMATCHED_PRIOR_REVIEWS.tsv")[0]["unmatched_reasons"])
        for field, value, expected in (("hunk_id", "D119-999", "missing_baseline_hunk_id"),
                                       ("printed_page", "120", "baseline_page_mismatch"),
                                       ("hunk_sha256", "f" * 64, "baseline_hash_mismatch")):
            with self.subTest(field=field), fixture(reviews=[{**review(hunk()), field: value}]) as (root, args):
                self.assertEqual(run(args)["unique_exact_rebinding_proposals"], 0)
                self.assertIn(expected, rows(root, "UNMATCHED_PRIOR_REVIEWS.tsv")[0]["unmatched_reasons"])

    def test_duplicate_id_and_hash_ambiguity(self):
        original, duplicate_hash = hunk(), {**hunk(), "hunk_id": "D119-002"}
        cases = [({"baseline": [original, duplicate_hash], "reviews": [review(original)]}, "duplicate_hunk_sha256"),
                 ({"current": [original, duplicate_hash]}, "ambiguous_current_exact_hash"),
                 ({"reviews": [review(original), review(original)]}, "duplicate_hunk_id"),
                 ({"current": [original, hunk(new="different synthetic fragment\n")]}, "duplicate_hunk_id")]
        for values, expected in cases:
            with self.subTest(expected=expected, keys=list(values)), fixture(**values) as (root, args):
                self.assertEqual(run(args)["unique_exact_rebinding_proposals"], 0)
                codes = {row["issue"] for row in rows(root, "VALIDATION_ISSUES.tsv")}
                self.assertIn(expected, codes)

    def test_id_binding_drift_candidate_membership_and_malformed_references(self):
        base = hunk(ids="R000001,R000002,R000003,R000005")
        fresh = {**base, "candidate_correction_ids": "R000001"}
        prior = review(base, "R000001, R000002,R000003,R000004,R000005,R000006")
        before = [binding(), binding("R000002", 2, "two"), binding("R000003", 3, "three"), binding("R000005", 5, "five")]
        after = [binding(record=10, source="changed synthetic index"), binding("R000002", 20, "changed two"),
                 binding("R000004", 40, "four"), binding("R000005", 50, "five"), binding("R000005", 51, "five"), binding("R000007", 70, "seven")]
        with fixture([base], [fresh], [prior], before, after) as (root, args):
            summary = run(args)
            self.assertEqual(summary["unique_exact_rebinding_proposals"], 1)
            comparison = {row["correction_id"]: row for row in rows(root, "ID_BINDING_COMPARISON.tsv")}
            expected = {"R000001": "unchanged_fingerprint", "R000002": "changed_fingerprint", "R000003": "missing_current_binding",
                        "R000004": "new_current_binding", "R000005": "ambiguous_binding", "R000006": "missing_both_bindings", "R000007": "new_current_binding"}
            self.assertEqual({key: row["binding_status"] for key, row in comparison.items()}, expected)
            self.assertEqual(comparison["R000001"]["ledger_record_changed"], "yes")
            self.assertEqual(comparison["R000001"]["id_source_changed"], "yes")
            self.assertEqual(summary["referenced_ids_not_in_current_candidates"], 5)
            self.assertTrue(all(row["review_status"] == "pending" for row in rows(root, "REBINDING_PROPOSALS.tsv")))
        for value, expected in (("R000001;R000002", "malformed"), ("R000001,R000001", "duplicate_ids"), ("", "empty")):
            with self.subTest(reference=value), fixture(reviews=[review(hunk(), value)]) as (root, args):
                run(args)
                proposal = rows(root, "REBINDING_PROPOSALS.tsv")[0]
                self.assertEqual(proposal["historical_correction_ids"], value)
                self.assertEqual(proposal["historical_correction_ids_parse_status"], expected)
                self.assertEqual(proposal["reference_metadata_attention_count"], "0" if expected == "empty" else "1")
                self.assertEqual(proposal["reference_metadata_status"], "no_referenced_ids" if expected == "empty" else "requires_manual_attention")
                if expected == "malformed":
                    self.assertEqual(rows(root, "REFERENCED_ID_CHECKS.tsv"), [])
                    self.assertTrue(rows(root, "VALIDATION_ISSUES.tsv"))
        for value in ("R000000", "R0000001", "L000000", "L0000001"):
            with self.subTest(noncanonical_id=value), fixture(before=[binding(value)]) as (root, args):
                run(args)
                comparison = {row["correction_id"]: row for row in rows(root, "ID_BINDING_COMPARISON.tsv")}
                self.assertEqual(comparison[value]["binding_status"], "invalid_binding")
                self.assertEqual(comparison[value]["identity_kind"], "invalid_identifier")
                if value.startswith("R"):
                    self.assertEqual(rebind.parse_ids(value, review=True), (None, "malformed"))
        self.assertTrue(rebind.canonical_correction_id("R1000000"))
        with fixture(reviews=[review(hunk(), "")], before=[binding("L000001")]) as (root, args):
            run(args)
            self.assertEqual(rows(root, "ID_BINDING_COMPARISON.tsv")[0]["identity_kind"], "snapshot_local_ledger_locator")
            self.assertTrue(all(row["identity_kind"] == "snapshot_local_ledger_locator" for row in rows(root, "BINDING_METADATA.tsv")))

    def test_privacy_hashes_blocking_and_explicit_marked_filtering(self):
        private = "synthetic" + "@" + "example.invalid"
        prior = {**review(hunk()), "reason": private, "reviewer": private}
        with fixture(reviews=[prior], before=[binding(source=private)]) as (root, args):
            run(args)
            self.assertNotIn(private.encode(), b"".join(path.read_bytes() for path in (root / args.output).iterdir()))
        prior["decision"] = private
        with fixture(reviews=[prior]) as (root, args):
            with self.assertRaisesRegex(RuntimeError, "privacy pattern"):
                run(args)
            self.assertFalse((root / args.output).exists())
            args.privacy_filter_derived = True
            summary = run(args)
            self.assertEqual(summary["privacy_filtered_metadata_fields"], 1)
            proposal = rows(root, "REBINDING_PROPOSALS.tsv")[0]
            self.assertEqual(proposal["privacy_filtered_fields"], "historical_decision")
            self.assertEqual(proposal["hunk_sha256"], hunk()["hunk_sha256"])
            filtered = rows(root, "PRIVACY_FILTERING.tsv")[0]
            self.assertEqual(filtered["original_value_sha256"], rebind.sha(private.encode()))
            self.assertNotIn(private.encode(), b"".join(path.read_bytes() for path in (root / args.output).iterdir()))
            self.assertIn(private.encode(), (root / args.review_table).read_bytes())

    def test_input_immutability_path_guards_snapshot_recheck_and_no_overwrite(self):
        with fixture() as (root, args):
            originals = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            run(args)
            for path, value in originals.items():
                self.assertEqual(path.read_bytes(), value)
            with self.assertRaisesRegex(ValueError, "never overwritten"):
                run(args)
            args.output = "empty-interim"
            (root / args.output).mkdir()
            with self.assertRaises(ValueError):
                run(args)
            for name in ("notes/result-interim", "sources/result-interim", "baseline/result-interim", "../result-interim"):
                with self.subTest(output=name):
                    args.output = name
                    with self.assertRaises(ValueError):
                        run(args)
            args.output = "new-interim"
            (root / "linked").symlink_to(root / "baseline", target_is_directory=True)
            args.baseline_inventory = "linked"
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                run(args)
            args.baseline_inventory = "baseline"
            original_recheck = rebind.recheck_snapshots
            def changed(snapshots):
                (root / args.review_table).write_bytes(originals[root / args.review_table] + b"\n")
                original_recheck(snapshots)
            with patch.object(rebind, "recheck_snapshots", side_effect=changed), self.assertRaisesRegex(RuntimeError, "changed"):
                run(args)
            self.assertFalse((root / args.output).exists())
            (root / args.review_table).write_bytes(originals[root / args.review_table])
            def manifest_appeared(snapshots):
                (root / "current" / "INPUT_HASHES.tsv").write_bytes(b"synthetic manifest\n")
                original_recheck(snapshots)
            with patch.object(rebind, "recheck_snapshots", side_effect=manifest_appeared), self.assertRaisesRegex(RuntimeError, "appeared"):
                run(args)
            self.assertFalse((root / args.output).exists())
            (root / "current" / "INPUT_HASHES.tsv").unlink()
            original_link, calls = rebind.os.link, []
            def interrupted_link(source, destination):
                calls.append(destination)
                if len(calls) == 2:
                    raise OSError("synthetic installation interruption")
                return original_link(source, destination)
            with patch.object(rebind.os, "link", side_effect=interrupted_link), self.assertRaisesRegex(OSError, "synthetic installation"):
                run(args)
            self.assertFalse((root / args.output).exists())
            for path, value in originals.items():
                self.assertEqual(path.read_bytes(), value)


if __name__ == "__main__":
    unittest.main()
