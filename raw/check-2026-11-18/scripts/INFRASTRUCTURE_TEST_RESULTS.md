# Mechanical infrastructure verification

Recorded 2026-11-18T16:42:32Z.

## Scope

This record concerns helper implementation and mechanical behavior. All test
sources, ledgers, reports and ZIPs used for final validation/packaging tests
were synthetic temporary fixtures. Blank fixture PDFs were generated directly;
no edition TeX build or image/scan inspection occurred. The actual delivery's
final validation, preflight and final archive creation were not run.

## Passed verification groups

| Group | Passed assertions | Main coverage |
| --- | ---: | --- |
| Literal-binding report | 43 | Exact presence/absence, empty replacements, locators, inherited-brace diagnostics, later-record candidates, unchanged inputs, privacy filtering, hashes and concurrent-edit refusal. |
| Privacy scanner | 44 | Text suffix independence, Unicode encodings, local-reference spellings, member names, ZIP/member comments, generated metadata, cross-chunk matching, missing parts and PDF textual metadata. |
| Packaging integration | 19 | Current all-pass reports, exact inventory hashes, stale/added/removed files, exact report-name exemptions, same-stat mutation, split-member maps, final refusal, hourly behavior and metadata-only dry run. |
| Complete synthetic final workflow | 18 | Validation → report-bound preflight → temporary ZIP checks → installation → read-only postcheck, plus unexpected members, source-credit conflicts and filename privacy. |
| Focused regressions | 10 | Unicode names, shared log filtering, valid Python path operators versus literals/comments, malformed-code fallback, diplomatic front-matter comparison and BOM-aware credit boundaries. |

These are assertion counts for grouped fixture runs, not counts of independent
real-world cases. All generated fixture directories and ZIPs were disposable.

## Verified final behavior

- Final packaging requires the five generated validation reports, all-pass
  checks including both privacy checks and, after the follow-up below, explicit
  second-reading confidence/unique-identifier checks, and matching current file hashes.
- Only the five exact root-relative validation-report names are exempt from
  their own stale-inventory comparison; their actual packaged bytes are still
  scanned and bound to fresh preflight hashes.
- All final ZIP parts are inspected together before installation. Logical
  chunks are reconstructed, and generated manifests, filenames and comments
  participate in privacy inspection.
- A later archive postcheck compares every current logical file, including
  validation reports, and is read-only by default.
- A synthetic privacy occurrence in byte-identical protected source content
  was reported separately, blocked the final gate and left the notice bytes
  unchanged. No automatic credit exception or source redaction was introduced.
- Hourly checkpoint timing/completion behavior and the metadata-only dry run
  remain separate from the final-validation gate.

## Actual helper-only checks

Python syntax was checked for returned helper files. The final shared privacy
scanner was applied to helper code and documentation only; it found no
recognizable private-reference pattern in those files. Relative parent/current
path examples remain valid, while literal root-level paths in Python strings
are still detected.

This helper-only result is not a privacy certification of edition sources,
mathematical records, PDFs, problem images or a final archive. Pattern-based
privacy inspection does not prove detection of every obfuscated reference,
and binary image contents are not OCRed.

## Interim literal-binding artifact

The separately authorized interim byte-presence check is retained in
`literal-binding-interim-01`. Its snapshot was recorded at
2026-11-18T16:07:20Z and contained 8,786 ledger rows. It reported 204 absent
nonempty replacement literals and 87 empty replacement fields, with every
flag undecided. Later edits require a new report. This was a mechanical check,
not source-page reading or a decision about any replacement's correctness.

## Subsequent mechanical verification on 2026-11-18

The earlier results above remain a record of their original runs. Subsequent
helper-only and disposable-fixture work added these groups:

