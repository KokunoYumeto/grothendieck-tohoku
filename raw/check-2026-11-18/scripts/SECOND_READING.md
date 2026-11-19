# Second-reading workbench

`second_reading.py` reads the correction ledger only. It never opens a scan,
rendered image, TeX page or research context, and never infers an image reading.
It does not modify `CORRECTIONS.tsv`, any TeX source, `CHECK_RECORD.md`,
`CHECK_EVENTS.tsv` or `progress.log`.

## Start and inspect

From the delivery directory:

```bash
python scripts/second_reading.py init --reviewer "GPT-6 Astra (ChatGPT Pro mode)"
python scripts/second_reading.py status
python scripts/second_reading.py pending
python scripts/second_reading.py page --page 150 --pending-only
```

Initialization assigns stable IDs such as `R000001`. Every imported row starts
**pending**, regardless of its first-pass confidence. The index is grouped in
printed order: 119-183, then 185-221, then unpaged build entries. Use
`page --page build` for that last group. IDs never change when the index is
sorted or the ledger's distinguishable rows are reordered.

The `second-reading/` sidecar contains:

- `ROW_REGISTRY.tsv`: original rows and stable IDs; existing rows are retained.
- `REVIEW_EVENTS.tsv`: append-only decisions, evidence notes, field amendments,
  timestamps, reviewers and a history hash chain.
- `REVIEW_INDEX.tsv`: the current grouped review state, rebuilt from the records.
- `REVIEW_META.tsv`: initialization and reviewer metadata.

`ledger_record` means the data-record number excluding the header; it is not
a physical line number in the multiline TSV.

## Supply each observed decision explicitly

After inspecting the relevant crop yourself, record one decision. Replace the
illustrative ID and note below with the actual ID and observed evidence:

```bash
python scripts/second_reading.py decide --id R000123 --outcome confirm --confidence high --evidence "Your note identifying the inspected scan location and exact reading."
```

Every decision requires an ID, `confirm`, `amend` or `withdraw`, a `high`,
`medium` or `low` confidence, and a nonempty review-evidence note. A later
decision for the same ID appends a new event and preserves the earlier one.

For an amendment, supply a JSON file containing explicit replacements for
correction fields, for example `new` and `evidence`, and add:

```bash
python scripts/second_reading.py decide --id R000123 --outcome amend --confidence high --evidence "Your second-reading observation." --changes amendment.json
```

The `changes` file replaces complete field values, with ordinary JSON escaping
for TeX backslashes. Confidence is supplied by the confidence flag, not by the
field-replacement file. Amendments and withdrawals **do not edit or revert
TeX**; the primary reviewer applies the corresponding source changes.

For multiple explicit decisions, use `decide --batch decisions.json`. The
file is a JSON array; each entry must supply its own ID, outcome, confidence
and evidence. For example, this is a schema illustration, not an actual review:

```json
[
  {
    "review_id": "R000123",
    "outcome": "confirm",
    "confidence": "high",
    "review_evidence": "Replace with the inspected scan location and reading."
  }
]
```

An amendment entry also supplies a `changes` object. The whole batch is
validated before any event is appended. There is no automatic page-confirm
or confidence-inference command.

## Keep IDs aligned and inspect history

```bash
python scripts/second_reading.py sync
python scripts/second_reading.py show --id R000123
```

`sync` registers genuinely new rows as pending. Unexplained changes or removal
of registered rows are refused. An explicit matching amendment or withdrawal
can document a ledger edit the primary reviewer has already made.

Identical rows whose positions change require explicit bindings; the tool
does not guess their identities. Supply `--bindings bindings.json` to `sync`
or `decide`, where the JSON object maps IDs to current ledger-record numbers,
for example `{"R000123": 127}`. Read-only status commands report unregistered
records as pending and direct the reviewer to synchronize them.

## Export a reviewed copy

When no registered or unregistered row remains pending:

```bash
python scripts/second_reading.py export --output CORRECTIONS.reviewed.tsv --withdrawn omit
```

The export retains the original columns and their order, and is grouped in printed
order. Its confidence cells include the explicit confidence, second-reading
outcome and review/event IDs. `--confidence-format plain` instead writes only
the confidence level; the outcome remains in the sidecar history.

Choose `--withdrawn omit` for an active correction ledger or `--withdrawn retain`
for a historical copy with withdrawals explicitly labeled. The choice is
required. A separate review-map TSV records every exported or omitted ID and
the row-content fingerprint. The fingerprint binds a later report's ID to
the exact correction content, including when confidence cells are exported
without ID annotations. It does not alter the correction-ledger schema.
Exports refuse pending rows and existing filenames, and cannot overwrite
`CORRECTIONS.tsv` or write into the source/PDF trees. The primary reviewer
reviews the copy and explicitly promotes it when appropriate.

## Preparation checks

The helper was checked with temporary synthetic ledgers: pending initialization,
printed ordering, explicit decisions, amendments and withdrawals, stable IDs
after reordering, new-row synchronization, invalid-batch rejection, unchanged
input ledgers, preserved event history and explicit duplicate-row bindings.
No actual ledger was initialized or reviewed during helper preparation.
