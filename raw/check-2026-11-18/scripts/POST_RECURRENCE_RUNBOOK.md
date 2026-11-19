# Post-recurrence mechanical runbook

Commands below are run from `TOHOKU_CHECK`. They describe later primary-controlled
work; preparing this runbook executes none of them. Use fresh suffixes for every
export, inventory, build phase and preview. Preserve earlier snapshots.

**Dependency rule:** complete the primary recurrence and any remaining primary
mathematical/context work first. Any later source or correction-row change
returns to review/promotion and invalidates affected inventories, row/group
fingerprints and builds. Only the primary supplies readings, classifications,
event normalization and PDF-review verdicts.

## 1. Resolve new rows and promote the reviewed ledger

```bash
python scripts/second_reading.py status
python scripts/second_reading.py pending
python scripts/second_reading.py export --output CORRECTIONS.reviewed-final-01.tsv \
  --withdrawn retain --confidence-format annotated
```

`export` is the enforced pending/unregistered-row gate; successful `status` or
`pending` exit alone does not mean completion. Retained withdrawals preserve
their explicit verdicts while active-count helpers exclude them.

There is no promotion subcommand. Execute the separately reviewable promotion
block in `SECOND_READING_PROMOTION.md`, using these matching filenames:

| Variable in that block | Final-cycle value |
| --- | --- |
| `reviewed` | `CORRECTIONS.reviewed-final-01.tsv` |
| `review_map` | `CORRECTIONS.reviewed-final-01.review-map.tsv` |
| `backup` | `CORRECTIONS.before-promotion-final-01.tsv` |
| `bindings_path` | `review-promotion-bindings-final-01.json` |

Keep its inputs stable and use ordinary Python, without optimization: that
existing manual block uses assertions, does not lock the whole transaction,
and rereads the export after checking it. Then run:

```bash
python scripts/second_reading.py sync --bindings review-promotion-bindings-final-01.json
python scripts/second_reading.py status
```

The explicit bindings protect identical rows when export changes their positions.

## 2. Refresh the complete French inventory and propose hash rebindings

```bash
python scripts/french_layer_inventory.py --interim --all-literal \
  --row-id-index second-reading/REVIEW_INDEX.tsv --privacy-filter-derived \
  --output french-layer-post-recurrence-interim-01
python scripts/french_layer_rebind.py \
  --baseline-inventory french-layer-inventory-01 \
  --review-table FRENCH_LAYER_REVIEW.tsv \
  --current-inventory french-layer-post-recurrence-interim-01 \
  --output french-layer-rebinding-interim-01 --privacy-filter-derived
```

The baseline above matches all 471 historical review ID/page/hash triples
observed during preparation. The new inventory includes metadata differences.
The rebinder requires unique exact full hashes and pages, reports changed/missing
hunks and correction-ID fingerprints, and leaves every proposal pending.
It does not transfer a verdict or rewrite `FRENCH_LAYER_REVIEW.tsv`.

The primary handles unmatched/changed rows and explicitly records the resulting
current review table while preserving the former review history. Hunk IDs alone
cannot carry a decision across changed hashes. A source/ledger edit here returns
to step 1 and needs another fresh inventory.

## 3. Run a diagnostic build only when the primary opens the build phase

```bash
python scripts/build_report.py --phase before-final-01 \
  --layers dip fr en --limit-pt 2
```

The default runtime is `../tmp/tex-runtime`; all three layer mains receive two
passes unless a fatal first pass stops that layer. Review diagnostics and make
only explicit primary-authorized fixes. A diagnostic run can exit zero despite
overflow above the limit, so its exit alone is not the final PDF gate.

Any source/correction fixes repeat steps 1–2 before later final artifacts.
Keep TeX stable during compilation; build hashes are captured before the build.

## 4. Classify all active kinds through exact literal groups

After the last intended source/ledger fixes and promotion:

```bash
python scripts/math_literal_groups.py prepare --ledger CORRECTIONS.tsv \
  --output math-literal-groups-interim-01 --privacy-filter-derived
```

This includes every active row, including unpaged build rows, and excludes
withdrawals. Groups use exact original `(kind, old, new)` values, with full
group and R-ID/fingerprint membership hashes. Display filtering cannot merge
different raw groups.

Make a separate primary working copy of `GROUP_DECISIONS.tsv` as
`GROUP_DECISIONS.primary.tsv`. Edit only classification, summary and reason;
retain the group/membership hashes. Review the full `GROUP_MEMBERS.tsv` when
context matters. Both yes/no require a reason; yes also needs a summary.
Unselected or pending groups supply no verdict.

For exceptions, create `ROW_EXCEPTIONS.primary.tsv` with the five core columns
shown in `MATH_LITERAL_GROUPS.md`, using exact current R IDs/fingerprints.
An explicit pending exception withholds that row from its group decision.

```bash
python scripts/math_literal_groups.py expand --ledger CORRECTIONS.tsv \
  --group-decisions GROUP_DECISIONS.primary.tsv \
  --row-exceptions ROW_EXCEPTIONS.primary.tsv \
  --output math-classification-expanded-interim-01 --privacy-filter-derived
```

