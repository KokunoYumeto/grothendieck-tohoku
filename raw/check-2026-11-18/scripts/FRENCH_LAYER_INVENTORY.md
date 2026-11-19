# Mechanical inventory of diplomatic/corrected French differences

`french_layer_inventory.py` compares the final `sources/dip/pNNN.tex` and
`sources/fr/pNNN.tex` pairs in the required 102-page order. It records every
remaining literal difference as a structured hunk, together with possible
correction-ledger associations for manual review. It makes no scan reading,
editorial judgment, mathematical judgment or finding that a change is justified.

The helper creates one new report directory. It does not edit source files,
`CORRECTIONS.tsv`, second-reading history, `CHECK_RECORD.md`, `CHECK_EVENTS.tsv`,
`progress.log`, or an existing report. No edition build is run.

## Complete literal snapshot before ledger promotion

To retain every literal difference, including comments and layer metadata,
and link the current unpromoted ledger to its stable review IDs:

```bash
python scripts/french_layer_inventory.py \
  --interim \
  --all-literal \
  --row-id-index second-reading/REVIEW_INDEX.tsv \
  --privacy-filter-derived \
  --output french-layer-current-interim-03
```

Choose a fresh output name on every run. `--all-literal` disables every
metadata substitution; the complete raw line comparison supplies the hunks.
It therefore does not depend on recognizing a TeX environment or deciding
whether an apparent command is metadata. All 102 expected page pairs are
included, and every hunk remains pending manual review.

`--row-id-index` supplies identity only. Every nonempty current record number
must be unique, every ID must be canonical and unique, every current ledger
fingerprint must match, and all current records must be bound. An incomplete,
stale or conflicting index is refused. The report copies no index verdict or
amended correction value into the ledger or into its literal matching fields.
Activity still comes from the actual `CORRECTIONS.tsv` annotation. Thus a
sidecar withdrawal or amendment not yet promoted does not silently change the
current-ledger comparison. `LEDGER_ID_BINDINGS.tsv` and `INPUT_HASHES.tsv`
record the exact identity binding and index snapshot. Do not combine this
option with `--review-map`.

The optional `--privacy-filter-derived` flag replaces privacy-pattern spans
only in derived presentation fields, after comparison, original hunk hashing
and literal candidate matching. Every affected field is marked, with original
and filtered hashes in `PRIVACY_FILTERING.tsv`. No hunk is omitted. Complete
original bytes remain at the source locators and are bound by source hashes.
Without this explicit flag, any privacy finding blocks report installation
instead of rewriting excerpts. Original source, credits and ledger bytes
remain unchanged in both modes.

The snapshot uses current ledger fields, not projected review amendments.
After promotion or another source/ledger/index change, make a new report.
Neither this invocation nor its pending list constitutes a final-readiness
gate or a decision about any French-layer difference.

## Invocation after final second-reading promotion

From the delivery directory:

```bash
python scripts/french_layer_inventory.py --output french-layer-inventory-01
```

The command requires all 102 ordered page-completion entries and refuses a
ledger that explicitly still marks an active row as pending, provisional or
first-reading-only. These are mechanical gates, not proof of a completed
reading: the reviewer chooses when the final source and promoted ledger are
ready. Preparation tests used synthetic fixtures; actual report runs retain
their input and source hashes.

For a mechanical snapshot after the ordered first pass, before review verdicts
have been promoted, use the explicit interim mode:

```bash
python scripts/french_layer_inventory.py --interim --output french-layer-first-pass-interim-01
```

This mode still requires all 102 completion entries, requires an output name
containing `interim`, and labels the report as an undecided interim snapshot.
The normal final-candidate mode continues to reject explicitly unfinished
confidence cells. Interim output does not satisfy a final-readiness gate.

Every invocation needs a new output name. Reports include input hashes and the
original fragments, so retain an earlier report when a later edit changes the
comparison. A source, ledger, progress, map or rule change detected during the
run aborts report installation.

To supply the map belonging to the exact promoted reviewed export:

```bash
python scripts/french_layer_inventory.py --output french-layer-inventory-02 --review-map CORRECTIONS.reviewed.review-map.tsv
```

`R000001`-style IDs come from the ledger's explicit second-reading confidence
annotation, a fingerprint-bound export map, or the explicitly supplied current
row-ID index described above. New workbench exports include
the fingerprint. A legacy map lacking fingerprints is accepted only where its
ID agrees with the explicit annotation in that row. If no stable ID is present
and no map is supplied, `L000001` identifies the first ledger record in this
snapshot. Match records always retain the current ledger-record number and
row-content fingerprint. A stale fingerprint is an error.

By default, associations consider all ledger layers on the same printed page,
plus unpaged build rows. To omit English candidates explicitly:

```bash
python scripts/french_layer_inventory.py --output french-layer-inventory-03 --candidate-layers as-printed corrected build
```

`--context-lines 2` is the default. All paths are selected at execution; the
helper has no machine-specific location embedded in it.

## Exactly what can be excluded

Only the following declared metadata substitutions are eligible. Every
successful substitution is separately recorded with both original values and
its equality criterion in `METADATA_EXCLUSIONS.tsv`.

1. A differing **first physical line that is a percent comment** may be
   normalized if replacing only `dip/pNNN.tex` versus `fr/pNNN.tex`, or the
   explicitly named `Layer: dip` versus `Layer: fr` field, makes the complete
   lines identical. The printed page must match; all other characters and line
   endings must agree. An unrecognized header remains a difference.
