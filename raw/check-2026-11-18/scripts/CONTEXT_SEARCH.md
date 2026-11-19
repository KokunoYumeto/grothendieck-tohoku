# Mechanical supplied-context search

The helper reads programme HTML, Stacks CSVs, the supplied context README and Markdown status/map/README text within the programme and Stacks directories. It neither follows source-file references nor fetches linked pages. Supplied context stays unchanged. Parsed source values stay in an external scratch cache; the report contains hashes, schemas, counts, record locators and the narrow README evidence for notes-directory absence. Search results carry only the explicitly requested note ID and matches needed for primary review.

The current index is `context-search-index-interim-02`: twelve source files, 3,107 CSV records, 333 static HTML text blocks, 178 literal `DATA.rows` objects and 167 Markdown text blocks. Other embedded DATA keys are outside its scope. The earlier seven-source index remains a historical snapshot. No mathematical comparison or note is drafted by these helpers.

## Prepare an index

Run from the workspace containing the supplied input and delivery directories:

```bash
python -B TOHOKU_CHECK/scripts/context_search.py index \
  --context-root input/context \
  --cache tmp/context-search-index-02 \
  --output TOHOKU_CHECK/context-search-index-interim-02
```

Cache and output directories must be fresh. The parsed cache must remain outside delivery and supplied context. The command snapshots every authorized source and verifies that its bytes are unchanged before writing. The generated report provides exact source SHA-256 hashes, per-file schema metadata, record counts and locators. Privacy masking applies to returned metadata if needed; source values remain intact in scratch.

## Query for one primary note

```bash
python -B TOHOKU_CHECK/scripts/context_search.py query \
  --context-root input/context \
  --cache tmp/context-search-index-02 \
  --note-id NOTE-ID \
  --term KEYWORD \
  --output TOHOKU_CHECK/context-query-NOTE-ID-interim-01
```

The primary supplies the actual note ID and search terms. Repeated `--term` arguments require all terms to occur somewhere in the same record by default; `--match any` requests their union. Matching is literal and case-insensitive unless `--case-sensitive` is supplied. Accents and punctuation are preserved. Use `--field` repeatedly to restrict searched field names, `--source` for a quoted relative-file glob, and `--kind` to select `csv`, `html_static`, `html_DATA.rows` or `markdown_text`.

`--anchor` matches an exact enclosing HTML id or an identifier token in a selected field. Hyphens and underscores are part of a token. Repeated anchor constraints all apply. `--page` matches a literal integer token only in fields explicitly named with `--page-field`. No page-field meaning is inferred, no numeric range is expanded, and programme page counts are not silently treated as printed-page references.

Results include matched fields. Repeated `--show-field` arguments add selected fields from the same record, for example an existing identifier or source locator. Default snippets are bounded to 260 characters; `--snippet-chars` adjusts that limit and `--full-fields` requests complete selected fields. The default limit is 50 matched records. `SEARCH_SUMMARY.json` explicitly reports the total, returned count and truncation status; `--limit` can raise the limit when the primary needs all matches.

Every query verifies the cache hash and current source hashes before retrieval and again checks source stability before writing. Search output is a fresh directory containing `SEARCH_SUMMARY.json`, `SEARCH_RESULTS.json` and `SEARCH_RESULTS.tsv`. A stale cache, changed source set or privacy finding blocks installation.

## Batch from explicit primary note metadata

```bash
python -B TOHOKU_CHECK/scripts/context_batch_search.py \
  --context-root input/context \
  --cache tmp/context-search-index-02 \
  --notes-jsonl TOHOKU_CHECK/AUTHOR_PROOF_OBLIGATIONS.jsonl \
  --output TOHOKU_CHECK/notes-context-search-interim-01 \
  --page-window 0 \
  --range-source stacks/tohoku_r71/units.csv \
  --range-source stacks/tohoku_r71/map.csv \
  --range-start-field source_start \
  --range-end-field source_end
```

The batch uses only each input's `note_id`, `printed_page`, explicit `context_search_terms` and optional `fragment_id`. It does not interpret the primary's claims or proof-needs prose. Repeated input fragments for one note are retained as source locators and their exact explicit terms are combined; inconsistent pages for the same note ID block retrieval. The input snapshot receives a SHA-256 binding. If the primary appends notes during retrieval, the completion flag reports that difference; a fresh batch is needed for the later records.

