# Interim terminology recurrence inventory

This helper lists requested literal/regex matches for manual recurrence
review. It makes no diagnosis about wording, translation, mathematics,
typography or scan fidelity. It does not edit TeX, the correction ledger or
review state, and it performs no build or image reading.

## Invocation

From the delivery directory:

```bash
python scripts/recurrence_inventory.py --output terminology-recurrence-interim-01
```

The root defaults to the parent of the script directory. The output must be
a fresh relative directory whose name includes `interim`; existing snapshots
are never overwritten. Use a different output name after further source edits.

Only regular leaf files named `pNNN.tex` in `sources/en`, `sources/dip` and
`sources/fr` are opened. Main files, preambles, scans, ZIPs, protected context
folders and symbolic links are excluded. The printed order is 119–183,
then 185–221. Missing page files are recorded in `SOURCE_INVENTORY.tsv`.
The eligible file set and all source hashes are checked again before the
new report is installed.

## Exact patterns

English patterns use Python regular expressions with `re.IGNORECASE` and
the default Unicode meaning of `\w`. French patterns are case-sensitive.
The common negative lookbehind excludes a preceding word character or
backslash; the trailing negative lookahead excludes a following word
character. This avoids ordinary word substrings and direct control-word
spellings. A hyphenated compound can still contain a matched word.

English multiword separators allow one or more spaces, tabs, CR/LF characters
or literal TeX nonbreaking-space tildes; alternatively, they allow a literal
hyphen with optional spaces/tabs around it. TeX commands and discretionary
hyphens are not removed or normalized.

Each line below gives the family ID followed by its exact regex:

```text
en_direct_limits: (?<![\w\\])direct(?:[ \t\r\n~]+|[ \t]*-[ \t]*)limits?(?!\w)
en_inverse_limits: (?<![\w\\])inverse(?:[ \t\r\n~]+|[ \t]*-[ \t]*)limits?(?!\w)
en_direct_systems: (?<![\w\\])direct(?:[ \t\r\n~]+|[ \t]*-[ \t]*)systems?(?!\w)
en_inverse_systems: (?<![\w\\])inverse(?:[ \t\r\n~]+|[ \t]*-[ \t]*)systems?(?!\w)
en_flabby: (?<![\w\\])flabby(?!\w)
en_schemes: (?<![\w\\])schemes?(?!\w)
en_boundary_elements: (?<![\w\\])boundary(?:[ \t\r\n~]+|[ \t]*-[ \t]*)elements?(?!\w)
en_boundary_homomorphisms: (?<![\w\\])boundary(?:[ \t\r\n~]+|[ \t]*-[ \t]*)homomorphisms?(?!\w)
en_positive_degrees: (?<![\w\\])positive(?:[ \t\r\n~]+|[ \t]*-[ \t]*)degrees?(?!\w)
```

The French families apply separately to `dip` and `fr`. Their words and
internal single spaces are literal; case, plural spelling and spacing are
not broadened.

| French literal | Exact regex |
| --- | --- |
| coefficients | `(?<![\w\\])coefficients(?!\w)` |
| du homomorphisme | `(?<![\w\\])du\ homomorphisme(?!\w)` |
| de homomorphisme | `(?<![\w\\])de\ homomorphisme(?!\w)` |

The report's `PATTERNS.tsv` contains these complete expressions, their flags,
layer bindings and context rules. `INPUT_HASHES.tsv` binds that exact pattern
table and the source inventory.

## Context filtering and limits

The helper requests lexical context at the first and last character of
each raw match from `math_font_context.scan_font_context`. Skipped material
such as comments, literal bodies and certain TeX syntax remains unvisited.
Matches with either endpoint unvisited are retained separately as excluded
raw matches. The `scheme(s)` family additionally excludes recognized math
context; text, deferred/unknown and mixed contexts remain candidates.
Other families retain all visited lexical contexts.

This is a lexical prose filter, not a judgment that a word is used correctly
or even that every text-mode argument is prose. Names, labels and custom
macro arguments may need manual assessment. The scanner starts each file in
assumed text mode, without expanding macros, interpreting package definitions,
evaluating conditionals, reconstructing catcodes or propagating cross-input
state. Unknown environments and unsupported boundaries are documented in
`LEXICAL_NOTES.tsv`; the underlying parser's other limits are described in
`MATH_FONT_CONTEXT.md`.

No formatting normalization joins a phrase interrupted by a TeX command.
Alternative terminology and unrequested spellings are not inferred. Zero
matches for a pattern do not establish terminology consistency or absence
of an issue. All raw regex matches remain available for manual inspection.

## Output fields and ordering

`CANDIDATES.tsv` is sorted by printed page, then `dip`, `fr`, `en`, then source
line/column. `ENGLISH_CANDIDATES.tsv` and `FRENCH_CANDIDATES.tsv` are separate
views. Each row contains a report-local match ID, family, relative file,
layer, printed page, source start/end line and column, exact matched token,
surrounding source line, lexical context and `pending manual review` status.
End coordinates are inclusive and count decoded Unicode characters.

For a match spanning lines, `source_line` contains the complete lines from
the first matching line through the last, including their intervening line
breaks. Only the final line ending is removed. TSV quoting preserves embedded
tabs/newlines. `source_line_sha256` hashes the original unfiltered line span
encoded as UTF-8. Privacy-pattern filtering, if needed, changes only the
derived report field and is explicitly marked; source bytes stay unchanged.

Additional files are `ALL_RAW_MATCHES.tsv`, `EXCLUDED_RAW_MATCHES.tsv`,
`FAMILY_COUNTS.tsv`, `PAGE_COUNTS.tsv`, `FILE_SUMMARY.tsv`,
`SOURCE_INVENTORY.tsv`, `SOURCE_HASHES.tsv`, `INPUT_HASHES.tsv`, `PATTERNS.tsv`,
`LEXICAL_NOTES.tsv`, `SUMMARY.json` and `REPORT.md`.

## Synthetic verification and interim run

```bash
python scripts/test_recurrence_inventory.py
python scripts/test_math_font_context.py
```

Thirteen recurrence/probe test methods passed. They cover all requested
families, French case/spacing literalness, boundaries, lexical exclusions,
uncertain contexts, source-line preservation, page/layer ordering, input hashes,
privacy filtering, unchanged sources, forbidden/nonpage/symlink exclusion,
changed-input refusal and immutable output. The existing 23 math-font tests
also passed after the optional probe API was added; default font results are
unchanged in the probe regression fixtures.

The authorized current-source snapshot is `terminology-recurrence-interim-01`,
generated at 2026-11-18T19:06:10Z. It contains 48 pending candidates on 21 pages:
34 English, nine diplomatic French and five corrected French. All 306 page
files were present. No raw match was excluded, and no source-line field needed
privacy filtering in that snapshot. The snapshot remains unchanged; all
content decisions belong to the primary reviewer.
