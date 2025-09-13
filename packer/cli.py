from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

from packer.discovery.detect import discover_roms
from packer.metadata.titles import parse_rom_title
from packer.icons.match import find_icon_with_alts
from packer.io.fsutil import clean_dir
from packer.io.filelist import write_filelist
from packer.build.hbmenu import build_nro_for_rom


DEFAULT_STUB_DIR = Path(__file__).resolve().parent.parent / "stub"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "out"
DEFAULT_FILELIST = Path(__file__).resolve().parent.parent / "filelist.txt"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="switch-rom-packer")
    ap.add_argument("rom_root", type=Path, help="Root folder containing platform folders with ROMs")
    ap.add_argument("--stub-dir", type=Path, default=DEFAULT_STUB_DIR)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--filelist-out", type=Path, default=DEFAULT_FILELIST)
    ap.add_argument("--build-nro", dest="build_nro", action=argparse.BooleanOptionalAction, default=True)
    # Accept (and currently ignore) the legacy flag so existing scripts don’t break
    ap.add_argument("--debug-icons", action="store_true", help="Enable extra icon lookup logging (currently verbose by default)")
    args = ap.parse_args(argv)

    rom_root: Path = args.rom_root
    stub_dir: Path = args.stub_dir
    out_dir: Path = args.output_dir
    filelist_out: Path = args.filelist_out

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nro").mkdir(parents=True, exist_ok=True)

    # Discover ROMs
    roms = discover_roms(rom_root)
    if not roms:
        print(f"[packer] No ROMs found under {rom_root}")
        return

    # Prepare RomFS inputs
    romfs_dir = stub_dir / "romfs"
    clean_dir(romfs_dir)

    entries_for_filelist: List[Tuple[str, str]] = []
    items: List[Dict[str, Any]] = []

    print("Visiting directories...")
    for platform, rom_path in roms:
        canonical_title, alt_titles = parse_rom_title(str(rom_path))
        items.append({
            "platform": platform,
            "rom_path": rom_path,
            "title": canonical_title,
            "alt_titles": alt_titles,
        })
        entries_for_filelist.append((platform, rom_path.name))

        # Copy ROM into RomFS (so stub runtime sees it)
        (romfs_dir / rom_path.name).write_bytes(rom_path.read_bytes())

        # Debug logging
        if alt_titles:
            preview = ", ".join(alt_titles[:4]) + ("..." if len(alt_titles) > 4 else "")
            print(f"[titles] {rom_path.name} -> title='{canonical_title}' alt_titles=[{preview}]")
        else:
            print(f"[titles] {rom_path.name} -> title='{canonical_title}' (no alts)")

    # Write filelist.txt (repo root and RomFS copy)
    write_filelist(filelist_out, entries_for_filelist)
    (romfs_dir / "filelist.txt").write_text(filelist_out.read_text(encoding="utf-8"), encoding="utf-8")

    print("Calculating metadata...")

    # Build NROs (per ROM)
    total = len(items)
    for idx, item in enumerate(items, start=1):
        platform = item["platform"]
        rom_path: Path = item["rom_path"]
        hb_title: str = item["title"]
        alt_titles: List[str] = item["alt_titles"]

        icon_path = find_icon_with_alts(platform, hb_title, alt_titles)

        print(f"Writing {romfs_dir / rom_path.name} to RomFS image...")
        print(f"Writing {romfs_dir / 'filelist.txt'} to RomFS image...")
        if args.build_nro:
            nro_out = build_nro_for_rom(stub_dir, out_dir, platform, rom_path, hb_title, icon_path)
            print(f"[{idx}/{total}] Built NRO for {hb_title} -> {nro_out}")

    print("[packer] Done.")
