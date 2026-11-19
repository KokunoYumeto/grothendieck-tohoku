# Read-only French hunk rebinding proposals

`french_layer_rebind.py` compares an explicit historical review table with its
baseline inventory and a newly generated current inventory. It writes one fresh
interim report directory and never writes `FRENCH_LAYER_REVIEW.tsv` or other live
records. Every output `review_status` is `pending`; prior decisions are historical
metadata only.

From the delivery directory, after generating a fresh current inventory:

```bash
python scripts/french_layer_rebind.py \
  --baseline-inventory french-layer-inventory-01 \
  --review-table FRENCH_LAYER_REVIEW.tsv \
  --current-inventory french-layer-current-interim-NEW \
  --output french-layer-rebinding-interim-NEW
```

Replace both `NEW` names with actual fresh directory names. The helper does not
generate the current inventory or verify its freshness against source files.
An older inventory predating source or ledger edits is insufficient. All three
input paths and the output path are relative to `--root`, which defaults to the
delivery directory containing `scripts`. Existing outputs, symlinks, protected
context folders and output paths inside source, PDF, review-state or input
inventory directories are refused.

## Match and input contract

Both inventory directories must contain `FRENCH_LAYER_DIFFERENCES.tsv` with
`hunk_id`, `printed_page`, `hunk_sha256`, `candidate_correction_ids`, and
`LEDGER_ID_BINDINGS.tsv` with `correction_id`, `ledger_record`, `row_fingerprint`,
`id_source`. Other inventory columns are permitted. Optional input/source hash,
comparison-settings, metadata-rule and privacy-filter manifests are captured
for provenance only; their referenced paths are never followed.

The review header must be exactly this ordered TSV schema:

```text
hunk_id  printed_page  hunk_sha256  decision  correction_ids  reason  reviewed_utc  reviewer
```

The displayed spaces above represent tab separators. Correction references are
blank or comma-separated canonical `R` IDs, allowing whitespace beside commas.
The original field and its hash preserve order and spacing. Malformed or
duplicate reference fields are flagged, without guessing partial IDs. They may
coexist with an exact hunk proposal, which then has an explicit reference metadata
attention flag and nonzero attention count. Canonical IDs use a positive integer,
at least six digits, and no excess leading zeroes. `R` is a stable review ID;
`L` is explicitly labelled a snapshot-local ledger locator. Comparing the same
`L` label across inventories never asserts stable cross-snapshot identity.

A proposal requires a unique prior review whose hunk ID, page and full SHA-256
agree with the unique baseline row, plus one uniquely identified current row
with that same full hash and page. Current hunk ordinals may differ. Duplicate
IDs or hashes prevent affected rebindings. Hashes include page, operation,
offsets and raw fragments: changed offsets can therefore leave visually similar
text unmatched. There is no fuzzy, moved-content or content-equivalence match.
The utility trusts the supplied inventory hash fields; it does not recompute
them or open TeX, scans, correction ledgers or readiness records.

## Reports

| File | Purpose |
| --- | --- |
| `REBINDING_PROPOSALS.tsv` | Page-sorted exact associations, always pending, with historical decision metadata. |
| `UNMATCHED_PRIOR_REVIEWS.tsv` | Every historical review without a unique validated association. |
| `UNMATCHED_BASELINE_HUNKS.tsv`, `UNMATCHED_CURRENT_HUNKS.tsv` | All inventory rows not linked by a proposal, including unreviewed rows. |
| `VALIDATION_ISSUES.tsv` | Invalid, duplicate, missing, changed and ambiguous identities. |
| `ID_BINDING_COMPARISON.tsv`, `BINDING_METADATA.tsv` | All bindings and their fingerprints; missing, new, changed and ambiguous bindings, record movement and identity-source changes. |
| `REFERENCED_ID_CHECKS.tsv` | Each historical R reference in original order, its binding status, and baseline/current candidate membership. |
| `INPUT_HASHES.tsv` | Exact input-file hashes, including the historical review bytes and optional manifest presence. |
| `PRIVACY_FILTERING.tsv`, `SUMMARY.json`, `REPORT.md` | Explicit presentation filtering, counts and limitations. |

Reasons, reviewers and identity-source prose are hashed rather than copied.
Canonical record hashes bind parsed cells and header order; complete input
hashes preserve the original TSV bytes. Every input and optional-manifest
presence is rechecked immediately before exclusive installation. All prepared
output bytes receive privacy inspection. By default a finding blocks the report.
Optional `--privacy-filter-derived` filters presentation fields only, with each
changed cell marked and both original and filtered hashes recorded. Comparison
and provenance always use the original captured values.

Neither exact matches, unchanged fingerprints nor candidate associations approve
a correction, transfer a decision, establish inventory freshness, or satisfy a
review or final-readiness gate. Six focused synthetic fixture groups are runnable
with `python -m unittest discover -s scripts -p 'test_french_layer_rebind.py'`.
