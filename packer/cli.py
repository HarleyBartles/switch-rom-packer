from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from packer.discovery.detect import discover_roms
from packer.metadata.titles import parse_rom_title
from packer.icons.match import find_icon_with_alts
from packer.io.filelist import write_filelist
from packer.build.hbmenu import build_nro_for_rom


DEFAULT_STUB_DIR = Path(__file__).resolve().parent.parent / "stub"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "out"
DEFAULT_FILELIST = Path(__file__).resolve().parent.parent / "filelist.txt"


def _prepare_romfs_for_single_rom(stub_dir: Path, platform: str, rom_path: Path) -> None:
    """
    Wipe stub/romfs, copy the ROM in, and write a one-line TAB-delimited manifest:
        "<platform>\t<romfilename>\n"
    """
    romfs_dir = stub_dir / "romfs"
    if romfs_dir.exists():
        shutil.rmtree(romfs_dir)
    romfs_dir.mkdir(parents=True, exist_ok=True)

    # Copy this ROM into RomFS (the stub will copy it out on first boot)
    shutil.copy2(rom_path, romfs_dir / rom_path.name)

    # TAB-delimited avoids the "Bad manifest line" when names contain spaces
    (romfs_dir / "filelist.txt").write_text(
        f"{platform}\t{rom_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="switch-rom-packer")
    ap.add_argument("rom_root", type=Path, help="Root folder containing platform folders with ROMs")
    ap.add_argument("--stub-dir", type=Path, default=DEFAULT_STUB_DIR)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--filelist-out", type=Path, default=DEFAULT_FILELIST)
    ap.add_argument("--build-nro", dest="build_nro", action=argparse.BooleanOptionalAction, default=True)
    # Accept (and currently ignore) the legacy flag so existing scripts don’t break
    ap.add_argument("--debug-icons", action="store_true", help="Enable extra icon lookup logging (currently verbose by default)")
    ap.add_argument(
        "--icon-preference",
        choices=["logos-first", "boxarts-first"],
        default="logos-first",
        help="Choose thumbnail set priority (default: logos-first)."
    )
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

        # Debug logging
        if alt_titles:
            preview = ", ".join(alt_titles[:4]) + ("..." if len(alt_titles) > 4 else "")
            print(f"[titles] {rom_path.name} -> title='{canonical_title}' alt_titles=[{preview}]")
        else:
            print(f"[titles] {rom_path.name} -> title='{canonical_title}' (no alts)")

    # Optional: write a combined filelist at repo root for inspection.
    # The actual stub uses a per-ROM filelist written just before each build.
    write_filelist(filelist_out, entries_for_filelist)

    print("Calculating metadata...")

    # Build NROs (per ROM)
    total = len(items)
    for idx, item in enumerate(items, start=1):
        platform = item["platform"]
        rom_path: Path = item["rom_path"]
        hb_title: str = item["title"]
        alt_titles: List[str] = item["alt_titles"]

        icon_path = find_icon_with_alts(
            platform,
            hb_title,
            alt_titles,
            source_name_hint=rom_path.name,
            preference=args.icon_preference
        )

        # Prepare a fresh RomFS containing only THIS ROM and a one-line TAB-delimited manifest
        _prepare_romfs_for_single_rom(stub_dir, platform, rom_path)

        if args.build_nro:
            nro_out = build_nro_for_rom(stub_dir, out_dir, platform, rom_path, hb_title, icon_path)
            print(f"[{idx}/{total}] Built NRO for {hb_title} -> {nro_out}")

    print("[packer] Done.")
