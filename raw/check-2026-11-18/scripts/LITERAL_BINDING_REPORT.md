# Correction replacement-literal report

`literal_binding_report.py` checks whether each nonempty `new` field in
`CORRECTIONS.tsv` occurs literally in its indicated current source file. It
performs byte comparisons and reports metadata. It makes no image reading,
editorial decision, mathematical judgment or claim of visual verification.

An absent literal is a **review flag**, not an error verdict. A later edit may
have changed that passage, the replacement may have been removed or reflowed,
or the ledger may need a more accurate literal binding. A present literal
proves presence somewhere in the indicated file, not application at the
intended occurrence or line.

## Run and rerun

From the delivery directory:

```bash
python scripts/literal_binding_report.py --output literal-binding-interim-02
```

After final second-reading promotion, choose a new directory:

```bash
python scripts/literal_binding_report.py --output literal-binding-final-01
```

Optional arguments:

```bash
python scripts/literal_binding_report.py --output literal-binding-final-02 --review-map CORRECTIONS.reviewed.review-map.tsv --max-locations 5
```

This report can run before the sequential audit is complete. It has no
completion gate and does not infer that any second reading has occurred.
Inputs are checked again before installation; a concurrent ledger, map or
indicated-source edit aborts the run so it can be repeated against the next
snapshot. An existing report directory is never overwritten.

The command never edits source files, the ledger, reading history, progress,
`CHECK_RECORD.md`, or another report. It performs no TeX build.

## Source binding and IDs

Source locators support delivery-relative `sources/fr/pNNN.tex`,
source-relative `fr/pNNN.tex`, page basenames resolved through the ledger layer,
and build basenames such as `main-dip.tex`. Only indicated TeX files inside the
source tree are opened. Missing files, unsupported types, traversal or external
locators, and inconsistent layer/page metadata are reported separately.

`R000001`-style identifiers come from explicit second-reading annotations or a
matching fingerprint-bound export map. A legacy map is accepted only where its
ID agrees with the row's explicit annotation. Without stable review IDs, the
report uses `L000001` for the first ledger record in this snapshot. Every row
also carries its ledger-record number and content fingerprint. Reordering a
ledger changes the meaning of an L locator; retain the report's ledger hash.

The source `line` field is retained as reference metadata. It is not parsed or
used to constrain the whole-file literal occurrence test. Locations in the
report count physical LF line boundaries. Exact matching preserves case,
accents, whitespace, CRLF/LF distinctions and TeX syntax. Counts are
nonoverlapping literal occurrences; at most five source locations are shown
by default.

Empty `new` fields have no presence test. They are counted separately, and
their deletion was not verified by this report. Explicitly withdrawn rows
remain visible with their activity labelled and grouped separately.

## Doubled braces and inherited records

The inherited classification is a mechanical check for the exact evidence
marker `Inherited correction retained:` written by `audit.inherited`. It does
not infer provenance from the mathematical content or general wording.

`INHERITED_DOUBLED_BRACES.tsv` includes every such row with literal `{{` or `}}`
in either `old` or `new`. Adjacent braces are often valid TeX; their presence is
not a finding of incorrect grouping.

For diagnostic purposes only, the helper performs one nonrecursive replacement
of each nonoverlapping `{{` with `{` and `}}` with `}` in `new`, and checks
whether that variant occurs. An absent original with a present variant is
highlighted for manual review. The variant is **not** a proposed amendment,
and no decision is inferred even if it occurs exactly once.

## Possible later-record associations

For an absent nonempty replacement, the helper compares it with `old` fields
in later ledger records for the same indicated file. It records exact literal
substring containment in either direction. These associations can help find a
possible follow-on edit, but may also be incidental, especially for short
signs. Ledger-record order is not proof of edit chronology. No association
clears a flag, confirms a row or withdraws it.

## Output files

| File | Contents |
| --- | --- |
| `ROW_BINDINGS.tsv` | Every ledger row's metadata, source hash/size/line count, presence status, occurrence counts/locations and review flags. |
| `ABSENT_NEW_LITERALS.tsv` | Nonempty replacements absent from the indicated source, including ledger fragments for the primary reviewer's inspection. |
| `INHERITED_DOUBLED_BRACES.tsv` | Explicit inherited records with doubled braces and the diagnostic variant counts. |
| `FLAGGED_ROWS.tsv` | All source-locator, absence and inherited-brace flags with their ledger fields. |
| `LATER_RECORD_CANDIDATES.tsv` | Candidate later-record associations; every association is explicitly undecided. |
| `GROUPS.tsv` | Counts by layer, kind, printed page, inherited marker and activity. |
| `SOURCE_HASHES.tsv` | Relative source locators, byte/line counts and SHA-256 values. |
| `INPUT_HASHES.tsv` | Ledger and optional review-map snapshots. |
| `SUMMARY.json` | Machine-readable totals and generation time. |
| `REPORT.md` | Totals, interpretation and limitations. |

Matching uses original ledger strings. Only generated report fields are
filtered for recognizable email, local path, network path and local-file URI
patterns. `privacy_redacted_fields` identifies substitutions, which can include
conservative false positives in TeX. Use the row ID/fingerprint to consult the
original ledger when a report field has been filtered. Redaction counts are
not a count of confirmed private disclosures. No source or ledger byte is
changed. Pattern filtering is not exhaustive privacy verification.

## Verification and interim run

Forty-three synthetic checks covered exact matching, empty replacements,
source resolution and mismatch flags, inherited markers, brace diagnostics,
later-record candidates, preserved inputs, privacy filtering, hashes, protected
output directories, existing-report protection and concurrent-edit refusal.

The first authorized interim run is in `literal-binding-interim-01`. It tested
only mechanical literal presence and exposed only metadata/counts to the
auxiliary reviewer. The primary reviewer remains responsible for examining the
flagged ledger fragments and deciding their disposition. Rerun after subsequent
edits; that interim result is not the final edition state.
