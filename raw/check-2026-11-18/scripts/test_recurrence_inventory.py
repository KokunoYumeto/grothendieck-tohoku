"""Synthetic-only tests for recurrence patterns, lexical probes and reports."""

from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from math_font_context import scan_font_context
import recurrence_inventory as inventory


def rows(source: str, layer: str = "en", table: str = "CANDIDATES.tsv") -> list[dict]:
    tables, _ = inventory.inventory_bytes({f"sources/{layer}/p119.tex": source.encode("utf-8")})
    return tables[table][1]


class ProbeFixtures(unittest.TestCase):
    def test_probe_modes_and_unchanged_font_results(self) -> None:
        for source, expected in (
            ("schemes", "text"), ("$schemes$", "math"),
            (r"$\text{schemes}$", "text"), (r"\ensuremath{schemes}", "math"),
            (r"\newcommand{\F}{schemes}", "unknown"),
            (r"\newcommand{\F}[1][schemes]{#1}", "unknown"),
            ("$schemes", "unknown"),
        ):
            with self.subTest(source=source):
                data = (source + r" \mathbf X").encode()
                position = source.index("schemes")
                baseline = scan_font_context(data)
                probed = scan_font_context(data, {position, position + 6})
                probes = probed.pop("probes")
                self.assertEqual(probed, baseline)
                self.assertTrue(all(item["visited"] for item in probes))
                self.assertTrue(all(item["observed_mode"] == expected for item in probes))

    def test_skipped_tokens_remain_unvisited(self) -> None:
        for source in (
            "% schemes", r"\verb+schemes+", r"\begin{verbatim}schemes\end{verbatim}",
            r"\detokenize{schemes}", r"\schemes", r"\string\schemes", r"\meaning\schemes",
            r"\begin{schemes}X\end{schemes}", r"\def\F schemes{X}", r"\let\saved=schemes",
        ):
            with self.subTest(source=source):
                probe = scan_font_context(source.encode(), {source.index("schemes")})["probes"][0]
                self.assertFalse(probe["visited"])
                self.assertNotIn("observed_mode", probe)

    def test_probe_unicode_offsets_and_validation(self) -> None:
        text = "é\n schemes"
        data = b"\xef\xbb\xbf" + text.encode()
        probe = scan_font_context(data, {text.index("schemes")})["probes"][0]
        self.assertEqual((probe["line"], probe["column"]), (2, 2))
        for invalid in ({-1}, {len(text)}, {True}):
            with self.assertRaises(ValueError):
                scan_font_context(data, invalid)


class PatternFixtures(unittest.TestCase):
    def test_nine_english_families(self) -> None:
        source = "direct limits; inverse limit; direct~systems; inverse-system; flabby; schemes; boundary elements; boundary-homomorphism; positive\ndegrees"
        found = rows(source)
        self.assertEqual({row["family"] for row in found}, {item[0] for item in inventory.ENGLISH_TERMS})
        self.assertEqual(len(found), 9)
        self.assertTrue(all(row["review_status"] == "pending manual review" for row in found))
        self.assertEqual(rows("DIRECT LIMIT")[0]["matched_token"], "DIRECT LIMIT")

    def test_word_boundaries_and_no_macro_normalization(self) -> None:
        source = r"indirect limit; flabbyness; schematically; \flabby; \schemes; boundary homomorphismology; direct \emph{limit}"
        self.assertFalse(rows(source))
        self.assertEqual(rows("scheme-theoretic")[0]["matched_token"], "scheme")

    def test_prose_scheme_filter_and_raw_retention(self) -> None:
        source = "scheme $schemes$ " + r"$\text{schemes}$ \ensuremath{scheme} \newcommand{\F}{scheme} " + "% schemes\n" + r"\verb|scheme| \let\saved=scheme"
        retained = rows(source)
        excluded = rows(source, table="EXCLUDED_RAW_MATCHES.tsv")
        all_matches = rows(source, table="ALL_RAW_MATCHES.tsv")
        self.assertEqual(len(retained), 3)
        self.assertEqual(len(excluded), 5)
        self.assertEqual(len(all_matches), 8)
        self.assertIn("deferred definition body", {row["context_category"] for row in retained})
        self.assertEqual(sum(row["exclusion_reason"].startswith("recognized math") for row in excluded), 2)

    def test_mixed_endpoint_context_remains_uncertain(self) -> None:
        found = rows(r"$\text schemes$")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["lexical_mode"], "unknown")
        self.assertEqual(found[0]["context_category"], "mixed lexical contexts")

    def test_french_literals_and_layer_separation(self) -> None:
        source = "coefficients; du homomorphisme; de homomorphisme; Coefficients; coefficient; du  homomorphisme; du\nhomomorphisme; DE homomorphisme; direct limit"
        for layer in ("dip", "fr"):
            found = rows(source, layer)
            self.assertEqual([row["matched_token"] for row in found], ["coefficients", "du homomorphisme", "de homomorphisme"])
        self.assertEqual([row["family"] for row in rows(source, "en")], ["en_direct_limits"])
        self.assertFalse(rows(r"\coefficients; surcoefficients", "dip"))

    def test_page_layer_order_and_exact_surrounding_lines(self) -> None:
        snapshot = {
            "sources/en/p185.tex": b"flabby",
            "sources/fr/p119.tex": b"coefficients",
            "sources/en/p119.tex": "é direct\nlimits rest\n".encode(),
            "sources/dip/p119.tex": b"coefficients",
        }
        tables, _ = inventory.inventory_bytes(snapshot)
        found = tables["CANDIDATES.tsv"][1]
        self.assertEqual([(row["printed_page"], row["layer"]) for row in found],
                         [(119, "dip"), (119, "fr"), (119, "en"), (185, "en")])
        span = found[2]
        self.assertEqual((span["line"], span["column"], span["end_line"], span["end_column"]), (1, 3, 2, 6))
        self.assertEqual(span["matched_token"], "direct\nlimits")
        self.assertEqual(span["source_line"], "é direct\nlimits rest")
        self.assertEqual(span["source_line_sha256"], inventory.sha(span["source_line"].encode()))
        self.assertEqual([row["match_id"] for row in found], [f"T{number:06d}" for number in range(1, 5)])


