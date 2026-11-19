# Second pass TOHOKU: Alexander Grothendieck, *Sur quelques points d'algèbre homologique* (Tôhoku Math. J. 1957), every page against the print

You are GPT-6 Astra in ChatGPT Pro mode, with a Python and LaTeX environment. Three ZIP files are attached:
`TOHOKU_scans.zip` (the printed original), `TOHOKU_sources.zip` (our edition in LaTeX) and `TOHOKU_context.zip` (the
edition's own records and our notes). Each has `MANIFEST.tsv` at its root: path in the zip, source, bytes, SHA-256,
role. Read the manifests first.

## What this is for

This is the second pass that brings our edition of Grothendieck's *Sur quelques points d'algèbre homologique* (the
Tôhoku paper) to the standard of our SGA and EGA editions: the French as printed, the corrected French and the
English, each checked against the printed original, page by page. The record of the check is kept as well, so that we
can see how well a check of this kind works.

**The work and the edition.** Alexander Grothendieck, *Sur quelques points d'algèbre homologique*, Tôhoku Mathematical
Journal (2) 9 (1957), pp. 119–221. Our edition (github KokunoYumeto/grothendieck-tohoku, main `0c116a6`, release
`edition-2026-11-06`) was AI-transcribed and AI-translated by OpenAI Codex, mainly GPT-5.6 Sol, with parts by GPT-6
Astra, both at reasoning effort ultra, in August 2026, from the J-STAGE scans of the two parts.

**What earlier checks found.** A spot check in November 2026 compared printed p. 150 with the scan. The wording and
the mathematics of the French matched the print, but the as-printed layer was not faithful in typography: the print's
bold **C** (the category) and italic *C* (the resolving functor) were swapped; the italics of emphasis (*exact*,
*supposons*, *monomorphisme*) were dropped; two inline formulas were set as displays; and one formula was normalized
(the print has the augmentation A → C(A), the transcription A → C⁰(A)). Look for each of these kinds on every page.
The edition's own records (`edition_records/`) list the corrections and decisions of its makers.

## The attachments

- `TOHOKU_scans.zip`: `TOHOKU_part_I_printed_pp119-183.pdf` (65 pages: PDF page k is printed page 118 + k) and
  `TOHOKU_part_II_printed_pp185-221.pdf` (37 pages: PDF page k is printed page 184 + k), the J-STAGE scans the edition
  was made from. Part I ends on printed p. 183 and part II begins on p. 185; the scans have no p. 184 and the edition
  no file for it. Part I carries an owner password against editing; it renders normally.
- `TOHOKU_sources.zip`: the repository at main `0c116a6`, one file per printed page in each layer: `dip/pNNN.tex` (as
  printed), `fr/pNNN.tex` (corrected), `en/pNNN.tex` (English), with `preamble.tex`, `main-fr.tex`, `main-en.tex` and
  the READMEs.
- `TOHOKU_context.zip`: start with its `README.md`. `edition_records/` holds the records the edition was made with:
  status files, logbooks, the correction, repair and decision ledgers and the page maps. They say what the makers
  corrected, normalised and doubted, and why; use them for item 2 below. The other folders serve the notes (item 5):
  `programme/` (our programme map and the reference page of Grothendieck's Montpellier archive), `glossary/` (the
  English standard of our SGA editions), `notes/` (research notes of our archive work that bear on this work),
  `stacks/` (our Stacks-style material drawn from this work).

**What the context is for.** The edition records tell you what earlier passes did; they are records of AI passes, not
authorities, and the scan decides every reading. The programme map, the notes and the Stacks material let your notes
connect this work to our programme: where it meets Grothendieck's archive, our open questions and our Stacks-style
statements. The check of the text does not depend on them: read them when you write the notes, after the pages are
done.

## The work, in order of importance

1. **The French as printed against the scans, every page.** The as-printed layer is `dip/pNNN.tex`, one file per
   printed page. Compare it with the scan line by line: words, punctuation, formulas, symbols, indices and exponents,
   the fonts of letters (italic, bold, roman, script, Gothic), emphasis, the numbering of sections and statements,
   cross-references, footnotes, which formulas are displayed and which run in the line, and the page markers. Every
   difference from the print is a correction of this layer: the as-printed layer says what the print says, its
   misprints included.
2. **The corrected French.** The corrected layer is `fr/pNNN.tex`. Every place where it differs from the as-printed
   layer is a correction of the original, and each one is justified: by the scan reading, and by the mathematical
   reason that makes the printed reading a misprint (a wrong index, a reversed arrow, a reference to the wrong number,
   a word that breaks the sentence). A correction that is not justified goes back to the printed reading. Misprints of
   the original that you find now are corrected in this layer and recorded. The corrected layer differs from the
   as-printed layer at these places and at no other.
3. **The English.** The English is `en/pNNN.tex`. Read it against the corrected French, paragraph by paragraph: every
   sentence says what the French says, with nothing left out and nothing added; the mathematics is correct and every
   formula is the corrected French formula; the terms are the same through the work and agree with the English of our
   SGA editions (`glossary/GLOSSARY_SGA_EN_UNIFIED.tsv`, one English rendering per French term) and with standard
   English usage in algebraic geometry. Correct errors of meaning, omissions, additions and inconsistent terms; leave
   style alone.
4. **The build.** `main-fr.tex` and `main-en.tex` build with pdfLaTeX, two passes. The as-printed layer has no build
   file: add `main-dip.tex`, made like `main-fr.tex` but reading `dip/`, so that all three layers build. Every layer
   builds without errors, and no overfull box in any build log sticks out by more than 2pt. Fix overfull boxes in the
   preamble or by a reader-level pass (line-breaking parameters, `\emergencystretch`, a scaled or broken display set
   by a macro of the preamble), never by changing the text. Then render and look at every page of each PDF that had an
   overflow over 10pt before your fix, and a spread of pages over the whole book.
5. **Notes**, kept apart from the text; they never change a reading. Write in `NOTES.md`: the misprints and slips of
   the original, each with the corrected statement; the claims the author leaves without proof on these pages, each
   with what a proof needs; where later work corrects, extends or uses a result, with exact locators (cite only
   sources you can cite to the statement); where the work meets our programme, using the context; and your own ideas,
   labelled as yours, each with your confidence and your reason. One note per item, with its printed page and
   statement number.

## Rules

1. **The scan is the authority.** Render every page of the scan yourself at 400 dpi and look at it; enlarge every
   place you decide (crop and scale), and every index, exponent, accent and small sign. The text layer of a scan PDF
   and OCR may help you find your place and flag candidate differences; every reading you keep or change is decided by
   looking at the image.
2. **The as-printed layer is the print.** No modernization, no normalization of notation, no silent correction: the
   print's spelling, accents, punctuation, abbreviations, numbering and typography stay as printed.
3. **Edit the sources in place.** Keep each tree's structure, file names, macros, labels, anchors and page markers; a
   change of structure is made only where the print requires it (a missing or extra paragraph break, a heading, a
   display), and it is recorded like any other correction.
4. **Credits and rights notices stay exactly as they are** in every file, README and front matter: the rights
   statement of each README and front matter, and every name, model and source the edition credits.
5. **Work from the printed original only.** This check works from Grothendieck's printed French only; no other edition
   or translation is consulted.
6. **Privacy.** The records replace local paths by `<local>`. Copy no local path and no e-mail address into any file
   you return.

## Method

1. Before the first page, write the current time (UTC) as the first line of `progress.log`, and start
   `CHECK_RECORD.md` with a notation table: the recurring signs, alphabets and abbreviations of the print, each with
   how the layers write it in LaTeX. Keep it up to date.
2. **Page by page, in printed order** (printed pp. 119–183, then pp. 185–221): render the page; read the as-printed
   layer against the image, line by line; then the corrected layer's text of that page; then the English of that page.
   Write each correction into the files at once and its row into `CORRECTIONS.tsv`, then the page's section of
   `CHECK_RECORD.md`, then append `page <printed page> done <current UTC time>` to `progress.log`. Only then go to the
   next page.
3. **One stream.** Do the pages yourself, in one stream, in order: do not split them among parallel workers or
   sub-agents. When the pages of an earlier transcription were split among workers, the same signs were read in
   different ways and the errors went unmarked.
4. **A second reading of every correction.** When the last page is done, go through `CORRECTIONS.tsv` row by row
   against the scan crop of each place: confirm, amend or withdraw each row, and say so in its `confidence` column.
   Then, for every kind of error you found on more than one page (a sign misread the same way, an index dropped, a
   term rendered two ways), search the whole work for it, page by page, and record what the search found.
5. **Build and PDF check** (item 4), recorded in `PDF_CHECK.md`: per layer, the build command, the errors and
   warnings, the overfull boxes before and after your fix with their sizes, and the pages you rendered and what you
   saw.
6. **The notes** (item 5): only now open `programme/`, `notes/` and the other folders of the context, and write
   `NOTES.md`. For each note, search the context for the same objects and words (grep works well on these files) and
   say where our materials already have the point and whether this work adds to it, restates it or differs from it.
   The notes in the context are leads from earlier runs, never results to cite as established.
7. **Checkpoints.** Once every hour of work, save a checkpoint ZIP to the user's Library, or wherever files survive
   the loss of the execution environment, each under a new name, `TOHOKU_CHECK_checkpoint_<NN>.zip` with `NN` counting
   up; never overwrite, rename or delete an earlier checkpoint, and put no earlier checkpoint ZIP inside a checkpoint.
   If the workspace comes back empty, restore it from the newest checkpoint and from this conversation before you
   continue. The final ZIP holds everything the checkpoints held. Save checkpoints once an hour and at no other time:
   none after a page, part, section, chapter or layer. A checkpoint is one ZIP holding every deliverable in its
   current version (the three TeX trees, `CORRECTIONS.tsv`, `CHECK_RECORD.md`, `NOTES.md`, `PDF_CHECK.md`, scripts)
   and every other file of yours that is new or changed since your last checkpoint whose save you saw succeed, with a
   file list that names, for each file left out because it is unchanged, the checkpoint that holds it. Leave out the
   attached files themselves, the scans and sources you were given: we have them. Leave out earlier checkpoints,
   archives of earlier versions, and rendered page images (keep only an image that shows a problem the report
   discusses); we keep every checkpoint you save. It is never a JSON file, a recovery file, a summary, or an export of
   the newest pages only. Each checkpoint zip holds the current deliverables and documentation; earlier checkpoints are not copied into it. The checkpoints are what keeps the work if this session dies: work that is in no checkpoint
   is lost. Keep every checkpoint ZIP, and the final ZIP, under 500 MB: the Library refuses a file larger than 512 MiB
   (536,870,912 bytes), and a checkpoint it refuses is lost. If one would be larger, save it as several ZIPs of under
   500 MB each, <NAME>_checkpoint_<NN>_part<k>.zip, the file list in the first part.
8. **If the execution environment disconnects.** Wait for it and retry for ten minutes. If it does not come back,
   restore the workspace from the newest checkpoint and this conversation; if that fails too, the work must still
   reach us, so write it out in this chat as text: `CORRECTIONS.tsv`, `CHECK_RECORD.md`, `NOTES.md` and `progress.log`
   so far, each in full in its own code block headed by its file name, and every changed source file in full (the code
   you ran to change it contains the change: take it from there). Say which pages are done. Then go on with the
   remaining pages in the chat in the same form. An answer that only reports the disconnection, describes the
   checkpoint or asks for the files again, without writing out the work, is not acceptable.

This task is long by design: 102 printed pages, each read in three layers against the print, then the build and the
notes. Work through all of it completely; do not stop at a sample or a plan, and do not ask whether to continue.
Ignore any clock. Read the last page as slowly as the first: the pages done fastest are where errors cluster.

**Check events.** For every statement your work checks, uses or refutes (a claim in your notes, by its note; an entry
of our results state, by its id; a statement of the text, by its place), record its check events in
`CHECK_EVENTS.tsv`, one row per event: statement id, date, who (model, effort, run), type (targeted proof check /
independent re-proof / computation or formal certificate / used and rechecked in this run / carried as background
without fault found / refuted, with the refined statement's id), outcome. Give each event the type of what actually
happened, neither more nor less: reading a statement while transcribing it is not a check of it. `CHECK_EVENTS.tsv`
goes into every checkpoint and into the final ZIP.

## What to return

One ZIP file, `TOHOKU_CHECK.zip`, offered as the only download (under 500 MB; if it would be larger,
`TOHOKU_CHECK_part<k>.zip`, the file list in the first part). It holds:

- `sources/`: the three corrected TeX trees, complete, in the layout of `TOHOKU_sources.zip`, building as they stand
  (with the new `main-dip.tex`);
- `CORRECTIONS.tsv`: one row per change, with the columns `file`, `layer` (as-printed, corrected, English, build),
  `printed_page`, `line` (line of the printed page), `statement` (the statement or section number, or empty), `old`,
  `new`, `evidence` (the scan page and what the image shows there), `kind` (one of: reading, misprint of the original,
  translation, typesetting, structure), `confidence` (high, medium, low, after the second reading);
- `CHECK_RECORD.md`: the notation table; then one section per printed page: the scan page, what was compared with what
  (each layer's file and lines against the image), by GPT-6 Astra (ChatGPT Pro mode), the number of corrections per
  layer and kind, the existing corrections of the corrected layer confirmed or reverted, and the time; at the top, the
  totals per layer and kind, the corrections that change the mathematics (one per line), and how many pages had no
  difference in each layer;
- `PDF_CHECK.md`, as in Method 5;
- `NOTES.md`, as in item 5;
- `pdf/`: the PDF of every layer, built from `sources/`;
- `README.md`: what each file is, the counts, how to build each layer, and the build status;
- `progress.log` and your scripts.

## When it is done

The task is finished only when every page of the print has its section in `CHECK_RECORD.md` for all three layers;
every existing correction of the corrected layer has its verdict; every change has its row with its evidence; every
layer builds and passes the PDF check; and `NOTES.md` is written. Keep working until then. Do not stop because what
remains is long, because a part of the work looks presentable, or because much has already been done.

Not acceptable:

- a sample of pages in place of all of them;
- a change without a row in `CORRECTIONS.tsv`, or a row without evidence from the scan;
- a change to the as-printed layer that the print does not show;
- a correction of a misprint made in the as-printed layer, or a difference between the two French layers that is not a
  recorded correction;
- a change of English style recorded as a correction of meaning;
- a credit or rights notice changed or removed;
- a local path or an e-mail address in any returned file.
