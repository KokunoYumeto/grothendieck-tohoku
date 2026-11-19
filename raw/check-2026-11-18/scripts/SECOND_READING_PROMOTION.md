# Manual second-reading commands and reviewed-ledger promotion

The existing `second-reading/` sidecar supplies the stable row IDs. Its registry
is already initialized. The primary reviewer supplies every scan observation,
outcome and confidence; the commands below do not infer a reading.

## Per-page, per-row work

From the delivery directory:

```bash
python scripts/second_reading.py status
python scripts/second_reading.py page --page 119 --pending-only
python scripts/second_reading.py show --id R000123
```

Use the current printed page in place of the example. `show` provides one
row's prior review history. After the primary reviewer has inspected that
row's evidence, record its explicit outcome:

```bash
python scripts/second_reading.py decide --id R000123 --outcome confirm --confidence high --evidence "Reviewer-supplied scan location and exact second-reading observation."
```

For an amendment:

```bash
python scripts/second_reading.py decide --id R000123 --outcome amend --confidence high --evidence "Reviewer-supplied second-reading observation." --changes amendment.json
```

The amendment JSON replaces complete ledger fields, for example:

```json
{
  "new": "EXACT_REVIEWED_NEW_LITERAL",
  "evidence": "REVIEWER_SUPPLIED_EVIDENCE"
}
```

The illustrative values are not decisions. TeX backslashes need ordinary JSON
escaping. The allowed field keys are the ledger columns except `confidence`;
the confidence flag supplies the latter. The workbench does not edit TeX.

For a withdrawal, use `--outcome withdraw` with its own confidence and evidence.
All earlier events remain in the append-only history. A batch is a JSON array
of explicit individual decisions, each with `review_id`, `outcome`,
`confidence`, `review_evidence`, and, for amendments, `changes`. There is no
page-confirm operation.

```bash
python scripts/second_reading.py decide --batch page-decisions.json
python scripts/second_reading.py pending --page 119
python scripts/second_reading.py page --page build --pending-only
```

Unpaged build records are reviewed for their stated structural/build evidence;
their review note must not claim an image reading that did not occur.

## Required schema and annotated verdicts

The correction ledger has these ten columns, unchanged and in this order:

```text
file, layer, printed_page, line, statement, old, new, evidence, kind, confidence
```

Stable IDs, review events and fingerprints remain in separate sidecar/map
tables. Each final confidence cell should retain the explicit annotated form:

```text
high; second reading confirmed; R000123; E000456
```

The degree is `high`, `medium` or `low`; the verdict is `confirmed`, `amended`
or `withdrawn`. R and E identify the stable row and its last explicit event.
This annotation is metadata, not proof that the reading itself was correct.
Final validation now requires this annotated form and unique row/event IDs;
plain degrees fail. See `REVIEW_METADATA_GATES.md` for the mechanical gates.

## Export with withdrawal verdicts still visible

After `status` and `pending` show no registered or unregistered pending rows:

```bash
python scripts/second_reading.py export --output CORRECTIONS.reviewed-01.tsv --withdrawn retain --confidence-format annotated
```

This route retains a visible verdict for every registered row in the exported
ledger, including withdrawals. It creates the matching
`CORRECTIONS.reviewed-01.review-map.tsv`. The live ledger, original registry
and review-event history remain unchanged by export.

An `omit` export is an active-only ledger: withdrawn IDs/events/fingerprints
remain in its map and sidecar, but their verdicts are absent from the exported
ledger itself. A `plain` export drops verdict and ID annotations from confidence
cells; a retained withdrawal then needs its map for readers to distinguish it
from an active row. Use annotated retain for the stated per-row-verdict
requirement. See `SECOND_READING_EXPORT_AUDIT.md` for the synthetic comparison.

## Reviewable atomic promotion

The exporter deliberately refuses to overwrite `CORRECTIONS.tsv`. The following
separate operation checks a fresh annotated-retain export against the current
verified sidecar, preserves the pre-promotion ledger, writes explicit new
position bindings, and atomically replaces only the ledger. Use fresh output
names for a later promotion. This block is documentation; it was not executed
against the edition.

```bash
python - <<'PY'
from pathlib import Path
import csv, json, os, sys, tempfile
sys.path.insert(0, str(Path('scripts').resolve()))
from second_reading import align, fingerprint, load_project, previous_positions, read_ledger

root = Path.cwd()
ledger = root / 'CORRECTIONS.tsv'
reviewed = root / 'CORRECTIONS.reviewed-01.tsv'
review_map = root / 'CORRECTIONS.reviewed-01.review-map.tsv'
backup = root / 'CORRECTIONS.before-promotion-01.tsv'
bindings_path = root / 'review-promotion-bindings-01.json'
directory = root / 'second-reading'

_, _, _, states = load_project(directory, ledger)
current, current_hash = read_ledger(ledger)
_, unregistered = align(current, states, previous_positions(directory, states))
assert not unregistered and all(s['status'] != 'pending' for s in states.values())
exported, _ = read_ledger(reviewed)
with review_map.open(encoding='utf-8', newline='') as stream:
    mapping = list(csv.DictReader(stream, delimiter='\t'))
assert len(mapping) == len(exported) == len(states)
assert {r['review_id'] for r in mapping} == set(states)
assert {int(r['export_record']) for r in mapping} == set(range(1, len(exported) + 1))
bindings = {}
for item in mapping:
    review_id = item['review_id']
    position = int(item['export_record'])
    state, row = states[review_id], exported[position - 1]
    assert item['status'] == state['status']
    assert item['last_event'] == state['last_event']
    assert item['row_fingerprint'] == fingerprint(row) == fingerprint(state['row'])
    expected = f"{state['confidence']}; second reading {state['status']}; {review_id}; {state['last_event']}"
    assert row['confidence'] == expected
    bindings[review_id] = position
assert read_ledger(ledger)[1] == current_hash
with backup.open('xb') as stream:
    stream.write(ledger.read_bytes())
with bindings_path.open('x', encoding='utf-8') as stream:
    json.dump(bindings, stream, indent=2)
    stream.write('\n')
temporary_path = None
try:
    with tempfile.NamedTemporaryFile('wb', dir=root, prefix='reviewed-ledger-', suffix='.tmp', delete=False) as stream:
        temporary_path = Path(stream.name)
        stream.write(reviewed.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, ledger)
finally:
    if temporary_path is not None:
        temporary_path.unlink(missing_ok=True)
PY
python scripts/second_reading.py sync --bindings review-promotion-bindings-01.json
python scripts/second_reading.py status
```

The explicit binding step matters: printed-page export ordering can move
identical rows, especially around unpaged build entries. The workbench refuses
to guess their identities from repeated literals. The exact export map supplies
the new positions while fingerprints and recorded versions remain enforced.
`sync` updates the derived index; it neither rewrites existing registry rows
nor appends a review decision.

Eight synthetic promotion checks confirmed this sequence, the refusal before
pending rows are resolved, the intentional duplicate-identity gate, unchanged
registry/event bytes and retained annotated withdrawal verdicts. No live ledger
or review state was promoted or synchronized by the auxiliary reviewer.