Omit `--row-exceptions` when none exist. For later batches, add
`--existing-classifications` pointing to the previous expanded per-row table,
and choose a new output directory. Existing yes/no values and marked pending
exceptions are preserved; explicit new row exceptions have priority. A changed
group membership or row fingerprint is rejected. Summaries/reasons are copied
exactly from primary decisions and are never generated or privacy-redacted.

The final per-row file for the commands below is
`math-classification-expanded-interim-01/MATHEMATICAL_CHANGE_CLASSIFICATION.tsv`.
Substitute the actual final expansion directory consistently. Every active row
must eventually have an explicit yes/no; a protected pending exception remains
a completion blocker. See `MATH_LITERAL_GROUPS.md` for schemas and provenance.

## 5. Normalize and bind CHECK_EVENTS under an explicit primary contract

```bash
python scripts/check_events_inventory.py --output check-events-before-final-interim-01
```

The helper is read-only and has no normalization command. The primary must
prepare and review the literal type mapping and any corrected/refined statement
ID records, preserve the former table, and promote the resulting event table.
Preserve reference information when changing type labels. A missing local ID
binding requires an explicit resolution, not disappearance of its marker.

Approve the literal vocabulary and reference rules in a separate policy file,
retaining all five required fields and Boolean approval flags. Then run:

```bash
python scripts/check_events_inventory.py --output check-events-final-interim-01 \
  --policy validation-policy/check-events-policy.json --require-gate
```

All eight checks must pass under that explicit contract. The catalog is literal
CHECK_EVENTS statement IDs; no external-ID exemption or automatic normalization
is implemented. This remains a separate prerequisite: final_validate/checkpoint
do not currently invoke or require these event checks. No new gate is installed
by this runbook. See `CHECK_EVENTS_VALIDATION.md` for the contract and limits.

## 6. Produce the final PDFs and complete actual PDF review

```bash
python scripts/build_report.py --phase after-final-01 --layers dip fr en \
  --limit-pt 2 --publish-pdfs
```

Publication requires both passes to succeed for all selected layers and the
requested overflow limit. Final validation independently requires all three
layers, exit codes `0,0`, zero final-pass errors and maximum overflow at most
2 pt. Warnings still require review; the gate does not interpret them.

Use `DIAGNOSTICS.tsv`, `PDF_SOURCE_MAP.tsv` and `REVIEW_GT10PT.tsv` as location aids. The primary
performs the actual required PDF inspection and completes `PDF_CHECK.md`.
The helpers do not supply a visual-success verdict. Any resulting source change
requires another review/promotion, affected inventory/classification update,
fresh build phase and PDF review.

## 7. Refresh final counts after the last source/ledger change

```bash
python scripts/refresh_check_record.py refresh \
  --math-classifications math-classification-expanded-interim-01/MATHEMATICAL_CHANGE_CLASSIFICATION.tsv \
  --require-all-math-classified --output CHECK_RECORD.final-preview-01.md
```

Review that separate preview, then apply the protected update:

```bash
python scripts/refresh_check_record.py refresh \
  --math-classifications math-classification-expanded-interim-01/MATHEMATICAL_CHANGE_CLASSIFICATION.tsv \
  --require-all-math-classified --write
```

The all-kind requirement is stronger than `--require-math-complete`, which
covers only misprint/translation. Row fingerprints survive confidence-only
annotation and reordering, but other row-field changes invalidate classifications.
Refresh preserves narrative and original timestamps. Keep its inputs stable;
its concurrency guard protects CHECK_RECORD but is not a whole-project snapshot.

## 8. Finish records, validate privacy/credits, then freeze and package

Finish NOTES, PDF_CHECK, README and every intended returned record first. Use
the supplied original source ZIP for byte-level credit/frontmatter comparison:

```bash
python scripts/final_validate.py --original-sources ../upload/TOHOKU_sources.zip \
  --final-phase after-final-01
python scripts/checkpoint.py preflight
python scripts/checkpoint.py final
python scripts/final_validate.py --original-sources ../upload/TOHOKU_sources.zip \
  --final-phase after-final-01 --archive ../TOHOKU_CHECK.zip
```

Validation binds current TeX and delivered PDFs to the selected final build and
checks structure, evidence, confidence, privacy and original credits. Preserve
credit bytes; protected-source privacy conflicts remain separate failing findings,
not automatic redactions or waivers. Proof judgments, mathematical classification
completion, event normalization and substantive PDF/notes completion remain the
explicit upstream responsibilities above.

Freeze the delivery after final validation: any included-file change or addition
requires validation again before packaging. Final packaging reruns preflight,
refuses stale inventories and enforces strictly less than 500,000,000 bytes per
ZIP. For a split archive, pass every actual part with a separate `--archive`.
The archive postcheck is read-only by default; if saved with `--report-dir`, put
that output outside the delivery tree. Do not change even validation-report
bytes after packaging without rebuilding and rechecking the archive.

Hourly checkpoint behavior is unchanged. No live promotion, classification,
event normalization, source edit, refresh, build, final validation or packaging
was performed in preparing this runbook and its synthetic-tested interfaces.
