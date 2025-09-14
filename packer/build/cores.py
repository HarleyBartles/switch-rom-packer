# packer/build/cores.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List

# YAML is preferred for the packaged cores.yml, but we degrade gracefully if unavailable.
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

# ---------- Canonicalization / aliasing ----------

_CANONICAL: Dict[str, str] = {
    "snes": "Nintendo - Super Nintendo Entertainment System",
    "super nintendo": "Nintendo - Super Nintendo Entertainment System",
    "super famicom": "Nintendo - Super Nintendo Entertainment System",

    "nes": "Nintendo - Nintendo Entertainment System",

    "gb": "Nintendo - Game Boy",
    "game boy": "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "game boy color": "Nintendo - Game Boy Color",
    "gba": "Nintendo - Game Boy Advance",

    "n64": "Nintendo - Nintendo 64",
    "ds": "Nintendo - Nintendo DS",
    "3ds": "Nintendo - 3DS",
    "virtual boy": "Nintendo - Virtual Boy",

    "genesis": "Sega - Mega Drive - Genesis",
    "mega drive": "Sega - Mega Drive - Genesis",
    "md": "Sega - Mega Drive - Genesis",
    "sms": "Sega - Master System - Mark III",
    "master system": "Sega - Master System - Mark III",
    "game gear": "Sega - Game Gear",
    "32x": "Sega - 32X",
    "saturn": "Sega - Saturn",
    "dreamcast": "Sega - Dreamcast",

    "ps1": "Sony - PlayStation",
    "playstation": "Sony - PlayStation",
    "psp": "Sony - PSP",

    "pc engine": "NEC - PC Engine - TurboGrafx 16",
    "turbografx-16": "NEC - PC Engine - TurboGrafx 16",
    "tg16": "NEC - PC Engine - TurboGrafx 16",
    "pc engine cd": "NEC - PC Engine CD - TurboGrafx-CD",
    "turbografx-cd": "NEC - PC Engine CD - TurboGrafx-CD",

    "ngpc": "SNK - Neo Geo Pocket Color",
    "neo geo pocket color": "SNK - Neo Geo Pocket Color",
    "wonderswan": "Bandai - WonderSwan Color",
    "ws": "Bandai - WonderSwan Color",

    "atari 2600": "Atari - 2600",
    "atari 7800": "Atari - 7800",
    "lynx": "Atari - Lynx",

    "msx": "MSX",
    "3do": "3DO",
    "c64": "Commodore - C64",
    "dos": "DOS",
    "scummvm": "ScummVM",

    "fbneo": "Arcade - FBNeo",
    "mame2003-plus": "Arcade - MAME 2003-Plus",
    "mame 2003 plus": "Arcade - MAME 2003-Plus",
    "mame2010": "Arcade - MAME 2010",
}

def canonical_platform(libretro_platform_or_alias: str) -> str:
    """
    Convert common aliases/short names to canonical Libretro platform names.
    Falls back to the input string untouched if unknown.
    """
    key = libretro_platform_or_alias.strip().casefold()
    return _CANONICAL.get(key, libretro_platform_or_alias)

# ---------- Core map loading & resolution ----------

@dataclass
class CoreMap:
    default_core_dir: str
    platforms: Dict[str, List[str]]

# Built-in minimal fallback (only the most common systems).
_BUILTIN_COREMAP = CoreMap(
    default_core_dir="sdmc:/switch/retroarch/cores",
    platforms={
        "Nintendo - Super Nintendo Entertainment System": [
            "snes9x2010_libretro_libnx.so",
            "snes9x_libretro_libnx.so",
        ],
        "Nintendo - Nintendo Entertainment System": [
            "mesen_libretro_libnx.so",
            "fceumm_libretro_libnx.so",
        ],
        "Nintendo - Game Boy": ["gambatte_libretro_libnx.so"],
        "Nintendo - Game Boy Advance": ["mgba_libretro_libnx.so"],
        "Sega - Mega Drive - Genesis": ["genesis_plus_gx_libretro_libnx.so"],
    },
)

def _parse_core_map_dict(data: dict, *, source: str) -> CoreMap:
    if not isinstance(data, dict):
        raise SystemExit(f"[packer] cores.yml at {source} must be a mapping.")
    default_dir = data.get("default_core_dir") or "sdmc:/switch/retroarch/cores"
    platforms = data.get("platforms") or {}
    if not isinstance(platforms, dict):
        raise SystemExit(f"[packer] cores.yml at {source} -> 'platforms' must be a mapping.")
    norm_platforms: Dict[str, List[str]] = {}
    for k, v in platforms.items():
        if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
            raise SystemExit(f"[packer] cores.yml at {source} -> platform '{k}' must map to a list of strings.")
        canon = canonical_platform(str(k))
        norm_platforms[canon] = list(v)
    return CoreMap(default_core_dir=str(default_dir), platforms=norm_platforms)

def load_core_map(custom_path: Optional[Path]) -> CoreMap:
    """
    Load a core map:
      - If custom_path provided, load that YAML.
      - Else, try repo default packer/data/cores.yml.
      - Else, fall back to built-in defaults.
    """
    if custom_path:
        if yaml is None:
            raise SystemExit("[packer] PyYAML is required for --core-map. Install pyyaml.")
        if not custom_path.exists():
            raise SystemExit(f"[packer] --core-map file not found: {custom_path}")
        data = yaml.safe_load(custom_path.read_text(encoding="utf-8")) or {}
        return _parse_core_map_dict(data, source=str(custom_path))

    # Default cores.yml in repo: packer/data/cores.yml
    default_path = Path(__file__).resolve().parents[1] / "data" / "cores.yml"
    if yaml is not None and default_path.exists():
        data = yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
        return _parse_core_map_dict(data, source=str(default_path))

    # Fallback
    return _BUILTIN_COREMAP

def resolve_core_so(platform_name: str, core_map: CoreMap) -> Optional[str]:
    """
    Returns absolute core path like:
      sdmc:/switch/retroarch/cores/snes9x2010_libretro_libnx.so
    Picks the first listed core for the (canonical) platform. Does not check SD existence.
    """
    canonical = canonical_platform(platform_name)
    candidates = core_map.platforms.get(canonical) or core_map.platforms.get(platform_name)
    if not candidates:
        return None
    return f'{core_map.default_core_dir.rstrip("/")}/{candidates[0]}'
