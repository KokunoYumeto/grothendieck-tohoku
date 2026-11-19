"""Focused privacy regressions: typed TeX expressions versus real paths.

Filesystem and email fixtures are assembled from components so this test file
does not itself contain an address or an absolute pathname for delivery.
"""

import json
import unittest

from privacy_guard import privacy_findings, safe_location, scan_bytes


class TexMorphismPrivacyTests(unittest.TestCase):
    def assert_preserved(self, text):
        self.assertEqual(privacy_findings(text), [])
        self.assertEqual(safe_location(text), text)
        self.assertEqual(scan_bytes("example.tsv", text.encode()), [])
        encoded = json.dumps({"value": text})
        self.assertEqual(privacy_findings(encoded), [])
        self.assertEqual(safe_location(encoded), encoded)
        self.assertEqual(scan_bytes("example.json", encoded.encode()), [])

    def assert_rejected(self, text):
        self.assertTrue(privacy_findings(text))
        self.assertNotEqual(safe_location(text), text)
        self.assertTrue(scan_bytes("example.tsv", text.encode()))
        self.assertTrue(scan_bytes("example.json", json.dumps({"value": text}).encode()))

    def test_observed_typed_math_forms(self):
        for text in (
            r"$F:\mathbf{C}\to \mathbf{C}'$",
            r"$G:\mathbf{C}'\to \mathbf{C}''$",
            r"F:\mathbf{C}\to\mathbf{C}' \qquad G:\mathbf{C}'\to\mathbf{C}",
            r"Let $F:\mathbf{C}\to \mathbf{C}'$ be a functor.",
            r"define u:\overline G\to M",
        ):
            with self.subTest(text=text):
                self.assert_preserved(text)

    def test_no_control_word_prefix_exemption(self):
        slash = chr(92)
        for tail in ("Users" + slash + "person" + slash + "file.txt", "mathbf", "mathbf{C}" + slash + "private.tex"):
            with self.subTest(tail=tail):
                self.assert_rejected("C:" + slash + tail)

    def test_path_continuations_remain_findings(self):
        slash = chr(92)
        typed_prefix = "C:" + slash + "mathbf{C}" + slash + "to" + slash + "mathbf{D}"
        for tail in (slash + "private.tex", chr(47) + "private.tex", ".txt", "_backup", ":stream"):
            with self.subTest(tail=tail):
                self.assert_rejected(typed_prefix + tail)

    def test_other_privacy_families_remain_active(self):
        forward, back = chr(47), chr(92)
        fixtures = (
            "D:" + forward + "Users" + forward + "person" + forward + "file.txt",
            forward + "workspace" + forward + "private.txt",
            back * 2 + "server" + back + "share" + back + "private.txt",
            forward * 2 + "server" + forward + "share" + forward + "private.txt",
            "file:" + forward * 3 + "private.txt",
            "person" + chr(64) + "example.invalid",
        )
        for text in fixtures:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_math_and_path_in_same_cell(self):
        text = r"$F:\mathbf{C}\to \mathbf{C}'$; " + "C:" + chr(92) + "private.txt"
        filtered = safe_location(text)
        self.assertEqual(filtered, r"$F:\mathbf{C}\to \mathbf{C}'$; <local>")
        self.assertEqual(len(privacy_findings(text)), 1)
        self.assertEqual(privacy_findings(filtered), [])

    def test_prospective_replacement_labels(self):
        path = "C:" + chr(92) + "private.txt"
        address = "person" + chr(64) + "example.invalid"
        self.assertEqual(safe_location(path), "<local>")
        self.assertEqual(safe_location(address), "<redacted-email>")
        self.assertTrue(privacy_findings(path))
        self.assertTrue(privacy_findings(address))

    def test_limit_index_array_break_is_preserved(self):
        self.assert_preserved(r"\longrightarrow\\i\in I}}")
        back = chr(92)
        self.assert_rejected(back * 2 + "i" + back + "in" + back + "private.txt")
        self.assert_rejected(r"\longrightarrow\\i\in I" + back + "private.txt")

    def test_exact_word_seam_descriptions(self):
        for text in ("The coho-/mologiques page-seam division is retained.",
                     "The printed coho-/mologiques division is retained.",
                     "The page seam immédi-/atement is retained.",
                     "% Two corrections and the immé-/atement page seam are recorded append-only.",
                     "% Four corrections and the immé-/atement seam are recorded append-only."):
            with self.subTest(text=text):
                self.assert_preserved(text)
        self.assert_rejected("The coho-" + chr(47) + "mologiques" + chr(47) + "private.txt division.")
        self.assert_rejected(chr(47) + "mologiques")

    def test_exact_flattened_quotient_context(self):
        forward = chr(47)
        prefix, suffix = "of I n+1 ", " . In the second product all terms"
        expression = prefix + forward + "G" + suffix
        self.assert_preserved(expression)
        self.assert_rejected(forward + "G")
        for continuation in (forward + "private.txt", ".txt", "_backup", "extra"):
            self.assert_rejected(prefix + forward + "G" + continuation + suffix)
        mixed = expression + "; " + forward + "workspace" + forward + "private.txt"
        self.assertEqual(safe_location(mixed), expression + "; <local>")


if __name__ == "__main__":
    unittest.main()
