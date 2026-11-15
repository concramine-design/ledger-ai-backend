"""Lecture tolérante du JSON renvoyé par l'IA.

Le piège principal : le LaTeX. Dans une chaîne JSON, « \\frac » écrit avec une seule
barre oblique devient un saut de page suivi de « rac », « \\times » une tabulation, etc.
On répare donc les barres obliques avant de lire le JSON.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Commandes LaTeX qui commencent par une lettre d'échappement JSON (b, f, n, r, t, u).
_LATEX_AMBIGUOUS = {
    # b
    "beta", "bar", "begin", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "bigcup", "bigcap",
    "binom", "bot", "boxed", "bullet", "bmod", "boldsymbol", "because", "backslash",
    # f
    "frac", "forall", "flat", "frown", "fbox",
    # n
    "nu", "neq", "ne", "nabla", "not", "notin", "neg", "nmid", "nearrow", "nwarrow", "nleq",
    "ngeq", "nsubseteq", "nparallel", "nexists", "newline", "nolimits", "ncong", "nless", "ngtr",
    "nRightarrow", "nrightarrow", "nleftarrow",
    # r
    "rho", "right", "rightarrow", "rangle", "rceil", "rfloor", "rbrace", "rbrack",
    "rightleftharpoons", "rightharpoonup", "rVert", "rvert",
    # t
    "times", "text", "tan", "tanh", "theta", "tau", "to", "top", "triangle", "tfrac", "tilde",
    "textbf", "textit", "textrm", "textsf", "texttt", "therefore", "triangleq", "tag", "tbinom",
    "textstyle", "textcolor",
    # u
    "underline", "underbrace", "uparrow", "upsilon", "uplus", "updownarrow", "underset",
}

_WORD = re.compile(r"[A-Za-z]+")
_UNICODE = re.compile(r"u[0-9a-fA-F]{4}")


def fix_backslashes(raw: str) -> str:
    """Double les barres obliques inverses qui appartiennent à du LaTeX."""
    out: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nxt = raw[i + 1] if i + 1 < n else ""
        if nxt == "\\":  # déjà doublée
            out.append("\\\\")
            i += 2
            continue
        if nxt in ('"', "/"):
            out.append(c + nxt)
            i += 2
            continue
        if nxt and nxt in "bfnrtu":
            m = _WORD.match(raw, i + 1)
            word = m.group(0) if m else ""
            if word in _LATEX_AMBIGUOUS:
                out.append("\\\\")
            elif nxt == "u" and not _UNICODE.match(raw, i + 1):
                out.append("\\\\")
            else:
                out.append("\\")  # véritable échappement JSON (\n, \t, \uXXXX...)
            i += 1
            continue
        out.append("\\\\")  # \alpha, \sqrt, \{ ... : invalide en JSON, c'est du LaTeX
        i += 1
    return "".join(out)


def _extract_block(text: str) -> str:
    """Isole l'objet JSON quand l'IA l'entoure de texte ou de balises ```."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    starts = [p for p in (text.find("{"), text.find("[")) if p != -1]
    if not starts:
        return text
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start : end + 1] if end > start else text[start:]


def _restore_control_chars(value: Any) -> Any:
    """Un \\b ou \\f lu comme caractère de contrôle était forcément du LaTeX."""
    if isinstance(value, str):
        return value.replace("\x08", "\\b").replace("\x0c", "\\f")
    if isinstance(value, list):
        return [_restore_control_chars(v) for v in value]
    if isinstance(value, dict):
        return {k: _restore_control_chars(v) for k, v in value.items()}
    return value


def parse_json(text: str) -> Any:
    """Lit le JSON de l'IA. Lève ValueError si c'est irrécupérable."""
    block = _extract_block(text or "")
    if not block:
        raise ValueError("réponse vide")
    fixed = fix_backslashes(block)
    candidates = [fixed, re.sub(r",\s*([}\]])", r"\1", fixed)]
    last: Exception | None = None
    for cand in candidates:
        try:
            return _restore_control_chars(json.loads(cand, strict=False))
        except json.JSONDecodeError as exc:
            last = exc
    raise ValueError(f"JSON illisible : {last}")
