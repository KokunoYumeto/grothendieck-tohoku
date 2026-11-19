"""Prepare or use a local pdfLaTeX runtime when generated system data is absent.

The edition itself needs only an ordinary pdfLaTeX installation with the
packages named in its preamble. This helper repairs the execution environment;
it does not edit, normalize, or otherwise transform edition sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

PACKAGE_BASE = (
    "https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2024/"
    "tlnet-final/archive/"
)
PACKAGES = {
    "babel-french": "9475bfc0f71e820c8e8de7d9e362062bec8f5e102ab11c9b4a4d6ff045951834",
    "hyphen-french": "77a89831bbda967aea80bd71c1e3809afaa9a37c4dba7ecc838ce89377ba1d78",
    "hyph-utf8": "ecf53abe0f4c00fee7c8931abeb626bd8ee1dcdc2877dba1ac9779590f348be9",
}


def installed_roots() -> list[Path]:
    roots = []
    for name in ("TEXMFDEBIAN", "TEXMFDIST", "TEXMFMAIN"):
        value = subprocess.check_output(
            ["kpsewhich", "-var-value=" + name], text=True
        ).strip()
        if value:
            root = Path(value).resolve()
            if root.is_dir() and root not in roots:
                roots.append(root)
    if not roots:
        raise RuntimeError("No installed TeX data trees were found.")
    return roots


def environment(runtime: Path) -> dict[str, str]:
    runtime = runtime.resolve()
    roots = [runtime / "texmf"] + installed_roots()
    result = os.environ.copy()
    # Omitting the !! prefix permits filesystem lookup without the absent
    # generated ls-R databases. No system file or global setting is changed.
    result["TEXMF"] = "{" + ",".join(map(str, roots)) + "}"
    result["TEXMFVAR"] = str(runtime / "texmf-var")
    result["TEXMFCONFIG"] = str(runtime / "texmf-config")
    result["VARTEXFONTS"] = str(runtime / "fontcache")
    result["MKTEXFMT"] = "0"
    return result


def install_packages(runtime: Path) -> None:
    vendor = runtime / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    records = []
    for name, expected in PACKAGES.items():
        filename = name + ".tar.xz"
        path = vendor / filename
        url = PACKAGE_BASE + filename
        if not path.is_file():
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"Package {name} no longer matches the recorded source hash. "
                "Review the upstream version before changing the pinned hash."
            )
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if member.name.startswith("tex/"):
                    archive.extract(member, runtime / "texmf", filter="data")
        records.append({
            "package": name, "source": url,
            "bytes": len(data), "sha256": actual,
        })
        print("Verified and installed", name)
    (vendor / "DOWNLOADS.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )


def configure(runtime: Path) -> None:
    texmf = runtime / "texmf"
    config = texmf / "tex/generic/config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "language.dat").write_text(
        "english hyphen.tex\n=usenglish\n=USenglish\n"
        "french loadhyph-fr.tex\n=francais\n\n",
        encoding="ascii",
    )
    maps = texmf / "fonts/map/pdftex/local"
    maps.mkdir(parents=True, exist_ok=True)
    entries = {}
    for root in installed_roots():
        candidates = list(root.glob("fonts/map/dvips/lm/lm.map"))
        candidates += sorted(root.glob("fonts/map/dvips/amsfonts/*.map"))
        for path in candidates:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("%"):
                    entries.setdefault(stripped.split()[0], line)
    if not entries:
        raise RuntimeError("No installed Latin Modern or AMS font maps found.")
    (maps / "pdftex.map").write_text(
        "% Local aggregate of installed Latin Modern and AMS font maps.\n"
        + "\n".join(entries.values()) + "\n",
        encoding="utf-8",
    )
    (texmf / "web2c/pdftex").mkdir(parents=True, exist_ok=True)
    for name in ("texmf-var", "texmf-config", "fontcache", "work"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    print("Configured English/French hyphenation and", len(entries), "font mappings")


def make_format(runtime: Path) -> None:
    directory = runtime / "texmf/web2c/pdftex"
    command = [
        "pdftex", "-ini", "-etex", "-progname=pdflatex",
        "-jobname=pdflatex", "-interaction=nonstopmode", "-halt-on-error",
        "pdflatex.ini",
    ]
    run = subprocess.run(
        command, cwd=directory, env=environment(runtime),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    (runtime / "work/format-output.log").write_text(run.stdout, encoding="utf-8")
    if run.returncode or not (directory / "pdflatex.fmt").is_file():
        print(run.stdout[-12000:], file=sys.stderr)
        raise RuntimeError("Local pdfLaTeX format generation failed.")
    print("Generated local pdfLaTeX format")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "run"))
    parser.add_argument("--runtime", type=Path, default=Path("tmp/tex-runtime"))
    parser.add_argument("--workdir", type=Path)
    args, command = parser.parse_known_args()
    runtime = args.runtime.resolve()
    if args.action == "setup":
        if command:
            parser.error("Unexpected setup arguments: " + " ".join(command))
        runtime.mkdir(parents=True, exist_ok=True)
        install_packages(runtime)
        configure(runtime)
        make_format(runtime)
        return
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("run requires a command after --")
    result = subprocess.run(command, cwd=args.workdir, env=environment(runtime))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
