# Static TeX control-word inventory

This helper compares lexical control-word names in the current TeX tree with
the supplied original source ZIP. It produces candidates for manual review,
not a verdict on TeX validity or editorial correctness. It performs no macro
expansion, external input, page audit or build and changes no source.

## Invocation

From the workspace containing the delivery directory:

```bash
python TOHOKU_CHECK/scripts/control_word_inventory.py --original-sources upload/TOHOKU_sources.zip --output interim-control-words-01 --include-declarations
```

The delivery root defaults to the parent of the script directory. Use
`--root` for a different delivery tree. `--output` is relative to that root
and must name a new directory outside the source and PDF trees. Existing
reports are never overwritten. `--include-declarations` is optional.

Current files under `sources/` are matched to exact ZIP-relative TeX member
names, without a guessed container prefix or basename fallback. A current
file absent from the original ZIP has a zero per-file baseline. Original-only
TeX members still contribute to the original global command vocabulary.
Directories named `programme`, `notes` or `stacks`, in any letter case, and
symbolic links are excluded from lexical inspection.

## Result files

| File | Contents |
| --- | --- |
| `REPORT.md` | Counts, interpretation and limitations of this snapshot. |
| `CANDIDATES.tsv` | Every current file/command pair whose count increased; original/current counts, new-to-file and globally-new flags, all current line numbers and possible original-prefix splits. |
| `CANDIDATE_OCCURRENCES.tsv` | One row for every current candidate occurrence, with one-based physical line and character column. |
| `POSSIBLE_PREFIX_SPLITS.tsv` | Every proper prefix that was an original control word, plus the remaining letters. |
| `GLOBALLY_NEW_COMMANDS.tsv` | Command names absent from the entire eligible original vocabulary. |
| `GLOBAL_COMMANDS.tsv` | Original/current totals for all observed command names. |
| `CONTROL_WORD_COUNTS.tsv` | Per-current-file counts, including unchanged and decreased counts. |
| `FILE_SUMMARY.tsv` | Exact-path matches, unmatched files, line counts and candidate totals. |
| `SOURCE_HASHES.tsv` | Size and SHA-256 for every lexically inspected original member and current source. |
| `INPUT_HASHES.tsv` | Original ZIP hash and a hash binding the combined source-inventory rows. |
| `LEXICAL_NOTES.tsv` | Observed catcode/name-construction signals and incomplete recognized literal boundaries. |
| `CURRENT_DECLARATIONS.tsv` | Optional literal macro-declaration forms and their locations. |

Reports contain command names and structural metadata, with no prose or
formula excerpts. Candidate IDs are specific to the snapshot. All current
occurrences are listed, including ones that already existed; the helper does
not infer which particular occurrence was added.

## Interpretation

For example, if the original vocabulary contained `noindent`, `in` and
`cdot`, new names `noindentAB`, `inZ` and `cdotb` generate possible splits
`noindent` + `AB`, `in` + `Z`, and `cdot` + `b`. All qualifying prefixes are
reported. None is selected as a correction.

A legitimate new macro is still a candidate. When requested, literal forms
of common declarations and definitions are reported separately, including
`newcommand`, `DeclareRobustCommand`, the document-command declarations,
`DeclareMathOperator`, `def` variants, `let` and `futurelet`. This metadata
does not establish execution, intended meaning or validity. It never clears
a candidate. A declaration-name token also contributes to lexical counts.

## Lexical limits

The scanner uses ASCII letters for control words. It consumes escaped
control symbols correctly: paired backslashes do not make the following
plain letters into a command, while a third backslash begins a new token.
Escaped percent signs remain literal; unescaped percent comments are skipped.

Simple `verb` and `verb*` bodies are skipped to the matching same-line
delimiter. Recognized literal environments are `verbatim`, `verbatim*`,
`Verbatim`, `Verbatim*`, `BVerbatim`, `LVerbatim`, `SaveVerbatim`, `lstlisting`,
`minted` and `comment`; their bodies are skipped to the first literal matching
end marker. This is not a package parser or a model of custom delimiters.

Catcodes, `makeatletter`, alternate Unicode letter conventions, `ExplSyntaxOn`,
custom literal macros, macro argument semantics and constructed `csname`
commands are not interpreted. Source occurrences inside ordinary macro
definitions are counted lexically. An absent candidate is not proof that a
file is valid or unchanged in every relevant way.

## Snapshot safeguards and synthetic verification

Before installation, the helper rechecks the current eligible file set,
every current source hash, and the complete original ZIP hash. It reserves
the output directory exclusively. Input changes abort the report; a report
created concurrently is preserved. The ZIP is never extracted or executed.

The lexer also accepts the optional `include_comment_ranges=True` argument
for other mechanical reports. It returns decoded-character comment boundaries
without changing the default occurrence, declaration, count or note results.
`notation_ledger_inventory.py` uses these boundaries to keep exact comment
spellings separate from source tokens.

Sixteen synthetic test groups passed: ordinary wrapper removal; the three
possible merged-word examples; escaped double/triple/four backslashes;
comments and escaped percent signs; inline literal forms; every recognized
literal environment; LF line coordinates; count increases and new-to-file
status; original-only vocabulary; declared legitimate additions retained as
candidates; all occurrence locations; hash and source-byte preservation;
forbidden-directory and symlink exclusion; excerpt-free privacy-checked
reports; changed source/file-set/ZIP rejection; and exclusive installation
without overwriting an existing report.

These implementation tests used temporary synthetic TeX files and ZIPs only.
The separately authorized actual lexical snapshot is retained in
`control-words-second-reading-interim-01`, with its own input hashes and
report. That run made no source changes or content decisions. No validator
was run as part of this inventory.
