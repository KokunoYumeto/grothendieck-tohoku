"""Mechanical file-local proof-cue and heading lexer; no I/O or TeX expansion.

scan_page returns cues, anchors, headings, cue-referenced fragments and notes.
Offsets index the supplied Python string; end offsets are exclusive. Lines and
columns are one-based, with LF defining lines. All matched strings are raw.
``active`` means ordinary visited lexical source, not executed or proved text.

CUE_PATTERNS lists every regex. Unicode IGNORECASE applies; [ée]/[èe] variants
are explicitly accepted, but TeX accent commands and decomposed accents are not
expanded or normalized. Stems consume Unicode letters, not digits/underscores.
Only sans preuve and nous omettons/omettrons are additional cue families.
"""

from __future__ import annotations

import re

from control_word_inventory import VERBATIM_ENVS, coordinates, lex_control_words, skip_space_comments
from math_font_context import balanced_end, scan_font_context, token


LEFT, RIGHT, SPACE, STEM = r"(?<![\w\\])", r"(?!\w)", r"[ \t\r\n~]+", r"[^\W\d_]*"
CUE_PATTERNS = [
    {"family": family, "label": label, "pattern": LEFT + pattern + RIGHT, "flags": "IGNORECASE; Unicode"}
    for family, label, pattern in [
        ("sans_demonstration", "sans démonstration", "sans" + SPACE + r"d[ée]monstration"),
        ("laiss", "laiss*", "laiss" + STEM),
        ("exercice", "exercice*", "exercice" + STEM),
        ("facile", "facile*", "facile" + STEM),
        ("evident", "évident*", r"[ée]vident" + STEM),
        ("trivial", "trivial*", "trivial" + STEM),
        ("verifi", "vérifi*", r"v[ée]rifi" + STEM),
        ("on_voit", "on voit", "on" + SPACE + "voit"),
        ("on_constate", "on constate", "on" + SPACE + "constate"),
        ("il_suffit", "il suffit", "il" + SPACE + "suffit"),
        ("nous_renvoy", "nous renvoy*", "nous" + SPACE + "renvoy" + STEM),
        ("se_montre", "se montre", "se" + SPACE + "montre"),
        ("demontrer", "démontrer", r"d[ée]montrer"),
        ("peut_montrer", "peut montrer", "peut" + SPACE + "montrer"),
        ("aisement", "aisément", r"ais[ée]ment"),
        ("n_ecrirons", "n'écrirons / n’écrirons", r"n['’][ée]crirons"),
        ("sans_preuve", "sans preuve (additional family)", "sans" + SPACE + "preuve"),
        ("nous_omettons_omettrons", "nous omettons/omettrons (additional family)", "nous" + SPACE + r"(?:omettons|omettrons)"),
    ]
]
LIMITATIONS = [
    "Regex matches are literal mechanical cues, never semantic classifications or evidence that a proof is absent.",
    "No TeX expansion, accent-command interpretation, Unicode normalization, conditional execution, catcode reconstruction or cross-file lexical state is performed.",
    "Comments and recognized literal/verbatim material are separate scopes; deferred definitions and unvisited or mixed lexical syntax remain uncertain.",
    "Recognized literal environments are the shared lexer set plus filecontents/filecontents*; custom literal macros and environments can be missed.",
    "Complete fragments mean only blocks bounded on both sides by recognized file-local blank lines or explicit par commands. Cross-file continuation is unresolved.",
    "File-edge, unresolved or whole-page blocks receive bounded fragments, at most 640 characters. A fragment is omitted when no proper non-whole-page span can contain its cue.",
    "Heading candidates use literal theorem/proposition/lemma/corollary labels at explicit heading arguments, leading font wrappers or physical line leads; semantic completeness and statement association are not asserted.",
    "Literal heading numbers are Arabic dotted numbers, canonical uppercase Roman numerals or one uppercase Latin letter, optionally parenthesized. Unknown numbering remains unnumbered.",
    "LayerTarget arguments are balanced literal source arguments, including raw nested braces and commands, never expanded destination identifiers.",
]
HEADING_COMMANDS = frozenset({"SectionHeading", "section", "subsection", "subsubsection", "paragraph", "subparagraph", "chapter", "part"})
WRAPPERS = frozenset({"textbf", "textsc", "emph"})
LEGACY_WRAPPERS = frozenset({"bf", "sc", "bfseries", "scshape"})
LEAD_COMMANDS = frozenset({"noindent", "indent", "leavevmode", "centering"})
LITERAL_ENVS = VERBATIM_ENVS | {"filecontents", "filecontents*"}
LABEL = re.compile(r"(?P<label>th[ée]or[èe]mes?|theorems?|propositions?|lemmes?|lemmas?|corollaires?|corollary|corollaries)(?!\w)", re.I)
ROMAN = r"(?=[MDCLXVI])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
NUMBER = re.compile(r"\(?(?:[0-9]+(?:\.[0-9]+)*(?:[A-Za-z])?|" + ROMAN + r"|[A-Z])\)?(?![\w])")
MAX_FRAGMENT_CHARS = 640


