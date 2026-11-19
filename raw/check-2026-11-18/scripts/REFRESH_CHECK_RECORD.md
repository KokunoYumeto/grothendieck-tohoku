# Refreshing mechanical check metadata

`refresh_check_record.py` is for use after the final second-reading ledger has
been promoted to `CORRECTIONS.tsv`. The helper was prepared without editing
the live check record or reading any source page or scan.

It updates only:

- The per-page correction counts by layer and kind, including page-scoped
  build rows that the original three-layer count line did not display.
- The numeric end of each source-file line range, by counting physical line
  breaks in the current file bytes.
- A marked top summary: totals by layer and kind, pages with no recorded
  change in each reading layer, and explicitly classified mathematical changes.

All other content is protected. The helper compares the protected text before
and after the proposed refresh and aborts if narrative, verdicts, comparison
wording or completion timestamps would change. A separate metadata-refresh
timestamp is added in the summary; no new scan reading or proof check is
claimed. Source files, the live ledger, progress log and check-event ledger
are never modified.

## Explicit mathematical classifications

Before final ledger promotion, use the separate read-only effective-state
inventory documented in `MATH_CLASSIFICATION_INTERIM.md`:

```bash
python scripts/refresh_check_record.py prepare-math-interim --output math-classification-interim-02 --privacy-filter-derived
```

It replays already recorded amendments/withdrawals, uses stable R IDs, creates
pending-only tables for both candidate scopes, and lists unpaged pending rows.
It changes no ledger or review state. The ordinary command below reads the
current ledger and does not replay unpromoted sidecar amendments.

From the delivery directory, prepare a manual classification table:

```bash
python scripts/refresh_check_record.py prepare-math --output MATHEMATICAL_CHANGE_CLASSIFICATION.tsv
```

The default candidate kinds are `misprint of the original` and `translation`.
Every row starts `pending`; the helper makes no significance judgment. Use
`--all-kinds` to include every active correction, since changes of another
kind can also affect mathematics.

For each supplied decision, set `mathematical_change` to `yes` or `no` and
provide a reason. A `yes` also needs a reviewer-written `summary`. The top
record prints each active `yes` on one physical Markdown line, with its row
ID, printed page, statement/line locator, file, summary and reason.

IDs normally come from the second-reading confidence annotations. If plain
confidence cells were exported, supply the matching export map using the
global `--review-map` option. Without either, the helper uses ledger-record
IDs. Every classification is also bound to the row fingerprint: an edited
correction invalidates its old classification instead of silently carrying
the decision forward. No missing classification is treated as `no`.

For annotated rows, a supplied map must also agree with the current verdict
and last event ID; a missing or stale event is refused. This prevents an
older withdrawal map from overriding a later confirmed annotation whose
literal content did not change. Use the current export's matching map or
omit the map when annotated IDs are already present. Plain confidence cells
remain an interim compatibility option, but cannot pass final validation.
See `REVIEW_METADATA_GATES.md` for the focused synthetic regression tests.

## Preview, then refresh

Print proposed statistics without writing:

```bash
python scripts/refresh_check_record.py refresh --math-classifications MATHEMATICAL_CHANGE_CLASSIFICATION.tsv
```

Write a separate reviewable copy:

```bash
python scripts/refresh_check_record.py refresh --math-classifications MATHEMATICAL_CHANGE_CLASSIFICATION.tsv --output CHECK_RECORD.refreshed.md
```

Apply the protected in-place update:

```bash
python scripts/refresh_check_record.py refresh --math-classifications MATHEMATICAL_CHANGE_CLASSIFICATION.tsv --require-math-complete --write
```

`--require-math-complete` requires an explicit yes/no for every active
original-misprint/translation candidate. The stronger
`--require-all-math-classified` requires a decision for every active row of
every kind. Both gates use supplied decisions; neither examines formulas or
infers mathematical meaning.

Refresh refuses to run before all 102 ordered page-completion entries and
page sections exist, or while confidence cells explicitly mark unfinished
second readings. Unexpected metadata syntax also causes refusal rather than
replacement of possible prose. Repeated refreshes replace the same managed
summary block and preserve the rest of the record.

Counts are active ledger rows. Explicit second-reading withdrawals are
excluded when identified by the supplied annotation or review map. A page
with no active row is described as having no **recorded change**, not as a
newly verified match to the scan.

## Preparation verification

Only temporary synthetic fixtures were used. A 102-section fixture verified
layer/kind totals, build-row inclusion, withdrawal exclusion, all source-line
ranges, narrative/timestamp preservation, explicit-only mathematical lists,
stale-fingerprint rejection and repeat-refresh stability. Its ledger,
progress log and source fixtures remained unchanged. The final validator's
heading recognizer was also corrected to accept the audit writer's actual
`### Printed page` headings as well as level-two headings.