| Group | Passed tests | Main coverage |
| --- | ---: | --- |
| Bookkeeping/interim-mode fixtures | 16 assertions | Stable row maps, duplicate/chain metadata, structural counts, interim French-inventory naming and unchanged final completion gate. |
| Reviewed-ledger promotion fixtures | 8 checks | Pending export refusal, explicit duplicate-row rebinding, annotated retained withdrawals and unchanged registry/event bytes. |
| Bibliography versus credit boundaries | 19 cases | Bibliographic author-spelling changes outside protected regions remain separate from exact README/front-matter checks; every changed TeX body still invalidates build hashes. |
| Static control-word inventory | 16 groups | Lexical token boundaries, comments/literal bodies, candidate counts and locations, declaration metadata, relative locators, immutable inputs, changed-input refusal and exclusive report installation. |
| Review metadata gates | 14 test methods | Recognized confidence/verdict/IDs, uniqueness, validator and final-preflight integration, stale map status/event refusal, normalized status, interim compatibility and real exporter annotated-retain output. |
| Math-font context detector | 23 test methods | Math/text nesting, outer versus inner environments, single-token restoration, box dimensions, deferred definitions/defaults, literal references, unclosed-scope retention, relative metadata-only reports and unchanged-input safeguards. |
| Recurrence inventory and lexical probes | 13 test methods | Requested English/French patterns, exact source lines and tokens, page/layer sorting, context exclusions/uncertainty, source hashes, privacy filtering, preservation and immutable interim reports. |
| Notation/ledger and structural recurrence | 6 + 3 focused fixture groups | Bounded control words, comments, argument forms, complete zero matrices, exact cross-page ledger pairs, immutable inputs/reports, nested-font containment and per-file anchor grouping. |

The reusable review-metadata suite is `scripts/test_review_metadata_gates.py`;
its latest run passed all fourteen methods. It supplies nine explicit synthetic
review decisions, retains three withdrawals, verifies six active rows, and
leaves prior history bytes unchanged. These fixtures never use the actual
edition ledger, sidecar, pages, scans, PDFs or research folders.

The latest helper-only check parsed fourteen Python files and privacy-scanned
twenty-seven returned helper code/documentation files, with zero reported
privacy occurrences. This is not a privacy certification of edition content
or an archive.

Separately authorized mechanical snapshots were saved in new directories:

- `bookkeeping-first-pass-interim-01`
- `literal-binding-first-pass-interim-01`
- `french-layer-first-pass-interim-01`
- `control-words-second-reading-interim-01`
- `math-font-context-interim-01`
- `terminology-recurrence-interim-01`
- `notation-ledger-recurrence-interim-01`

Their reports and hashes identify the input snapshots. They remain unchanged;
later edits require a fresh report directory. Literal presence, lexical
novelty, differences and bookkeeping associations remain candidates for the
primary reviewer's decision. No edition build or live final-validation run
was performed by this auxiliary work.

The math-font detector's one authorized current-source run was generated at
2026-11-18T18:48:09Z. It retained two pending candidates from 7,508 target-command
tokens in 310 TeX files. Both candidates are on diplomatic p. 207; the primary
reviewer alone will assess them during the sequential second reading. The
report does not constitute a source correction or a review decision.

The recurrence inventory's authorized current-source run was generated at
2026-11-18T19:06:10Z. It retained 48 pending candidates on 21 pages from all 306
page files: 34 English, nine diplomatic French and five corrected French.
No raw match was excluded and no source-line field was privacy-filtered in
this snapshot. All 23 existing math-font tests were rerun successfully after
the optional ordinary-character probe interface was added. No prior interim
report was regenerated or modified.

The notation/ledger snapshot was generated at 2026-11-18T19:22:34Z. It binds
all 306 page sources and 11,791 current ledger rows. It records 110 requested
source matches, 23 pending nested-font source pairs, no duplicate anchor group,
and 111 exact old/new groups recurring on at least two printed pages. Those
ledger groups contain 6,320 rows; this is a recurrence count, not a conclusion
about correction coverage. Three derived source-line fields were privacy-filtered
and marked. No source, ledger, review state or prior report was changed.

## CHECK_EVENTS inventory and proposed gate

Ten focused synthetic fixture groups passed for
`scripts/check_events_inventory.py`: exact schema and approved-policy binding;
malformed widths, strict quoting, UTF-8 and header order; required cells and
unnormalized literal types; exact duplicates versus repeated IDs/dates;
quoted tabs/newlines and physical spans; marker selection and literal case;
draft-policy and reference-presence refusal; immutable inputs/output, relative
policies, changed-input refusal and symlinks; longer-ID boundary regressions;
and independent policy copies that cannot mutate the fixed schema or rules.

