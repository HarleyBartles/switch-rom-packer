# packer/system_detect.py
from __future__ import annotations
from pathlib import Path
from typing import Optional

# Canonical Libretro thumbnails folder names (destination)
LR = {
    # Nintendo
    "NES": "Nintendo - Nintendo Entertainment System",
    "FDS": "Nintendo - Family Computer Disk System",
    "SNES": "Nintendo - Super Nintendo Entertainment System",
    "GB": "Nintendo - Game Boy",
    "GBC": "Nintendo - Game Boy Color",
    "GBA": "Nintendo - Game Boy Advance",
    "VB": "Nintendo - Virtual Boy",
    "N64": "Nintendo - Nintendo 64",
    "N64DD": "Nintendo - Nintendo 64DD",
    "NDS": "Nintendo - Nintendo DS",
    "NDSi": "Nintendo - Nintendo DSi",
    "3DS": "Nintendo - Nintendo 3DS",
    "SATELLAVIEW": "Nintendo - Satellaview",
    "SUFAMI": "Nintendo - Sufami Turbo",
    "POKEMINI": "Nintendo - Pokemon Mini",
    "GC": "Nintendo - GameCube",
    "WII": "Nintendo - Wii",
    "WIIU": "Nintendo - Wii U",

    # Sega
    "SG1000": "Sega - SG-1000",
    "SMS": "Sega - Master System - Mark III",
    "GG": "Sega - Game Gear",
    "MD": "Sega - Mega Drive - Genesis",
    "SEGA_CD": "Sega - Mega-CD - Sega CD",
    "32X": "Sega - 32X",
    "SATURN": "Sega - Saturn",
    "DREAMCAST": "Sega - Dreamcast",
    "NAOMI": "Sega - Naomi",
    "NAOMI2": "Sega - Naomi 2",
    "PICO": "Sega - PICO",

    # Sony
    "PSX": "Sony - PlayStation",
    "PS2": "Sony - PlayStation 2",
    "PSP": "Sony - PlayStation Portable",
    "PS3": "Sony - PlayStation 3",

    # SNK
    "NEOGEO": "SNK - Neo Geo",
    "NEOGEO_CD": "SNK - Neo Geo CD",
    "NGP": "SNK - Neo Geo Pocket",
    "NGPC": "SNK - Neo Geo Pocket Color",

    # NEC
    "PCE": "NEC - PC Engine - TurboGrafx 16",
    "SUPERGRAFX": "NEC - PC Engine SuperGrafx",
    "PCE_CD": "NEC - PC Engine CD - TurboGrafx-CD",
    "PCFX": "NEC - PC-FX",

    # Atari / others
    "A26": "Atari - 2600",
    "A52": "Atari - 5200",
    "A78": "Atari - 7800",
    "LYNX": "Atari - Lynx",
    "VECTREX": "GCE - Vectrex",

    # Commodore (optional micros)
    "C64": "Commodore - 64",
    "AMIGA": "Commodore - Amiga",
    "CD32": "Commodore - CD32",
    "CDTV": "Commodore - CDTV",
    "PET": "Commodore - PET",
    "PLUS4": "Commodore - Plus-4",
    "VIC20": "Commodore - VIC-20",
}

# Primary extension heuristics (lowercase)
EXT_MAP = {
    # Nintendo
    ".nes": "NES",
    ".fds": "FDS",
    ".sfc": "SNES", ".smc": "SNES",
    ".gb": "GB",
    ".gbc": "GBC",
    ".gba": "GBA",
    ".vb": "VB",
    ".z64": "N64", ".n64": "N64", ".v64": "N64",
    ".ndd": "N64DD",
    ".nds": "NDS",
    ".dsi": "NDSi",
    ".3ds": "3DS", ".cci": "3DS", ".cxi": "3DS",
    ".bs": "SATELLAVIEW",
    ".st": "SUFAMI",
    ".min": "POKEMINI",
    ".gcm": "GC", ".iso": None,  # .iso handled later by hints
    ".wad": "WII",
    ".wud": "WIIU", ".wux": "WIIU",

    # Sega
    ".sg": "SG1000",
    ".sms": "SMS",
    ".gg": "GG",
    ".md": "MD", ".bin": None, ".gen": "MD", ".smd": "MD",
    ".chd": None, ".cue": None,  # disambiguate later
    ".32x": "32X",
    ".cdi": "DREAMCAST", ".gdi": "DREAMCAST",
    ".naomi": "NAOMI",
    ".pico": "PICO",

    # Sony
    ".m3u": "PSX",  # playlists
    ".pbp": "PSX",  # eboots (PSX or PSP) — prefer PSX here, PSP handled via hints
    ".chd_psx": "PSX",  # helper if you rename; generic .chd handled later
    ".iso_ps2": "PS2", ".chd_ps2": "PS2",
    ".iso_psp": "PSP", ".cso": "PSP", ".pbp_psp": "PSP",

    # SNK / NEC
    ".ngp": "NGP", ".ngc": "NGPC", ".npc": "NGPC",
    ".pce": "PCE", ".sgx": "SUPERGRAFX",

    # Atari / others
    ".a26": "A26", ".a52": "A52", ".a78": "A78", ".lnx": "LYNX", ".vec": "VECTREX",

    # Commodore
    ".d64": "C64", ".t64": "C64", ".prg": "C64",
    ".adf": "AMIGA", ".ipf": "AMIGA",
}

