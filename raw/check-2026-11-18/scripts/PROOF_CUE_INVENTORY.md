# Lexical proof-cue inventory

From the delivery directory:

```bash
python -B scripts/proof_cue_inventory.py --output proof-cues-interim-01
```

Use a new name containing `interim` for every later snapshot. Existing output
directories are refused. The helper requires the 102 regular diplomatic page
files in the documented printed-page order. It reads only those leaf files,
captures their bytes, and rechecks their file set and hashes before installing
the new report. It does not read other layers, original scans, main files,
preambles, ledgers, review events, or protected context folders.

## Meaning of the output

These are literal and lexical leads for the primary reviewer. A cue match does
not establish that a proof is omitted, deferred, supplied, valid, required, or
checked. The inventory does not claim to cover every author assertion or proof
obligation. Every row remains pending.

- `CUES.tsv` contains active or uncertain lexical cue matches. Each row includes
  the exact cue, source coordinates and hash, a paragraph fragment, and nearby
  structural locators.
- `COMMENT_CUES.tsv` and `LITERAL_CUES.tsv` retain other lexical scopes
  separately. `ALL_CUE_MATCHES.tsv` is the union.
- `PARAGRAPH_FRAGMENTS.tsv` deduplicates only fragments referenced by a cue.
- `LAYER_TARGETS.tsv` lists literal explicit `LayerTarget` arguments.
- `HEADING_CANDIDATES.tsv` lists mechanically recognized typed headings;
  `NUMBERED_HEADINGS.tsv` retains the active candidates with a parsed literal
  number. These tables do not establish mathematical statement identities.
- `PAGE_COVERAGE.tsv` includes all 102 pages, including pages with zero matches.
- `FAMILY_COUNTS.tsv`, `RULES.json`, `LEXICAL_NOTES.tsv`, `SOURCE_HASHES.tsv`, and
  `INPUT_HASHES.tsv` expose counts, exact matching rules, parser limits, and input
  bindings. `SUMMARY.json` and `REPORT.md` describe the snapshot.

The exact regex families, flags, structural rules, and limitations are recorded
in `RULES.json` and in `proof_cue_lex.py`. Cue patterns include the requested
French stems and phrases; case-insensitive matching does not expand TeX accent
commands, macros, discretionary hyphens, or phrases interrupted by markup.

## Locators and fragments

Lines and columns are one-based decoded-character positions. Offsets are
zero-based. Both end coordinates and end offsets are exclusive. Each cue carries the strictly preceding
active lexical `LayerTarget` and recognized numbered heading in printed-page
order, including across input-file boundaries. This is an ordering relation,
not a claim that the cue belongs to that statement. A cue in a comment or other
nonactive region remains in its separate table.

Paragraph fragments are file-local lexical blocks, bounded by recognized blank
lines or explicit `par` commands. They may continue across printed-page files.
If a complete block cannot safely be returned without reproducing a whole
page, the parser reports a bounded or omitted fragment and explains why.
Completeness describes the lexical fragment boundary only. It is not a prose,
proof, or typesetting verdict.

Comment, literal, or uncertain matches receive a bounded raw source-line
fragment when possible, at most 640 characters. These fragments make no
paragraph-boundary claim and are labeled separately from active paragraph
blocks. An otherwise whole-page context is withheld.

Source-derived display fields pass through the existing privacy filter. Any
altered field is marked, with hashes and source offsets binding its original
literal value. Source files and credits are never rewritten. A privacy-filtered
display is not byte-for-byte literal text.

The `C`, `P`, `A`, `H`, and `N` identifiers are snapshot-local cue, fragment,
anchor, heading, and parser-note locators. They are not correction-ledger `R`
identifiers and never update review state.

## Synthetic checks

```bash
python -B scripts/test_proof_cue_lex.py
```

The focused tests use synthetic strings only. The live inventory is a read-only
mechanical run and does not inspect the meaning of the matched passages.
