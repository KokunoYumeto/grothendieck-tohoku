# Alexandre Grothendieck, *Sur quelques points d'algèbre homologique* (1957)

[English](README.md)

L'article « Tôhoku » de Grothendieck, *Tôhoku Mathematical Journal* (2) 9 (1957), p. 119–221 : l'article qui a
refondé l'algèbre homologique dans les catégories abéliennes et traité la cohomologie des faisceaux comme foncteur
dérivé. Cette édition donne l'article entier en LaTeX : le français tel qu'imprimé, le français corrigé et une
traduction anglaise.

| | |
|---|---|
| [Français corrigé (PDF, 83 pages)][fr] | coquilles évidentes de l'imprimé corrigées, pages imprimées 119–221 |
| [Français tel qu'imprimé (PDF, 83 pages)][dip] | le texte tel qu'imprimé, coquilles comprises |
| [Traduction anglaise (PDF, 81 pages)][en] | anglais, pages imprimées 119–221 |
| [Sources LaTeX (ZIP)][zip] | les trois couches ci-dessous, aussi consultables dans ce dépôt |

Les sources ont trois couches, alignées page par page sur les pages imprimées (`p119.tex` … `p221.tex` ; la revue n'a
pas de p. 184, entre les deux parties) :

- `dip/` : le français tel qu'imprimé, coquilles comprises, compilé par `main-dip.tex` ;
- `fr/` : le français où les coquilles évidentes sont corrigées, compilé par `main-fr.tex` ;
- `en/` : la traduction anglaise, compilée par `main-en.tex`.

Compiler chaque édition avec pdfLaTeX, en deux passes : `pdflatex main-dip.tex`, `pdflatex main-fr.tex`,
`pdflatex main-en.tex`.

## Comment elle a été faite

Transcription et traduction produites par IA (OpenAI Codex, surtout GPT-5.6 Sol, avec des parties par GPT-6 Astra,
tous deux en effort de raisonnement ultra), août 2026, à partir des numérisations de la revue sur J-STAGE (partie I :
[10.2748/tmj/1178244839][p1] ; partie II : [10.2748/tmj/1178244774][p2]).

Le 18 novembre 2026, GPT-6 Astra (mode Pro de ChatGPT) a contrôlé toute l'édition sur ces numérisations : chaque page
imprimée, dans les trois couches. Il a rendu la couche « tel qu'imprimé » conforme à l'imprimé, justifié chaque
correction de la couche corrigée ou rétabli la leçon imprimée, relu l'anglais sur le français corrigé, soumis chaque
modification à une seconde lecture, recompilé les trois livres et écrit des notes sur les mathématiques. Les relevés de
ce contrôle sont dans [raw/check-2026-11-18](raw/check-2026-11-18/README.md), avec le prompt tel qu'envoyé ; le retour
complet, fichiers de travail compris, est joint à la publication (release).

## Qualité

Le contrôle du 18 novembre 2026 a relevé **11 870 modifications** (couche tel qu'imprimé 3 815, français corrigé 4 259,
anglais 3 789, compilation 7) :

| Nature | Modifications |
|---|---:|
| lecture de l'imprimé | 575 |
| coquille de l'original, corrigée | 488 |
| traduction | 162 |
| typographie (caractères, italiques d'insistance, formules en ligne ou en display) | 8 707 |
| structure (paragraphes, titres, displays, sauts de page) | 1 938 |

5 520 d'entre elles touchent une formule ou un signe mathématique. À la seconde lecture, 11 765 ont été confirmées,
105 amendées et 139 retirées. Les notes ([NOTES.md](raw/check-2026-11-18/NOTES.md), 891 entrées) donnent les 482
coquilles de l'original avec les énoncés corrigés, 188 affirmations dont l'article abrège la preuve, 203 vérifications
mathématiques, dix comparaisons avec des travaux ultérieurs et huit liens avec nos autres travaux ;
[CHECK_EVENTS.tsv](raw/check-2026-11-18/CHECK_EVENTS.tsv) consigne 1 741 événements de vérification, chacun avec ce qui
a réellement été fait. Les trois livres compilent sans erreur et sans ligne ni formule qui déborde dans la marge.

Avant cette publication, Claude (Claude Opus 5.5, effort high) a recompilé les trois livres (pdfLaTeX, deux passes :
aucune erreur, aucune boîte trop pleine), regardé des pages de chacun et comparé six corrections portant sur des
formules aux numérisations ; toutes les six sont conformes à l'imprimé.

Des erreurs peuvent subsister. Merci de les signaler par une issue GitHub.

## Droits

Les droits sur l'œuvre originale appartiennent à son auteur ou à ses représentants ou ayants droit. Notre
transcription, notre traduction, nos corrections et notre composition ont été produites par IA. Elles n'ont pas
d'auteur humain et, selon notre compréhension, ne sont pas protégées par le droit d'auteur ; là où un droit nous
appartiendrait malgré tout, il est versé au domaine public sous CC0 1.0. Tout ce travail reproduit ou traduit l'œuvre
originale : rien ici n'accorde de licence ni n'autorise une reproduction, une traduction ou un autre usage de cette
œuvre. Cette édition est publiée à des fins éducatives et non lucratives, et nous ne revendiquons aucun droit que nous
ne détenons pas. Si vous détenez des droits sur cette œuvre et vous opposez à sa publication ici, veuillez ouvrir une
issue GitHub et nous la retirerons.

[fr]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-fr.pdf
[dip]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-dip.pdf
[en]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-en.pdf
[zip]: https://github.com/KokunoYumeto/grothendieck-tohoku/releases/download/edition-2026-11-19/tohoku-sources.zip
[p1]: https://doi.org/10.2748/tmj/1178244839
[p2]: https://doi.org/10.2748/tmj/1178244774
