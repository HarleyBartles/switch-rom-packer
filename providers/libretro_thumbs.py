# providers/libretro_thumbs.py
from __future__ import annotations
import io, re, urllib.parse, urllib.request, html
from typing import Iterable, Optional, List, Tuple, Dict
from PIL import Image
from difflib import SequenceMatcher

BASE = "https://thumbnails.libretro.com"

# -------------------------
# Normalization & scoring
# -------------------------
_WS = re.compile(r"\s+")
_PARENS = re.compile(r"\s*\([^)]*\)\s*$")
_SYMS = re.compile(r"[™®©]")

def _norm(s: str) -> str:
    s = _SYMS.sub("", s)
    s = s.replace("_", " ").replace("-", " ")
    s = _WS.sub(" ", s).strip()
    s = s.lower()
    return s

def _strip_parens(s: str) -> str:
    return _PARENS.sub("", s).strip()

def _token_set(s: str) -> List[str]:
    return [t for t in _norm(s).split(" ") if t]

def _ratio(a: str, b: str) -> float:
    # base ratio
    r1 = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    # token-set ratio (order-insensitive)
    ta, tb = _token_set(a), _token_set(b)
    jo = len(set(ta) & set(tb)) / max(1, len(set(ta) | set(tb)))
    # substring bonus
    na, nb = _norm(a), _norm(b)
    sub = 1.0 if (na and nb and (na in nb or nb in na)) else 0.0
    # weighted blend
    return (0.6 * r1) + (0.35 * jo) + (0.05 * sub)

# -------------------------
# HTTP helpers
# -------------------------
def _fetch(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ct = r.headers.get_content_type()
            if r.status == 200 and ct in ("image/png", "image/jpeg"):
                return r.read()
    except Exception:
        pass
    return None

def _fetch_text(url: str, timeout: int = 10) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status == 200:
                data = r.read()
                enc = r.headers.get_content_charset() or "utf-8"
                return data.decode(enc, errors="replace")
    except Exception:
        pass
    return None

def _list_pngs(playlist: str, subdir: str) -> List[str]:
    # Libretro serves a simple index listing; parse anchor hrefs ending .png
    p = urllib.parse.quote(playlist)
    url = f"{BASE}/{p}/{subdir}/"
    html_text = _fetch_text(url)
    if not html_text:
        return []
    # crude but effective: find links like href="Game Name.png"
    candidates: List[str] = []
    for m in re.finditer(r'href="([^"]+\.png)"', html_text, flags=re.IGNORECASE):
        name = html.unescape(m.group(1))
        # keep only filename (strip query/paths)
        name = name.split("?")[0].split("/")[-1]
        try:
            name_decoded = urllib.parse.unquote(name)
        except Exception:
            name_decoded = name
        candidates.append(name_decoded)
    # unique preserve order
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

# -------------------------
# Image shaping
# -------------------------
def _to_256_png(img_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w)//2, (side - h)//2))
    out = canvas.resize((256, 256), Image.LANCZOS).convert("RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

# -------------------------
# Public entry
# -------------------------
def fetch_icon_256_png(
    title: str,
    playlist_name: str,
    alt_titles: Iterable[str] = (),
    confidence_threshold: float = 0.87,
    debug: bool = False
) -> Tuple[Optional[bytes], Optional[Dict[str, object]]]:
    """
    1) Try exact fetch (title and alt_titles) across Boxarts->Titles->Snaps.
    2) If not found, list directory and fuzzy-match the best filename.
    3) Return (256x256 JPEG bytes, debug_info) if a match clears the threshold, else (None, None).
    """
    candidates = _exact_title_candidates(title, alt_titles)
    subdirs: Tuple[str, ...] = ("Named_Boxarts", "Named_Titles", "Named_Snaps")

    # 1) Exact attempts
    for game in candidates:
        data, matched_sub = _try_fetch_one(playlist_name, game, subdirs)
        if data:
            if debug:
                print(f"[icons] exact match: '{game}' in '{playlist_name}' [{matched_sub}]")
            info = {"match": f"{game}.png", "score": 1.0, "source": matched_sub}
            return _to_256_png(data), info

    # 2) Fuzzy listing attempts
    best_bytes: Optional[bytes] = None
    best_score: float = 0.0
    best_name: Optional[str] = None
    best_sub: Optional[str] = None

    for sub in subdirs:
        filenames = _list_pngs(playlist_name, sub)  # e.g., ["Super Mario World.png", ...]
        if not filenames:
            continue
        for fname in filenames:
            # strip .png to compare names
            base = fname[:-4] if fname.lower().endswith(".png") else fname
            # consider title and all alts
            scores = [_ratio(title, base)] + [_ratio(alt, base) for alt in alt_titles]
            score = max(scores) if scores else 0.0
            if score > best_score:
                best_score = score
                best_name = fname
                best_sub = sub
                if best_score >= 0.995:  # early-perfect
                    break
        if best_name and best_score >= confidence_threshold:
            # fetch this file
            data = _fetch_png_by_name(playlist_name, sub, best_name)
            if data:
                if debug:
                    print(f"[icons] fuzzy match: '{best_name}' in '{playlist_name}' [{sub}] (score={best_score:.3f})")
                best_bytes = data
                break

    if best_bytes and best_score >= confidence_threshold:
        info = {"match": best_name, "score": best_score, "source": best_sub}
        return _to_256_jpeg(best_bytes), info

    if debug:
        print(f"[icons] no suitable match for '{title}' in '{playlist_name}' (threshold={confidence_threshold})")
    return None, None

# -------------------------
# Internals
# -------------------------
def _exact_title_candidates(title: str, alts: Iterable[str]) -> List[str]:
    base = [title] + list(alts)
    # also try trimmed variants without trailing parentheses
    trimmed = [_strip_parens(t) for t in base]
    out: List[str] = []
    seen = set()
    for t in base + trimmed:
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out

def _try_fetch_one(playlist: str, name: str, subdirs: Tuple[str, ...]) -> Tuple[Optional[bytes], Optional[str]]:
    p = urllib.parse.quote(playlist)
    g = urllib.parse.quote(name)
    for sub in subdirs:
        url = f"{BASE}/{p}/{sub}/{g}.png"
        data = _fetch(url)
        if data:
            return data, sub
    return None, None

def _fetch_png_by_name(playlist: str, subdir: str, filename: str) -> Optional[bytes]:
    p = urllib.parse.quote(playlist)
    fn = urllib.parse.quote(filename)
    url = f"{BASE}/{p}/{subdir}/{fn}"
    return _fetch(url)