Batch keyword retrieval uses `--match any` by default. The default limit is fifty records per note, ordered by the number of distinct supplied terms matched, then source, kind and logical record. `TERM_COVERAGE.tsv` reports the total and returned qualified matches for every explicit term. `SOURCE_COVERAGE.tsv` reports every indexed source for every note, including zero matches. Truncation is always explicit in `QUERY_SUMMARY.tsv` and `BATCH_SUMMARY.json`.

Page-window retrieval is optional and separate from keyword retrieval. It requires explicit source patterns and start/end field names. A radius of zero matches the supplied printed page against declared integer intervals; a positive radius expands the requested window by that many pages on each side. Matching uses inclusive interval overlap, with no word search, page-field inference or range repair. Missing, noninteger, duplicate or reversed bounds are excluded and listed in `STRUCTURAL_RANGE_ANOMALIES.tsv`. The supplied units and map tables each contain one reversed interval at logical record 29, physical line 30; neither is normalized.

The default page-window limit is twenty-five records per note, ordered by narrower declared interval first, then source and logical record. `--range-limit` changes the limit; `--range-show-field` can select displayed fields. Otherwise, every field of a selected structural record receives its own bounded snippet. `NOTE_RESULTS.jsonl` keeps keyword and structural result sets separate. `MATCHES.tsv` provides one row per returned field with its retrieval basis. No context file is copied in full.

Every note result reports that the supplied notes directory is absent and supplies the exact context README evidence at physical lines 14–16, with its source hash and Markdown logical records. The text is a manifest statement and the absence is a directory observation; neither is an inferred mathematical judgment.

## Compact exact-anchor retrieval

For the primary note review, use the source-anchor join report:

```bash
python -B TOHOKU_CHECK/scripts/context_anchor_search.py \
  --context-root input/context \
  --cache tmp/context-search-index-02 \
  --notes-jsonl TOHOKU_CHECK/AUTHOR_PROOF_OBLIGATIONS.jsonl \
  --slip-inventory TOHOKU_CHECK/original-slip-notes-inventory-interim-02 \
  --slip-notes-jsonl TOHOKU_CHECK/ORIGINAL_SLIP_NOTE_INPUTS.jsonl \
  --output TOHOKU_CHECK/notes-context-anchors-interim-03
```

The OP input supplies exact page-source lines and a primary fragment hash. The helper checks that hash before extracting literal `LayerTarget` arguments. It selects arguments whose macros begin within the exact supplied range; otherwise it records the nearest preceding argument in that same file. It skips comments and recognized verbatim material lexically, expands no macros and reports nonliteral or unbalanced arguments separately. A mismatching fragment hash remains an unresolved binding, with no anchor silently selected.

Slip-query IDs must exactly cover the existing inventory groups. Their pages, member correction IDs and statement sets must also match exactly. Current active ledger fingerprints are checked. Exact statement identifiers or pure numeric heading suffixes are tried first, retaining multiple exact candidates visibly. Otherwise existing primary French-hunk references supply exact current source ranges. Explicit numeric ledger lines and exact occurrences of the current ledger-new literal provide labelled fallback locators. No textual similarity or mathematical interpretation is used.

The relation step selects exact `units.id` and `map.unit_id` records for each anchor, then one declared `parent_id` level from those direct records. Decisions and issues join only on exactly equal selected `unit_id`. It does not traverse children or descendants, use page proximity, or interpret dispositions and rationales. The term-seed page intervals in the supplied context can be broad; page-window output remains retrieval metadata rather than semantic evidence.

`CONTEXT_RECORDS.jsonl` and `CONTEXT_FIELDS.tsv` provide each selected context record once, with complete selected-record fields, privacy flags, original-value hashes, file/logical-record/physical-line locators and source hashes. `NOTE_CONTEXT_BINDINGS.tsv` explains every exact relation. `SOURCE_ANCHOR_BINDINGS.tsv` preserves each source item and its macro or hunk locator; `EXTRACTION_ISSUES.tsv` keeps unresolved and ambiguous cases visible. No supplied context file is copied wholesale.

`KEYWORD_QUERY_LOG.tsv` runs every exact primary-assigned OP and slip term against every indexed source and records actual per-term counts, including zero. It supplies query coverage independently of anchor-selected content. Keywords do not add a semantic verdict or silently enlarge the exact relation join. The generic query helper remains available for primary review of a particular keyword result outside those exact joins.

Fresh reports bind both primary input hashes and the context cache hash. Existing report snapshots remain untouched. All relation and note conclusions remain pending primary review.

## Supplemental primary selections and reading order

