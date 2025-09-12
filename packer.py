#!/usr/bin/env python3
"""
packer.py
----------
Build Switch stub NROs from ROM files.

- Default: one NRO per ROM (each mode).
- Bundle: one NRO with all ROMs, named with --bundle-name.
- PSX: .cue pulls in its referenced .bin tracks; lone .bin is upgraded to PSX if a sibling .cue references it.

Destination on device:
  SD:/roms/<platform>/<romfile>

Supported platform folders:
  3ds, 32x, gb, gbc, gba, nds, psp, psx, smd, snes, nes, sms, gg, tg, sdc
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Set

ROOT = Path(__file__).parent.resolve()
STUB_DIR = ROOT / "stub"
ROMFS_DIR = STUB_DIR / "romfs"
OUT_DIR = ROOT / "out"

# Recognized ROM extensions (lowercase, no dot)
ROM_EXTS = {
    "smc", "sfc", "nes", "bin",
    "gba", "gb", "gbc",
    "gen", "md", "sms", "pce", "smd",
    "fig", "swc",
    "z64", "n64", "v64",
    "gg", "nds", "3ds",
    "iso", "cso", "cue", "gdi", "chd",
    "32x"
}

# Map extensions → platform folder names
PLATFORM_MAP = {
    # Nintendo
    "smc": "snes", "sfc": "snes", "swc": "snes", "fig": "snes",
    "nes": "nes",
    "gb": "gb",
    "gbc": "gbc",
    "gba": "gba",
    "nds": "nds",
    "3ds": "3ds",

    # Sega
    "gen": "smd", "md": "smd", "smd": "smd",     # Genesis/Mega Drive
    "32x": "32x",
    "sms": "sms",       # Master System
    "gg": "gg",         # Game Gear
    "pce": "tg", "tg": "tg",  # TurboGrafx-16 / PC Engine
    "gdi": "sdc", "chd": "sdc",  # Dreamcast

    # Sony
    "iso": "psp", "cso": "psp",   # PSP
    "cue": "psx",                 # PSX (driver; brings .bin tracks)
    # NOTE: plain ".bin" stays mapped by ext unless upgraded by a cue scan
}

def collect_roms(paths: List[str]) -> List[Path]:
    roms: List[Path] = []
    for raw in paths:
        p = Path(raw).resolve()
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.is_file() and f.suffix.lower().lstrip(".") in ROM_EXTS:
                    roms.append(f)
        elif p.is_file() and p.suffix.lower().lstrip(".") in ROM_EXTS:
            roms.append(p)
        else:
            if not p.exists():
                print(f"⚠️ Skipping non-existent: {p}")
    return roms

# --- PSX helpers -------------------------------------------------------------

def parse_cue(cue_path: Path) -> List[Path]:
    """
    Parse a .cue file and return a list of referenced files (usually .bin),
    resolved relative to the .cue location. Very lightweight parsing.
    """
    refs: List[Path] = []
    try:
        text = cue_path.read_text(errors="ignore")
    except Exception:
        return refs
    # FILE "xxx.bin" BINARY
    for m in re.finditer(r'(?i)^\s*FILE\s+"([^"]+)"', text, flags=re.MULTILINE):
        ref = m.group(1)
        # normalize separators, resolve relative to cue
        ref_path = (cue_path.parent / ref).resolve()
        refs.append(ref_path)
    return refs

def index_cues(roms: List[Path]) -> Dict[Path, List[Path]]:
    """Return mapping: cue_path -> [referenced track paths] (existing only)."""
    cues: Dict[Path, List[Path]] = {}
    for p in roms:
        if p.suffix.lower() == ".cue":
            tracks = parse_cue(p)
            # keep only tracks that actually exist
            tracks = [t for t in tracks if t.exists()]
            if tracks:
                cues[p] = tracks
            else:
                # even if no tracks found, still treat cue as primary PSX artifact
                cues[p] = []
    return cues

def find_cue_for_bin(bin_path: Path) -> Path | None:
    """
    Try to find a sibling .cue that references this .bin.
    Search all .cue files in the same directory and check FILE entries.
    """
    dirpath = bin_path.parent
    for cue in dirpath.glob("*.cue"):
        tracks = parse_cue(cue)
        for t in tracks:
            if t.resolve() == bin_path.resolve():
                return cue
    # fallback: stem match (game.bin ↔ game.cue)
    guess = dirpath / (bin_path.stem + ".cue")
    if guess.exists():
        return guess
    return None

# --- Platform / output helpers ----------------------------------------------

def infer_platform(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return PLATFORM_MAP.get(ext, "unknown")

def sanitize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name or "output"

# --- RomFS + build steps -----------------------------------------------------

def write_romfs_with_manifest(items: List[Tuple[Path, str]]):
    if ROMFS_DIR.exists():
        shutil.rmtree(ROMFS_DIR)
    ROMFS_DIR.mkdir(parents=True)

    seen: Set[str] = set()
    lines: List[str] = []

    for rp, platform in items:
        # De-duplicate by absolute path to avoid copying same track twice
        key = str(rp.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)

        dest = ROMFS_DIR / rp.name
        shutil.copy2(rp, dest)
        lines.append(f"{platform}\t{rp.name}")
        print(f"📦 Injected {rp.name}  → platform: {platform}")

    (ROMFS_DIR / "filelist.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"📝 Wrote romfs/filelist.txt with {len(lines)} entr{'y' if len(lines)==1 else 'ies'}.")

def build_stub(out_name: str, title: str, icon_path: Path | None = None):
    """
    Builds the stub with a dynamic hbmenu title (and optional icon).
    - out_name: filename for the resulting .nro in ./out/
    - title: NACP title shown in hbmenu
    - icon_path: optional path to a .png/.jpg to use as hbmenu icon
    """
    print("🔨 Building stub...")
    # Clean first
    subprocess.run(["make", "clean"], cwd=STUB_DIR, check=True)

    # Prepare make args with dynamic title/author/version
    make_cmd = [
        "make",
        f"APP_TITLE={title}",
        "APP_AUTHOR=switch-rom-packer",
        "APP_VERSION=0.1.0",
    ]

    # Optional icon support — switch_rules expects the icon to be in stub/
    if icon_path:
        icon_path = icon_path.resolve()
        if icon_path.exists():
            dest_icon = STUB_DIR / icon_path.name
            if dest_icon.resolve() != icon_path:
                shutil.copy2(icon_path, dest_icon)
            make_cmd.append(f"ICON={dest_icon.name}")

    subprocess.run(make_cmd, cwd=STUB_DIR, check=True)

    OUT_DIR.mkdir(exist_ok=True)
    nro_src = STUB_DIR / "stub.nro"
    nro_out = OUT_DIR / f"{sanitize_name(out_name)}.nro"
    shutil.copy2(nro_src, nro_out)
    print(f"✅ Built {nro_out} (title: {title})")

# --- Orchestration -----------------------------------------------------------

def expand_psx_sets(candidates: List[Path]) -> Tuple[List[Tuple[Path, List[Path]]], Set[Path]]:
    """
    Return:
      - list of (cue_path, [track_paths])
      - set of all track paths included by any cue (for skipping as standalones)
    Only considers cues present in candidates (we also 'upgrade' lone bins later).
    """
    cues_map = index_cues(candidates)
    included_bins: Set[Path] = set()
    cue_sets: List[Tuple[Path, List[Path]]] = []
    for cue, tracks in cues_map.items():
        cue_sets.append((cue, tracks))
        for t in tracks:
            included_bins.add(t.resolve())
    return cue_sets, included_bins

def main():
    ap = argparse.ArgumentParser(description="ROM → Switch stub packer (to SD:/roms/<platform>/<rom>)")
    ap.add_argument("paths", nargs="+", help="ROM files or directories")
    ap.add_argument("--mode", choices=["each", "bundle"], default="each",
                    help="each: one NRO per ROM (default); bundle: one NRO with all ROMs")
    ap.add_argument("--bundle-name", default=None,
                    help="Output filename (without extension) for bundle mode")
    ap.add_argument("--platform", default=None,
                    help="Force platform name for ALL ROMs in this run (overrides detection)")
    args = ap.parse_args()

    # Collect candidate files
    candidates = collect_roms(args.paths)
    if not candidates:
        print("❌ No ROMs found.")
        return

    # Build cue sets from any .cue present in inputs
    cue_sets, bins_referenced = expand_psx_sets(candidates)
    bins_referenced = {p.resolve() for p in bins_referenced}

    # Prepare work items for modes
    if args.mode == "each":
        # For each candidate:
        # - if it's a .cue: build NRO including cue + its tracks as PSX
        # - if it's a .bin referenced by a .cue: skip (covered by cue)
        # - if it's a .bin with a sibling cue (even if cue not passed): upgrade to cue set
        # - otherwise: build single-file NRO using ext mapping or forced platform
        handled_cues: Set[Path] = set()

        for p in candidates:
            ext = p.suffix.lower()
            if ext == ".cue":
                if p in handled_cues:
                    continue
                tracks = dict(cue_sets).get(p, [])
                items = [(p, "psx")] + [(t, "psx") for t in tracks]
                print(f"\n=== Building PSX set (CUE): {p.name} ({len(tracks)} track(s)) ===")
                write_romfs_with_manifest(items)
                build_stub(out_name=p.stem, title=p.stem)
                handled_cues.add(p)
                continue

            if ext == ".bin":
                if p.resolve() in bins_referenced:
                    # already included by a cue in inputs
                    continue
                # Try to upgrade via sibling cue
                cue = find_cue_for_bin(p)
                if cue and cue.exists():
                    tracks = parse_cue(cue)
                    tracks = [t for t in tracks if t.exists()]
                    items = [(cue, "psx")] + [(t, "psx") for t in tracks]
                    print(f"\n=== Upgrading BIN to PSX set via CUE: {cue.name} ({len(tracks)} track(s)) ===")
                    write_romfs_with_manifest(items)
                    build_stub(out_name=cue.stem, title=cue.stem)
                    handled_cues.add(cue)
                    continue

            # Non-PSX or un-upgraded .bin
            plat = (args.platform or infer_platform(p)).lower()
            print(f"\n=== Building for {p.name} → {plat} ===")
            write_romfs_with_manifest([(p, plat)])
            build_stub(out_name=p.stem, title=p.stem)

    else:
        # BUNDLE: combine everything into ONE NRO
        items: List[Tuple[Path, str]] = []
        seen_abs: Set[Path] = set()

        # First, include all cue sets (cue + tracks) as psx
        for cue, tracks in cue_sets:
            parts = [cue] + tracks
            for x in parts:
                xa = x.resolve()
                if xa in seen_abs:
                    continue
                items.append((x, "psx"))
                seen_abs.add(xa)

        # Then include remaining files not already part of a cue set
        for p in candidates:
            pa = p.resolve()
            if pa in seen_abs:
                continue
            if p.suffix.lower() == ".bin":
                # Try to upgrade via sibling cue even if cue wasn't provided
                cue = find_cue_for_bin(p)
                if cue and cue.exists():
                    tracks = parse_cue(cue)
                    tracks = [t for t in tracks if t.exists()]
                    for x in [cue] + tracks:
                        xa = x.resolve()
                        if xa not in seen_abs:
                            items.append((x, "psx"))
                            seen_abs.add(xa)
                    continue
            plat = (args.platform or infer_platform(p)).lower()
            items.append((p, plat))
            seen_abs.add(pa)

        name = args.bundle_name or candidates[0].stem
        print(f"=== Building bundle: {name} ({len(items)} files) ===")
        write_romfs_with_manifest(items)
        build_stub(out_name=name, title=name)

if __name__ == "__main__":
    main()
