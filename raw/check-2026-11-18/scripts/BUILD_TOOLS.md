# Build and final-validation helpers

These tools were prepared without inspecting edition page files or scans.
Preparing them did not run an edition build. Actual build results are recorded
only when the build runner is invoked later.

## Before and after build phases

From the delivery directory:

```bash
python scripts/build_report.py --phase before
```

The runner requires `progress.log` to contain all 102 page-completion entries,
once each and in printed order. It then runs two pdfLaTeX passes for each of
`main-dip.tex`, `main-fr.tex` and `main-en.tex`, using `sources/` as the working
directory and the existing task-local TeX runtime. The `--system-tex` option
selects a normally configured system installation instead.

A fatal first pass is recorded as a failure; the runner does not describe an
identical rerun of that fatal error as a completed second pass. It continues
with the other selected layers so that their independent diagnostics are
available. No source is modified.

After the primary reviewer has fixed the reported typesetting issues, use a
new phase name:

```bash
python scripts/build_report.py --phase after-01 --publish-pdfs
```

Earlier phases cannot be overwritten. Each successful phase records the exact
hashes of all TeX inputs. `--publish-pdfs` copies the resulting files into the
delivery's `pdf/` folder only when every selected layer completed both passes
and its largest reported overflow is at most 2 pt. The term refers solely to
copying files within the delivery; it performs no external publication.

The runner emits:

- `REPORT.md`: commands, results, scope and limitations.
- `SUMMARY.tsv`: exit statuses, page counts, diagnostic counts, overflow
  maxima, and PDF hashes.
- `SOURCE_HASHES.tsv`: the exact source state used by the build phase.
- `DIAGNOSTICS.tsv`: errors, warnings, underfull boxes and overfull boxes from
  both passes, including sizes and source-input context.
- `PDF_SOURCE_MAP.tsv`: physical PDF-page candidates obtained from the
  existing source-page hyperlink destinations.
- `REVIEW_GT10PT.tsv`: candidates requiring visual location and inspection
  because a final-pass overflow exceeded 10 pt.
- One sanitized TeX log and process-output transcript for each attempted pass.

The raw logs and working PDFs remain outside the delivery tree. The retained
copies replace absolute filesystem paths and email addresses while preserving
line count. Edition-relative locators remain usable. The source files,
front matter, credits and rights notices are never changed by this process.

### Page-location limits

An explicit pdfLaTeX file-and-line error is distinguished from the last page
input observed in the log. Overfull-box diagnostics are sometimes emitted
after their material was read, so the latter context is not an exact claim
about the physical page.

The PDF's named source-page destinations give an inclusive range through the
next source-page destination. The range is deliberately described as a set
of candidates. An unmapped overflow remains unresolved. The primary reviewer
must locate and inspect the actual affected pages and the requested spread
across the book. These helpers perform no visual review and do not write a
claim of visual success into `PDF_CHECK.md`.

## Final mechanical validation

Run the final validator with the supplied original source ZIP and the chosen
final build phase:

```bash
python scripts/final_validate.py --original-sources TOHOKU_sources.zip --final-phase after-01
```

Provide the actual relative location of the original ZIP. The validator
creates a Markdown report and TSV tables for checks, privacy locations,
protected-source credit/rights conflicts and inventory. It scans returned
textual files independently of extension, including helper scripts. It creates
no archive and makes no edits to the edition.

The checks cover the 102-file sets in all three layers, main files, required
records, completion markers, page-section headings, correction-ledger schema,
nonempty evidence cells, explicitly provisional confidence wording, recognized
degrees plus explicit second-reading verdicts and canonical R/E identifiers,
unique row/event identifiers, obvious placeholder wording, privacy patterns,
and build provenance. The selected
build must match every current TeX hash, meet the 2 pt limit, and have PDF
hashes matching the delivered files.

Use annotated second-reading exports for final confidence cells. Plain
degrees alone cannot pass. See `REVIEW_METADATA_GATES.md` for exact accepted
forms and the synthetic verification; these metadata checks do not establish
the correctness of any reading or independently replay its event history.

The optional original-source comparison checks both supplied source READMEs
byte for byte, and all three main files through the first page input. The
diplomatic main uses the supplied French prefix as its reference. An
intentional change anywhere in those prefixes needs manual review; this broad
check does not silently exempt a rights or credit change. Privacy findings in
unchanged protected regions are reported separately and remain blockers;
credits are never automatically edited or silently waived.

An optional `--archive` argument verifies an already-created ZIP's size,
member names, CRCs, current file bytes and privacy. Repeat it for every split
part. Every textual member, generated manifest, member name, ZIP/member comment
and reconstructed logical chunked file is examined. This postcheck is read-only
by default and compares all current validation-report bytes too. Optional
`--report-dir` output must be outside the delivery tree for an archive check.

Potential privacy matches are reported by location, without copying the
matched text. A mathematical expression or a regular expression can resemble
a path, so a reported match requires review. Nothing is automatically
redacted or normalized in source files.

A passing mechanical report is not evidence that a scan reading, translation,
mathematical claim, correction rationale, note, or visual check was performed.
Those records and judgments remain the primary reviewer's responsibility.

## Final archive

After the required work and final validation are complete:

```bash
python scripts/checkpoint.py preflight
python scripts/checkpoint.py final
```

This produces `TOHOKU_CHECK.zip` beside the delivery directory, with the same
complete-current-deliverables policy and exclusions as the hourly checkpoints.
It is a final delivery, so the hourly checkpoint clock does not apply. It
requires the ordered 102 page-completion entries, required final files and a
current successful final-validation report containing the explicit-confidence
and unique-review-identifier checks as well as both privacy checks. Preflight compares the complete
included-file set, sizes and hashes against that report. Only the five exact
generated report names are excluded from their own stale-inventory comparison;
they are still inspected and freshly bound to the packaged bytes. Final mode
runs preflight automatically. These checks do not replace substantive review.

The helper verifies the archived bytes against SHA-256 values and checks ZIP
CRCs and the complete archive-set privacy scan before exposing the finished
archive. Every ZIP is strictly below
500,000,000 bytes. If splitting is needed, it uses `TOHOKU_CHECK_part1.zip`,
`TOHOKU_CHECK_part2.zip`, and so forth, with the file list in the first part.
Existing final archives and earlier checkpoints are never overwritten or
nested. An optional `--previous` names the last successfully saved checkpoint
for unchanged-file references; all current deliverables are still included.

`--dry-run` reports metadata only and creates nothing. The `create --number N`
action remains the hourly-checkpoint command and retains its time guard.

After packaging, a read-only byte/privacy check can be run with:

```bash
python scripts/final_validate.py --original-sources TOHOKU_sources.zip --final-phase after-01 --archive ../TOHOKU_CHECK.zip
```

See `FINAL_PRIVACY_COVERAGE.md` for the exact privacy coverage, protected-source
conflict handling and remaining pattern/binary-image limits.

## Verification of the helpers

Python syntax and synthetic diagnostic/privacy cases were checked during
preparation. The synthetic cases exercised an overfull box with its printed
page and line interval, an explicit TeX error, warnings, and redaction of
filesystem paths and email addresses while preserving web URLs. No edition
build, final validation, page reading or PDF inspection was performed as part
of this helper preparation.
