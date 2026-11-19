# Alexander Grothendieck, *Sur quelques points d'algèbre homologique* (1957)

[Français](README.fr.md)

Grothendieck's "Tôhoku paper", *Tôhoku Mathematical Journal* (2) 9 (1957), pp. 119–221: the paper that recast
homological algebra in abelian categories and treated the cohomology of sheaves as a derived functor. This edition
gives the whole paper in LaTeX: the French as printed, the corrected French and an English translation.

| | |
|---|---|
| [Corrected French (PDF, 83 pages)][fr] | evident misprints of the print corrected, printed pages 119–221 |
| [French as printed (PDF, 83 pages)][dip] | the text as printed, misprints included |
| [English translation (PDF, 81 pages)][en] | English, printed pages 119–221 |
| [LaTeX sources (ZIP)][zip] | the three layers below, also browsable in this repository |

The sources have three layers, aligned page by page with the printed pages (`p119.tex` … `p221.tex`; the journal has
no p. 184, between the two parts):

- `dip/`: the French as printed, including its misprints, built by `main-dip.tex`;
- `fr/`: the French with evident misprints corrected, built by `main-fr.tex`;
- `en/`: the English translation, built by `main-en.tex`.

Build each with pdfLaTeX, two passes: `pdflatex main-dip.tex`, `pdflatex main-fr.tex`, `pdflatex main-en.tex`.

## How it was made

AI-transcribed and AI-translated by OpenAI Codex, mainly GPT-5.6 Sol, with parts by GPT-6 Astra, both at reasoning
effort ultra, in August 2026, from the scans of the journal on J-STAGE (Part I: [10.2748/tmj/1178244839][p1]; Part II:
[10.2748/tmj/1178244774][p2]).

On 18 November 2026 GPT-6 Astra (ChatGPT Pro mode) checked the whole edition against those scans: every printed page,
in all three layers. It made the as-printed layer say what the print says, justified every correction of the
corrected layer or put the printed reading back, read the English against the corrected French, gave every recorded
change a second reading, rebuilt the three books, and wrote notes on the mathematics. The records of that check are in
[raw/check-2026-11-18](raw/check-2026-11-18/README.md), with the prompt as sent; the whole return, working files
included, is a release asset.

## Quality

The check of 18 November 2026 recorded **11,870 changes** (as-printed layer 3,815, corrected French 4,259, English
3,789, build 7):

| Kind | Changes |
|---|---:|
| reading of the print | 575 |
| misprint of the original, corrected | 488 |
| translation | 162 |
| typesetting (fonts of letters, emphasis, inline and displayed formulas) | 8,707 |
| structure (paragraphs, headings, displays, page breaks) | 1,938 |

5,520 of these change a formula or a mathematical sign. In the second reading 11,765 were confirmed, 105 amended and
139 withdrawn. The notes ([NOTES.md](raw/check-2026-11-18/NOTES.md), 891 items) give the 482 misprints of the original
with the corrected statements, 188 claims whose proof the paper abbreviates, 203 mathematical checks, ten comparisons
with later work, and eight links to our other work; [CHECK_EVENTS.tsv](raw/check-2026-11-18/CHECK_EVENTS.tsv) records
1,741 check events, each with what was actually done. The three books build with no error and no line or formula
running into the margin.

Before this release Claude (Claude Opus 5.5 at effort high) rebuilt the three books (pdfLaTeX, two passes: no error,
no overfull box), looked at pages of each, and compared six corrections in formulas with the scans; all six agree
with the print.

Errors may remain. Please report them as GitHub issues.

## Rights

The rights in the original work belong to its author or the author's representatives or heirs. Our transcription,
translation, corrections and typesetting were produced by AI. They have no human author and, in our understanding, are
not protected by copyright; where any right of ours exists nonetheless, it is dedicated to the public domain under CC0
1.0. All of this work reproduces or translates the original work, so nothing here licenses or authorizes any
reproduction, translation or other use of that work. This edition is published for educational, non-profit purposes,
and we claim no rights we do not hold. If you hold rights in this work and object to its publication here, please open
a GitHub issue and we will take it down.

[fr]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-fr.pdf
[dip]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-dip.pdf
[en]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-en.pdf
[zip]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-sources.zip
[p1]: https://doi.org/10.2748/tmj/1178244839
[p2]: https://doi.org/10.2748/tmj/1178244774
