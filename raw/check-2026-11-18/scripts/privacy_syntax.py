"""Narrow syntax recognizers proposed for the delivery privacy checker.

These recognize token syntax, never mathematical or editorial correctness.
No source bytes are rewritten. Unknown or unparseable forms retain findings.
"""

from __future__ import annotations

from pathlib import Path
import re
import tempfile


_OPERATOR_MORPHISM = re.compile(
    r"[A-Za-z]:(?P<slash>\\{1,2})mathrm\{Coim\}(?P=slash),[A-Za-z]"
    r"[ \t]*(?P=slash)(?:to|rightarrow|longrightarrow)[ \t]*"
    r"(?P=slash)mathrm\{Im\}(?P=slash),[A-Za-z]"
)
_FUNCTOR_MORPHISM = re.compile(
    r"[A-Za-z]:(?P<slash>\\{1,2})mathbf[ \t]*[A-Za-z]"
    r"\(\{(?P=slash)mathbf[ \t]*[A-Za-z]\}_[0-9]\)"
    r"[ \t]*(?P=slash)(?:to|rightarrow|longrightarrow)[ \t]*"
    r"(?P=slash)mathbf[ \t]*[A-Za-z]"
    r"\(\{(?P=slash)mathbf[ \t]*[A-Za-z]\}_[0-9]\)"
)
_SERIALIZED_ARROW_NEWLINE = re.compile(
    r"\\\\(?:to|rightarrow|longrightarrow)\\n(?=\\\\(?:mathbf|mathrm)\{Hom\})"
)
_HOM_TERM = re.compile(
    r"\\(?:mathbf|mathrm)\{Hom\}_\{"
    r"(?:\\mathbf[ \t]*[A-Za-z]|\{\\mathbf[ \t]*[A-Za-z]\})"
    r"(?:\([A-Za-z]\))?\}"
    r"\(\{\\mathbf[ \t]*[A-Za-z]\}\^[A-Za-z](?:\([A-Za-z]\))?,"
    r"[A-Za-z](?:\([A-Za-z]\))?\)"
)
_GLYPH_SEQUENCE = re.compile(r"(?:/[A-Za-z.][A-Za-z0-9_.]*)+")


def extra_tex_morphism(text, match, term_ends):
    for grammar in (_OPERATOR_MORPHISM, _FUNCTOR_MORPHISM):
        parsed = grammar.match(text, match.start())
        if parsed is not None and term_ends(text, parsed.end()):
            return True
    return False


def serialized_hom_newline(text, match):
    """Recognize one JSON escaping layer around a complete Hom term.

    Require a TeX inline-math opener in the same quoted field, a bounded
    arrow, an encoded newline, and the entire balanced target term through
    the closing math delimiter. A path suffix or unknown command fails.
    """
    prefix = _SERIALIZED_ARROW_NEWLINE.match(text, match.start())
    if prefix is None:
        return False
    opener = text.rfind("$", 0, match.start())
    if opener < 0 or any(c in text[opener:match.start()] for c in ('"', "\t")):
        return False
    close = text.find("$", prefix.end(), prefix.end() + 1024)
    if close < 0:
        return False
    raw = text[prefix.end():close]
    slash = chr(92)
    decoded = raw.replace(slash * 2, slash)
    # Reject a mixed or additional escaping layer, rather than guessing.
    if decoded.replace(slash, slash * 2) != raw:
        return False
    return _HOM_TERM.fullmatch(decoded) is not None


def editorial_slash_not_path(text, match, term_ends):
    token, before = match.group(0), text[:match.start()]
    if token == chr(47) + "Nos" and before.endswith("N" + chr(176)):
        return term_ends(text, match.end())
    # A slash immediately inside this complete printed quotient is relative
    # to its numerator. It is not a root slash. No other symbol is waived.
    if (re.fullmatch(chr(47) + r"[A-Za-z]∗", token)
            and re.search(r"[A-Za-z]∗$", before)
            and term_ends(text, match.end())):
        return True
    if token == chr(47) + "logique" and before.endswith("cohomo-"):
        context = text[max(0, match.start() - 64):match.end() + 64]
        return bool(re.search(r"\bsplit\b", context)
                    and re.search(r"\bpage boundary\b", context))
    return False


def embedded_type1_glyph_names(descriptor):
    """Read glyph names from this descriptor's embedded Type 1 subset.

    A PDF may omit the final 512-zero/cleartomark segment. Only when the
    explicit Length3 is zero, append that syntax in disposable parser input.
    The original stream and PDF are never modified. Missing dependencies,
    inconsistent lengths or parser errors leave the original finding active.
    """
    from fontTools.t1Lib import T1Font
    from pypdf.generic import StreamObject

    slash = chr(47)
    reference = descriptor.get(slash + "FontFile")
    if reference is None:
        return None
    stream = reference.get_object()
    if not isinstance(stream, StreamObject):
        return None
    lengths = tuple(int(stream.get(slash + key, -1))
                    for key in ("Length1", "Length2", "Length3"))
    data = stream.get_data()
    if (lengths[0] <= 0 or lengths[1] <= 0 or lengths[2] < 0
            or sum(lengths) != len(data) or len(data) > 16 * 1024 * 1024):
        return None
    if lengths[2] == 0:
        data += b"\n" + b"0" * 512 + b"\ncleartomark\n"
    with tempfile.TemporaryDirectory(prefix="pdf-font-inspection-") as directory:
        path = Path(directory) / "subset.pfa"
        path.write_bytes(data)
        font = T1Font(path, kind="OTHER")
        return frozenset(font["CharStrings"])


def verified_pdf_charset(text, key, descriptor, cache):
    """Accept only a typed glyph list proven against its own embedded font."""
    slash = chr(47)
    if (key != slash + "CharSet" or descriptor is None
            or str(descriptor.get(slash + "Type", "")) != slash + "FontDescriptor"
            or len(text) > 131072 or _GLYPH_SEQUENCE.fullmatch(text) is None):
        return False
    names = text.split(slash)[1:]
    if len(names) != len(set(names)) or len(names) > 4096:
        return False
    identity = id(descriptor)
    if identity not in cache:
        try:
            cache[identity] = embedded_type1_glyph_names(descriptor)
        except Exception:
            cache[identity] = None
    glyphs = cache[identity]
    return glyphs is not None and set(names).issubset(glyphs)
