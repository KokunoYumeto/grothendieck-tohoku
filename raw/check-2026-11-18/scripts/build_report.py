"""Run later edition builds and retain privacy-safe diagnostic reports.

This helper never edits an edition source. Its run action requires all 102
ordered page-completion entries before it invokes pdfLaTeX. Diagnostics locate
the last page input and candidate physical PDF pages, not a visual verdict.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess

from tex_runtime import environment as local_tex_environment
from privacy_guard import EMAIL, WINDOWS_PATH, POSIX_PATH, safe_location

PRINTED_PAGES = list(range(119, 184)) + list(range(185, 222))
PAGE_INPUT = re.compile(r"\((?:[^()\s]*/)?((dip|fr|en)/p(\d{3})\.tex)\b")
FILE_ERROR = re.compile(r"^(.+?\.(?:tex|sty|cls|ldf)):(\d+):\s*(.*)")
OVERFULL = re.compile(r"Overfull \\([hv])box \(([\d.]+)pt too (wide|high)\)")
UNDERFULL = re.compile(r"Underfull \\([hv])box \(badness (\d+)\)")
WARNING = re.compile(r"^(?:LaTeX(?: Font)?|Package \S+|Class \S+|pdfTeX|LuaTeX).*?\bwarning\b", re.I)
SOURCE_LINE = re.compile(r"(?:at lines?|on input line|at line)\s+(\d+)(?:--(\d+))?")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_text(text: str, sources: Path | None = None) -> str:
    if sources is not None:
        # Preserve a useful edition-relative locator before masking other paths.
        source_prefix = str(sources.resolve())
        text = text.replace(source_prefix + os.sep, "sources/")
    return safe_location(text)


def write_tsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def completed_pages(root: Path) -> list[int]:
    progress = root / "progress.log"
    if not progress.is_file():
        return []
    return [int(value) for value in re.findall(r"(?m)^page (\d{3}) done\s", progress.read_text(encoding="utf-8"))]


def require_completed_pages(root: Path) -> None:
    pages = completed_pages(root)
    if pages != PRINTED_PAGES:
        raise RuntimeError(
            "Edition builds are gated until progress.log contains each of the "
            "102 printed pages exactly once, in printed order."
        )


def source_locator(value: str) -> tuple[str, str]:
    match = re.search(r"((?:dip|fr|en)/p(\d{3})\.tex)", value.replace("\\", "/"))
    if match:
        return match.group(1), match.group(2)
    return Path(value).name, ""


def diagnostics(log: str, layer: str, pass_number: int) -> list[dict]:
    lines = log.splitlines()
    current_file, current_page = f"main-{layer}.tex", ""
    result = []
    for index, line in enumerate(lines):
        matches = list(PAGE_INPUT.finditer(line))
        if matches:
            current_file, current_page = matches[-1].group(1), matches[-1].group(3)
        kind, amount, orientation = "", "", ""
        exact_file, exact_line = "", ""
        overfull = OVERFULL.search(line)
        underfull = UNDERFULL.search(line)
        file_error = FILE_ERROR.match(line)
        if overfull:
            kind, orientation, amount = "overfull", overfull.group(1), overfull.group(2)
        elif underfull:
            kind, orientation = "underfull", underfull.group(1)
        elif file_error:
            kind = "error"
            exact_file, exact_page = source_locator(file_error.group(1))
            exact_line = file_error.group(2)
        elif line.startswith("!"):
            kind = "error"
        elif WARNING.match(line.strip()):
            kind = "warning"
        elif "Fatal error occurred" in line or "Emergency stop" in line:
            kind = "fatal"
        if not kind:
            continue
        block = [line]
        for following in lines[index + 1:index + 13]:
            if not following.strip():
                break
            if OVERFULL.search(following) or UNDERFULL.search(following) or WARNING.match(following.strip()) or following.startswith("!"):
                break
            block.append(following)
        detail = "\n".join(block)
        line_match = SOURCE_LINE.search(detail)
        source_lines = exact_line or (
            line_match.group(1) + ("--" + line_match.group(2) if line_match.group(2) else "")
            if line_match else ""
        )
        source_file = exact_file or current_file
        source_page = source_locator(source_file)[1]
        result.append({
            "layer": layer, "pass": pass_number, "kind": kind,
            "orientation": orientation, "amount_pt": amount,
            "input_context": source_file, "printed_page": source_page,
            "source_lines": source_lines,
            "context_basis": "explicit file-line error" if exact_file else "last page input observed in TeX log",
            "pdf_page_candidates": "", "log_line": index + 1,
            "detail": detail,
        })
    return result


def pdf_source_map(pdf: Path) -> tuple[int, dict[int, list[int]], str]:
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    anchors = []
    for name, destination in reader.named_destinations.items():
        match = re.fullmatch(r"tohoku:source-page:(\d{3})(?::(?:dip|fr|en):ed)?", name)
        if match:
            anchors.append((int(match.group(1)), reader.get_destination_page_number(destination) + 1))
    anchors.sort()
    mapping = {}
    for index, (printed, first) in enumerate(anchors):
        last = anchors[index + 1][1] if index + 1 < len(anchors) else len(reader.pages)
        mapping[printed] = list(range(first, max(first, last) + 1))
    basis = "named source-page destinations; inclusive interval through the next source-page anchor"
    if not anchors:
        basis = "no recognized source-page destinations; PDF locations require manual resolution"
    return len(reader.pages), mapping, basis


def apply_pdf_context(rows: list[dict], mapping: dict[int, list[int]]) -> None:
    for row in rows:
        if row["printed_page"]:
            row["pdf_page_candidates"] = ",".join(map(str, mapping.get(int(row["printed_page"]), [])))


def portable_command(layer: str) -> str:
    return (
        "pdflatex -interaction=nonstopmode -halt-on-error -file-line-error "
        f"-recorder -output-directory=<build-output> main-{layer}.tex"
    )


def run_builds(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    require_completed_pages(root)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.phase):
        raise RuntimeError("Use a simple, unique phase name, for example before or after-01.")
    sources = root / "sources"
    for layer in args.layers:
        if not (sources / f"main-{layer}.tex").is_file():
            raise RuntimeError(f"Missing main-{layer}.tex; the helper does not create or edit source files.")
    report = root / "build-reports" / args.phase
    if report.exists():
        raise RuntimeError("This report phase already exists; use a new phase name to preserve earlier logs.")
    work = (args.work or root.parent / "tmp/edition-build") / args.phase
    work = work.resolve()
    if work == root or root in work.parents:
        raise RuntimeError("Raw build outputs must be outside the delivery tree; only sanitized reports are retained inside it.")
    if work.exists():
        raise RuntimeError("This temporary build phase already exists; use a new phase name.")
    runtime = (args.runtime or root.parent / "tmp/tex-runtime").resolve()
    env = os.environ.copy() if args.system_tex else local_tex_environment(runtime)
    report.mkdir(parents=True)
    work.mkdir(parents=True)
    started = utc()
    version = subprocess.run(["pdflatex", "--version"], capture_output=True, text=True, env=env)
    (report / "ENGINE.txt").write_text(sanitize_text(version.stdout + version.stderr, sources), encoding="utf-8")
    fingerprints = []
    for source in sorted(sources.rglob("*.tex")):
        fingerprints.append({
            "file": source.relative_to(sources).as_posix(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        })
    write_tsv(report / "SOURCE_HASHES.tsv", ["file", "sha256"], fingerprints)
    all_rows, summary, source_map_rows, review_rows = [], [], [], []
    final_pdfs = {}
    for layer in args.layers:
        output = (work / layer).resolve()
        output.mkdir()
        public = report / layer
        public.mkdir()
        layer_rows, pass_codes = [], []
        for pass_number in (1, 2):
            command = [
                "pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                "-file-line-error", "-recorder", "-output-directory=" + str(output),
                f"main-{layer}.tex",
            ]
            process = subprocess.run(command, cwd=sources, env=env, capture_output=True, text=True, errors="replace")
            pass_codes.append(process.returncode)
            raw_stdout = process.stdout + process.stderr
            (output / f"pass-{pass_number}.stdout.log").write_text(raw_stdout, encoding="utf-8")
            raw_path = output / f"main-{layer}.log"
            raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else raw_stdout
            (output / f"pass-{pass_number}.raw.log").write_text(raw, encoding="utf-8")
            clean = sanitize_text(raw, sources)
            (public / f"pass-{pass_number}.log").write_text(clean, encoding="utf-8")
            (public / f"pass-{pass_number}.stdout.txt").write_text(sanitize_text(raw_stdout, sources), encoding="utf-8")
            rows = diagnostics(raw, layer, pass_number)
            for row in rows:
                row["detail"] = sanitize_text(row["detail"], sources)
                row["input_context"] = sanitize_text(row["input_context"], sources)
            if process.returncode and not any(row["kind"] in {"error", "fatal"} for row in rows):
                rows.append({
                    "layer": layer, "pass": pass_number, "kind": "process-error",
                    "orientation": "", "amount_pt": "", "input_context": f"main-{layer}.tex",
                    "printed_page": "", "source_lines": "", "context_basis": "process exit status",
                    "pdf_page_candidates": "", "log_line": "",
                    "detail": f"pdfLaTeX exited with status {process.returncode}; inspect the sanitized log.",
                })
            layer_rows.extend(rows)
            if process.returncode:
                # Repeating an unchanged fatal build is not a second successful pass.
                break
        pdf = output / f"main-{layer}.pdf"
        pdf_pages, mapping, mapping_basis = 0, {}, "no PDF produced"
        if pdf.is_file():
            try:
                pdf_pages, mapping, mapping_basis = pdf_source_map(pdf)
            except Exception as exc:
                mapping_basis = "PDF mapping failed: " + sanitize_text(str(exc), sources)
        apply_pdf_context(layer_rows, mapping)
        for printed, candidates in mapping.items():
            source_map_rows.append({
                "layer": layer, "printed_page": printed,
                "pdf_page_candidates": ",".join(map(str, candidates)), "basis": mapping_basis,
            })
        final_pass = len(pass_codes)
        final_rows = [row for row in layer_rows if row["pass"] == final_pass]
        overfulls = [row for row in final_rows if row["kind"] == "overfull"]
        max_overfull = max((float(row["amount_pt"]) for row in overfulls), default=0.0)
        success = pass_codes == [0, 0] and pdf.is_file()
        status = "two passes successful" if success else "build incomplete or failed"
        summary.append({
            "layer": layer, "phase": args.phase, "passes_attempted": len(pass_codes),
            "exit_codes": ",".join(map(str, pass_codes)), "status": status,
            "pdf_pages": pdf_pages, "errors_final_pass": sum(row["kind"] in {"error", "fatal", "process-error"} for row in final_rows),
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.is_file() else "",
            "warnings_final_pass": sum(row["kind"] == "warning" for row in final_rows),
            "overfull_count_final_pass": len(overfulls), "max_overfull_pt": f"{max_overfull:.5f}",
            "overfull_gt_2pt": sum(float(row["amount_pt"]) > 2 for row in overfulls),
            "overfull_gt_10pt": sum(float(row["amount_pt"]) > 10 for row in overfulls),
            "limit_passed": "yes" if success and max_overfull <= args.limit_pt else "no",
            "pdf_context_basis": mapping_basis,
        })
        for row in overfulls:
            if float(row["amount_pt"]) > 10:
                candidates = row["pdf_page_candidates"].split(",") if row["pdf_page_candidates"] else [""]
                for candidate in candidates:
                    review_rows.append({
                        "layer": layer, "phase": args.phase, "printed_page_context": row["printed_page"],
                        "candidate_pdf_page": candidate, "amount_pt": row["amount_pt"],
                        "log_line": row["log_line"], "review_status": "not visually inspected by this helper",
                    })
        if success:
            final_pdfs[layer] = pdf
        all_rows.extend(layer_rows)
    diagnostic_fields = [
        "layer", "pass", "kind", "orientation", "amount_pt", "input_context",
        "printed_page", "source_lines", "context_basis", "pdf_page_candidates", "log_line", "detail",
    ]
    write_tsv(report / "DIAGNOSTICS.tsv", diagnostic_fields, all_rows)
    write_tsv(report / "SUMMARY.tsv", list(summary[0]), summary)
    write_tsv(report / "PDF_SOURCE_MAP.tsv", ["layer", "printed_page", "pdf_page_candidates", "basis"], source_map_rows)
    write_tsv(report / "REVIEW_GT10PT.tsv", ["layer", "phase", "printed_page_context", "candidate_pdf_page", "amount_pt", "log_line", "review_status"], review_rows)
    ready = all(row["limit_passed"] == "yes" for row in summary)
    copied = False
    if args.publish_pdfs and ready:
        (root / "pdf").mkdir(exist_ok=True)
        for layer, pdf in final_pdfs.items():
            shutil.copyfile(pdf, root / "pdf" / f"main-{layer}.pdf")
        copied = True
    table = ["| Layer | Passes | Errors in final pass | Warnings in final pass | Largest overflow | Limit |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for row in summary:
        table.append(f"| {row['layer']} | {row['passes_attempted']} | {row['errors_final_pass']} | {row['warnings_final_pass']} | {row['max_overfull_pt']} pt | {row['limit_passed']} |")
    report_text = (
        f"# Build phase: {args.phase}\n\nStarted {started}; finished {utc()}.\n\n"
        + "\n".join(table)
        + "\n\n## Commands\n\nWorking directory: `sources/`. Each successful layer ran the following command twice.\n\n"
        + "\n".join("- `" + portable_command(layer) + "`" for layer in args.layers)
        + "\n\nThe temporary output directory is distinct for every layer and phase. "
        "The source hash table identifies the exact TeX inputs used. Earlier phase logs are retained.\n\n"
        "## Meaning and limits of the report\n\n"
        "Sanitized logs replace absolute filesystem locations and email addresses. "
        "The logs preserve line count, and DIAGNOSTICS.tsv gives the corresponding original log-line number. "
        "Error locations supplied explicitly by pdfLaTeX are distinguished from the last page input observed in its log. "
        "An overflow may be emitted after the material that caused it was read; that input context is not an exact physical-page assertion.\n\n"
        "PDF source-page anchors give inclusive candidate intervals through the next source-page anchor. "
        "REVIEW_GT10PT.tsv lists those candidates for every overflow exceeding 10 pt in the final pass of this phase. "
        "Unmapped entries remain unresolved and require manual location. "
        "The reviewer must inspect the affected PDF pages and an additional spread across the book. "
        "This helper performs no visual examination and certifies no reading, translation, mathematical claim, or preservation of typography.\n\n"
        f"Requested overflow limit: {args.limit_pt:g} pt. Final PDFs copied to the delivery folder: {'yes' if copied else 'no'}.\n"
    )
    (report / "REPORT.md").write_text(report_text, encoding="utf-8")
    print(f"Recorded build phase {args.phase}: {len(summary)} layers, {len(all_rows)} diagnostics.")
    print("Final overflow limit passed:" , "yes" if ready else "no")
    if args.publish_pdfs and not ready:
        raise SystemExit(2)
    if any(row["status"] != "two passes successful" for row in summary):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--phase", required=True, help="Unique phase name, for example before, after-01")
    parser.add_argument("--layers", nargs="+", choices=("dip", "fr", "en"), default=["dip", "fr", "en"])
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--system-tex", action="store_true", help="Use a normally configured system installation")
    parser.add_argument("--limit-pt", type=float, default=2.0)
    parser.add_argument("--publish-pdfs", action="store_true", help="Copy successful PDFs only if every selected layer meets the limit")
    args = parser.parse_args()
    run_builds(args)


if __name__ == "__main__":
    main()
