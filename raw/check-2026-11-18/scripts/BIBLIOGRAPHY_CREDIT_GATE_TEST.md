# Bibliography spelling and credit-preservation gates

Tested on 2026-11-18 using helper code and temporary synthetic fixtures only.

## Result

The requested substitutions `Atyah` → `Atiyah` and `Maclane` → `MacLane`,
when confined to bibliography body text, leave the source-README and main-file
frontmatter preservation checks passing. They still change the TeX source
hashes, so a build recorded before those edits becomes stale.

The same substitutions inside protected frontmatter or either source README
fail the corresponding exact-byte preservation check. No validator change,
author-name exception, or weakened gate was needed.

## What the helpers actually distinguish

`original_frontmatter_checks()` compares both complete source READMEs with
their supplied-original counterparts. It compares each main file's prefix
before its first recognized page input with the corresponding original
prefix. The diplomatic main uses the original French main as its reference.

`preserved_source_regions()` recognizes only those byte-identical README and
main-prefix regions. A source-page bibliography is outside those protected
regions, as is bibliography text after the first page input in a main file.
These decisions use file location and exact bytes, without interpreting an
author's name or deciding whether a bibliographic substitution is justified.

The privacy scanner produced no finding for either spelling in the synthetic
bibliography text. Consequently, these plain name substitutions did not
produce a protected-source privacy/credit conflict. This does not waive any
privacy finding or credit-preservation failure elsewhere.

## Exact synthetic coverage

Nineteen cases passed their assertions:

| Cases | Synthetic operation | Observed preservation result |
| ---: | --- | --- |
| 1 | Unchanged baseline with two READMEs and three mains | All five checks passed; all five protected regions were recognized. |
| 3 | Each substitution separately, then both together, in a French source-page bibliography | All five checks passed; protected-region data remained identical to baseline. |
| 3 | Both substitutions after the first page input in each of the diplomatic, French, and English mains | All five checks passed; protected-region data remained identical to baseline. |
| 6 | Each substitution separately in each main's protected prefix | The affected main's frontmatter check failed, and its changed prefix was no longer classified as a preserved region. Other preservation checks still passed. |
| 4 | Each substitution separately in each complete source README | The affected README check failed, and that changed README was no longer classified as a preserved region. Other preservation checks still passed. |
| 1 | Whitespace added inside a protected main prefix | The corresponding frontmatter check failed. |
| 1 | The first recognized page-input command replaced with a different command | The corresponding frontmatter check failed. |

The names were deliberately also placed in fictional protected credit text
to test that the same substitutions are rejected there. These fixtures do
not describe the edition's actual credits.

For provenance, the test extracted and evaluated the exact `current_tex`,
`recorded`, and `recorded == current_tex` expressions from the validator's
syntax tree against synthetic SHA-256 dictionaries. The unchanged baseline
matched. All six bibliography-body variants and all six protected-prefix
spelling variants made that comparison unequal. This included
`Maclane` → `MacLane`, whose byte length stays unchanged. README-only edits
left the TeX dictionary unchanged but independently failed the README gate.

## Scope and versions

The tests invoked only the two preservation helpers, the privacy scanner on
synthetic text, and the extracted dictionary expressions. They did not invoke
full validation, create or read PDFs, run TeX, or inspect actual edition
pages, mains, READMEs, scans, review records, or research context. No validator
or live report was modified. Temporary fixtures were discarded.

Helper SHA-256 values at test time:

| Helper | SHA-256 |
| --- | --- |
| `final_validate.py` | `3d12bd31ba4779e9f5259506e64ad3e5fc8585677e1202f0fbca8f35cbfe897c` |
| `privacy_guard.py` | `d1fb0141d659e1b5a2c9e3b087e7ca3b5d7cc4736c2e92068dbaf590fce2e629` |

This is an infrastructure regression result, not a judgment about the
edition's bibliography, correction records, credit text, or final build.
