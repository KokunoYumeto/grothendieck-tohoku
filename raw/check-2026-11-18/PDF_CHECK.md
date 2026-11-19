# PDF check

## Final result

All three editions pass the build and PDF review. The final phase is **after-final-03**, completed 2026-11-18 22:03:02 UTC. Each main file received two successful pdfLaTeX passes. There are no TeX errors, package warnings, or overfull boxes. The PDFs contain 83 diplomatic French pages, 83 corrected French pages, and 81 English pages.

The primary reviewer, GPT-6 Astra in ChatGPT Pro mode, inspected a spread through all three books and every paragraph that had exceeded the 2 pt limit. The final review covers **101 distinct physical PDF pages**: 29 diplomatic, 31 corrected French, and 41 English. Physical PDF page numbers differ from the printed-source margin markers.

## Commands and build provenance

From the delivery root:

```sh
python -B scripts/build_report.py --phase before-final-01 --layers dip fr en --runtime <local> --limit-pt 2
python -B scripts/build_report.py --phase after-layout-01 --layers dip fr en --runtime <local> --limit-pt 2
python -B scripts/build_report.py --phase after-final-03 --layers dip fr en --runtime <local> --limit-pt 2 --publish-pdfs
```

The runtime argument names the temporary pdfLaTeX installation. For an ordinary installed TeX distribution, run each of these commands **twice** from `sources/`:

```sh
pdflatex -interaction=nonstopmode -halt-on-error main-dip.tex
pdflatex -interaction=nonstopmode -halt-on-error main-fr.tex
pdflatex -interaction=nonstopmode -halt-on-error main-en.tex
```

The reporting helper additionally uses `-file-line-error -recorder` and a separate output directory for each layer and phase. Full privacy-filtered logs, commands, source hashes, page mappings and diagnostics are retained in `build-reports/`. The final input captures verify that all 310 TeX files and the correction ledger stayed unchanged through the build.

| Phase | Six pass exits | Final errors | Final package warnings | Overfull paragraphs |
| --- | --- | ---: | ---: | ---: |
| before-final-01 | all 0 | 0 | 15 empty-anchor warnings per layer | 3 in total |
| after-layout-01 | all 0 | 0 | 0 | 0 |
| after-final-03 | all 0 | 0 | 0 | 0 |

Intermediate phases `after-final-01` and `after-final-02` are retained as superseded build records. They are not the delivered PDF source binding.

## Overflow comparison

| Layer | Printed source page and TeX lines | Before (pt) | Final (pt) |
| --- | --- | ---: | ---: |
| Diplomatic French | p199, lines 6–12 | 2.83362 | 0 |
| Corrected French | p199, lines 6–12 | 4.30376 | 0 |
| English | p178, lines 57–71 | 6.10078 | 0 |

No paragraph or display exceeded 10 pt in the diagnostic build. Thus the mandatory set of pages with a previous overflow over 10 pt is empty. The review nevertheless includes all above-limit locations and surrounding pages.

R012002 increases `\emergencystretch` from 2em to 4em, changing line-breaking flexibility without changing text. R012003 gives `\SourceFootnote` an explicit current footnote-counter argument, preserving the original visible labels while removing empty-anchor warnings. R012004 locally disables the French footnote-label dot; the original labels are `11)` and `12)`, not `11).` and `12).`.

Five final-pass underfull diagnostics remain. They were inspected and accepted as readable; no warning suppression was added:

| Layer | Printed source | Badness | Physical PDF pages inspected | Observation |
| --- | --- | ---: | --- | --- |
| dip | p151, lines 16–21 | 10000 | 24 | Some expanded word spaces near inline formulas; text and indices clear. |
| fr | p151, lines 17–22 | 10000 | 24–25 | Same spacing issue; adjacent side diagram and footnote remain separate. |
| dip | p199, lines 6–12 | 1270 | 61–62 | Long direct-limit formula wraps within the margins; footnote 10 intact. |
| fr | p199, lines 6–12 | 1270 | 61–62 | Corrected limit index and all terms readable; no overlap. |
| en | p178, lines 57–71 | 1810 | 40–41 | A few formula-heavy lines have loose spacing, but the former overflow is removed and every symbol is readable. |

## Defects found by actual PDF inspection

