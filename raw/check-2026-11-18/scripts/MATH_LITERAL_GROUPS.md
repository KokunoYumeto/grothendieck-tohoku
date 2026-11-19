# Exact literal groups for primary mathematical classification

`math_literal_groups.py` prepares every **active** row of an explicitly promoted
ledger, across all kinds and pages including unpaged build rows. It groups by
the exact original `(kind, old, new)` strings, with no normalization or semantic
inference. Full member metadata remains available for context-sensitive decisions.
The ledger must have canonical, unique annotated R IDs and last-event IDs;
withdrawn entries are excluded. No review history or source is opened.

## Prepare a fresh pending snapshot

From the delivery directory, after promotion:

```bash
python scripts/math_literal_groups.py prepare \
  --ledger CORRECTIONS.tsv \
  --output math-literal-groups-interim-01 \
  --privacy-filter-derived
```

`GROUP_DECISIONS.tsv` contains one row per exact literal group.
`GROUP_MEMBERS.tsv` lists each R ID, row fingerprint, current position and all ten
ledger fields. Pages, layers and member IDs are also listed in the group table.
`MATHEMATICAL_CHANGE_CLASSIFICATION.tsv` has the existing fourteen-column core
plus provenance columns. Every new group and row is `pending`, with blank summary
and reason. `ROW_EXCEPTIONS.tsv` initially has only the five core column headers
shown below, ready for explicit primary row exceptions.
The helper's unclassified rows explicitly have `row_exception=no`; passing that
marked pending table as an existing input still permits group decisions to apply.

Make a separate primary working copy of `GROUP_DECISIONS.tsv`. Edit only
`mathematical_change`, `summary` and `reason`; preserve `group_id`, `group_sha256`
and `membership_sha256`. Both `yes` and `no` require an explicit reason; `yes`
also requires an explicit summary. An omitted group or `pending` group supplies
no row decision. Equal literals do not establish equal mathematical significance.

## Expand only explicit decisions

```bash
python scripts/math_literal_groups.py expand \
  --ledger CORRECTIONS.tsv \
  --group-decisions GROUP_DECISIONS.primary.tsv \
  --row-exceptions ROW_EXCEPTIONS.primary.tsv \
  --output math-classification-expanded-interim-01 \
  --privacy-filter-derived
```

Omit `--row-exceptions` if there are none. A row-exception file requires the
existing five core columns, with exact current R IDs and row fingerprints:

```text
correction_id, row_fingerprint, mathematical_change, summary, reason
```

Use actual tab separators. Each listed row is an explicit override, including
`pending`; pending prose may be blank or explicitly supplied. The empty exception
template uses those five columns; expanded exception-history tables add
permitted provenance columns.

For later expansions, add the previous output explicitly:

```bash
python scripts/math_literal_groups.py expand \
  --ledger CORRECTIONS.tsv \
  --group-decisions GROUP_DECISIONS.primary.tsv \
  --existing-classifications math-classification-expanded-interim-01/MATHEMATICAL_CHANGE_CLASSIFICATION.tsv \
  --output math-classification-expanded-interim-02 \
  --privacy-filter-derived
```

Precedence is: explicit new row exception; existing per-row yes/no or protected
pending exception; explicit group yes/no; fresh pending. Thus a group never
overwrites an existing yes/no or a pending exception. New row exceptions may
explicitly supersede earlier per-row values. `row_exception=yes` and decision
provenance preserve holds across repeats even without resupplying the exception
file. Legacy existing pending rows lacking that marker are conservatively kept
as row holds; omit a pristine legacy pending template when that is not intended.

## Binding, provenance and limits

The full group hash binds the original exact three-field tuple. The membership
hash binds that group hash and the complete sorted set of R IDs and row
fingerprints. Every supplied group row must match both current hashes, even when
pending. Changed, removed or added members require a fresh reviewed group
snapshot; changed row fingerprints also invalidate existing row decisions.
Ledger reordering alone preserves these identities. Classification decisions
carry their original group/row origin, input-file hash and data-record number.
Existing helper decisions are hash-bound; change them through a separate explicit
row-exception input. Missing decisions remain pending and are never treated as no.

Outputs also include `WITHDRAWN_ROWS_EXCLUDED.tsv`, `INPUT_HASHES.tsv`,
`PRIVACY_FILTERING.tsv`, `SUMMARY.json` and `REPORT.md`. All selected input bytes
are rechecked before exclusive installation. Paths are relative to `--root`
(default: the delivery directory); protected folders, symlinks and existing output
paths are refused. Existing snapshots and all live records remain unchanged.

Optional privacy filtering affects displayed ledger metadata only, after grouping
and fingerprinting. Every altered cell is marked and retains original/filtered
hashes. Different raw values remain different groups even when filtered displays
look identical. Mathematical decisions, summaries and reasons are never filtered;
a privacy finding in decision prose blocks output. Without the flag, any output
privacy finding blocks installation.

The existing per-row loader validates every prepared classification output before
installation. This helper runs no source read, scan reading, build, refresh or
final-readiness gate, and changes none of those workflows. Review and use its
explicit per-row output through the existing primary-controlled refresh sequence.

Synthetic checks: `python -m unittest discover -s scripts -p 'test_math_literal_groups.py'`.
