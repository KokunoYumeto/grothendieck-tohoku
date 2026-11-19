# Interim math-font context detector

`math_font_context.py` enumerates literal occurrences of `mathrm`, `mathbf`,
`mathcal`, `mathfrak`, `mathbb` and `boldsymbol` outside recognized lexical
math contexts. It reports candidates for the primary reviewer's decision.
It neither reads an image nor decides a correction, changes source text,
updates review state, expands input files, or runs TeX.

## Invocation

From the delivery directory:

```bash
python scripts/math_font_context.py --output math-font-context-interim-01
```

The default root is the script directory's parent. `--root` can identify a
different delivery tree. The output must be a fresh relative directory whose
name includes `interim`, outside the source and PDF trees. Existing reports
are never overwritten. Use a new output name after further source edits.

The helper reads eligible `.tex` files under `sources/` as a static snapshot.
It excludes symbolic links and directories named `programme`, `notes` or
`stacks`, ignoring letter case. It does not use the original ZIP or any scan.
Before installing a report, it checks the eligible file set and every source
hash again. All recorded locators are relative; source excerpts are omitted.

## Reports

| File | Contents |
| --- | --- |
| `CANDIDATES.tsv` | One row per invocation token outside recognized math, including uncertain/deferred contexts; file, layer/page, line, column, command name, context and pending review status. |
| `FONT_COMMAND_OCCURRENCES.tsv` | Every recognized font-command token, including math contexts and literal/declaration references that are not invocation candidates. |
| `LEXICAL_NOTES.tsv` | Unrecognized, unclosed, recovered or unsupported lexical boundaries and execution signals. |
| `FILE_SUMMARY.tsv` | Per-file line, token, candidate and note counts. |
| `SOURCE_HASHES.tsv` | Exact byte size and SHA-256 of each inspected source. |
| `INPUT_HASHES.tsv` | Hash binding the combined source inventory. |
| `SUMMARY.json` | Machine-readable counts and candidate context groups. |
| `REPORT.md` | Timestamp, counts and interpretation limits. |

Coordinates use one-based physical LF lines and character columns. Candidate
IDs are local to a snapshot. Every candidate remains `pending manual review`;
no ledger row, confidence or reading evidence is created automatically.

## Recognized contexts

The scanner tracks single/double dollar delimiters, parenthesized and bracketed
math delimiters, and common outer math environments such as `equation`,
`align`, `gather`, `multline`, `math` and `displaymath`, including documented
starred variants. Adjacent inline dollar spans are tokenized in context.

Inner math environments such as `array`, `cases`, matrix variants, `aligned`,
`gathered` and `split` inherit surrounding math. If encountered outside
recognized math, they create an uncertainty note and retain candidate tokens.
`subequations` alone does not establish math mode. The exact environment sets
are explicit constants in the helper.

Common text arguments override surrounding math while their argument is
scanned. These include `text`, text font commands, `emph`, `mbox`, `fbox`,
`intertext`, `shortintertext`, and the bodies of supported box/footnote/caption
commands. `ensuremath` establishes math for its argument. Both balanced braced
arguments and direct single-token arguments restore the prior context.
Nested explicit math inside a text argument is tracked independently.

Braced `hbox`, `vbox` and `vtop` bodies are text. Literal `to`/`spread`
dimensions with standard units are recognized. For macro-based or unsupported
dimensions, the helper does not guess which brace begins the body: it records
a note and keeps font tokens in the containing math scope as uncertain
candidates. This can include tokens before or after the box within that scope.
Supported `parbox`, `raisebox`, `makebox` and `framebox` forms also identify
their explicit body groups. Known text environments include tabular variants,
`longtable` and `minipage`.

Common literal macro/environment definition bodies and optional defaults are
deferred templates, initially scanned in unknown mode. They are kept distinct
from executed plain text. Declaration targets, primitive definition parameter
tokens, literal `let` sources, and tokens consumed by `string` or `meaning`
are recorded as references rather than invocation candidates. Balanced
`detokenize` bodies are treated as literal text.

Percent comments, escaped control symbols, simple `verb`/`verb*` bodies, and
the common verbatim environments shared with `control_word_inventory.py`
are skipped. Unclosed or recovered math scopes are demoted to uncertainty;
their font-command occurrences remain candidates.

## Limits

Each file begins in assumed text mode. Math started by a caller or continued
across an input boundary is not reconstructed. Packages, custom commands,
macro expansion, conditionals, catcode changes, Unicode letter conventions
and constructed command names are not executed. Unknown environments inherit
their surrounding lexical mode and generate a note. A custom environment or
macro may establish text or math differently, so candidates and notes require
manual context. Unsupported argument forms and literal constructs can also
produce false positives or missed contexts.

Definition parsing covers common explicit signatures; it is not a general TeX
definition parser. A macro template containing a font command is not proof that
the command will run in text. Likewise, a token classified as math is only a
lexical classification. Absence of candidates or notes establishes neither
valid TeX nor faithful transcription. The report does not inspect ordinary-word
spelling or infer whether a font command was inserted into a word.

## Synthetic verification

```bash
python scripts/test_math_font_context.py
```

All 23 synthetic test methods passed. They cover the six target commands,
inline/display/environment math, nested text and math, adjacent inline spans,
single-token arguments, literal and macro-based box widths, definition roles
and defaults, references, comments/literals, unclosed-scope retention,
coordinates, relative excerpt-free reports, source/hash preservation,
forbidden-directory and symlink exclusion, changed-input refusal and immutable
interim output. Test files and reports are created only in disposable temporary
directories. No edition source or review record is used by the test suite.

The Python function also accepts an optional `probe_offsets` set for other
mechanical reports. Offsets index the text decoded with `utf-8-sig`; probes
return context for visited ordinary characters and mark skipped offsets
unvisited. They share the font scanner's final uncertainty demotion without
changing its traversal, font occurrences or notes. Probes return no word or
source excerpt. `recurrence_inventory.py` uses this optional interface for
match-endpoint context, with separate synthetic regression coverage.

## Authorized interim snapshot

The one authorized current-source run was saved as
`math-font-context-interim-01`, generated at 2026-11-18T18:48:09Z. It inspected
310 eligible TeX files and recorded 7,508 target-command tokens. Two candidates
were retained, both in `sources/dip/p207.tex`: `mathrm` at line 17, column 53,
and line 23, column 14. They remain pending the primary reviewer's sequential
content review; this helper made no correction or correctness decision.

The snapshot also records 70 lexical notes: 63 single-token argument notes
and seven unrecognized-environment notes, across seven files. The candidate
file itself has no lexical notes. Neither that fact nor the small candidate
count certifies the source. Later edits require a new interim snapshot.
