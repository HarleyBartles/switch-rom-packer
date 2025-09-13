from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .providers import libretro  # your existing provider, can add more later


def _platform_safe(platform: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _\-\+]", "_", platform).replace(" ", "_")


def _title_safe(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _\-\+\(\)]", "_", title).replace(" ", "_")


def _cache_icon_path(platform: str, title: str) -> Path:
    # Mirrors existing log pattern:
    # ~/.switch-rom-packer/cache/icons/<PlatformSafe>__<TitleSafe>.png
    from pathlib import Path
    cache_root = Path.home() / ".switch-rom-packer" / "cache" / "icons"
    cache_root.mkdir(parents=True, exist_ok=True)
    filename = f"{_platform_safe(platform)}__{_title_safe(title)}.png"
    return cache_root / filename


def icon_provider_search(platform: str, title: str, threshold: float = 0.87) -> Optional[Path]:
    """
    Delegate to one or more providers to try and resolve an icon.
    Currently wires into libretro provider; can add others later.
    """
    # 1) Try libretro provider if available
    try:
        p = libretro.search_icon(platform, title, threshold)
        if p:
            return Path(p)
    except Exception:
        pass

    # 2) Fallback: check for a cached file matching observed naming scheme
    p = _cache_icon_path(platform, title)
    if p.exists():
        return p

    return None


def find_icon_with_alts(
    platform: str,
    primary_title: str,
    alt_titles: List[str],
    thresholds: Tuple[float, float, float] = (0.87, 0.83, 0.80),
) -> Optional[Path]:
    """
    Try the primary title, then each alt title.
    For each title, step the threshold down until a match is found.
    """
    candidates = [primary_title] + [t for t in alt_titles if t.lower() != primary_title.lower()]

    for title in candidates:
        for thr in thresholds:
            print(f"[icons] trying '{title}' in '{platform}' (threshold={thr})")
            path = icon_provider_search(platform, title, threshold=thr)
            if path and path.exists():
                if title != primary_title:
                    print(f"[icons] matched via alt title: {title}")
                print(f"[icons] using ICON file: {path}")
                return path
    print(f"[icons] no suitable match for '{primary_title}' in '{platform}' after {len(candidates)} titles")
    return None
