# Pending mathematical-change inventory from effective review rows

`refresh_check_record.py prepare-math-interim` projects already recorded
review amendments and withdrawals through the existing workbench. It supplies
no mathematical classification. Every candidate starts `pending`, with an
empty summary and reason.

## Reproduce in a fresh directory

From the delivery root:

```bash
python scripts/refresh_check_record.py prepare-math-interim \
  --output math-classification-interim-02 \
  --privacy-filter-derived
```

The default review directory is `second-reading`. An explicit `--review-dir`
must be relative. This mode cannot use an export `--review-map`. It never
overwrites a snapshot or writes into sources, PDFs or review state.

Only the current ledger and the four sidecar files are read: REVIEW_META,
ROW_REGISTRY, REVIEW_EVENTS and REVIEW_INDEX. A shared read lock covers capture;
replay uses disposable copies of those exact bytes. The existing workbench
validates the event hash chain, before/after fingerprints and stable-ID
alignment. The captured index must match the replayed state and current
alignment. All five live inputs are checked again before installation.

No TeX, scan, CHECK_RECORD, check-event table or restricted context content is
read. No live ledger, event, registry, index, source, build output or final gate
is changed.

## Candidate scopes

| File | Contents |
| --- | --- |
| `MATHEMATICAL_CHANGE_CLASSIFICATION.tsv` | All nonwithdrawn registered effective rows, for the optional stronger all-active-kinds scope. |
| `DEFAULT_KIND_CANDIDATES.tsv` | The subset whose effective kind is literally `misprint of the original` or `translation`. |
| `ROW_PROJECTION.tsv` | Stable R IDs, current positions, effective locators, review status/last event and current/effective fingerprints. |
| `UNPAGED_PENDING_REVIEW_ROWS.tsv` | Every registered pending review row without a printed page, including build rows. |
| `UNREGISTERED_PENDING_ROWS.tsv` | Current ledger rows without an assigned stable ID; no ID is invented. |
| `WITHDRAWN_ROWS_EXCLUDED.tsv` | Metadata for explicit withdrawals omitted from the templates. |
| `GROUP_COUNTS.tsv` | Effective page/layer/kind/review-status counts. |
| `INPUT_HASHES.tsv` | Five captured input hashes and byte counts. |
| `PRIVACY_FILTERING.tsv` | Marked display-field filtering, with original/filtered hashes. |
| `SUMMARY.json`, `REPORT.md` | Counts, scope and limitations. |

Amended fields, including kind and page, come from the effective state. The
latest explicit withdrawal excludes a row. A pending review row remains in
the template with its review status recorded separately. Unregistered rows
are reported separately and make registered-only coverage incomplete.

The all-active table is a superset; the stronger scope is supported by the
existing helper, not declared mandatory by this inventory. Choose one scope
for later manual decisions. The default-kind table is not a second set of
judgments. Neither table imports an earlier mathematical decision file.

The fourteen core columns are:

```text
correction_id, row_fingerprint, mathematical_change, summary, reason,
ledger_record, file, layer, printed_page, line, statement, kind, old, new
```

The interim tables append `privacy_filtered_fields`. The existing loader
requires the first five columns and permits informational additions. It
requires a unique current ID and matching fingerprint. Both `yes` and `no`
need a reason; `yes` also needs a summary. Missing or pending entries are
never treated as `no`.

With explicit privacy filtering, only displayed pattern spans are replaced,
after projection, selection and fingerprinting. The original hash is retained
and each affected field is marked. A filtered `old` or `new` field is not the
complete literal; inspect the effective stable-ID row before deciding. Without
the flag, a privacy finding blocks installation. No original source, credit
or history byte is rewritten.

## Current immutable snapshot

`math-classification-interim-01` binds 11,888 stable rows and 11,939 verified
review events. It excludes 139 withdrawals, supplies 11,749 all-active pending
rows and 594 default-kind candidates, and has no review-pending or unregistered
row. In particular, no unpaged pending build row remains in that snapshot.
Nineteen derived fields are explicitly privacy-filtered. Later changes require
a new directory; this snapshot is not updated in place.

## Fingerprints and the later workflow

The row fingerprint covers the nine correction fields other than confidence.
Annotated export and byte-preserving promotion retain it when effective fields
are unchanged; reordered positions do not alter it. Stable R IDs distinguish
identical contents. A later amendment to wording, evidence, kind or locators
invalidates an older binding. Decisions are never transferred automatically.

The existing `prepare-math` reads the live ledger only; it does not replay
unpromoted review amendments. Its intended use is after promotion. The interim
mode above is the appropriate preparation route before promotion.

For later primary-controlled work, the existing sequence is:

1. Resolve all registered/unregistered review-pending rows, including unpaged
   build entries. Inspect with `second_reading.py status` and
   `second_reading.py pending --page build`.
2. Export an annotated ledger retaining withdrawal verdicts:

   ```bash
   python scripts/second_reading.py export --output CORRECTIONS.reviewed-01.tsv \
     --withdrawn retain --confidence-format annotated
   ```

3. Review and promote that exact export using the separately documented
   operation in `SECOND_READING_PROMOTION.md`, preserving the prior ledger and
   explicit ID/new-position bindings. Then run:

   ```bash
   python scripts/second_reading.py sync --bindings review-promotion-bindings-01.json
   python scripts/second_reading.py status
   ```

4. Make explicit mathematical decisions in a separate working copy of the
   selected pending table, preserving the interim snapshot. Alternatively,
   create a fresh pending table from the promoted ledger:

   ```bash
   python scripts/refresh_check_record.py prepare-math --all-kinds \
     --output MATHEMATICAL_CHANGE_CLASSIFICATION.tsv
   ```

   That command starts every selected row pending; it does not preserve prior
   mathematical decisions. Omit `--all-kinds` for the default two-kind scope.
5. Preview, then apply the separately authorized refresh:

   ```bash
   python scripts/refresh_check_record.py refresh \
     --math-classifications MATHEMATICAL_CHANGE_CLASSIFICATION.tsv \
     --output CHECK_RECORD.refreshed-01.md
   python scripts/refresh_check_record.py refresh \
     --math-classifications MATHEMATICAL_CHANGE_CLASSIFICATION.tsv \
     --require-math-complete --write
   ```

`--require-math-complete` requires explicit decisions for every active default
kind candidate. `--require-all-math-classified` is the stronger all-active
requirement. Neither infers mathematical meaning. Refresh requires all 102
completion entries/page sections and no explicitly unfinished active confidence
cells; it protects narrative and completion timestamps while updating numeric
metadata and the managed summary.

The existing documented promotion block uses assertions, does not lock the
whole validation/replacement sequence, and rereads export bytes after checking
parsed rows. It requires stable inputs and ordinary, nonoptimized Python.
The current refresh protects CHECK_RECORD against concurrent changes but does
not bind all ledger/classification/line-count reads as one atomic generation.
These are limitations of the existing examples; this inventory does not change
their workflow or execute promotion, refresh or final validation.
