"""Synthetic-only regression tests for the static math-font context detector."""

from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import math_font_context as detector


def scan(source: str) -> dict:
    return detector.scan_font_context(source.encode("utf-8"))


def candidates(source: str) -> list[dict]:
    return [row for row in scan(source)["occurrences"] if row["candidate"] == "yes"]


class ContextFixtures(unittest.TestCase):
    def test_all_six_commands_in_plain_text(self) -> None:
        source = " ".join("\\" + name + "{X}" for name in sorted(detector.FONT_COMMANDS))
        found = candidates(source)
        self.assertEqual({row["command"] for row in found}, detector.FONT_COMMANDS)
        self.assertTrue(all(row["context_category"] == "lexically plain text" for row in found))

    def test_standard_inline_and_display_delimiters(self) -> None:
        body = " ".join("\\" + name + "{X}" for name in sorted(detector.FONT_COMMANDS))
        for opening, closing in [("$", "$"), ("$$", "$$"), (r"\(", r"\)"), (r"\[", r"\]")]:
            with self.subTest(opening=opening):
                result = scan(opening + body + closing)
                self.assertEqual(len(result["occurrences"]), 6)
                self.assertFalse([row for row in result["occurrences"] if row["candidate"] == "yes"])
                self.assertFalse(result["notes"])

    def test_outer_and_inner_math_environments(self) -> None:
        for name in sorted(detector.OUTER_MATH_ENVS):
            with self.subTest(outer=name):
                self.assertFalse(candidates(r"\begin{" + name + r"}\mathbf X\end{" + name + "}"))
        for name in sorted(detector.INNER_MATH_ENVS):
            body = r"\begin{" + name + r"}\mathbf X\end{" + name + "}"
            with self.subTest(inner=name):
                self.assertFalse(candidates("$" + body + "$"))
                uncertain = candidates(body)
                self.assertEqual(len(uncertain), 1)
                self.assertEqual(uncertain[0]["observed_mode"], "unknown")
        self.assertEqual(len(candidates(r"\begin{subequations}\mathbf X\begin{equation}\mathbf Y\end{equation}\end{subequations}")), 1)

    def test_text_arguments_restore_outer_math(self) -> None:
        for name in sorted(detector.TEXT_DIRECT):
            with self.subTest(command=name):
                found = candidates("$\\" + name + r"{\mathrm X}\mathbf Y$")
                self.assertEqual([row["command"] for row in found], ["mathrm"])
                self.assertEqual(found[0]["context_category"], "recognized text argument")

    def test_nested_math_inside_text_argument(self) -> None:
        source = r"$\text{a $\mathbf X$ \mathrm Y}\mathbf Z$"
        self.assertEqual([row["command"] for row in candidates(source)], ["mathrm"])
        self.assertFalse(candidates(r"$\text{\ensuremath{\mathbf X}}\mathbf Y$"))

    def test_intertext_restores_alignment_math(self) -> None:
        for command in ("intertext", "shortintertext"):
            source = r"\begin{align}\mathbf X\\" + "\\" + command + r"{\mathrm X}\mathbf Y\end{align}"
            self.assertEqual([row["command"] for row in candidates(source)], ["mathrm"])

    def test_adjacent_inline_spans(self) -> None:
        result = scan(r"$\mathbf A$$\mathbf B$")
        self.assertFalse([row for row in result["occurrences"] if row["candidate"] == "yes"])
        self.assertFalse(result["notes"])

    def test_single_token_arguments_do_not_leak_modes(self) -> None:
        self.assertEqual([row["command"] for row in candidates(r"\ensuremath\alpha \mathbf B")], ["mathbf"])
        self.assertFalse(candidates(r"$\text A \mathbf B$"))
        self.assertEqual([row["command"] for row in candidates(r"$\text\mathbf X$")], ["mathbf"])

    def test_box_arguments(self) -> None:
        for specification in ("", " to 2em", " to2em", " spread 2em"):
            with self.subTest(specification=specification):
                found = candidates(r"$\hbox" + specification + r"{\mathbf X}\mathcal Y$")
                self.assertEqual([row["command"] for row in found], ["mathbf"])
        for source in (
            r"$\makebox[2em][c]{\mathbf X}\mathcal Y$",
            r"$\parbox[c][2em][t]{4em}{\mathbf X}\mathcal Y$",
            r"$\raisebox{1em}[2em][0em]{\mathbf X}\mathcal Y$",
            r"$\footnotetext[1]{\mathbf X}\mathcal Y$",
        ):
            self.assertEqual([row["command"] for row in candidates(source)], ["mathbf"])

    def test_text_environment_body(self) -> None:
        self.assertEqual([row["command"] for row in candidates(
            r"$\begin{tabular}{l}\mathbf X\end{tabular}\mathcal Y$"
        )], ["mathbf"])

    def test_comments_and_escaped_control_symbols(self) -> None:
        source = "\\$ \\mathrm X % $ \\mathbf Y\n$\\{\\mathcal Z\\}$"
        self.assertEqual([row["command"] for row in candidates(source)], ["mathrm"])
        self.assertFalse(scan(r"\\mathbf X")["occurrences"])
        self.assertEqual([row["command"] for row in candidates(r"\\\mathbf X")], ["mathbf"])
        self.assertFalse(candidates(r"$\%\{\mathbf X\}$"))

    def test_literal_bodies(self) -> None:
        self.assertFalse(scan(r"\verb|$\mathbf X| \verb*+\mathrm X+ \detokenize{\mathcal X}")["occurrences"])
        for name in sorted(detector.VERBATIM_ENVS):
            with self.subTest(environment=name):
                result = scan(r"\begin{" + name + r"}$\mathbf X\end{" + name + "}" + r"\mathrm Y")
                self.assertEqual([row["command"] for row in result["occurrences"]], ["mathrm"])

    def test_literal_references_are_not_invocations(self) -> None:
        result = scan(r"\string\mathbf \meaning\mathrm \let\saved=\mathcal \boldsymbol X")
        self.assertEqual([row["command"] for row in result["occurrences"] if row["candidate"] == "yes"], ["boldsymbol"])
        self.assertEqual(len(result["occurrences"]), 4)
        self.assertTrue(all(row["token_role"] != "invocation token" for row in result["occurrences"][:3]))

    def test_definition_body_and_target_roles(self) -> None:
        result = scan(r"\newcommand{\F}[1]{\mathbf{#1}} \mathbf X \renewcommand{\mathbf}[1]{\mathrm{#1}}")
        found = [row for row in result["occurrences"] if row["candidate"] == "yes"]
        self.assertEqual([row["context_category"] for row in found],
                         ["deferred definition body", "lexically plain text", "deferred definition body"])
        targets = [row for row in result["occurrences"] if row["token_role"] == "declaration target"]
        self.assertEqual(len(targets), 1)
        self.assertFalse(candidates(r"\newcommand{\F}[1]{\ensuremath{\mathbf{#1}}}"))
        self.assertEqual(candidates(r"\def\F#1{\mathbf{#1}}")[0]["context_category"], "deferred definition body")
        self.assertEqual(candidates(r"\NewDocumentCommand{\F}{m}{\mathbf{#1}}")[0]["context_category"], "deferred definition body")
        self.assertEqual(len(candidates(r"\newenvironment{synthetic}{$\mathbf X$}{\mathrm{Y}}")), 1)

    def test_deferred_defaults_and_literal_parameter_signatures(self) -> None:
        default = candidates(r"\newcommand{\foo}[1][\mathrm X]{#1}")
        self.assertEqual(len(default), 1)
        self.assertEqual(default[0]["context_category"], "deferred definition body")
        result = scan(r"\def\foo#1\mathrm#2{#1#2}\mathbf X")
        self.assertEqual([row["command"] for row in result["occurrences"] if row["candidate"] == "yes"], ["mathbf"])
        self.assertEqual(result["occurrences"][0]["token_role"], "literal definition-signature token")
        self.assertEqual([row["command"] for row in candidates(r"\def\foo$#1{#1}\mathbf X")], ["mathbf"])

    def test_nonliteral_box_dimensions_keep_uncertain_candidates(self) -> None:
        source = r"\newcommand{\W}[1]{#1}\(\hbox to \W{2em}{\mathrm{X}}\)"
        result = scan(source)
        found = [row for row in result["occurrences"] if row["candidate"] == "yes"]
        self.assertEqual([row["command"] for row in found], ["mathrm"])
        self.assertEqual(found[0]["observed_mode"], "unknown")
        self.assertIn("unsupported box dimension", {row["kind"] for row in result["notes"]})

    def test_unclosed_or_recovered_math_is_retained_as_uncertain(self) -> None:
        for source in (r"$\mathbf X", r"\[\mathbf X\)", r"\begin{equation}\mathbf X", r"${\mathbf X$"):
            with self.subTest(source=source):
                result = scan(source)
                found = [row for row in result["occurrences"] if row["candidate"] == "yes"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["observed_mode"], "unknown")
                self.assertTrue(result["notes"])
        result = scan(r"\def\open{$\mathbf X}\mathrm Y")
        found = [row for row in result["occurrences"] if row["candidate"] == "yes"]
        self.assertEqual([row["context_category"] for row in found], ["deferred definition body", "lexically plain text"])

    def test_unknown_environments_and_catcodes_produce_notes(self) -> None:
        result = scan(r"\begin{synthetic}\mathbf X$\mathcal Y$\end{synthetic}\makeatletter")
        self.assertEqual([row["command"] for row in result["occurrences"] if row["candidate"] == "yes"], ["mathbf"])
        self.assertTrue(all(row["file_has_lexical_notes"] == "yes" for row in result["occurrences"]))
        self.assertEqual({row["kind"] for row in result["notes"]}, {"unrecognized environment mode", "uninterpreted execution signal"})

    def test_line_and_character_coordinates(self) -> None:
        result = scan("% synthetic\r\né \\mathrm X\n")
        self.assertEqual((result["occurrences"][0]["line"], result["occurrences"][0]["column"]), (2, 3))
        self.assertEqual(result["lines"], 2)


