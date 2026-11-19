# CHECK_EVENTS mechanical inventory and final gate

`check_events_inventory.py` reads only `CHECK_EVENTS.tsv` and an optional
explicit policy. It does not read page sources, scans, research folders,
correction rows or second-reading state. It creates a new interim report and
never edits the event table. No outcome prose is copied into the reports.

This utility does not decide whether a statement is true, a proof is valid,
an outcome is a refutation, or the required proof coverage is complete.

The final gate is implemented separately by `check_events_gate.py` and is now
mandatory in `final_validate.py` and FINAL checkpoint preflight. It uses the
approved policy at `validation-policy/check-events-policy.json`. Its selector
is exact, case-sensitive equality of the `type` cell to
`refuted, with the refined statement's id`; outcome prose never selects a row.
The historical inventory command and its broader default marker remain
available for diagnostics. Hourly checkpoint creation is unchanged.

## Historical inventory snapshots

The early diagnostic report is `check-events-interim-02`. The earlier
`check-events-interim-01` is preserved unchanged. The second snapshot records
tighter identifier boundaries after synthetic testing found that a longer
token could otherwise be mistaken for a shorter declared identifier. The
two snapshots have the same event input hash and numerical findings.

| Measure | Count |
| --- | ---: |
| Logical event records | 187 |
| Correct-width records | 187 |
| Distinct literal event types | 19 |
| Distinct literal statement IDs | 183 |
| Malformed records or parse errors | 0 |
| Missing or blank required cells | 0 |
| Exact duplicate record groups | 0 |
| Rows selected by a refutation-word marker | 28 |
| Extracted ID occurrences in selected rows | 27 |
| Extracted occurrences without an equal statement-ID cell | 11 |
| Distinct unmatched candidate IDs | 11 |
| Marker-selected rows without an extracted ID | 1 |

The full literal type values and counts are in `EVENT_TYPE_COUNTS.tsv`.
`UNMATCHED_ID_CANDIDATES.tsv` gives each unmatched literal, its containing
event record and statement ID, the field and character offsets, the extraction
rule, and its hash. Event record 92, with literal ID
`p193:stalk-failure-example`, is the one selected row without an extracted
candidate. These are pending mechanical findings, not editorial decisions.

## Invocation

Run from the delivery root, using a fresh relative output directory:

```sh
python scripts/check_events_inventory.py --output check-events-interim-03
```

An existing report is never overwritten. The default policy is deliberately
unapproved, has an empty allowed-type list, and cannot pass the proposed gate.
The report command still succeeds so that its findings can be reviewed.

For a later, separately approved policy stored inside the delivery tree:

```sh
python scripts/check_events_inventory.py \
  --output check-events-interim-04 \
  --policy validation-policy/check-events-policy.json \
  --require-gate
```

The policy path is relative to the delivery root. The script rejects policy
symlinks, protected context folders and paths escaping that root. The option
`--require-gate` installs the report and returns a nonzero exit status if any
check fails. It changes no event data and does not authorize packaging.

`PROPOSED_GATE_POLICY.json` is a reviewable starting point. The primary must
explicitly approve its literal type vocabulary and reference contract. The
utility never derives approval from the fact that a value already occurs.
Keep all five required fields. Do not treat `approved` as a proof verdict.

## Schema and parsing rules

The exact required header and order are:

```text
statement_id  date  who  type  outcome
```

The actual file uses tab separators. The existing writer appends five
positional fields in this order. It defines no event-type enumeration or
identifier-reference parser. The separate `COLS` constant in the audit helper
belongs to the correction ledger and is not the event-table schema.

The inventory parses UTF-8, permits an initial byte-order mark, and uses strict
CSV-style quoting with a tab delimiter. Quoted tabs and newlines are preserved.
Logical event records are numbered from one, excluding the header; physical
line spans are recorded where needed. An unparseable row stops reliable
enumeration and marks the inventory incomplete. A width mismatch is reported
without guessing which field is missing. A duplicate or absent header name
cannot silently supply an expected field.

Required cells are checked for absent/ambiguous columns, empty strings and
whitespace-only strings. The values themselves are never trimmed or
normalized. Dates are checked for presence only; this helper does not validate
calendar values or the writer's timestamp format.

Exact duplicate groups compare every parsed field value. Each member also has
a hash of its serialized record, so different quoting or line endings remain
visible. Repeated statement IDs or timestamps alone are allowed: events can
record multiple actions for one statement, and the writer can give several
events the same timestamp. The inventory neither deletes nor merges records.

## Explicit lexical reference contract

The default selector looks in both `type` and `outcome`, using this
case-insensitive regex:

```regex
\b(?:refutation|refuted|refute|refutes|refuting)\b
```

Selecting a row by this word marker makes no judgment about its proof.
Reference extraction then considers those same two fields. The policy records
the exact regular expressions, their order, and all selector fields.

