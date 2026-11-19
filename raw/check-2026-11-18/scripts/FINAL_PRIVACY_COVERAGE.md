# Final validation and archive privacy gate

These helpers perform mechanical inspection and preserve source bytes. Their
preparation and verification used helper code and synthetic fixtures, without
an edition build, final delivery validation, page-text reading or scan review.

## Coverage

`privacy_guard.py` supplies the shared checks used by `final_validate.py`,
`checkpoint.py` and retained build-log filtering.

| Material | Inspection |
| --- | --- |
| Returned textual files | Declared or detected text is scanned regardless of extension, including Python/shell helpers, TeX support files, data/configuration files, HTML and extensionless text. |
| Text encodings | UTF-8, BOM-labelled Unicode, detectable UTF-16/UTF-32 and a single-byte fallback are supported. Ambiguous Unicode, decoding failures and excessive unbroken text lines are blockers. |
| Included filenames | Relative names are checked; private patterns are reported with safe locators. Unsafe member-name forms are rejected. |
| Generated reports/manifests | Validation reports, file lists, archive information and chunk maps are scanned. Discarded-file and previous-reference names are filtered in derived manifests. |
| ZIP metadata | Archive/member names, ZIP/member comments and Unicode name/comment extra fields are scanned. |
| Split files | Every ZIP part is supplied together; logical files are reconstructed and their chunk sizes/hashes verified before privacy inspection. |
| PDFs | Extracted page text, textual objects, Info metadata, annotation/URI strings and XMP are inspected. An embedded attachment blocks automatic privacy clearance. |

Patterns include ordinary and Unicode email forms, multi-component and
root-level POSIX paths, drive paths, UNC/network paths and local-file URIs.
Public web URLs and delivery-relative locators are retained. In valid Python,
path-division syntax outside strings/comments is not treated as a literal
pathname; strings, comments and all email matches remain checked.

Findings contain safe file locations, categories and content hashes. They do
not repeat the sensitive matched values. A finding or inspection blocker
fails validation; no source is redacted automatically.

## Credits and rights remain exact

The original source ZIP supports exact comparisons of both source READMEs and
all three main-file prefixes through the first page input. The diplomatic main
is compared with the supplied French main prefix.

A privacy-pattern occurrence inside a byte-identical protected source region
is placed in `FINAL_VALIDATION_CREDIT_CONFLICTS.tsv`, with the byte-preservation
basis. The ordinary findings appear in `FINAL_VALIDATION_PRIVACY.tsv`. No
credit, rights notice, source passage or mathematical record is changed.

A protected-region conflict is an unresolved requirement, not an automatic
exception. The separate `privacy-source-credit-conflicts` check fails until
the primary reviewer resolves the conflict explicitly. The helper does not
infer that every word in a protected README or front-matter region is itself
a credit, and it does not silently remove or waive a matched occurrence.

## Report-bound final preflight

After all source, report and PDF work is complete, from the delivery directory:

```bash
python scripts/final_validate.py --original-sources TOHOKU_sources.zip --final-phase after-01
python scripts/checkpoint.py preflight
python scripts/checkpoint.py final
```

Use the actual relative location of the original source ZIP and the actual
final build phase. The standalone `preflight` action prints counts and writes
neither an archive nor a report; `final` runs the same preflight automatically.

Preflight requires all five generated validation reports, a nonempty all-pass
check table including both privacy checks and the explicit-confidence and
unique-review-identifier checks, and an exact match between current
included-file names/sizes/hashes and the validation inventory. Only the five
exact root-relative generated report names are exempt from their own stale
inventory comparison. Those reports are still privacy-scanned and freshly
hashed, and their hashes are bound to the packaged bytes.

Final ZIPs remain temporary until CRC/hash checks and the complete archive-set
privacy scan pass. The scan checks generated metadata and exact stored-member
sets before any final ZIP is installed. Every ZIP remains strictly below
500,000,000 bytes. Source bytes are copied without transformation.

Hourly checkpoints retain their existing timing and completion behavior; the
new successful-final-validation gate applies to final delivery. Metadata-only
`--dry-run` still does not read file contents or create an archive.

## Read-only post-packaging check

```bash
python scripts/final_validate.py --original-sources TOHOKU_sources.zip --final-phase after-01 --archive ../TOHOKU_CHECK.zip
```

Repeat `--archive` for every part when the delivery is split. Archive checks
are read-only by default, so they do not change report bytes already packaged.
An optional `--report-dir` may save postcheck reports outside the delivery tree.

The postcheck requires the exact current logical file set and hashes,
including all validation reports. It rejects unexpected files, verifies the
generated file-list bindings, and checks the final archive kind and part count.

## Limits

This is pattern-based inspection, not proof that every possible obfuscation of
a private reference has been found. Binary image contents are not OCRed, and
general image metadata is not decoded. Arbitrary nontext binary formats are
not reverse-engineered. Ambiguous or uninspectable declared text and PDF
attachments are reported as blockers rather than being certified clean.

A mathematical expression or regular expression may still resemble a path.
Review a reported location before changing anything. No privacy result
establishes scan fidelity, correction-literal correctness, translation
fidelity, mathematical validity or visual PDF quality.

## Verification

Synthetic checks exercised text types/encodings, private-reference spellings,
filenames and comments, unknown-extension members, cross-chunk matches,
missing chunks, PDF metadata, stale inventories, exact report-name exemptions,
mutation after preflight, and final installation refusal on privacy findings.
A complete synthetic validate → preflight → package → read-only postcheck
workflow passed. A protected-source conflict remained byte-identical and was
reported separately as a failing check. No actual edition was certified.
