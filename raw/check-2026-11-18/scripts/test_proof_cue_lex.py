"""Focused synthetic fixtures for the proof-cue lexer; no file/source reads."""

import json
import unittest

from proof_cue_lex import CUE_PATTERNS, LIMITATIONS, MAX_FRAGMENT_CHARS, scan_page


class ProofCueFixtures(unittest.TestCase):
    def check_spans(self, text, result):
        for rows in result.values():
            for row in rows:
                self.assertTrue(0 <= row["offset"] <= row["end_offset"] <= len(text))
                for field in ("line", "column", "end_line", "end_column"):
                    self.assertGreaterEqual(row[field], 1)
                if "matched" in row:
                    self.assertEqual(row["matched"], text[row["offset"]:row["end_offset"]])
                if "fragment" in row:
                    self.assertEqual(row["fragment"], text[row["offset"]:row["end_offset"]])
                    self.assertNotEqual(row["fragment"].strip(), text.strip())

    def test_every_explicit_cue_family_unicode_and_raw_preservation(self):
        middle = ("SANS DÉMONSTRATION; laissée; exercices; facilement; ÉVIDENTE; trivialement; vérification; "
                  "on voit; on constate; il suffit; nous renvoyons; se montre; démontrer; peut montrer; "
                  "aisément; n'écrirons; n’écrirons; sans preuve; nous omettons; nous omettrons.")
        text = "Préambule.\n\n" + middle + "\n\nFin.\n"
        result = scan_page(text)
        self.assertEqual({row["family"] for row in result["cues"]}, {row["family"] for row in CUE_PATTERNS})
        self.assertTrue(all(row["scope"] == "active" for row in result["cues"]))
        self.assertIn("SANS DÉMONSTRATION", {row["matched"] for row in result["cues"]})
        self.assertEqual(len([row for row in result["cues"] if row["family"] == "n_ecrirons"]), 2)
        self.assertEqual(len(result["fragments"]), 1)
        self.assertEqual(result["fragments"][0]["fragment"], middle)
        self.assertEqual(result["fragments"][0]["completeness"], "complete_file_local_paragraph")
        self.assertFalse(scan_page(r"\facile prefixfacile exercice9")["cues"])
        self.assertTrue(json.dumps(CUE_PATTERNS, ensure_ascii=False))
        self.assertTrue(all(isinstance(item, str) for item in LIMITATIONS))
        self.check_spans(text, result)

    def test_comments_literals_deferred_definitions_and_escaped_percent(self):
        text = ("Préambule.\n\nActif \\% facile.\n% on voit; \\LayerTarget{comment}\n"
                "\\verb|trivial|\n\\begin{verbatim}\nexercice \\LayerTarget{literal}\n\\end{verbatim}\n"
                "\\detokenize{évident}\n\\newcommand{\\F}{vérifier}\n\nFin.\n")
        result = scan_page(text)
        scopes = {row["family"]: row["scope"] for row in result["cues"]}
        self.assertEqual(scopes, {"facile": "active", "on_voit": "comment", "trivial": "literal_or_verbatim",
                                  "exercice": "literal_or_verbatim", "evident": "literal_or_verbatim", "verifi": "uncertain"})
        self.assertEqual({row["argument"]: row["scope"] for row in result["anchors"]}, {"comment": "comment", "literal": "literal_or_verbatim"})
        self.assertTrue(all(bool(row["fragment_id"]) == (row["scope"] == "active") for row in result["cues"]))
        self.check_spans(text, result)

    def test_blank_and_explicit_par_boundaries_not_paragraph_commands(self):
        first = "Il suffit ici.\n\\paragraph{Titre ordinaire} Cela est facile.\n% \\par commentaire\n"
        second = "On voit la suite."
        text = "Préambule.\n\n" + first + "\\par\n" + second + "\n\nFin.\n"
        result = scan_page(text)
        cues = {row["family"]: row for row in result["cues"]}
        self.assertEqual(cues["il_suffit"]["fragment_id"], cues["facile"]["fragment_id"])
        fragments = {row["fragment_id"]: row for row in result["fragments"]}
        self.assertEqual(fragments[cues["il_suffit"]["fragment_id"]]["fragment"], first.rstrip())
        self.assertEqual(fragments[cues["on_voit"]["fragment_id"]]["fragment"], second)
        self.assertTrue(all(row["completeness"] == "complete_file_local_paragraph" for row in fragments.values()))
        self.assertEqual(fragments[cues["on_voit"]["fragment_id"]]["left_boundary"], "explicit_par")
        self.check_spans(text, result)

    def test_bounded_single_block_edges_omissions_and_referenced_fragments_only(self):
        for text in ("  Ceci est facile à lire.  ", "facile", "\n\nfacile\n\n", "facile au début.\n\nTexte indépendant.", "Avant " + "texte " * 200 + "facile " + "texte " * 200):
            with self.subTest(length=len(text)):
                result = scan_page(text)
                self.assertTrue(result["cues"])
                self.assertTrue(all(row["completeness"] != "complete_file_local_paragraph" for row in result["fragments"]))
                self.assertTrue(all(len(row["fragment"]) <= MAX_FRAGMENT_CHARS for row in result["fragments"]))
                self.assertEqual({row["fragment_id"] for row in result["fragments"]}, {row["fragment_id"] for row in result["cues"]})
                self.check_spans(text, result)
        text = "Unrelated opening.\n\nIl suffit ici.\n\nUnrelated closing."
        result = scan_page(text)
        self.assertEqual([row["fragment"] for row in result["fragments"]], ["Il suffit ici."])

    def test_balanced_literal_anchors_parse_notes_and_character_coordinates(self):
        text = "\ufeffé\r\n\\LayerTarget{a:{b}\\{c\\}}\r\n% \\LayerTarget{comment%raw}\r\n\\verb|\\LayerTarget{literal}|\r\n\\LayerTarget{unclosed"
        result = scan_page(text)
        self.assertEqual([row["argument"] for row in result["anchors"]], [r"a:{b}\{c\}", "comment%raw", "literal"])
        first = result["anchors"][0]
        self.assertEqual((first["offset"], first["line"], first["column"]), (4, 2, 1))
        self.assertEqual(first["scope"], "active")
        self.assertIn("unresolved_layer_target", {row["kind"] for row in result["notes"]})
        for row in result["anchors"]:
            self.assertEqual(row["argument"], text[row["argument_offset"]:row["argument_end_offset"]])
        self.check_spans(text, result)
        referenced = scan_page(r"\string\LayerTarget{reference}")
        self.assertEqual(referenced["anchors"][0]["scope"], "uncertain")

    def test_typed_numbered_unnumbered_headings_and_overlap_deduplication(self):
        text = ("\\SectionHeading{\\textbf{THÉORÈME 2.3.}}\n"
                "\\textbf{Lemme 4.}\n{\\sc Corollaire IV.}\nTheorem 5.\n"
                "Proposition non numérotée.\n\\paragraph{Lemma (2.1)}\n"
                "\\textbf{Théorème} 7.\n\\section*{\n\\emph{Theorem 8.}\n}\n"
                "THEOREME A.\nNous citons le Théorème 9.\n% COROLLAIRE 10.\n")
        result = scan_page(text)
        headings = result["headings"]
        self.assertEqual(len(headings), 10)
        self.assertEqual([row["number"] for row in headings], ["2.3", "4", "IV", "5", "", "(2.1)", "7", "8", "A", "10"])
        self.assertEqual(headings[4]["heading_type"], "proposition")
        self.assertIs(headings[4]["numbered"], False)
        self.assertEqual(headings[-1]["scope"], "comment")
        self.assertEqual(headings[7]["rule"], "explicit_section;leading_emph;plain_line_lead")
        self.assertTrue(all(isinstance(row["numbered"], bool) for row in headings))
        self.assertEqual(len({row["offset"] for row in headings}), len(headings))
        self.check_spans(text, result)
        wrapped = scan_page("\\textbf{\nThéorème 3.\n}\n")
        self.assertEqual([(row["number"], row["numbered"]) for row in wrapped["headings"]], [("3", True)])
        self.assertEqual(scan_page(r"\string\section{Theorem 3}")["headings"][0]["scope"], "uncertain")


if __name__ == "__main__":
    unittest.main()
