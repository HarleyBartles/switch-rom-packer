from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Optional

import requests


# Cache root: ~/.switch-rom-packer/cache/icons
_CACHE_ROOT = Path.home() / ".switch-rom-packer" / "cache" / "icons"
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# Base URL for Libretro thumbnail packs
_BASE_URL = "http://thumbnails.libretro.com"


def _platform_safe(platform: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _\-\+]", "_", platform).replace(" ", "_")


def _title_safe(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _\-\+\(\)]", "_", title).replace(" ", "_")


def _icon_cache_path(platform: str, title: str) -> Path:
    """Where we save an icon for this (platform, title) in the local cache."""
    filename = f"{_platform_safe(platform)}__{_title_safe(title)}.png"
    return _CACHE_ROOT / filename


def _download_icon(url: str, dest: Path) -> bool:
    """Download icon from URL to dest. Returns True on success."""
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200 and r.content:
            dest.write_bytes(r.content)
            return True
    except Exception as e:
        print(f"[icons] download failed from {url}: {e}")
    return False


def search_icon(platform: str, title: str, threshold: float = 0.87) -> Optional[Path]:
    """
    Attempt to fetch a Libretro thumbnail PNG for this platform + title.
    Will return a local Path if found or downloaded, else None.
    """
    cache_path = _icon_cache_path(platform, title)
    if cache_path.exists():
        return cache_path

    # Remote URL layout:
    # http://thumbnails.libretro.com/<platform>/Named_Boxarts/<title>.png
    platform_url = _platform_safe(platform).replace("_", " ")
    title_norm = title.strip()

    # Try exact match first
    url = f"{_BASE_URL}/{platform_url}/Named_Boxarts/{title_norm}.png"
    if _download_icon(url, cache_path):
        return cache_path

    # If exact fails: fetch the listing, fuzzy-match titles
    try:
        list_url = f"{_BASE_URL}/{platform_url}/Named_Boxarts/"
        r = requests.get(list_url, timeout=15)
        if r.status_code == 200:
            # Extract .png filenames
            matches = re.findall(r'href="([^"]+\.png)"', r.text, re.IGNORECASE)
            if matches:
                # Drop .png extension for fuzzy matching
                names = [m[:-4] for m in matches]
                best = difflib.get_close_matches(title_norm, names, n=1, cutoff=threshold)
                if best:
                    best_name = best[0]
                    url = f"{_BASE_URL}/{platform_url}/Named_Boxarts/{best_name}.png"
                    if _download_icon(url, cache_path):
                        return cache_path
    except Exception as e:
        print(f"[icons] failed to fetch list from {platform_url}: {e}")

    return None
