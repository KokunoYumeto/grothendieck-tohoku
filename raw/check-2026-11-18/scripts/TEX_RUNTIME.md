# Auxiliary pdfLaTeX runtime

This helper prepares the execution environment without changing the edition.
An ordinary complete TeX Live installation can build the edition directly and
does not need this helper.

## Observed environment and repair

The supplied environment has pdfTeX 1.40.26, the LaTeX kernel dated 2024-11-01
(patch level 2), the document class and almost all required packages. Its
generated TeX filename databases, format and font-map configuration were
absent. French Babel and French hyphenation resources were also absent.

`tex_runtime.py` discovers the existing TeX trees, searches them without the
missing filename databases, and supplies a separate runtime tree. It writes
an English/French `language.dat`, assembles 774 mappings from the installed
Latin Modern and AMS maps, and generates a local `pdflatex.fmt` using the
installed `pdflatex.ini`. It changes no system file and no edition source.

The current 2026 Babel French package was tried first. It uses
`\IfDocumentMetadataT`, which this installed kernel does not supply; the
disposable test therefore failed. The working setup instead uses unmodified,
compatible packages from the final TeX Live 2024 historical distribution.
Its Babel French version is 2024-07-25 v3.6c. All three downloaded packages
are pinned by SHA-256, and the helper refuses an unexpected replacement.

## Package sources

The packages come from the TeX Live historical distribution archive:

<https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2024/tlnet-final/archive/>

| Package | Bytes | SHA-256 |
| --- | ---: | --- |
| `babel-french.tar.xz` | 15,784 | `9475bfc0f71e820c8e8de7d9e362062bec8f5e102ab11c9b4a4d6ff045951834` |
| `hyphen-french.tar.xz` | 11,420 | `77a89831bbda967aea80bd71c1e3809afaa9a37c4dba7ecc838ce89377ba1d78` |
| `hyph-utf8.tar.xz` | 15,980 | `ecf53abe0f4c00fee7c8931abeb626bd8ee1dcdc2877dba1ac9779590f348be9` |

The downloaded dependencies retain their own rights notices and remain
unmodified. The helper extracts only their TeX runtime files. This report
and the helper contain no edition readings or mathematical judgments.

## Additional available dependency

`wrapfig.sty` is already present in an installed TeX tree and resolves through
the same task-local runtime environment. Its package declaration is
2003-01-31 v3.6. No download, replacement or system change was needed to make
it available for the later `wrapfigure` use. This was verified by a package
lookup; no edition build or source-page inspection was performed.

## Invocation

From the delivery directory, prepare a runtime with:

```bash
python scripts/tex_runtime.py setup --runtime ../tmp/tex-runtime
```

Run a command with that runtime, selecting the source directory separately:

```bash
python scripts/tex_runtime.py run --runtime ../tmp/tex-runtime --workdir sources -- pdflatex -interaction=nonstopmode -halt-on-error main-fr.tex
```

Repeat the build command for the second pass. Substitute `main-dip.tex` or
`main-en.tex` for the other layers. The edition build results belong in
`PDF_CHECK.md`; this auxiliary setup is not itself a build of the edition.

The Python function `environment(runtime)` can also supply the environment
to `subprocess.run`. All runtime and system locations are discovered at
execution; no private absolute location is embedded in the helper.

## Verification performed on 2026-11-18

A disposable, one-page document loaded every package used by the supplied
preamble. It contained French accents and ligatures, French punctuation,
English prose, italic and bold text, a displayed exact sequence, subscripts,
superscripts, and calligraphic, bold and Gothic mathematical letters.

Both final pdfLaTeX passes exited successfully, with zero errors, no warnings
and no overfull or underfull boxes. The language diagnostics selected French
language 1 and English language 0; format generation loaded both English and
French hyphenation patterns. The final PDF contained embedded Type 1 fonts
for every listed font. Its single page was rendered and visually inspected:
accents, ligatures, mathematical letters, arrows and indices were present,
legible and unclipped.

This was an infrastructure fixture only. No edition page or scan was read,
checked or compiled by the auxiliary agent.