1. **Footnote calls 11 and 12.** `\SourceFootnote` creates the body but not the call. Calls were missing on printed pp217–218 in all three layers. The six existing correction rows R011292, R011321, R011350, R011399, R011445 and R011491 were amended and second-read against the scans. Call 11 follows the preceding period; call 12 precedes the final period. The primary inspected all six complete footnote-bearing PDF pages: dip79–80, fr79–80 and en77–78. Both calls and the undotted body labels are visible and correctly placed.
2. **The inverted h on printed p221.** The earlier diplomatic rendering placed the entire turned letter below the baseline. The original image has the inverted bowl at x-height and a right descender. R011885 was amended to set the rotated letter using the measured x-height. The primary compared the original enlargement with a compiled before/after specimen, then inspected final dip PDF83. The baseline now matches the original. See `evidence/p221-inverted-h.png` and `evidence/p221-turned-h-baseline-specimen.png`.
3. **English page-boundary defects.** The English PDF exposed duplicated “conditions” across printed pp129–130. A primary recurrence check of all 100 adjacent source boundaries found four further defects: duplicated “it” (141/142), omitted opening parentheses (154/155 and 163/164), and “a exact” (161/162). R012005–R012009 record the five minimal repairs, each with enlarged original-image evidence and a confirmed second reading. The primary inspected the resulting final English PDF9,17,25,30,31 and neighboring pages. All five repaired sentences are now complete and correctly punctuated. See `PAGE_BOUNDARY_REVIEW.md` and its 100-row table.

## Final visual coverage and image identity

Images were rendered at 160 dpi. The earlier 91-page inspection is preserved in `PDF_VISUAL_REVIEW.after-final-02.tsv`, including its two explicitly observed defects. The final 101-row table is `PDF_VISUAL_REVIEW.tsv`; each row contains its actual viewed image hash, PDF hash, date, reviewer, selection reason and observation.

The entire 247-page final set was compared with phase02 using exact raster pixels and dimensions. Both the full comparison and the independent PyMuPDF comparison found exactly six changed physical pages: dip83 and en9,17,25,30,31. The other 241 pages are pixel-identical. Pixel equality is an image-identity check, not a new visual or mathematical judgment.

The primary explicitly carried **89 prior observations** only where the complete page image is identical. The primary freshly inspected **12 final-phase pages**: dip83 and en8,9,15,17,18,24,25,26,30,31,32. These include all six changes and all ten added targets. The final table records which method was used; carried rows retain the original inspection time and add the final binding time. `PDF_VISUAL_REVIEW_BINDING.json` records the binding. Mechanical render metadata and comparisons are retained in `pdf-review-final-03/` without returning hundreds of full-page images.

| Layer | Physical PDF pages inspected and bound to the final PDF | Count |
| --- | --- | ---: |
| dip | 1, 2, 9, 10, 16, 17, 20, 23, 24, 30, 36, 37, 42, 46, 47, 48, 55, 56, 61, 62, 65, 66, 72, 73, 79, 80, 81, 82, 83 | 29 |
| fr | 1, 2, 9, 10, 16, 17, 20, 23, 24, 25, 30, 31, 36, 37, 42, 46, 47, 48, 55, 56, 61, 62, 65, 66, 72, 73, 79, 80, 81, 82, 83 | 31 |
| en | 1, 2, 8, 9, 10, 15, 16, 17, 18, 19, 20, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 34, 35, 40, 41, 44, 45, 46, 53, 54, 59, 60, 63, 64, 70, 71, 77, 78, 79, 80, 81 | 41 |

The spread covers front matter and introductions, all five chapters, the start and end of both original parts, the bibliography, dense formula pages, spectral-sequence formulas, footnotes, commutative diagrams, and the original p150 typography problem. Specific observations include:

- The printed mathematical alphabets remain distinguishable, including bold category letters, italic resolving functors, script/Gothic notation, and bold sheaf Hom/Ext versus ordinary Hom/Ext.
- The augmentation on printed p150 remains `A → C(A)`; display placement and emphasis are preserved in the diplomatic layer.
- The compact side diagrams on pp152 and203 fit beside their paragraphs; labels, primes and arrows remain distinct.
- Long Ext/Tor expressions, nested inverse-image indices, cochain omission hats and large sums/products remain legible and inside the text area.
- The two-line exact sequences, final zero terms, formula numbers, source-page markers, running heads and footnotes do not overlap.
- Blank lower space at the end of Part I and on the bibliography page is intentional pagination; no content is lost there.

## Delivered PDF hashes

| PDF | SHA-256 |
| --- | --- |
| `pdf/main-dip.pdf` | `ba88cc4b6fc4d1eff1d41f340293ce9c05f9de061d05c95f87ed80980023d14c` |
| `pdf/main-fr.pdf` | `5544a6756dbb38fd974d4e904c88b7cc9a135cd69652d0e68de3cc44236b072f` |
| `pdf/main-en.pdf` | `70595a2c3450a0c1ce071a0f71b24d10b2599e1b889c644a27b7b8c97aeccd22` |

The PDF review was completed before opening the research-context folders. Layout approval does not certify the mathematical claims of the book; those are distinguished in `NOTES.md` and `CHECK_EVENTS.tsv`.
