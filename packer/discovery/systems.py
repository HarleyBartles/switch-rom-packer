# packer/discovery/systems.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

# ---- 1) Baseline platform -> extensions mapping ----
_DEFAULT_PLATFORM_EXTS: Dict[str, Iterable[str]] = {
    "Nintendo - Super Nintendo Entertainment System": (".smc", ".sfc"),
    "Nintendo - Nintendo Entertainment System": (".nes",),
    "Sega - Mega Drive - Genesis": (".bin", ".md", ".gen"),
    "Nintendo - Game Boy Advance": (".gba",),
    "Nintendo - Game Boy": (".gb",),
    "Nintendo - Game Boy Color": (".gbc",),
}

# ---- 2) Config file paths ----
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_ALIASES_JSON = _CONFIG_DIR / "systems_aliases.json"
_EXTS_JSON = _CONFIG_DIR / "systems_exts.json"   # optional: override/add extensions per platform


def _load_json_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[systems] Failed to load {path}: {e}")
        return {}


# ---- 3) Merge defaults + optional config overrides ----
_cfg_exts = _load_json_dict(_EXTS_JSON)
PLATFORM_EXTS: Dict[str, Iterable[str]] = dict(_DEFAULT_PLATFORM_EXTS)
for k, v in _cfg_exts.items():
    if isinstance(v, (list, tuple)):
        PLATFORM_EXTS[k] = tuple(str(x).lower() for x in v)

# Build a lowercase extension set per platform for quick checks
PLATFORM_EXTS = {plat: tuple(ext.lower() for ext in exts) for plat, exts in PLATFORM_EXTS.items()}

# Reverse map ext -> set(platforms)
EXT_TO_PLAT: Dict[str, set[str]] = {}
for plat, exts in PLATFORM_EXTS.items():
    for ext in exts:
        EXT_TO_PLAT.setdefault(ext.lower(), set()).add(plat)

# ---- 4) Aliases (case-insensitive) ----
# Built-ins, can be extended via config/systems_aliases.json
_DEFAULT_ALIASES = {
    "snes": "Nintendo - Super Nintendo Entertainment System",
    "super nintendo": "Nintendo - Super Nintendo Entertainment System",
    "super nintendo entertainment system": "Nintendo - Super Nintendo Entertainment System",

    "nes": "Nintendo - Nintendo Entertainment System",

    "genesis": "Sega - Mega Drive - Genesis",
    "mega drive": "Sega - Mega Drive - Genesis",
    "megadrive": "Sega - Mega Drive - Genesis",

    "gba": "Nintendo - Game Boy Advance",
    "game boy advance": "Nintendo - Game Boy Advance",

    "gb": "Nintendo - Game Boy",
    "game boy": "Nintendo - Game Boy",

    "gbc": "Nintendo - Game Boy Color",
    "game boy color": "Nintendo - Game Boy Color",
}

_alias_overrides = _load_json_dict(_ALIASES_JSON)
# Normalize to lowercase keys
ALIASES: Dict[str, str] = dict(_DEFAULT_ALIASES)
for k, v in _alias_overrides.items():
    if isinstance(k, str) and isinstance(v, str):
        ALIASES[k.lower()] = v


def resolve_platform(folder_name: str) -> Optional[str]:
    """
    Resolve a folder name to a canonical platform:
    - exact match (case-insensitive) against PLATFORM_EXTS keys
    - alias match via ALIASES (case-insensitive)
    Returns canonical platform or None.
    """
    name = folder_name.strip().lower()

    # Exact (case-insensitive) match against known platform names
    for plat in PLATFORM_EXTS.keys():
        if plat.lower() == name:
            return plat

    # Alias map
    return ALIASES.get(name)
