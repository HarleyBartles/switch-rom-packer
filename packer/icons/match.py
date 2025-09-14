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
    cache_root = Path.home() / ".switch-rom-packer" / "cache" / "icons"
    cache_root.mkdir(parents=True, exist_ok=True)
    filename = f"{_platform_safe(platform)}__{_title_safe(title)}.png"
    return cache_root / filename


def icon_provider_search(
    platform: str,
    title: str,
    threshold: float = 0.87,
    *,
    source_name_hint: Optional[str] = None,
    subdirs: Optional[list[str]] = None,
) -> Optional[Path]:
    """
    Delegate to one or more providers to try and resolve an icon.
    Currently wires into libretro provider; can add others later.
    subdirs: override search order (e.g. logos vs boxarts).
    """
    # 1) Try libretro provider if available
    try:
        p = libretro.search_icon(
            platform,
            title,
            threshold=threshold,
            source_name_hint=source_name_hint,  # <--- pass ROM filename here
            subdirs=subdirs,                    # <--- new arg
        )
        if p:
            return Path(p)
    except Exception as e:
        print(f"[icons] libretro provider failed for {title}: {e}")

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
    *,
    source_name_hint: Optional[str] = None,
    preference: str = "logos",
) -> Optional[Path]:
    """
    Try the primary title, then each alt title.
    For each title, step the threshold down until a match is found.

    preference:
        - "logos"   -> ["Named_Logos", "Named_Titles", "Named_Boxarts", "Named_Snaps"]
        - "boxarts" -> ["Named_Boxarts", "Named_Titles", "Named_Logos", "Named_Snaps"]
    """
    if preference == "boxarts":
        subdirs = ["Named_Boxarts", "Named_Titles", "Named_Logos", "Named_Snaps"]
    else:
        subdirs = ["Named_Logos", "Named_Titles", "Named_Boxarts", "Named_Snaps"]

    candidates = [primary_title] + [
        t for t in alt_titles if t.lower() != primary_title.lower()
    ]

    for title in candidates:
        for thr in thresholds:
            print(f"[icons] trying '{title}' in '{platform}' (threshold={thr}) [{preference}]")
            path = icon_provider_search(
                platform,
                title,
                threshold=thr,
                source_name_hint=source_name_hint,
                subdirs=subdirs,   # <-- forward preference
            )
            if path and path.exists():
                if title != primary_title:
                    print(f"[icons] matched via alt title: {title}")
                print(f"[icons] using ICON file: {path}")
                return path

    print(
        f"[icons] no suitable match for '{primary_title}' in '{platform}' "
        f"after {len(candidates)} titles [{preference}]"
    )
    return None