# Folder/name hints to disambiguate ambiguous containers (lowercase substrings)
HINTS = [
    ("neogeo", "NEOGEO"),
    ("neo-geo", "NEOGEO"),
    ("naomi2", "NAOMI2"),
    ("naomi 2", "NAOMI2"),
    ("naomi", "NAOMI"),
    ("pc engine cd", "PCE_CD"),
    ("turbografx-cd", "PCE_CD"),
    ("turbocd", "PCE_CD"),
    ("saturn", "SATURN"),
    ("sega cd", "SEGA_CD"),
    ("mega-cd", "SEGA_CD"),
    ("megacd", "SEGA_CD"),
    ("playstation 2", "PS2"),
    ("ps2", "PS2"),
    ("psp", "PSP"),
    ("dreamcast", "DREAMCAST"),
    ("cd32", "CD32"),
    ("cdtv", "CDTV"),
]

def _read_chunk(p: Path, n: int, offset: int = 0) -> bytes:
    with p.open("rb") as f:
        if offset:
            f.seek(offset)
        return f.read(n)

def _probe_magic(p: Path, ext: str) -> Optional[str]:
    """Lightweight magic checks to rescue ambiguous cases."""
    try:
        data = _read_chunk(p, 0x200, 0)
    except Exception:
        return None

    # NES: iNES header "NES\x1A"
    if data.startswith(b"NES\x1A"):
        return "NES"

    # GBA: 'AGB' often appears in header region
    if ext == ".gba" or b"AGB" in data[:0xC0]:
        return "GBA"

    # NDS: "NTR" or "NDS" near start
    if ext == ".nds" or b"NTR" in data[:0x40] or b"NDS" in data[:0x40]:
        return "NDS"

    # Mega Drive: "SEGA" string in header blob
    if b"SEGA" in data:
        return "MD"

    return None

def _apply_hints(p: Path) -> Optional[str]:
    s = str(p).lower()
    for needle, syscode in HINTS:
        if needle in s:
            return syscode
    return None

def detect_system_code(rom_path: Path) -> Optional[str]:
    """
    Returns an internal system code (keys of LR) or None if unknown.
    Strategy:
      1) Extension-based mapping (fast path)
      2) Quick magic probe to disambiguate some overlaps
      3) Folder/name hints for tricky multi-disc & arcade/zip cases
    """
    name = rom_path.name.lower()
    ext = rom_path.suffix.lower()

    # Obvious extensions first
    code = EXT_MAP.get(ext)
    if code:
        return code

    # Cue/bin/iso/chd/zip need hints or magic
    if ext == ".cue":
        hinted = _apply_hints(rom_path)
        return hinted or "PSX"  # safe default
    if ext == ".bin":
        magic = _probe_magic(rom_path, ext)
        return magic or _apply_hints(rom_path) or "MD"
    if ext == ".iso":
        hinted = _apply_hints(rom_path)
        return hinted or "PSX"
    if ext == ".chd":
        hinted = _apply_hints(rom_path)
        return hinted or "PSX"
    if ext == ".zip":
        hinted = _apply_hints(rom_path)
        if hinted:
            return hinted
        if "neogeo" in name:
            return "NEOGEO"
        return None

    magic = _probe_magic(rom_path, ext)
    return magic

def detect_libretro_folder(rom_path: Path) -> str:
    code = detect_system_code(rom_path)
    if code and code in LR:
        return LR[code]
    return "Unknown"
