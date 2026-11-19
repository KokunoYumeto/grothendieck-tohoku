# Build phase: after-final-03

Started 2026-11-18T22:02:24Z; finished 2026-11-18T22:03:02Z.

| Layer | Passes | Errors in final pass | Warnings in final pass | Largest overflow | Limit |
| --- | ---: | ---: | ---: | ---: | --- |
| dip | 2 | 0 | 0 | 0.00000 pt | yes |
| fr | 2 | 0 | 0 | 0.00000 pt | yes |
| en | 2 | 0 | 0 | 0.00000 pt | yes |

## Commands

Working directory: `sources/`. Each successful layer ran the following command twice.

- `pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -recorder -output-directory=<build-output> main-dip.tex`
- `pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -recorder -output-directory=<build-output> main-fr.tex`
- `pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -recorder -output-directory=<build-output> main-en.tex`

The temporary output directory is distinct for every layer and phase. The source hash table identifies the exact TeX inputs used. Earlier phase logs are retained.

## Meaning and limits of the report

Sanitized logs replace absolute filesystem locations and email addresses. The logs preserve line count, and DIAGNOSTICS.tsv gives the corresponding original log-line number. Error locations supplied explicitly by pdfLaTeX are distinguished from the last page input observed in its log. An overflow may be emitted after the material that caused it was read; that input context is not an exact physical-page assertion.

PDF source-page anchors give inclusive candidate intervals through the next source-page anchor. REVIEW_GT10PT.tsv lists those candidates for every overflow exceeding 10 pt in the final pass of this phase. Unmapped entries remain unresolved and require manual location. The reviewer must inspect the affected PDF pages and an additional spread across the book. This helper performs no visual examination and certifies no reading, translation, mathematical claim, or preservation of typography.

Requested overflow limit: 2 pt. Final PDFs copied to the delivery folder: yes.
