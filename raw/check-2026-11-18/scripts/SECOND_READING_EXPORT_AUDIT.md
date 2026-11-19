# Second-reading export audit

Tested on 2026-11-18 using helper code and temporary synthetic ledgers only.
This note describes the helper versions identified below; it is not a report
on the edition's actual review state.

The initial findings below are retained as the tested historical baseline.
An authorized follow-up has since added explicit confidence/ID gates and
stale-map status/event checks. See `REVIEW_METADATA_GATES.md` for their current
behavior and synthetic tests; the hashes at the end identify the earlier
versions to which the original findings apply.

## Findings

The annotated export writes an explicit verdict, confidence degree, stable
row ID and last event ID into each retained row's `confidence` cell. The
plain export writes only `high`, `medium` or `low`. Under the stated
requirement for an explicit confidence-column verdict, a plain export does
not contain the required information.

The tested `final_validate.py` does not enforce that requirement. Its
confidence check rejects only text matching `first[ -]reading`, `pending`,
`provisional` or `not yet`, ignoring case. It does not require a recognized
degree, verdict, row ID or event ID, and does not bind a verdict to the
review-event history. Checkpoint preflight relies on the resulting validation
checks and inventory; it does not independently parse confidence cells.

There is also a downstream counting hazard: a withdrawn row retained in a
plain export is counted as active by `load_rows()` when no review map is
provided. Its withdrawal is recognized when the matching map is supplied.

## Four export combinations

The fixture contained one confirmed row, one amended row and one withdrawn
row. The withdrawn row had an earlier confirmation event that remained in
the history.

| Confidence format | Withdrawal choice | Exported rows | Active rows without a map | Active rows with the matching map |
| --- | --- | ---: | ---: | ---: |
| `annotated` | `retain` | 3 | 2 | 2 |
| `annotated` | `omit` | 2 | 2 | 2 |
| `plain` | `retain` | 3 | 3 | 2 |
| `plain` | `omit` | 2 | 2 | 2 |

Annotated retained rows contained these synthetic confidence values:

```text
high; second reading confirmed; R000001; E000001
medium; second reading amended; R000002; E000002
low; second reading withdrawn; R000003; E000004
```

Without a map, annotated exports retained their `R` identifiers. Plain
exports received positional `L` identifiers. Each matching export map
restored the stable `R` identifiers and the withdrawn status. The maps also
contained row fingerprints.

With `omit`, the withdrawn row was absent from the exported ledger but
remained in the map with an empty `export_record`, status
`withdrawn; omitted from active export`, its stable ID, its final event ID
and its row fingerprint. Its original registry row and all prior events
also remained in the sidecar.

## Confidence and activity checks

The exact unfinished-confidence expression was extracted from the
validator's syntax tree and evaluated on sixteen synthetic cells. The
confidence gate accepted plain `high`, `medium`, `low`, an empty cell,
arbitrary text, an invalid degree, an unrecognized verdict, an annotation
without IDs, bare withdrawal wording and all three normal annotated
verdicts. It rejected the four tested unfinished-word forms. This evaluates
that particular gate; it does not assert that an entire delivery would pass
full validation.

Six direct `load_rows()` fixtures established that, without a map, plain
`high`, arbitrary text, `withdrawn` and `second reading withdrawn` all count
as active. The recognized semicolon-delimited form
`low; second reading withdrawn` counts as inactive, with or without the
following IDs. Thus the loader does not infer a withdrawal from arbitrary
verdict wording.

## History and replacement behavior

The tests confirmed that pending rows prevent export. Explicit confirmation,
amendment and withdrawal events left the original ledger and registry bytes
unchanged. The withdrawal appended to the previous event bytes rather than
replacing the earlier confirmation. All four exports left every sidecar
file unchanged. The history loader rejected a synthetic event alteration
whose hash chain had not been updated.

Exporting directly to the current `CORRECTIONS.tsv` was refused, and its
bytes remained unchanged. The exporter has no promotion action: it creates
a separate ledger plus a corresponding map. Eventual replacement of the
live ledger is a separate, explicit operation. Promotion and rebinding of
identical rows were outside this test's scope.

## Exact export options

To retain explicit withdrawal verdicts in the exported ledger itself:

```bash
python scripts/second_reading.py export --output CORRECTIONS.reviewed.tsv --withdrawn retain --confidence-format annotated
```

For an active-only ledger while preserving withdrawal history separately:

```bash
python scripts/second_reading.py export --output CORRECTIONS.reviewed-active.tsv --withdrawn omit --confidence-format annotated
```

`annotated` is the default confidence format; the withdrawal choice is
mandatory. `--confidence-format plain` is available but removes the verdict
and IDs from the confidence column. None of these commands replaces the
live ledger or edits page sources.

## Scope and versions

Only helper code, temporary synthetic ledgers, synthetic review sidecars and
their export maps were used. No actual ledger, review state, page, scan,
research context or PDF was inspected. No source file, validator or live
record was modified; no build or full final validation was run. Temporary
fixtures were discarded.

| Helper | SHA-256 at test time |
| --- | --- |
| `second_reading.py` | `c19ca4b62c01e98b99e8a856f426d8ea0ac67ab74b54b5ba733ec847b62cca8b` |
| `final_validate.py` | `3d12bd31ba4779e9f5259506e64ad3e5fc8585677e1202f0fbca8f35cbfe897c` |
| `refresh_check_record.py` | `2d39de6c56cc628296f3f8904a438fc8a85e1a63725a73513b45d16d18c5b7f8` |
| `checkpoint.py` | `7e81aed0330e4562f3118882c3db60e4742f46d284a28a4450d360ea32feee20` |
