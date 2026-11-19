# TOHOKU_CHECK

This delivery contains a diplomatic French transcription, a corrected French
layer and an English translation of the supplied printed pages 119–183 and
185–221, together with their correction, checking and PDF review records.

**NOTES status: complete.** `NOTES.md` contains **891 notes**: **482 SL,
188 OP, 203 MC, 10 LW and 8 PRG**, with **482 paragraph bindings** and zero
assembly issues.

`CHECK_EVENTS.tsv` contains **1,741 records** for **1,734 distinct statement IDs**.
The **210 prior event records are unchanged**; the **1,531 new records are
background links only**. The scope of individual mathematical checks is recorded
by statement ID. The final mechanical result is recorded in
[FINAL_VALIDATION.md](FINAL_VALIDATION.md).

## Deliverables

| File or directory | Contents |
| --- | --- |
| `pdf/` | The three compiled reading PDFs listed below. |
| `sources/` | Three standalone main files, the shared preamble and the page files for all three layers. The supplied source READMEs and main-file front matter retain their credits and rights notices. |
| `CORRECTIONS.tsv` | The correction ledger, including active records, explicit second-reading verdicts, stable review/event IDs and withdrawn history. |
| `CHECK_RECORD.md` | The sequential page record, source locators, correction counts and documented checking work. |
| `CHECK_EVENTS.tsv` | Individually identified check events and outcomes using the six approved event types. |
| `NOTES.md` | The mathematical and contextual notes associated with those checks and references. |
| `PDF_CHECK.md`, `PDF_VISUAL_REVIEW.tsv`, `PDF_VISUAL_REVIEW_BINDING.json` | The PDF review record and its bindings to the delivered files and inspected images. |
| `build-reports/` | Preserved build phases, source hashes, diagnostics and PDF receipts. The selected publication phase is `after-final-03`. |
| `pdf-review-final-03/` | Final source/page mappings, selected-render metadata and the comparison of all 247 PDF pages. |
| `second-reading/` | Stable row identities and the history of confirmed, amended and withdrawn review decisions. |
| `scripts/`, `validation-policy/` | Build, inventory, validation and packaging helpers and the approved event-validation policy. |
| `FINAL_VALIDATION.md` and companion tables | The final mechanical validation result, its individual checks, privacy findings, inventory and credit-preservation results. |
| Other named report directories | Preserved inventories, classifications, comparison evidence and earlier working snapshots. Their names and status identify their role. |

All paths in this README are relative to the delivery directory. The supplied
notices remain available in `sources/README.md`, `sources/README.fr.md` and the
front matter of the three main files.

## Source layers and PDFs

| Layer | Page-source directory | Page-source files | Published PDF | PDF pages |
| --- | --- | ---: | --- | ---: |
| Diplomatic French (`dip`) | `sources/dip` | 102 | `pdf/main-dip.pdf` | 83 |
| Corrected French (`fr`) | `sources/fr` | 102 | `pdf/main-fr.pdf` | 83 |
| English (`en`) | `sources/en` | 102 | `pdf/main-en.pdf` | 81 |

There are **306 page-source files**, with filenames `p119.tex` through
`p183.tex` and `p185.tex` through `p221.tex` in each layer. The three main files
and shared preamble bring the selected build's TeX inventory to 310 files.
Every printed page has recorded changes in each layer; **there are no unchanged
pages in any layer**. Printed-page source counts and physical PDF-page counts
are separate measures. [M1, M4]

The delivered PDFs match the `after-final-03` build hashes. [M2]

| Published PDF | SHA-256 |
| --- | --- |
| `pdf/main-dip.pdf` | `ba88cc4b6fc4d1eff1d41f340293ce9c05f9de061d05c95f87ed80980023d14c` |
| `pdf/main-fr.pdf` | `5544a6756dbb38fd974d4e904c88b7cc9a135cd69652d0e68de3cc44236b072f` |
| `pdf/main-en.pdf` | `70595a2c3450a0c1ce071a0f71b24d10b2599e1b889c644a27b7b8c97aeccd22` |

## Correction ledger and classifications

`CORRECTIONS.tsv` contains **12,009 retained ledger records**: **11,870 active**
records and **139 withdrawn** records. Active totals exclude withdrawals while
the retained total preserves that history. The totals below count ledger
records rather than unique errors or unique textual changes. [M1]

| Explicit second-reading verdict | Retained records | Included in active count |
| --- | ---: | --- |
| `confirmed` | 11,765 | Yes |
| `amended` | 105 | Yes |
| `withdrawn` | 139 | No |

