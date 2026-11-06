# Alexandre Grothendieck, *Sur quelques points d'algèbre homologique* (1957)

[English](README.md)

L'article « Tôhoku » de Grothendieck, *Tôhoku Mathematical Journal* (2) 9 (1957), p. 119–221 : l'article qui a
refondé l'algèbre homologique dans les catégories abéliennes et traité la cohomologie des faisceaux comme foncteur
dérivé. Cette édition donne l'article entier en LaTeX, en français et en traduction anglaise.

| | |
|---|---|
| [Édition de lecture française (PDF, 94 pages)][fr] | français corrigé, pages imprimées 119–221 |
| [Traduction anglaise (PDF, 90 pages)][en] | anglais, pages imprimées 119–221 |
| [Sources LaTeX (ZIP)][zip] | les trois couches ci-dessous, aussi consultables dans ce dépôt |

Les sources ont trois couches, alignées page par page sur les pages imprimées (`p119.tex` … `p221.tex`) :

- `dip/` : le français tel qu'imprimé, coquilles comprises ;
- `fr/` : le français où les coquilles évidentes sont corrigées, compilé par `main-fr.tex` ;
- `en/` : la traduction anglaise, compilée par `main-en.tex`.

Compiler chaque édition avec pdfLaTeX, en deux passes : `pdflatex main-fr.tex` et `pdflatex main-en.tex`.

## Comment elle a été faite

Transcription et traduction produites par IA (OpenAI Codex, surtout GPT-5.6 Sol, avec des parties par GPT-6 Astra,
tous deux en effort Ultra), août 2026, à partir des numérisations de la revue sur J-STAGE (partie I :
[10.2748/tmj/1178244839][p1] ; partie II : [10.2748/tmj/1178244774][p2]).

## Qualité

Un contrôle ponctuel par Claude (Anthropic), novembre 2026, a comparé la p. 150 imprimée à la numérisation :

- Le texte et les mathématiques du français correspondent à l'imprimé.
- La couche « français tel qu'imprimé » n'est pas fidèle à la typographie sur cette page. Le **C** gras de l'imprimé
  (la catégorie) et le *C* italique (le foncteur résolvant) sont intervertis. Les italiques d'insistance (*exact*,
  *supposons*, *monomorphisme*) manquent. Deux formules en ligne sont composées en display. Une formule est
  normalisée : l'imprimé a l'augmentation A → C(A), la transcription A → C⁰(A).

D'autres contrôles sur les numérisations sont prévus. D'ici là, citer l'article imprimé pour la typographie et les
notations.

## Droits

Les droits sur l'œuvre originale appartiennent à son auteur ou à ses représentants ou ayants droit. Dans la mesure
où nous détenons des droits sur la transcription, la traduction, les corrections et la composition produites par IA,
ils sont dédiés au domaine public sous CC0 1.0. Cette édition est publiée à des fins éducatives et non lucratives, et
nous ne revendiquons aucun droit que nous ne détenons pas. Si vous détenez des droits sur cette œuvre et vous opposez
à sa publication ici, ouvrez une issue GitHub et nous la retirerons.

[fr]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-06/tohoku-fr.pdf
[en]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-06/tohoku-en.pdf
[zip]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-06/tohoku-sources.zip
[p1]: https://doi.org/10.2748/tmj/1178244839
[p2]: https://doi.org/10.2748/tmj/1178244774