The code-only review found and the fixtures resolved two defects: accepting a
shorter known identifier inside an unsupported longer token, and sharing
mutable policy lists with schema/rule constants. Timestamp calendar validity
is explicitly outside this helper's current checks; only presence is checked.

The first read-only event snapshot remains at `check-events-interim-01`.
The current snapshot, `check-events-interim-02`, records the tightened lexical
boundaries. Both bind identical event bytes and have the same counts: 187
rows, 19 literal types, no malformed rows, missing required cells or exact
duplicate groups, and 11 extracted IDs without a literal matching event ID.
One marker-selected row has no extracted ID. These findings remain pending.

The draft gate is explicitly unapproved and fails three named checks. No
event data was edited; no current final-validator or checkpoint gate was
changed. `scripts/CHECK_EVENTS_VALIDATION.md` documents the exact scope,
commands, lexical rules, limitations and proposed packaging integration.

The event helper parsed successfully. The shared privacy scanner inspected
the helper, its documentation, this test record and all files in both event
snapshots: 33 returned textual files, with no reported privacy occurrence.
All eleven generated table payloads and the policy in the current snapshot
were reproduced byte-for-byte from the unchanged event input. This verifies
the mechanical artifact only, not proof coverage or final-edition privacy.

## Complete literal French snapshot support

The existing `french_layer_inventory.py` now has optional all-literal mode and
a fingerprint-checked current row-ID index. The latter contributes identity
only: it never applies sidecar verdicts, withdrawals or amended ledger fields.
Five focused synthetic fixture groups passed for literal metadata/environment
coverage, line endings, complete and stale/duplicate identity mappings,
captured-input parsing, incidental R-token fallback, a full 102-pair fixture,
exclusive output, protected paths, and privacy block/explicit filtering modes.

The default metadata detector now uses the shared verbatim-environment set
plus filecontents forms. The complete current inventory uses all-literal mode,
which bypasses that detector and retains every raw line difference. All
prepared outputs are privacy-scanned before installation. Explicitly filtered
derived fields are marked and retain original hashes; raw comparison, hunk
hashes, candidate associations and all original inputs remain unchanged.

`french-layer-current-interim-01` was generated at 2026-11-18T19:57:38Z. It
records all 102 expected dip/fr pairs, 204 source hashes and 470 pending hunks,
with no metadata exclusions. Its 11,880 current ledger records all have
fingerprint-bound stable R IDs. Five presentation fields were explicitly
privacy-filtered and logged. The actual layer directories contained exactly
the 102 expected direct page TeX filenames each, with none missing or extra.
This snapshot remains unchanged while later edits require a fresh report.

After the helper checks, `french-layer-current-interim-02` was generated at
2026-11-18T20:00:41Z against the latest available ledger/index. It binds 11,884
current records and stable R IDs, retains 470 pending hunks and records 8,849
candidate associations. There are no metadata exclusions. All 102 French page
pairs reconstructed exactly using the original hunk spans; all 470 hunk hashes
and source fragments/context matched, accounting explicitly for the five
marked privacy-filtered presentation fields. The 204 source hashes and three
input hashes matched the snapshot during this verification.

Fourteen returned files comprising this report, the helper and its two
documentation/test records were privacy-scanned with zero reported findings.
The original event, correction, review and source bytes were not changed.
This verifies literal coverage and mechanical bindings only; it does not
classify, justify or approve any French-layer difference.

## Effective-row mathematical classification preparation

The new optional `prepare-math-interim` mode in `refresh_check_record.py`
reuses workbench replay/alignment and the existing pending-template schema.
Five focused fixture groups checked amended fields/kinds, explicit withdrawal
exclusion, separate default/all-active scopes, unpaged pending build rows,
unchanged live-fixture inputs, confidence-independent fingerprints, stale-index
refusal, exclusive output, unregistered coverage gaps, explicit privacy
filtering and compatibility with the classification loader. A changed effective
fingerprint was rejected; no mathematical decision was supplied.