def span(text: str, starts: list[int], first: int, last: int, scope: str) -> dict:
    line, column = coordinates(first, starts)
    end_line, end_column = coordinates(last, starts)
    return {"offset": first, "end_offset": last, "line": line, "column": column,
            "end_line": end_line, "end_column": end_column, "scope": scope}


def balanced_raw(text: str, start: int, limit: int) -> int | None:
    """Brace balance in comment/literal material, where percent is ordinary."""
    depth, at = 1, start + 1
    while at < limit:
        if text[at] == "\\":
            _, _, at = token(text, at)
            continue
        depth += int(text[at] == "{") - int(text[at] == "}")
        at += 1
        if depth == 0:
            return at
    return None


def containing(ranges: list[tuple[int, int]], first: int, last: int) -> tuple[int, int] | None:
    return next(((a, b) for a, b in ranges if a <= first and last <= b), None)


def literal_ranges(text: str, lexical: dict) -> list[tuple[int, int]]:
    ranges = []
    for item in lexical["occurrences"]:
        at, end, name = item["offset"], item["end"], item["command"]
        if containing(ranges, at, end):
            continue
        if name == "verb":
            delimiter = end + int(end < len(text) and text[end] == "*")
            if delimiter < len(text) and text[delimiter] not in "\r\n":
                line_end = text.find("\n", delimiter)
                line_end = len(text) if line_end < 0 else line_end
                close = text.find(text[delimiter], delimiter + 1, line_end)
                ranges.append((at, line_end if close < 0 else close + 1))
        elif name == "detokenize":
            opening = skip_space_comments(text, end)
            close = balanced_end(text, opening)
            if close is not None:
                ranges.append((at, close))
        elif name == "begin":
            opening = skip_space_comments(text, end)
            found = re.match(r"\{([A-Za-z][A-Za-z0-9*_-]*)\}", text[opening:])
            if found and found[1] in LITERAL_ENVS:
                marker = "\\end{" + found[1] + "}"
                close = text.find(marker, opening + found.end())
                ranges.append((at, len(text) if close < 0 else close + len(marker)))
    return ranges


