# Alexander Grothendieck, *Sur quelques points d'algèbre homologique* (1957)

[Français](README.fr.md)

Grothendieck's "Tôhoku paper", *Tôhoku Mathematical Journal* (2) 9 (1957), pp. 119–221: the paper that recast
homological algebra in abelian categories and treated the cohomology of sheaves as a derived functor. This edition
gives the whole paper in LaTeX, in French and in an English translation.

| | |
|---|---|
| [French reader edition (PDF, 94 pages)][fr] | corrected French, printed pages 119–221 |
| [English translation (PDF, 90 pages)][en] | English, printed pages 119–221 |
| [LaTeX sources (ZIP)][zip] | the three layers below, also browsable in this repository |

The sources have three layers, aligned page by page with the printed pages (`p119.tex` … `p221.tex`):

- `dip/`: the French as printed, including its misprints;
- `fr/`: the French with evident misprints corrected, built by `main-fr.tex`;
- `en/`: the English translation, built by `main-en.tex`.

Build each reader with pdfLaTeX, two passes: `pdflatex main-fr.tex` and `pdflatex main-en.tex`.

## How it was made

AI-transcribed and AI-translated by OpenAI Codex, mainly GPT-5.6 Sol, with parts by GPT-6 Astra, both at Ultra
effort, in August 2026, from the scans of the journal on J-STAGE (Part I: [10.2748/tmj/1178244839][p1]; Part II:
[10.2748/tmj/1178244774][p2]).

## Quality

A spot check by Claude (Anthropic), November 2026, compared printed p. 150 with the scan:

- The wording and the mathematics of the French match the print.
- The printed-French layer is not typographically faithful on that page. The print's bold **C** (the category) and
  italic *C* (the resolving functor) are swapped. The italics of emphasis (*exact*, *supposons*, *monomorphisme*) are
  dropped. Two inline formulas are set as displays. One formula is normalized: the print has the augmentation
  A → C(A), the transcription A → C⁰(A).

More checking against the scans is planned. Until then, cite the printed paper for typography and notation.

## Rights

The rights in the original work belong to its author or the author's representatives or heirs. Where we hold rights,
in the AI-produced transcription, translation, corrections and typesetting, they are dedicated to the public domain
under CC0 1.0. This edition is published for educational, non-profit purposes, and we claim no rights we do not hold.
If you hold rights in this work and object to its publication here, please open a GitHub issue and we will take it
down.

[fr]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-06/tohoku-fr.pdf
[en]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-06/tohoku-en.pdf
[zip]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-06/tohoku-sources.zip
[p1]: https://doi.org/10.2748/tmj/1178244839
[p2]: https://doi.org/10.2748/tmj/1178244774