class ReportFixtures(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="recurrence-fixture-")
        self.root = Path(self.temporary.name)
        for layer in inventory.LAYER_RANK:
            (self.root / "sources" / layer).mkdir(parents=True)
        self.path = self.root / "sources" / "en" / "p119.tex"
        self.path.write_text("direct limits", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_report(self, name: str = "recurrence-interim-fixture") -> dict:
        with redirect_stdout(io.StringIO()):
            return inventory.run(Namespace(root=self.root, output=Path(name)))

    def test_report_sources_and_privacy_filtered_context(self) -> None:
        address = "synthetic-person" + "@" + "example.invalid"
        original = f"direct limits {self.root / 'synthetic-private'} {address}\n".encode()
        self.path.write_bytes(original)
        summary = self.run_report()
        self.assertEqual(summary["source_line_fields_privacy_filtered"], 1)
        self.assertEqual(self.path.read_bytes(), original)
        payload = b"\n".join(path.read_bytes() for path in (self.root / "recurrence-interim-fixture").iterdir())
        self.assertNotIn(str(self.root).encode(), payload)
        self.assertNotIn(address.encode(), payload)
        self.assertIn(inventory.sha(original.rstrip(b"\n")).encode(), payload)
        self.assertIn(b"pending manual review", payload)

    def test_no_nonpage_context_or_symlink_reads(self) -> None:
        (self.root / "sources" / "preamble.tex").write_bytes(b"\xff")
        (self.root / "sources" / "main-en.tex").write_bytes(b"\xff")
        for folder in ("programme", "notes", "stacks"):
            directory = self.root / "sources" / "en" / folder
            directory.mkdir()
            (directory / "p120.tex").write_bytes(b"\xff")
        trap = self.root / "unread.tex"
        trap.write_bytes(b"\xff")
        (self.root / "sources" / "en" / "p120.tex").symlink_to(trap)
        self.assertEqual(self.run_report()["source_files"], 1)

    def test_existing_report_and_noninterim_refusal(self) -> None:
        with self.assertRaisesRegex(ValueError, "interim"):
            self.run_report("report-final")
        self.run_report()
        output = self.root / "recurrence-interim-fixture"
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_report()
        self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})

    def test_source_change_refuses_installation(self) -> None:
        original = inventory.recheck
        def mutation(root: Path, snapshot: dict[str, bytes]) -> None:
            self.path.write_text("flabby", encoding="utf-8")
            original(root, snapshot)
        with patch.object(inventory, "recheck", mutation):
            with self.assertRaisesRegex(RuntimeError, "source changed"):
                self.run_report("changed-source-interim")
        self.assertFalse((self.root / "changed-source-interim").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