def scan_page(text: str) -> dict:
    if not isinstance(text, str):
        raise TypeError("scan_page requires the original decoded text string.")
    result = {name: [] for name in ("cues", "anchors", "headings", "fragments", "notes")}
    if not text:
        return result
    starts = [0] + [match.end() for match in re.finditer("\n", text)]
    # Shared scanners strip a UTF-8 BOM. Supplying one additional marker keeps
    # any original leading BOM in the decoded string and preserves all offsets.
    data = b"\xef\xbb\xbf" + text.encode("utf-8")
    lexical = lex_control_words(data, include_comment_ranges=True)
    comments = lexical["comment_ranges"]
    literals = literal_ranges(text, lexical)
    command_offsets = {item["offset"]: item for item in lexical["occurrences"]}
    referenced_commands = set()
    for item in lexical["occurrences"]:
        if item["command"] in {"string", "meaning", "noexpand"}:
            at = skip_space_comments(text, item["end"])
            if text[at:at + 1] == "\\":
                referenced_commands.add(at)
    notes = result["notes"]

    def note(at: int, end: int, kind: str, detail: str, scope: str = "uncertain") -> None:
        notes.append({**span(text, starts, at, end, scope), "kind": kind, "detail": detail})

    def preliminary(first: int, last: int) -> str:
        if containing(literals, first, last):
            return "literal_or_verbatim"
        if containing(comments, first, last):
            return "comment"
        if any(a < last and first < b for a, b in literals + comments):
            return "uncertain"
        return "active"

    raw_cues = [(pattern, match) for pattern in CUE_PATTERNS for match in re.finditer(pattern["pattern"], text, re.I)]
    raw_anchors, raw_headings = [], []

    def argument_after(end: int, at: int) -> tuple[int, int] | None:
        initial = preliminary(at, end)
        container = containing(literals if initial == "literal_or_verbatim" else comments, at, end)
        limit = container[1] if container else len(text)
        if initial in {"comment", "literal_or_verbatim"}:
            opening = end
            while opening < limit and text[opening].isspace():
                opening += 1
            close = balanced_raw(text, opening, limit) if opening < limit and text[opening] == "{" else None
        else:
            opening = skip_space_comments(text, end)
            close = balanced_end(text, opening)
        return (opening, close) if close is not None else None

    for match in re.finditer(r"\\LayerTarget(?![A-Za-z])", text):
        argument = argument_after(match.end(), match.start())
        if argument is None:
            note(match.start(), match.end(), "unresolved_layer_target", "No balanced explicit LayerTarget argument was recognized in its lexical scope.", preliminary(*match.span()))
            continue
        first, last = argument
        raw_anchors.append({"start": match.start(), "end": last, "argument_start": first + 1, "argument_end": last - 1,
                            "recognized_command": match.start() in command_offsets and match.start() not in referenced_commands})

    def number_after(at: int, limit: int) -> re.Match | None:
        gap = re.match(r"[ \t~]*(?:\r?\n[ \t~]*)?(?:[.:–—-][ \t~]*(?:\r?\n[ \t~]*)?)?", text[at:limit])
        position = at + gap.end()
        found = NUMBER.match(text, position, limit)
        if found and bool(found.group().startswith("(")) != bool(found.group().endswith(")")):
            return None
        return found

    def typed_at(at: int, limit: int, rule: str, outside: int | None = None) -> None:
        while at < limit and (text[at].isspace() or text[at] == "\ufeff"):
            at += 1
        if at >= limit:
            return
        if text[at] == "{":
            close = balanced_end(text, at)
            if close is not None and close <= limit:
                typed_at(at + 1, close - 1, rule, outside=close)
            return
        if text[at] == "\\":
            _, name, end = token(text, at)
            if name in LEAD_COMMANDS | LEGACY_WRAPPERS:
                typed_at(end, limit, rule + ";leading_" + name, outside)
            elif name in WRAPPERS:
                argument = argument_after(end, at)
                if argument and argument[1] <= limit:
                    typed_at(argument[0] + 1, argument[1] - 1, rule + ";leading_" + name, outside=argument[1])
            return
        label = LABEL.match(text, at, limit)
        if label is None:
            return
        number = number_after(label.end(), limit)
        if number is None and outside is not None:
            end_of_line = text.find("\n", outside)
            number = number_after(outside, len(text) if end_of_line < 0 else end_of_line)
        end = number.end() if number else label.end()
        folded = label["label"].casefold()
        heading_type = "theorem" if folded.startswith("th") else "lemma" if folded.startswith("lemm") else "corollary" if folded.startswith("coroll") else "proposition"
        raw_headings.append({"start": at, "end": end, "label": label["label"], "heading_type": heading_type,
                             "number": number.group() if number else "", "numbered": number is not None, "rule": rule})

    command_expression = r"\\(" + "|".join(sorted(HEADING_COMMANDS, key=len, reverse=True)) + r")(?![A-Za-z])"
    for match in re.finditer(command_expression, text):
        end = match.end() + int(match.end() < len(text) and text[match.end()] == "*")
        while True:
            at = skip_space_comments(text, end)
            close = balanced_end(text, at) if text[at:at + 1] == "[" else None
            if close is None:
                break
            end = close
        argument = argument_after(end, match.start())
        if argument is None:
            note(match.start(), match.end(), "unresolved_heading_argument", "No balanced explicit heading title was recognized.", preliminary(*match.span()))
        else:
            previous_count = len(raw_headings)
            typed_at(argument[0] + 1, argument[1] - 1, "explicit_" + match[1])
            if match.start() in referenced_commands:
                for row in raw_headings[previous_count:]:
                    row["referenced_command"] = True
    for line_start in starts:
        line_end = text.find("\n", line_start)
        line_end = len(text) if line_end < 0 else line_end
        # A braced leading wrapper can contain a line-wrapped literal title.
        # The eventual matched heading is still only the label/number span.
        lead = text[line_start:line_end].lstrip(" \t\r\ufeff")
        wrapped = lead.startswith("{") or bool(re.match(r"\\(?:textbf|textsc|emph)(?![A-Za-z])", lead))
        typed_at(line_start, len(text) if wrapped else line_end, "plain_line_lead")
        comment = next(((a, b) for a, b in comments if line_start <= a <= line_end), None)
        if comment:
            typed_at(comment[0] + 1, comment[1], "comment_line_lead")

    blanks = [(match.start(), match.end(), "blank_line") for match in re.finditer(r"(?m)^[ \t]*\r?\n", text)]
    pars = [(item["offset"], item["end"], "explicit_par") for item in lexical["occurrences"] if item["command"] == "par"]
    probes = set()
    for _, match in raw_cues:
        probes.update((match.start(), match.end() - 1))
    for row in raw_headings:
        probes.update((row["start"], row["start"] + len(row["label"]) - 1))
    for row in raw_anchors:
        letters = [at for at in range(row["argument_start"], row["argument_end"]) if text[at].isalnum()]
        if letters:
            row["probes"] = (letters[0], letters[-1])
            probes.update(row["probes"])
        else:
            row["probes"] = ()
    for first, last, kind in blanks + pars:
        at = first if kind == "blank_line" else last
        if at < len(text):
            probes.add(at)
    context = scan_font_context(data, probes)
    by_offset = {item["offset"]: item for item in context["probes"]}

    def scope_for(first: int, last: int, positions: tuple[int, ...] | None = None) -> str:
        initial = preliminary(first, last)
        if initial != "active":
            return initial
        selected = positions if positions is not None else (first, last - 1)
        if not selected:
            return "uncertain"
        states = [by_offset.get(at, {"visited": False}) for at in selected]
        if any(not state["visited"] for state in states):
            return "uncertain"
        if any(state["context_category"] in {"deferred definition body", "uncertain context"} for state in states):
            return "uncertain"
        if len({(state.get("context_category"), state.get("context_name")) for state in states}) > 1:
            return "uncertain"
        return "active"

    for item in context["notes"]:
        at = starts[item["line"] - 1] + item["column"] - 1
        note(at, min(at + 1, len(text)), item["kind"], item["detail"])
    for item in lexical["notes"]:
        at = starts[item["line"] - 1]
        note(at, at, item["kind"], item["detail"])
    boundaries = []
    for first, last, kind in blanks + pars:
        position = first if kind == "blank_line" else last
        state = scope_for(first, last, (position,) if position < len(text) else ())
        if state == "active":
            boundaries.append((first, last, kind))
        elif kind == "explicit_par" and preliminary(first, last) == "active":
            note(first, last, "unresolved_par_boundary", "The par command has no reliably visited adjacent lexical context; it is not used as a paragraph boundary.")
    boundaries.sort()

    for number, row in enumerate(sorted(raw_anchors, key=lambda item: item["start"]), 1):
        state = scope_for(row["argument_start"], row["argument_end"], row["probes"])
        initial = preliminary(row["start"], row["end"])
        if initial in {"comment", "literal_or_verbatim"}:
            state = initial
        elif not row["recognized_command"]:
            state = "uncertain"
        result["anchors"].append({**span(text, starts, row["start"], row["end"], state), "anchor_id": f"A{number:04d}",
                                  "matched": text[row["start"]:row["end"]], "argument": text[row["argument_start"]:row["argument_end"]],
                                  "argument_offset": row["argument_start"], "argument_end_offset": row["argument_end"]})
    merged = {}
    for row in raw_headings:
        previous = merged.get(row["start"])
        if previous is None:
            merged[row["start"]] = row
        else:
            rules = sorted(set(previous["rule"].split(";") + row["rule"].split(";")))
            if row["numbered"] and not previous["numbered"]:
                merged[row["start"]] = row
            if previous.get("referenced_command") or row.get("referenced_command"):
                merged[row["start"]]["referenced_command"] = True
            merged[row["start"]]["rule"] = ";".join(rules)
    for number, row in enumerate(sorted(merged.values(), key=lambda item: item["start"]), 1):
        state = scope_for(row["start"], row["end"], (row["start"], row["start"] + len(row["label"]) - 1))
        if state == "active" and row.get("referenced_command"):
            state = "uncertain"
        result["headings"].append({**span(text, starts, row["start"], row["end"], state), "heading_id": f"H{number:04d}",
                                   **{field: row[field] for field in ("heading_type", "label", "number", "numbered", "rule")},
                                   "matched": text[row["start"]:row["end"]]})
    fragment_by_key = {}
    for number, (pattern, match) in enumerate(sorted(raw_cues, key=lambda item: (item[1].start(), item[1].end(), item[0]["family"])), 1):
        first, last = match.span()
        state = scope_for(first, last)
        if state == "active" and any(a < last and first < b for a, b, _ in boundaries):
            state = "uncertain"
            note(first, last, "cue_crosses_paragraph_boundary", "The literal regex match crosses a recognized paragraph boundary; it has no single complete paragraph fragment.")
        cue = {**span(text, starts, first, last, state), "cue_id": f"Q{number:04d}", "family": pattern["family"], "matched": match.group(), "fragment_id": ""}
        if state == "active":
            before = [item for item in boundaries if item[1] <= first]
            after = [item for item in boundaries if item[0] >= last]
            left, left_kind = (before[-1][1], before[-1][2]) if before else (0, "file_start_unresolved")
            right, right_kind = (after[0][0], after[0][2]) if after else (len(text), "file_end_unresolved")
            while left < first and text[left].isspace():
                left += 1
            while right > last and text[right - 1].isspace():
                right -= 1
            complete = bool(before and after)
            limitation = "Cross-file continuation remains unresolved; completeness is only the recognized file-local block."
            whole_page = text[left:right].strip() == text.strip()
            if not complete or whole_page:
                complete = False
                limitation = "At least one file-local boundary is unresolved or the block spans the whole page; this is bounded context, not a complete paragraph."
                if last - first > MAX_FRAGMENT_CHARS or text[first:last].strip() == text.strip():
                    left = right = first
                    limitation += " No proper bounded non-whole-page fragment containing the entire cue is available; fragment omitted."
                else:
                    width = min(MAX_FRAGMENT_CHARS, right - left)
                    if whole_page:
                        width = min(width, max(last - first, (right - left) // 2))
                    left = max(left, min(first - max(0, (width - (last - first)) // 2), right - width))
                    right = left + width
                    if text[left:right].strip() == text.strip():
                        left, right = first, last
            completeness = "complete_file_local_paragraph" if complete else "bounded_unresolved_fragment" if left < right else "omitted_whole_page_fragment"
            key = (left, right, completeness, left_kind, right_kind)
            if key not in fragment_by_key:
                identifier = f"P{len(fragment_by_key) + 1:04d}"
                fragment_by_key[key] = identifier
                result["fragments"].append({**span(text, starts, left, right, "active"), "fragment_id": identifier,
                                            "fragment": text[left:right], "completeness": completeness,
                                            "left_boundary": left_kind, "right_boundary": right_kind, "limitation": limitation})
            cue["fragment_id"] = fragment_by_key[key]
        result["cues"].append(cue)
    notes.sort(key=lambda row: (row["offset"], row["kind"], row["detail"]))
    return result