class ReportFixtures(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="math-font-report-fixture-")
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        (self.sources / "dip").mkdir(parents=True)
        (self.sources / "dip" / "p119.tex").write_text(r"SYNTHETIC_PROSE_MARKER \mathbf X", encoding="utf-8")
        (self.sources / "preamble.tex").write_text(r"\newcommand{\F}{\mathrm X}", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_report(self, name: str = "math-font-interim-fixture") -> dict:
        with redirect_stdout(io.StringIO()):
            return detector.run(Namespace(root=self.root, output=Path(name)))

    def test_metadata_only_report_and_source_preservation(self) -> None:
        before = {name: path.read_bytes() for name, path in detector.current_files(self.sources).items()}
        summary = self.run_report()
        self.assertEqual(summary["candidate_occurrences"], 2)
        self.assertEqual(before, {name: path.read_bytes() for name, path in detector.current_files(self.sources).items()})
        output = self.root / "math-font-interim-fixture"
        payload = b"\n".join(path.read_bytes() for path in output.iterdir())
        self.assertNotIn(b"SYNTHETIC_PROSE_MARKER", payload)
        self.assertNotIn(str(self.root).encode(), payload)
        with (output / "CANDIDATES.tsv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual([row["candidate_id"] for row in rows], ["M000001", "M000002"])
        self.assertTrue(all(row["review_status"] == "pending manual review" for row in rows))
        with (output / "SOURCE_HASHES.tsv").open(encoding="utf-8", newline="") as stream:
            hashes = list(csv.DictReader(stream, delimiter="\t"))
        self.assertTrue(all(row["sha256"] == detector.sha(before[row["file"].removeprefix("sources/")]) for row in hashes))

    def test_forbidden_folders_and_symlinks_are_not_opened(self) -> None:
        for folder in ("programme", "notes", "stacks", "NOTES"):
            target = self.sources / folder
            target.mkdir()
            (target / "unread.tex").write_bytes(b"\xff")
        external = self.root / "external-synthetic"
        external.mkdir()
        (external / "unread.tex").write_bytes(b"\xff")
        (self.sources / "symbolic-folder").symlink_to(external, target_is_directory=True)
        (self.sources / "symbolic-file.tex").symlink_to(external / "unread.tex")
        self.assertEqual(self.run_report()["source_files"], 2)

    def test_interim_name_and_overwrite_refusal(self) -> None:
        with self.assertRaisesRegex(ValueError, "interim"):
            self.run_report("final-report")
        self.run_report()
        output = self.root / "math-font-interim-fixture"
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_report()
        self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})

    def test_changed_input_or_file_set_prevents_installation(self) -> None:
        original = detector.recheck_sources
        def changed_content(sources: Path, snapshot: dict) -> None:
            (sources / "dip" / "p119.tex").write_text(r"\mathbb Y", encoding="utf-8")
            original(sources, snapshot)
        with patch.object(detector, "recheck_sources", changed_content):
            with self.assertRaisesRegex(RuntimeError, "source changed"):
                self.run_report("changed-source-interim")
        self.assertFalse((self.root / "changed-source-interim").exists())
        def changed_set(sources: Path, snapshot: dict) -> None:
            (sources / "added.tex").write_text("Synthetic addition.", encoding="utf-8")
            original(sources, snapshot)
        with patch.object(detector, "recheck_sources", changed_set):
            with self.assertRaisesRegex(RuntimeError, "file set changed"):
                self.run_report("changed-set-interim")
        self.assertFalse((self.root / "changed-set-interim").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
