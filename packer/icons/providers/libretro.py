from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.parse import unquote

import requests

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    import difflib
    _HAS_RAPIDFUZZ = False

from PIL import Image
from io import BytesIO

# Cache root: ~/.switch-rom-packer/cache/icons
_CACHE_ROOT = Path.home() / ".switch-rom-packer" / "cache" / "icons"
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# Base URL for Libretro thumbnail packs
_BASE_URL = "http://thumbnails.libretro.com"

# Search order across Libretro packs (prefer clean system logos)
_SUBDIRS = ["Named_Logos", "Named_Boxarts", "Named_Titles", "Named_Snaps"]

# Articles to ignore at the start of titles
_ARTICLES = {"the", "a", "an"}

# Optional alias expansions for famous edge-cases
_ALIASES = {
    "super mario all stars": [
        "super mario all-stars + super mario world",
        "super mario allstars",
    ],
}

# Region mapping: common ROM tags -> preferred label fragments used by Libretro
_REGION_MAP = {
    "u": ["(USA)"],
    "usa": ["(USA)"],
    "e": ["(Europe)"],
    "eu": ["(Europe)"],
    "europe": ["(Europe)"],
    "j": ["(Japan)"],
    "jp": ["(Japan)"],
    "japan": ["(Japan)"],
    "w": ["(World)"],
    "world": ["(World)"],
    "a": ["(Australia)", "(Oceania)"],
    "au": ["(Australia)", "(Oceania)"],
    "k": ["(Korea)"],
    "kr": ["(Korea)"],
    "b": ["(Brazil)"],
    "br": ["(Brazil)"],
    # sometimes present mixed labels
    "usaeurope": ["(USA, Europe)"],
    "usa/europe": ["(USA, Europe)"],
}

# Secondary fallback ordering if nothing matches the preferred region explicitly
_FALLBACK_BY_PRIMARY = {
    "(USA)": ["(World)", "(USA, Europe)", "(Europe)", "(Japan)"],
    "(Europe)": ["(World)", "(USA, Europe)", "(USA)", "(Japan)"],
    "(Japan)": ["(World)", "(USA)", "(Europe)"],
    "(World)": ["(USA)", "(Europe)", "(Japan)"],
}


def _platform_url(platform: str) -> str:
    p = re.sub(r"[^A-Za-z0-9 _\-\+]", " ", platform)
    p = re.sub(r"\s+", " ", p).strip()
    return p


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_PARENS_RE = re.compile(r"(\([^)]*\)|\[[^\]]*\])")   # remove (...) and [...]
_PLUS_RE   = re.compile(r"\s*\+\s*")


def _normalize_title(s: str) -> str:
    s = _strip_accents(s)
    s = s.lower()
    s = _PARENS_RE.sub(" ", s)
    s = _PLUS_RE.sub(" ", s)
    s = s.replace("-", " ").replace("_", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    parts = s.split()
    if parts and parts[0] in _ARTICLES:
        parts = parts[1:]
    return " ".join(parts)


def _expand_aliases(query: str) -> List[str]:
    norm = _normalize_title(query)
    extras = []
    for key, vals in _ALIASES.items():
        if key in norm:
            extras.extend(vals)
    return extras


def _sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _\-\+\(\)]", "_", s).replace(" ", "_")


def _icon_cache_path(platform: str, source_name: str) -> Path:
    # Cache by actual Libretro basename (no extension) to avoid poisoning
    platform_safe = _sanitize(platform)
    source_safe = _sanitize(source_name)
    filename = f"{platform_safe}__{source_safe}.jpg"
    return _CACHE_ROOT / filename