Recorded confidence degrees are 11,965 `high`, 44 `medium` and 0 `low`.
Every retained record has an explicit second-reading annotation with its
review and event identifiers. [M1]

### Active records by kind and layer

| Kind | as-printed | corrected | English | build | Active total |
| --- | ---: | ---: | ---: | ---: | ---: |
| reading | 292 | 211 | 72 | 0 | 575 |
| misprint of the original | 0 | 482 | 6 | 0 | 488 |
| translation | 0 | 0 | 162 | 0 | 162 |
| typesetting | 2,899 | 2,891 | 2,913 | 4 | 8,707 |
| structure | 624 | 675 | 636 | 3 | 1,938 |
| **Total** | **3,815** | **4,259** | **3,789** | **7** | **11,870** |

These categories are the ledger's recorded `kind` and `layer` values. [M1]

### Mathematical-change classification

All active ledger records have a classification. [M14–M15]

| Active ledger classification | Records |
| --- | ---: |
| Mathematical | 5,520 |
| Nonmathematical | 6,350 |
| Pending | 0 |
| **Total active records** | **11,870** |

The classification applies to ledger rows. Mathematical checks and refinements
are documented individually by statement ID in `CHECK_EVENTS.tsv` and the
associated notes, with the scope and outcome of each check recorded there.

## Build the three layers

### Direct pdfLaTeX commands

Use a working pdfLaTeX installation with the dependencies declared in
`sources/preamble.tex`, including Latin Modern fonts, English and French Babel
resources, the AMS packages, `geometry`, `microtype`, `xcolor`, `paracol`,
`wrapfig`, `graphicx`, `fancyhdr`, `hyperref` and `bookmark`.

Starting in the delivery directory, enter `sources/` and run two passes for
each standalone main file:

```bash
cd sources
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main-dip.tex
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main-dip.tex
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main-fr.tex
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main-fr.tex
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main-en.tex
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main-en.tex
```

These commands produce `main-dip.pdf`, `main-fr.pdf` and `main-en.pdf` in
`sources/`. The delivered reading copies are in `pdf/`.

### Optional report runner and auxiliary runtime

The report runner provides two passes per layer, preserved logs and structured
diagnostics. Runtime preparation is described in `scripts/TEX_RUNTIME.md`;
runner behavior is described in `scripts/BUILD_TOOLS.md`. [M11–M13]

From the delivery directory, with that runtime prepared at `../tmp/tex-runtime`,
use a fresh phase name:

```bash
python -B scripts/build_report.py \
  --phase reproduction-01 \
  --layers dip fr en \
  --runtime ../tmp/tex-runtime \
  --limit-pt 2
```

Reports are written under `build-reports/` and working products under
`../tmp/edition-build/`. Existing phases are preserved, so use another unused
phase name for a later run.

### Recorded publication-build diagnostics

The selected phase `after-final-03` records two successful pdfLaTeX passes for
each layer, with exit codes `0,0`. [M2]

