# packer/discovery/detect.py
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .systems import PLATFORM_EXTS, EXT_TO_PLAT, resolve_platform


def _list_roms_in_dir_for_platform(dir_path: Path, platform: str) -> List[Path]:
    exts = set(PLATFORM_EXTS.get(platform, ()))
    out: List[Path] = []
    for p in dir_path.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    return out


def _infer_platform_from_ext(p: Path) -> str | None:
    """For flat layouts: infer platform by file extension if unambiguous."""
    plats = EXT_TO_PLAT.get(p.suffix.lower())
    if not plats:
        return None
    if len(plats) == 1:
        return next(iter(plats))
    # Ambiguous ext (e.g., .bin used by multiple) — don’t guess
    return None


def discover_roms(rom_root: Path) -> List[Tuple[str, Path]]:
    """
    Discover ROMs either under <rom_root>/<platform_dir>/file
    (where platform_dir can be exact or an alias) OR directly under
    <rom_root> (flat), in which case we infer platform from extension when unambiguous.
    """
    rom_root = Path(rom_root)
    results: List[Tuple[str, Path]] = []

    if not rom_root.exists():
        return results

    # 1) Platform subdirectories (exact or alias)
    for entry in rom_root.iterdir():
        if not entry.is_dir():
            continue
        plat = resolve_platform(entry.name)
        if not plat:
            continue
        roms = _list_roms_in_dir_for_platform(entry, plat)
        if roms:
            # Optional: noisy debug here if needed
            # print(f"[discover] {entry.name} -> {plat} ({len(roms)} ROMs)")
            for r in roms:
                results.append((plat, r))

    # 2) Flat files directly in rom_root (infer by extension)
    for p in rom_root.iterdir():
        if not p.is_file():
            continue
        plat = _infer_platform_from_ext(p)
        if plat:
            results.append((plat, p))

    return results