def _download_bytes(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print(f"[icons] download failed from {url}: {e}")
    return None


def _cover_fit_center_crop_to_square(img: Image.Image, size: int = 256) -> Image.Image:
    """
    Old behavior: scale to cover then center-crop to exact square.
    Keeps image edge-to-edge but can cut off content.
    """
    w, h = img.size
    if w == 0 or h == 0:
        return img.convert("RGB").resize((size, size))
    scale = max(size / w, size / h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - size) // 2
    top = (new_h - size) // 2
    right = left + size
    bottom = top + size
    return img.crop((left, top, right, bottom)).convert("RGB")


def _letterbox_fit_to_square(img: Image.Image, size: int = 256, bg=(0, 0, 0)) -> Image.Image:
    """
    New default: preserve aspect ratio and pad to exact square (letterboxing).
    No cropping; full art is visible with blank bars where needed.
    """
    img = img.convert("RGB")
    # scale to fit within size x size
    w, h = img.size
    if w == 0 or h == 0:
        return Image.new("RGB", (size, size), bg)
    # thumbnail keeps aspect ratio and ensures both dims <= size
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), bg)
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def _png_bytes_to_jpeg_file(
    png_bytes: bytes,
    dest: Path,
    *,
    normalize_method: str = "letterbox",  # "letterbox" (default) or "crop"
    bg=(0, 0, 0),
) -> bool:
    """
    Convert the downloaded PNG bytes into a 256x256 RGB JPEG on disk.
    normalize_method:
      - "letterbox": preserve aspect ratio, pad to square with bg color.
      - "crop": cover-fit then center-crop to square (legacy behavior).
    """
    try:
        img = Image.open(BytesIO(png_bytes))
        if normalize_method == "crop":
            norm = _cover_fit_center_crop_to_square(img, 256)
        else:
            norm = _letterbox_fit_to_square(img, 256, bg)
        dest.parent.mkdir(parents=True, exist_ok=True)
        norm.save(dest, format="JPEG", quality=92)
        return True
    except Exception as e:
        print(f"[icons] PNG->JPEG convert failed for {dest.name}: {e}")
        return False


def _list_png_names(platform_url: str, subdir: str) -> List[str]:
    list_url = f"{_BASE_URL}/{platform_url}/{subdir}/"
    try:
        r = requests.get(list_url, timeout=20)
        if r.status_code == 200:
            raw = re.findall(r'href="([^"]+\.png)"', r.text, re.IGNORECASE)
            return [unquote(n)[:-4] for n in raw]  # unquote %20 etc., drop .png
    except Exception as e:
        print(f"[icons] failed to fetch list from {list_url}: {e}")
    return []


def _score_best(query: str, candidates: List[str]) -> List[Tuple[str, float, str]]:
    qn = _normalize_title(query)
    results: List[Tuple[str, float, str]] = []
    if _HAS_RAPIDFUZZ:
        for raw in candidates:
            cn = _normalize_title(raw)
            s1 = fuzz.token_set_ratio(qn, cn)
            s2 = fuzz.WRatio(qn, cn)
            score = max(s1, s2) / 100.0
            results.append((raw, score, cn))
        results.sort(key=lambda x: x[1], reverse=True)
    else:
        norm_map = [(raw, _normalize_title(raw)) for raw in candidates]
        for raw, cn in norm_map:
            score = difflib.SequenceMatcher(None, qn, cn).ratio()
            results.append((raw, score, cn))
        results.sort(key=lambda x: x[1], reverse=True)
    return results


def _extract_region_hints(title: str, source_name_hint: Optional[str]) -> List[str]:
    """
    From '(U)', '(USA)', '(E)', '(J)', etc. choose preferred Libretro label fragments.
    Returns a priority list like ['(USA)', '(World)', '(USA, Europe)', '(Europe)'].
    """
    tags: List[str] = []
    hay = " ".join([title or "", source_name_hint or ""])
    for tag in re.findall(r"\(([A-Za-z0-9 ,\/\-]+)\)", hay):
        t = tag.strip().lower().replace(" ", "")
        tags.append(t)

    preferred: List[str] = []
    for t in tags:
        for key, labels in _REGION_MAP.items():
            if key in t:
                for lab in labels:
                    if lab not in preferred:
                        preferred.append(lab)

    if preferred:
        primary = preferred[0]
        for fb in _FALLBACK_BY_PRIMARY.get(primary, []):
            if fb not in preferred:
                preferred.append(fb)

    return preferred


def _prefer_region_among_ties(
    ranked: List[Tuple[str, float, str]],
    preferred_labels: List[str],
    eps: float = 0.02
) -> Tuple[str, float, str]:
    if not ranked:
        raise ValueError("ranked must be non-empty")
    best_score = ranked[0][1]
    near = [r for r in ranked if best_score - r[1] <= eps]
    if len(near) == 1 or not preferred_labels:
        return ranked[0]
    for label in preferred_labels:
        for r in near:
            if label.lower() in r[0].lower():
                return r
    return ranked[0]