`math-classification-interim-01` was generated at 2026-11-18T20:10:57Z. It binds
11,888 stable rows and 11,939 verified review events, excludes 139 withdrawals,
and supplies 11,749 all-active pending rows. Its default subset contains 442
original-misprint and 152 translation rows. All summaries/reasons are empty;
there are no pending review rows, unpaged pending build rows or unregistered
records in that snapshot. Nineteen derived fields are marked as privacy-filtered.
All candidate fingerprints match the effective projection, and the default
subset exactly matches the two literal kinds in the master pending table.

Fifteen returned helper/documentation/report files passed the shared privacy
pattern check. The snapshot remains immutable; later changes require a fresh
directory. No live source, ledger, review event/index, CHECK_RECORD, final gate
or PDF was changed by this work. Promotion/refresh instructions and their
existing concurrency limitations are documented in `MATH_CLASSIFICATION_INTERIM.md`.

A separate lookup-only runtime check resolved regular installed files for
graphicx.sty, graphics.sty, keyval.sty, graphics.cfg and pdftex.def through the
established task-local environment. No download, installation, format build,
source inspection or edition build was performed for that check.

## Plain unwrapped math-capital candidates

`plain_math_capitals.py` and `PLAIN_MATH_CAPITALS.md` were prepared using
thirty focused synthetic checks. They cover recognized math, group/single-token
and nested font wrappers, text/reference/comment exclusions, literal controls,
uncertain contexts, all 102 pages and 510 page/capital cells, privacy filtering,
source preservation, exclusive output and changed-snapshot refusal. Shared
lexical helpers were not changed for this inventory.

The authorized mechanical run, `plain-math-capitals-interim-01`, was generated
at 2026-11-18T20:34:05Z. It accounts for 3,616 raw target letters in the 102
diplomatic page files: 1,133 recognized-math candidates, 122 uncertain matches
and 2,361 known exclusions. Candidate counts are C 292, O 91, U 529, V 151 and
Z 70, distributed across 80 pages; the other 22 pages have explicit zero counts.
All findings remain pending. No candidate context needed privacy filtering;
23 raw excluded/uncertain contexts were explicitly marked filtered.

The 102-row coverage table, 510-cell matrix, unique raw match IDs, exclusive
dispositions and recognized-math candidate categories were mechanically checked.
Fourteen helper/documentation/report files passed the privacy-pattern scanner
with zero findings. No source, review state, ledger, scan, build output or
restricted context material was changed or interpreted.

## Exact French rebinding and literal-group classification interfaces

`french_layer_rebind.py` passed six focused synthetic fixture groups covering
exact identities/page order, changed or missing hunks, duplicate/ambiguous
hashes, correction-ID drift and membership, malformed references/canonical IDs,
privacy, snapshot guards and exclusive installation/rollback. Its proposals
remain pending; historical decisions are metadata only. The supplied primary
review table was checked only for schema and metadata correspondence: all 471
ID/page/hash triples match `french-layer-inventory-01`. No live rebinding run or
review-table update was performed.

`math_literal_groups.py` passed six focused synthetic fixture groups covering
exact original (kind, old, new) grouping, complete R-ID/fingerprint membership,
pending templates, explicit decision copying, per-row precedence and repeated
pending-exception preservation, stale membership/fingerprint refusal, required
decision prose, display-filter collisions, input/privacy/path guards and
exclusive installation/rollback. Decision summaries and reasons are copied
exactly and never filtered; a privacy finding in that prose blocks output.
No live ledger was grouped, no live row was classified, and no review, source,
count, gate or build state was changed.

`POST_RECURRENCE_RUNBOOK.md` records the verified command order and dependencies
for later review/promotion, inventories/rebinding, explicit classifications,
event-table checks, builds/PDF review, counts, privacy/credits and ZIP checks.
It identifies the existing manual-promotion concurrency assumptions and the
separate CHECK_EVENTS policy gate. No event normalization or final gate was
installed or executed by this preparation.