The default identifier atom is:

```regex
[A-Za-z0-9]+(?:[_.:–-][A-Za-z0-9]+)*(?:\([A-Za-z0-9]+\))?
```

Candidate rules recognize `TOH-`/`TOH:` prefixes, numeric variants such as
`TOH218-`, three-digit page prefixes such as `p119:` or `p119-`, dotted numeric
prefixes followed by a colon, backtick-delimited ID-shaped tokens, and explicit
statement-ID introducers. The quoted and introduced rules require a digit and
an identifier separator. Exact occurrences of already declared statement IDs
are considered as well. The longest known IDs are considered first; earlier
rule spans take precedence and overlapping extractions are not counted twice.

Prefix and exact-known matching rejects an identifier embedded in a longer
identifier token. The default left boundary excludes letters, digits and
`_.:–-`; the right boundary rejects letters, digits, an underscore, a separator
followed by a letter/digit, or a further parenthesized suffix. Unsupported or
ambiguous token forms may therefore remain unextracted and require manual
review. Bare theorem numbers are not generally assumed to be statement IDs.

Candidate extraction may recognize a prefix without regard to case, but the
captured literal is preserved. Binding is strictly case-sensitive equality
against the `statement_id` cells in this event table. No spelling, punctuation,
case, whitespace or ID is normalized. An ID found only in some other document
is outside this catalog. A missing local binding does not establish that the
statement or its proof is absent elsewhere.

## Final packaging checks

All eight named checks are mandatory in final validation and FINAL checkpoint
preflight. The inventory command itself remains read-only. The adapter requires
the six exact user-authorized type values, all five required fields, the approved
reference rules and explicit Boolean approval fields. It neither normalizes
values nor infers approval from observed event counts:

| Check | Requirement |
| --- | --- |
| `check-events-schema` | Exact five-column header and order. |
| `check-events-tsv` | Complete strict parsing, correct row widths and at least one event. |
| `check-events-required-fields` | Every required field is present and nonblank. |
| `check-events-exact-duplicates` | No exact parsed-value duplicate group remains unresolved. |
| `check-events-literal-types` | Every literal type value belongs to an explicitly approved list. |
| `check-events-refutation-id-bindings` | Every extracted reference has an exactly equal local statement-ID value. |
| `check-events-reference-presence-policy` | Every exact-type-selected row has an extracted ID under the approved contract. |
| `check-events-policy-approved` | The approved policy retains the exact six-type, five-field and reference contract, with explicit true approval and reference requirements. |

The historical draft reports recorded three failed checks: unapproved type vocabulary, 11 missing
literal ID bindings, and unapproved policy. The no-reference row is visible
regardless of the optional reference-presence requirement. The default does
not invent a requirement that every marker-bearing row must contain an ID.

Final validation captures the event and policy bytes during inventory hashing,
evaluates all eight named results and rechecks both snapshots before returning.
It rejects an event input whose byte count changed after inventory. Missing or
malformed policy cannot receive permissive defaults. Final checkpoint preflight
requires both files and every named check, evaluates the same current bytes it
hashes, and rechecks them. An omitted check cannot count as passing. The hourly
`create` path does not invoke these FINAL-only prerequisites.

Reference binding is literal and case-sensitive. Ambiguous prose introduced by
`Refined statement:` retains the approved ID-shape filter. A token introduced
by an actual bounded `ID` word is also required to bind even if it lacks a digit
or separator. This adds no prose or mathematical classification. An extracted
ID can bind only to an exactly equal `CHECK_EVENTS.statement_id` value.

Existing source-credit, privacy, review, PDF and build checks remain active.
No external-ID exemption or automatic type normalization is implemented. A
separate external catalog would need its own explicit contract and hash binding.
Implementation and synthetic-test receipts are preserved in
`mechanical-final-detector-proposal-interim-01/event-integration/`.

## Output and limitations

`SCHEMA.tsv`, malformed/missing-field tables, duplicate tables, literal type
counts, the statement-ID catalog, marker rows, reference tables and proposed
gate checks accompany `REPORT.md`, `SUMMARY.json`, the draft policy and
`INPUT_HASHES.tsv`. All reviewable findings remain pending. The report hashes
the original input bytes and rechecks them immediately before exclusive
installation. Later event changes require another fresh report.

Generated payloads pass through the existing privacy scanner before being
installed. Any derived literal that needs privacy filtering is marked and
retains a hash of the original value. This is not an event-source privacy
certification; the existing final privacy scan remains necessary. Relative
locators contain no private workspace path.

The lexical rules cannot prove that all possible prose references were found,
that an outcome is mathematically valid, that an event is sufficient evidence,
or that every required statement has been checked. These questions stay with
the primary reviewer. No event value, source, mathematical record, review
decision, existing snapshot or edition PDF was changed by this work.
