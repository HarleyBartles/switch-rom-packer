# packer/metadata/titles.py
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

_ARTICLES = ("The", "A", "An")

_ORDINAL_MAP = {
    "1st": "First", "2nd": "Second", "3rd": "Third", "4th": "Fourth", "5th": "Fifth",
    "6th": "Sixth", "7th": "Seventh", "8th": "Eighth", "9th": "Ninth", "10th": "Tenth",
}

_ROMAN_MAP = {
    "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
    "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "X": "10",
}

_MANUAL_OVERRIDES = {
    "7th Saga, The": "The 7th Saga",
    "Legend of Zelda, The": "The Legend of Zelda",
}


def _strip_tags(s: str) -> str:
    """Remove region/revision/translation tags like (U), (Rev A), [!], [T+Eng], etc."""
    s = re.sub(r"\([^)]*\)", "", s)     # remove (...) blocks
    s = re.sub(r"\[[^\]]*\]", "", s)    # remove [...] blocks
    s = re.sub(r"\s+", " ", s).strip(" -_.,!+")
    return s.strip()


def _move_trailing_article(s: str) -> str:
    """Turn 'Game, The' into 'The Game'."""
    m = re.match(r"^(.*?),\s*(%s)\b$" % "|".join(_ARTICLES), s, flags=re.IGNORECASE)
    if not m:
        return s
    core, art = m.group(1), m.group(2)
    return f"{art} {core}"


def _roman_to_arabic_tokens(tokens: List[str]) -> List[str]:
    return [_ROMAN_MAP.get(tok, tok) for tok in tokens]


def _arabic_ord_to_word(tokens: List[str]) -> List[str]:
    return [_ORDINAL_MAP.get(tok, tok) for tok in tokens]


def _tidy_spaces_commas(s: str) -> str:
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_rom_title(rom_path: str) -> Tuple[str, List[str]]:
    """
    Derive a canonical hbmenu title and a list of alt_titles from a ROM filename.

    Example:
        '7th Saga, The (U) [!].smc'
        -> canonical: 'The 7th Saga'
        -> alts: ['Seventh Saga', '7th Saga, The', '7th Saga', 'The Seventh Saga', ...]
    """
    stem = Path(rom_path).stem
    raw = _strip_tags(stem)

    # Base variants
    art_fixed = _move_trailing_article(raw)
    no_comma = raw.replace(",", "")
    no_punct = re.sub(r"[!._\-]+", " ", raw)
    base_candidates = {raw, art_fixed, no_comma, no_punct}

    # Token transforms (roman→arabic, ordinal→word)
    extra = set()
    for s in list(base_candidates):
        toks = s.split()
        roman_fix = " ".join(_roman_to_arabic_tokens(toks))
        ord_fix = " ".join(_arabic_ord_to_word(toks))
        extra.update({roman_fix, ord_fix})

    # Build candidate set, add trailing-article variants
    final = set()
    for s in base_candidates | extra:
        s = _tidy_spaces_commas(s)
        if not s:
            continue
        final.add(s)
        for art in _ARTICLES:
            if s.lower().startswith(art.lower() + " "):
                final.add(f"{s[len(art)+1:]}, {art}")

    # Pick canonical
    canonical = art_fixed if art_fixed.strip() else raw
    canonical = _MANUAL_OVERRIDES.get(canonical, canonical)

    # Rank alts
    def score_key(t: str):
        starts_with_article = any(t.startswith(a + " ") for a in _ARTICLES)
        has_digit = any(ch.isdigit() for ch in t)
        punct_penalty = len(re.findall(r"[,!_\-\.]", t))
        return (-int(starts_with_article), -int(has_digit), punct_penalty, len(t))

    alts = sorted([t for t in final if t != canonical], key=score_key)

    # Generate extras (e.g., "7th" -> "Seventh")
    tokens = canonical.split()
    num_to_word = " ".join(_arabic_ord_to_word(tokens))
    if num_to_word and num_to_word != canonical:
        alts.insert(0, num_to_word)
        for art in _ARTICLES:
            if num_to_word.startswith(art + " "):
                alts.insert(1, f"{num_to_word[len(art)+1:]}, {art}")
                break

    # Deduplicate preserving order
    seen = set()
    deduped: List[str] = []
    for t in alts:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)

    return canonical, deduped
