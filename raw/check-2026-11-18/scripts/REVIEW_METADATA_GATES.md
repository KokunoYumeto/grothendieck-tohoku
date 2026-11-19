# Explicit second-reading metadata gates

These gates validate correction-ledger metadata. They do not judge a scan
reading, a TeX literal, mathematical meaning or the adequacy of evidence.
The implementation and tests changed only helper code/documentation and
disposable synthetic fixtures; the current edition ledger and review state
were not changed.

## Final confidence cells

`final_validate.py` requires every retained `confidence` cell to have the
annotated exporter form:

```text
high; second reading confirmed; R000123; E000456
```

The recognized degrees are `high`, `medium` and `low`. The recognized final
verdicts are `confirmed`, `amended` and `withdrawn`. Row and event identifiers
use the workbench's canonical positive numbering: an `R` or `E` prefix and
at least six decimal digits, zero-padded to six digits where necessary.
Horizontal space around separators is permitted. Multiline cells, extra
trailing annotations, missing IDs, zero IDs, noncanonical padding, plain
degrees and unrecognized wording fail this check.

The named checks are:

- `explicit-second-reading-confidence`: every retained row has the required
  degree, verdict and identifiers.
- `unique-second-reading-identifiers`: retained rows do not repeat a stable
  row ID or a last-event ID.

The prior `no-explicitly-provisional-confidence` check remains in place.
Invalid-cell reports give logical ledger-record numbers, without copying
the cell contents. Final archive preflight requires both new checks as well
as the two privacy checks. An older check table that lacks the new gates
cannot authorize final packaging. Hourly checkpoint behavior is unchanged.

These format checks do not independently replay review history. The separate
promotion procedure in `SECOND_READING_PROMOTION.md` compares each exported
annotation and fingerprint with the verified sidecar state before replacing
the ledger. Keep the original registry, append-only events and export map.

## Map consistency for mechanical counts

When a row has a recognized confidence annotation and an explicit review
map is supplied, `refresh_check_record.load_rows` now requires the map's
status and `last_event` to agree with that annotation. A missing event also
fails. The existing row-ID and content-fingerprint checks remain active.
Map status is normalized once and must be `pending`, `confirmed`, `amended`
or `withdrawn`; an unknown status is refused even for an interim plain cell.

This closes a reproduced bookkeeping defect: a row confirmed after an older
withdrawal could previously be counted as inactive under its stale map,
because row fingerprints intentionally exclude confidence. The helper now
refuses that inconsistent map instead of selecting a verdict.

Use the exact map created with the current annotated export, or omit the
map when the final annotated ledger already supplies the stable IDs. Plain
exports/maps remain usable for explicitly requested interim tooling, but a
plain confidence cell cannot pass the final confidence gate. No script
automatically changes a review outcome or updates a stale map.

## Synthetic verification

Run the focused reusable suite from the delivery directory:

```bash
python scripts/test_review_metadata_gates.py
```

The suite creates and removes its own temporary directory. It never opens
the actual edition ledger, review sidecar, page sources, scans, PDFs or
research folders. Fourteen test methods cover the nine degree/verdict
combinations, invalid annotations, duplicate IDs, final-validator integration,
old-check-table refusal, current maps, stale status/event refusals, missing
events, retained earlier fingerprint/ID gates, normalized/recognized map
statuses, interim compatibility, and
the actual exporter's annotated-retain output with unchanged history bytes.

The test exporter uses nine explicitly supplied synthetic decisions,
including three withdrawals. All nine annotated records pass the metadata
checks; the matching map counts six active rows. This does not certify any
actual correction or build.