def _try_exact_variants(platform_url: str, subdir: str, title: str, preferred_labels: List[str]) -> Optional[Tuple[str, bytes]]:
    variants: List[str] = []
    base = title.strip()
    base_no_paren = _PARENS_RE.sub("", base).strip()
    base_no_paren = re.sub(r"\s+", " ", base_no_paren)

    # Region-biased first
    for lab in preferred_labels:
        lab_clean = lab.strip("()")
        v = f"{base_no_paren} ({lab_clean})"
        variants.append(v)

    # Generic variants
    variants.extend([base, base.replace(" - ", " "), base.replace("-", " "), base_no_paren])
    variants.extend(_expand_aliases(base))

    seen = set()
    for v in variants:
        v = re.sub(r"\s+", " ", v).strip()
        if not v or v in seen:
            continue
        seen.add(v)
        url = f"{_BASE_URL}/{platform_url}/{subdir}/{v}.png"
        data = _download_bytes(url)
        if data:
            return (v, data)
    return None


def search_icon(
    platform: str,
    title: str,
    threshold: float = 0.80,
    debug: bool = True,
    *,
    source_name_hint: Optional[str] = None,
    normalize_method: str = "letterbox",  # "letterbox" (default) or "crop"
    bg=(0, 0, 0),
    subdirs: Optional[list[str]] = None,  # <--- new
) -> Optional[Path]:
    """
    Attempt to fetch a Libretro thumbnail for this platform + title.
    Returns a local **JPEG** Path if found/converted, else None.

    - Attempts exact matches first (region-biased).
    - Then fuzzy matches all candidates, and prefers near-ties with the preferred region.
    - Caches by Libretro source name to avoid poisoning.
    - Will *not* return a cached non-preferred region if a preferred-region icon is available.
    - Normalizes icons to 256x256 using 'letterbox' (default) or 'crop'.
    """
    platform_url = _platform_url(platform)
    preferred_labels = _extract_region_hints(title, source_name_hint)
    if debug and preferred_labels:
        print(f"[icons] region preference: {preferred_labels}")

    # choose search order
    dirs = subdirs if subdirs is not None else _SUBDIRS

    # 1) Exact filename variants across subdirs (region-biased first)
    for subdir in dirs:
        hit = _try_exact_variants(platform_url, subdir, title, preferred_labels)
        if hit:
            source_name, data = hit
            cache_jpg = _icon_cache_path(platform, source_name)
            if cache_jpg.exists():
                return cache_jpg
            if _png_bytes_to_jpeg_file(
                data, cache_jpg, normalize_method=normalize_method, bg=bg
            ):
                if debug:
                    print(f"[icons] exact icon hit in {subdir} for '{title}' -> '{source_name}'")
                return cache_jpg

    # 2) Fuzzy match over listings (search order controls priority)
    for subdir in dirs:
        names = _list_png_names(platform_url, subdir)
        if not names:
            continue

        ranked = _score_best(title, names)
        if not ranked:
            continue

        if debug:
            for raw, sc, cn in ranked[:5]:
                print(f"[icons] cand[{subdir}]: {raw} | norm='{cn}' | score={sc:.3f}")

        # prefer region among near ties
        best_raw, best_sc, _ = _prefer_region_among_ties(ranked, preferred_labels, eps=0.02)

        if preferred_labels:
            for label in preferred_labels:
                cand = next((r for r in ranked if label.lower() in r[0].lower()), None)
                if cand and (best_sc - cand[1]) <= 0.02:
                    best_raw, best_sc = cand[0], cand[1]
                    break

        if best_sc >= threshold:
            preferred_cache = _icon_cache_path(platform, best_raw)
            if preferred_cache.exists():
                if debug:
                    print(f"[icons] using cached icon for '{best_raw}'")
                return preferred_cache

            url = f"{_BASE_URL}/{platform_url}/{subdir}/{best_raw}.png"
            data = _download_bytes(url)
            if data and _png_bytes_to_jpeg_file(
                data, preferred_cache, normalize_method=normalize_method, bg=bg
            ):
                if debug:
                    print(
                        f"[icons] matched '{title}' -> '{best_raw}' in {subdir} (score={best_sc:.3f})"
                    )
                return preferred_cache

    return None
