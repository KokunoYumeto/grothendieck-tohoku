# Pending plain math-capital inventory

`plain_math_capitals.py` inventories literal, unwrapped capital `C`, `O`, `U`,
`V` and `Z` character tokens in recognized lexical math in the 102 diplomatic
page files. Every finding remains pending; the helper makes no correctness,
font-choice, source-fix or scan-reading judgment.

From the delivery directory:

```bash
python scripts/plain_math_capitals.py --output plain-math-capitals-interim-01
```

From the directory above the delivery:

```bash
python TOHOKU_CHECK/scripts/plain_math_capitals.py --output plain-math-capitals-interim-01
```

Use a new output directory on every run. `--root` is optional and defaults to
the helper's delivery directory. `--context-chars 120` is the default; the
permitted range is 40–240 characters. Only regular leaf `sources/dip/pNNN.tex`
files are read. All 102 expected files must exist, with no extra TeX files;
missing pages are never silently counted as zero. No ledger, review state,
event table, source ZIP, main, preamble, scan or context folder is opened.

## Selection and exclusions

The existing `math_font_context.scan_font_context` probes establish lexical
mode. A candidate must be a visited ordinary character in nondeferred,
recognized math, with no supplementary exclusion or uncertainty. Control-word
names, comments, verbatim material and known literal token references are
skipped by the lexical helpers. Known text arguments remain text unless an
explicit nested math construction re-enters math.

Explicit groups or single-token arguments of known math-font commands are
excluded, including `\mathbf C`, `\mathbf{C}`, nested wrappers, `\mathcal`,
`\mathbb`, `\mathrm`, `\mathfrak`, `\mathscr`, `\boldsymbol`, `\bm` and the
other exact names recorded in `RULES.json`. Comments and whitespace before an
argument are consumed lexically. Known label/reference arguments, including
`\label`, `\LayerTarget`, `\ref`, `\eqref` and citation commands, are excluded.

Unrecognized environments are uncertain within their lexical span. Unresolved
boundary/execution notes conservatively demote otherwise-math matches for the
whole file. Declaration-style font commands such as `\cal` or `\bf` make
subsequent otherwise-math matches uncertain because their scope is not
executed. These conservative cases can suppress otherwise valid candidates;
they remain visible separately and are never described as recognized math.

No macro expansion, package loading or catcode execution occurs. Custom font
macros, custom argument conventions, math opened in another input file, and
nonstandard literal environments remain limitations. Each file starts in
assumed text mode. A zero count is not a correctness or absence certificate.
Adjacent target letters are separate character matches, not inferred words.

## Reports

| File | Contents |
| --- | --- |
| `CANDIDATES.tsv` | Page-ordered plain capitals in recognized lexical math, with short contexts and pending status. |
| `UNCERTAIN_MATCHES.tsv` | Raw target capitals whose context is unresolved or deferred. |
| `EXCLUDED_RAW_MATCHES.tsv` | Known wrapped, label/reference, text, and skipped-syntax matches. |
| `ALL_RAW_MATCHES.tsv` | Every literal target capital, assigned exactly one disposition. |
| `PAGE_COVERAGE.tsv` | All 102 pages with raw, candidate, uncertain and excluded-category counts, including zeros. |
| `PAGE_CAPITAL_COUNTS.tsv` | All 510 page/capital combinations with the same disposition counts. |
| `LEXICAL_NOTES.tsv` | Parser boundary, unsupported-construction and conservative-exclusion notes. |
| `SOURCE_HASHES.tsv` | Original byte counts and SHA-256 values for the 102 source files. |
| `INPUT_HASHES.tsv` | Hashes of the complete source-hash table and exact rules payload. |
| `RULES.json` | Capitals, page order, known wrapper/reference commands and uncertainty policy. |
| `SUMMARY.json`, `REPORT.md` | Totals, scope and limitations. |

Coordinates are one-based decoded-character line/column positions; LF defines
physical lines. A leading UTF-8 BOM is removed for lexical positions. Snapshot
match IDs are not review/correction IDs. Source-line hashes bind the complete
original decoded line with its CR/LF ending removed.

Contexts are filtered for recognizable private paths/emails **before** they
are cropped, with `context_privacy_filtered=yes` whenever changed. Cropping
and filtering can remove the target from the short excerpt; original source
coordinates remain authoritative. These are marked derived contexts, not
claims of exact source quotation. Every final payload is privacy-scanned;
remaining findings block installation. Sources are never redacted or edited.

The input file set and hashes are rechecked immediately before installation.
Output names must be relative, fresh and explicitly contain `interim`;
source, PDF, review-state and context trees are protected. Existing reports
are never overwritten. No build is performed.