| Layer | Final-pass errors | Final-pass warnings | Final-pass overfull boxes | Largest overfull amount | Final-pass underfull boxes |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dip` | 0 | 0 | 0 | 0.00000 pt | 2 |
| `fr` | 0 | 0 | 0 | 0.00000 pt | 2 |
| `en` | 0 | 0 | 0 | 0.00000 pt | 1 |

The final-pass underfull diagnostics remain in the logs and review record.
Their locations and details are recorded in the build diagnostics. [M2–M3]

## PDF review and provenance

`PDF_VISUAL_REVIEW.tsv` contains **101 inspected-page records**: 12 record fresh
inspection of the final rendering, and 89 record an explicit carry of a prior
observation after exact image comparison. The whole table is bound by
`PDF_VISUAL_REVIEW_BINDING.json`. [M5–M6]

The saved comparison covers all **247 PDF pages**: 241 compare identically and
six have changed-page keys. The comparison receipt is
`pdf-review-final-03/FITZ_ALL_PAGES_COMPARISON.json`. [M6–M7]

The provenance audit records **2,300 matching mechanical checks**, zero
unresolved or mismatched hash bindings, and exact resolution of all 101 reviewed
image filenames. Eighteen reviewed PNG hashes differ from the standard-render
hashes; their identified primary or special image files and exact bindings
remain recorded in the audit's `ROW_BINDINGS.tsv`. Fresh-observation hashes and
historical table hashes are linked through the observation receipt, final
binding and audit. [M8, M10]

## Preservation and validation

Exact byte comparisons recorded passes for the two supplied source READMEs and
the three main-file prefixes through their first page input. The notices in
those files retain their original bytes. M9 below identifies the retained
preservation-check snapshot. The final mechanical result is in
[FINAL_VALIDATION.md](FINAL_VALIDATION.md), with its companion check, privacy,
inventory and credit-conflict tables. [M9]

Final validation checks source/build/PDF bindings, record structure, confidence
metadata, privacy and the approved event policy. FINAL packaging requires all
eight named event checks as well as the other existing gates. Refutation rows
are selected only by exact equality to the approved event type; their literal
references must bind to the local statement-ID catalog. The contract and its
limits are documented in `scripts/CHECK_EVENTS_VALIDATION.md`.

## Metadata evidence

Each SHA-256 below binds the complete named metadata input supporting the
figures and preservation records in this README. Historical reports retain
their own snapshot status.

| ID | Metadata input | SHA-256 |
| --- | --- | --- |
| M1 | `CORRECTIONS.tsv` | `94e02f79955e558df521da6f65fed48cb2b64558b6be2ca1ea48c4aa15ea69b2` |
| M2 | `build-reports/after-final-03/SUMMARY.tsv` | `215d179cd16a0a52d8dd5e934fcb4a1929f247a0c992415e9cd7f656c1255967` |
| M3 | `build-reports/after-final-03/DIAGNOSTICS.tsv` | `f25729b846d83181152fd67f58b2c3c9b32718f1a13b5cca2b19301f4f5b8171` |
| M4 | `build-reports/after-final-03/SOURCE_HASHES.tsv` | `c51d622416cd01a16ea53ad5fbbfdef2f426006f09bfdff0c0131357cd2bf87a` |
| M5 | `PDF_VISUAL_REVIEW.tsv` | `cd630850887c2625940d191f32963c08e8a2f7b8c09075c047af35b94ab1cdf3` |
| M6 | `PDF_VISUAL_REVIEW_BINDING.json` | `e0ef8fad276e5014502c1833c1d6f7a50e31aa11bd02bd57fa44d485171c5c6f` |
| M7 | `pdf-review-final-03/FITZ_ALL_PAGES_COMPARISON.json` | `3d2761db5a8c124e2d06394e95e63009eae8b3c3a907dee740e07bff1b3c79a9` |
| M8 | `pdf-review-final-03/PRIMARY_OBSERVATION_HASH_RECEIPT.json` | `ba8722b51dec6ba628ac5b160b07f7d147732360a5e7a62027e67c36cbb90391` |
| M9 | `mechanical-final-gate-integration-interim-01/validation/FINAL_VALIDATION_CHECKS.tsv` | `d915007246349d54a13bcc22ca468794f595fa6ebf6b775ee599dc334789027d` |
| M10 | `mechanical-final-dry-run-interim-01/provenance-audit/FINAL_SUMMARY.json` | `64b9f81b297e79d719fff0351a9a8682a6c54740bdc03454fe431679a9b31a7c` |
| M11 | `scripts/build_report.py` | `e74f7be3c0267b4d962331bb0f2677a1fec9bd68adb941db17c626d2f80bbf3f` |
| M12 | `scripts/TEX_RUNTIME.md` | `4610dbbeee096ae777458c89d51cdd828cdf5b73e6fe8e048dca2b64b0e6b3a2` |
| M13 | `scripts/BUILD_TOOLS.md` | `ed0dbfe1dfe5c6b899bb0102aa53dfa8e906e8d16c3cea8905089bef45e341a2` |
| M14 | `math-classification-expanded-final-interim-03/SUMMARY.json` | `1bd12aea94d597d67f82b55abde609fe0e08615bdaf11588a1d3f29269dbf7a5` |
| M15 | `ENGLISH_SEAM_CLASSIFICATION_COVERAGE_05.json` | `052d6857c9433962803c994ac28e92ba7ead4aabf875fb7b073f2444b45ac3c7` |

The 306-path page-filename inventory has SHA-256
`c72dae87f16fafd82afcfc338a0f403522e977a70eab08886e4e3bca77ba9d54`.
Its input is the UTF-8 encoding of all delivery-relative page-source paths,
sorted lexicographically, joined with LF and terminated by one LF. Content
hashes are recorded separately in the selected build's source manifest. [M4]
