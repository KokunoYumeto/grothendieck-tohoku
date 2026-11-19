# Interim notation, structural and ledger recurrence inventory

This helper records lexical/literal candidates and exact ledger pairs. It
makes no content, mathematical, translation or correction-coverage judgment.
Every review status is `pending`. Sources, ledgers, review state and existing
reports remain unchanged; no scan or build is used.

## Invocation and input coverage

From the delivery directory:

```bash
python scripts/notation_ledger_inventory.py --output notation-ledger-recurrence-interim-01
```

The output must be a fresh relative directory explicitly named `interim`.
All regular page files for 119–183 and 185–221 are required in all three
layers: 306 files. Missing files block installation rather than receiving a
zero. The script also snapshots `CORRECTIONS.tsv`. The source set, every
source hash and the ledger hash are rechecked before installation. Main files,
preambles, scans, ZIPs, symbolic links and protected context folders are excluded.

## Exact notation patterns and scopes

These case-sensitive control-word names use an ASCII letter boundary:

```text
mathcal mathbb longrightarrow longleftarrow longleftrightarrow longmapsto
leq geq varepsilon epsilon varinjlim varprojlim
noindentAB inZ toI toII cdotb cdotu
```

Each raw spelling uses `re.escape(backslash + name) + (?![A-Za-z])`.
Thus `toI` does not match `toII` or `toIIG`, and `leq` does not match
`leqslant`. The existing lexer then distinguishes source control tokens
from escaped or literal spellings, consuming paired/triple backslashes.

The French phrases are case-sensitive with literal single spaces:
`de homologies`, `de homomorphisme`, and `du homomorphisme`.
Their escaped literals have `(?<![\w\\])` before them and `(?!\w)` after
them. The spelling `\mathrm{g}énéralement` is escaped literally and followed
by `(?!\w)`. Python's default Unicode word boundaries apply to those phrases.
No accent, plural, whitespace or formatting normalization is performed.
`PATTERNS.tsv` records all 22 complete expressions.

Matching categories are:

- `source`: a recognized lexical control token or visited literal source phrase.
- `comment`: an exact bounded spelling in a lexical percent-comment range.
- `reference`: a retained raw spelling not recognized as a source token.

Comment ranges respect escaped percent signs and documented verbatim forms.
Comments are never treated as executing commands. These are lexical scopes,
not correctness labels.

## Mathcal/mathbb arguments and context

The next explicit braced group or single control-word, control-symbol or
character token is captured without expansion. `argument_source` retains
braces; `argument_tokens` is the group payload or single token. Empty, missing
and unclosed groups are distinguished, and argument locations are separate
when comments or line breaks intervene. Known declaration/reference tokens
receive no inferred argument. Comment argument spellings stay within their
comment line.

Text/math/unknown mode and reference roles come from the existing font-context
occurrence metadata. Unsupported or skipped forms remain uncertainty. No
symbol, mathematical object or intended font meaning is classified.
The source-context field contains complete lines covering the command and
captured argument, minus the final line ending. Privacy filtering affects
derived fields only and is named in `privacy_filtered_fields`; hashes bind
the original unfiltered line and argument. Source bytes remain unchanged.

## Location-only nested fonts and repeated anchors

`NESTED_FONT_CANDIDATES.tsv` lists identical named font/style token pairs
when the inner token lies in the next explicit argument of the outer token.
The fixed name set is:

```text
boldsymbol mathbb mathbf mathcal mathfrak mathit mathnormal mathrm mathsf mathtt
emph textbf textit textmd textnormal textrm textsc textsf textsl texttt textup
```

The table contains outer/inner line and column, first/later argument position,
argument form and hash. It copies no argument text or surrounding prose.
Every containment pair is listed: three nested identical commands can yield
three pairs. They are not assumed to be independent errors. Source and comment
scopes remain distinct.

`DUPLICATE_LAYER_TARGETS.tsv` groups exactly equal, unexpanded braced
`LayerTarget` argument strings within the same page file and scope. It gives
the identifier/hash, count and every line:column location. Source/comment
occurrences are not combined; different files are not compared. Computed
labels are not expanded, and no duplicate PDF destination is inferred.
`LAYER_TARGET_PARSE_NOTES.tsv` lists locations lacking a recognized balanced
explicit argument.

## Matrices and exact ledger groups

`PAGE_LAYER_MATRIX.tsv` has all 102 pages, with counts and zero/nonzero fields
for each layer and source/comment/reference scope, plus source nested-font
pair and duplicate-anchor counts. `FAMILY_PAGE_LAYER_MATRIX.tsv` has every
102 × 22 page/family combination and all three layers, including numeric
zeros. Zero means no match under these rules, not a reading or coverage verdict.

`LEDGER_PAIR_GROUPS.tsv` groups parsed `(old, new)` strings by exact equality,
without trimming or Unicode, TeX or whitespace normalization. Empty values
participate. A group qualifies only if it occurs on at least two distinct
nonempty printed pages; three layer rows on one page still count as one page.
Unpaged members of an otherwise qualifying group remain listed but do not
increase its page count.

All current ledger rows participate. The review sidecar is not read, and
withdrawal/activity is not inferred. `LEDGER_PAIR_MEMBERS.tsv` supplies each
member's one-based logical ledger record, locator and exact-row hash;
`LEDGER_PAIR_PAGE_COUNTS.tsv` supplies counts. IDs are local to this snapshot.
No applicability, correctness, missing-correction or coverage conclusion is made.

## Safeguards, tests and snapshot

Source occurrences are page-sorted in `SOURCE_CANDIDATES.tsv`,
`COMMENT_MATCHES.tsv`, `REFERENCE_MATCHES.tsv` and `ALL_MATCHES.tsv`.
`FAMILY_COUNTS.tsv`, `SOURCE_HASHES.tsv`, `INPUT_HASHES.tsv`, `PATTERNS.tsv`,
`LEXICAL_NOTES.tsv`, `SUMMARY.json` and `REPORT.md` retain counts and provenance.
Macro expansion, packages, catcodes, conditionals and cross-input state are
not reconstructed. Definitions and literal templates may need manual context.
No absence or presence of a candidate certifies the source.

Six focused synthetic fixture groups covered boundaries, comments, arguments,
zero matrices, exact/distinct-page ledger groups and unchanged inputs/output.
Three additional groups covered nested-pair multiplicity, per-file/source-versus-
comment anchor grouping and unclosed-anchor notes. All passed. No persistent
test file or broad test suite was added for this task.

`notation-ledger-recurrence-interim-01` was generated at
2026-11-18T19:22:34Z from all 306 page sources and 11,791 ledger rows. It contains
110 requested source matches, no comment/reference matches, 23 nested-font
source pairs, and no duplicate anchor group or anchor parse note. All 23 pairs
are literal `textit` pairs; their purpose is not interpreted.

The ledger inventory has 111 exact pairs recurring on at least two printed
pages, with 6,320 member rows. Three surrounding-source-line fields are
privacy-filtered and marked; matched tokens and input hashes remain intact.
The snapshot is immutable and every review status remains pending.