2. A **standalone, outer-level, literal `\LayerTarget{...}` invocation** may
   have its declared `dip`/`fr` layer tokens normalized. The remaining label
   characters, token counts, and multiplicity of that canonical label must
   agree. Locations and surrounding source text are retained in the comparison.

Inline, nested, complex, unmatched or differently numbered labels remain
visible. Known verbatim contents are not treated as target metadata. Literal
or control-definition constructs that can reinterpret tokens across lines,
unbalanced brace groups, and an existing `<layer>` comparison placeholder
conservatively disable target exclusions. An existing placeholder in a header
also prevents that header's exclusion. This is deliberately conservative and
does not attempt to execute or fully parse arbitrary TeX.
The known literal-environment set includes the shared lexer's verbatim forms,
`SaveVerbatim`, `filecontents` and `filecontents*`. Unknown token-reinterpreting
constructs remain a limitation of metadata mode. Use `--all-literal` when every
literal source difference must remain visible regardless of environment.

An optional reviewer-declared JSON rule can identify another known header
field. This **synthetic example** is not a claim about the edition's headers:

```json
{
  "layer_tokens": {"dip": "dip", "fr": "fr"},
  "header_rule": {
    "pattern": "% Fixture p(?P<page>\\d{3}) -- (?P<layer>diplomatic|corrected)",
    "dip_value": "diplomatic",
    "fr_value": "corrected"
  }
}
```

Pass the reviewed declaration with `--metadata-rules metadata-rules.json`.
The pattern must match the entire first comment line excluding its line
ending. It must capture exactly the field to substitute in the named `layer`
group. If it captures `page`, that value must match the printed page. Even
with an explicit rule, replacing only that field must make the full original
lines identical. A rule never authorizes dropping a whole differing comment.

No whitespace, math syntax, punctuation, wording, case, accent, line wrapping,
or inline/display distinction is normalized.

## Report files

| File | Contents |
| --- | --- |
| `FRENCH_LAYER_DIFFERENCES.tsv` | One row per non-equal line opcode: original diplomatic and corrected fragments, original context, line coordinates, hash, candidate IDs, and pending manual-review status. |
| `FRENCH_LAYER_MATCHES.tsv` | Candidate ledger rows, IDs, current record numbers/fingerprints, layer/kind, match direction and exact containment relation. |
| `METADATA_EXCLUSIONS.tsv` | Every excluded metadata pair, its original values, declared rule and structural equality criterion. |
| `PAGE_SUMMARY.tsv` | All 102 pages, line counts, raw/normalized equality and counts of hunks, exclusions and candidate categories. |
| `SOURCE_HASHES.tsv` | SHA-256 and byte counts for all 204 compared source files. |
| `INPUT_HASHES.tsv` | The ledger, progress and any supplied index/map/rule input snapshots. |
| `LEDGER_ID_BINDINGS.tsv` | Every current ledger record, its fingerprint and correction ID, with the identity source. |
| `METADATA_RULES.json` | The declarations used for this comparison. |
| `COMPARISON_SETTINGS.json` | All-literal versus metadata mode, context and candidate scope, index role and derived-excerpt privacy policy. |
| `PRIVACY_FILTERING.tsv` | Explicitly filtered presentation fields, their locators, original/filtered hashes and pattern types; empty when no filtering occurred. |
| `REPORT.md` | Totals, candidate scope, interpretation and limitations. |

Hunk IDs such as `D119-001` are snapshot locators, not permanent review IDs.
An insertion/deletion has a zero-line side whose boundary is the number of
source lines before it; boundary zero is the start of the file. LF defines
physical source lines. CSV-compatible TSV quoting preserves multiline source
fragments without flattening or rewriting them.
The source-file locators in each hunk are relative to the delivery root.
If privacy filtering is expressly enabled, a marked presentation field is the
exception to exact excerpt preservation; hunk hashes and matching continue to
use original bytes. Input TSVs and rules are parsed from their captured bytes,
and all inputs are checked again immediately before exclusive installation.

## Meaning of a candidate

Matching uses literal substring containment between ledger `old`/`new` fields
and the two hunk fragments, in both forward and reverse directions. It also
reports one-sided matches and exact empty-side insertion/deletion associations
when the other side has a real literal match. It does not normalize the text
or discard short mathematical signs. Rows with identical `old` and `new` fields
provide no directional association. Explicitly withdrawn rows are excluded.
For the identity-only row-index option, only a withdrawal in the current
ledger annotation affects activity; an unpromoted index verdict is not applied.

A two-sided match does not establish that an entire hunk is recorded, correct
or justified. A one-character match may be incidental. An English row cannot
by itself justify a corrected-French difference. A missing candidate does not
prove that a change is unrecorded. Every hunk remains pending the reviewer's
inspection and decision; the utility never confirms or amends a correction.

## Verification performed

Synthetic fixtures exercised 40 checks, including metadata equality, ambiguous
literal text, placeholder collisions, unchanged nonmetadata differences,
forward/reverse/partial and insertion/deletion matches, physical line numbers,
all 102 page pairs, input preservation, report overwrite protection, stale-map
rejection, and new fingerprint-bound workbench exports. No live edition page,
scan, correction row or audit narrative was read for those tests.

Five further focused fixture groups checked all-literal metadata/environment
coverage and line endings; complete fingerprint-bound identity-only mappings;
captured inputs and incidental R-token fallback; a 102-pair synthetic inventory
with preserved inputs and exclusive installation; and privacy blocking versus
explicitly marked presentation filtering with unchanged original hashes and
candidate IDs. Protected input/output paths are rejected. Current task runs
inspect only mechanical result metadata; content judgments remain with the
primary reviewer.