The current combined reading plan is `context-note-additions-interim-06`. It reuses the 1,671 complete context records in `notes-context-anchors-interim-03` and adds only 74 newly selected records. Its `READING_INDEX.tsv` names the exact content file for each of the 1,745 combined records. `PAGE_READING_PLAN.tsv` groups records by the first printed page of a bound note, and `PER_NOTE_BINDING_COUNTS.tsv` supplies the units/map/decision/issue counts for every one of the 895 input/search IDs. Full summary/rationale fields remain in the two deduplicated content tables.

```bash
python -B TOHOKU_CHECK/scripts/context_note_additions.py \
  --context-root input/context \
  --cache tmp/context-search-index-02 \
  --base-report TOHOKU_CHECK/notes-context-anchors-interim-03 \
  --op-notes TOHOKU_CHECK/AUTHOR_PROOF_OBLIGATIONS.jsonl \
  --slip-inventory TOHOKU_CHECK/original-slip-notes-inventory-interim-02 \
  --primary-bindings TOHOKU_CHECK/PRIMARY_CONTEXT_ANCHOR_BINDINGS_04.tsv \
  --math-inputs TOHOKU_CHECK/MATHEMATICAL_NOTE_INPUTS.jsonl \
  --math-selections TOHOKU_CHECK/MATHEMATICAL_NOTE_CONTEXT_SELECTION.jsonl \
  --later-inputs TOHOKU_CHECK/LATER_WORK_NOTES.jsonl \
  --programme-inputs TOHOKU_CHECK/PROGRAMME_OWN_NOTES.jsonl \
  --output TOHOKU_CHECK/context-note-additions-interim-06
```

Use a fresh output name for a new run. The supplement verifies all 203 supplied mathematical choices against their exact context unit ID, map logical record and physical line. It also records the four explicit primary anchor authorizations for the bounded p183 fragments and p211 slips, preserving the original fragment hashes and ledger fingerprints. Later-work and programme anchors join by exact supplied identifier; no prose is assessed or changed.

`QUERY_COVERAGE.jsonl` preserves all-source counts for the 221 new mathematical/later-work/programme note queries. `LITERAL_TERM_HITS.jsonl` records exact matched field positions using references resolved by `MATCH_RECORD_LOCATORS.tsv`; it avoids a repeated full-snippet dump. `MATHEMATICAL_PAGE_CANDIDATES.jsonl` retains the integer interval candidates separately from the primary's actual selections. The latter appear in `MATHEMATICAL_SELECTIONS_APPLIED.tsv` and alone govern the mathematical-note relation joins.

Four original-slip search IDs may remain aliases of principal NOTES items after primary consolidation. Search coverage retains all 486 original-slip input IDs; consolidation does not erase or transfer their query bindings. A structural check of the assembled NOTES must count principal entries and retained aliases separately.

## Exact locators and privacy

CSV logical data records begin at 1 after the header and include blank records if any. Physical start and end lines are one-based and inclusive. The CSV reader preserves LF, CRLF and lone CR within quoted fields. Field positions are one-based; duplicate or empty header names are preserved, missing values remain null and surplus fields retain a null header. No delimiter guessing or field normalization occurs.

HTML static records group text outside script/style by the nearest text block, retain enclosing id attributes and decode character entities. Their source spans cover that enclosing block; a block may contain nested markup. Line breaks from `br` or `hr` become newline characters in parsed text. Each `DATA.rows` object has its own exact JSON source span even when all records share a physical line. JavaScript is never executed. HTML character offsets are zero-based Unicode code-point positions, with an exclusive end; physical lines are one-based LF lines.

Markdown records preserve exact text blocks, splitting at blank lines, headings and list-item starts. Their inclusive physical line ranges and Unicode character offsets refer directly to the supplied bytes decoded as UTF-8. Markdown links are not followed, and no content outside the authorized context scope is opened.

`value_sha256` hashes the exact parsed value serialized as compact UTF-8 JSON with `ensure_ascii=False`. `fields_sha256` hashes the ordered field objects, including position, name, value and value hash. These bind original values even when a returned field must be masked. Actual local-reference matches become `<local>` and email matches become `<redacted-email>` through the shared privacy helper. Masking occurs before snippet selection, and every returned field records whether masking or truncation occurred. Returned files are scanned before installation.

Retrieval supplies no adds/restates/differs verdict. Every result says `pending primary review`. An empty result means only that the exact query did not match the indexed scope. The primary must read the relevant context and decide any mathematical or later-work relation.
