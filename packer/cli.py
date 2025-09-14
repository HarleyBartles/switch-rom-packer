from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from packer.discovery.detect import discover_roms
from packer.metadata.titles import parse_rom_title
from packer.icons.match import find_icon_with_alts
from packer.io.filelist import write_filelist

# NRO builder (use the refactor's module name; change to hbmenu if that's your layout)
from packer.build.nro import build_nro_for_rom  # if your repo still uses hbmenu, swap to: from packer.build.hbmenu import build_nro_for_rom

# NSP forwarder builder (provided in packer/build/nsp.py)
try:
    from packer.build.nsp import build_nsp_forwarder  # type: ignore
except Exception:
    build_nsp_forwarder = None  # graceful if not implemented yet


DEFAULT_STUB_DIR = Path(__file__).resolve().parent.parent / "stub"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "out"
DEFAULT_FILELIST = Path(__file__).resolve().parent.parent / "filelist.txt"


def _prepare_romfs_for_single_rom(stub_dir: Path, platform: str, rom_path: Path) -> None:
    """
    Wipe stub/romfs, copy THIS ROM into RomFS, and write a one-line TAB-delimited manifest:
        "<platform>\t<romfilename>\n"

    The libnx stub will copy this embedded ROM to /roms/<platform>/<romfile> on first boot.
    """
    romfs_dir = stub_dir / "romfs"
    if romfs_dir.exists():
        shutil.rmtree(romfs_dir)
    romfs_dir.mkdir(parents=True, exist_ok=True)

    # Copy this ROM into RomFS (embed in the NRO)
    shutil.copy2(rom_path, romfs_dir / rom_path.name)

    # TAB-delimited avoids issues when names contain spaces
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

    # NRO build flags
    ap.add_argument(
        "--build-nro",
        dest="build_nro",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Build NROs (default: enabled).",
    )

    # NSP build flags (default enabled to match NRO)
    ap.add_argument(
        "--build-nsp",
        dest="build_nsp",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Build NSP forwarders with hacBrewPack (default: enabled).",
    )
    ap.add_argument(
        "--keys",
        type=Path,
        default=Path.home() / ".switch" / "prod.keys",
        help="Path to prod.keys for hacBrewPack (default: ~/.switch/prod.keys).",
    )
    ap.add_argument(
        "--forwarder",
        choices=["retroarch", "nro"],
        default="retroarch",
        help="Forwarder mode: 'retroarch' boots a core+nro with the ROM; 'nro' jumps to an arbitrary NRO.",
    )
    ap.add_argument(
        "--core-map",
        type=Path,
        default=None,
        help="YAML file mapping <platform> -> <retroarch core nro path>. Used when --forwarder=retroarch.",
    )
    ap.add_argument(
        "--titleid-base",
        type=str,
        default=None,
        help="Optional 16-hex prefix/salt for deterministic TitleIDs.",
    )

    ap.add_argument(
        "--debug-icons",
        action="store_true",
        help="Enable extra icon lookup logging.",
    )
    ap.add_argument(
        "--icon-preference",
        choices=["logos", "boxarts"],
        default="logos",
        help="Choose thumbnail priority (default: logos).",
    )

    args = ap.parse_args(argv)

    rom_root: Path = args.rom_root
    stub_dir: Path = args.stub_dir
    out_dir: Path = args.output_dir
    filelist_out: Path = args.filelist_out

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nro").mkdir(parents=True, exist_ok=True)
    if args.build_nsp:
        (out_dir / "nsp").mkdir(parents=True, exist_ok=True)

    # Discover ROMs
    roms = discover_roms(rom_root)
    if not roms:
        print(f"[packer] No ROMs found under {rom_root}")
        return

    # Keep the combined filelist (for inspection) and item metadata (alt_titles)
    entries_for_filelist: List[Tuple[str, str]] = []
    items: List[Dict[str, Any]] = []

    print("Visiting directories...")
    for platform, rom_path in roms:
        # Original behavior: parse title + alt titles
        canonical_title, alt_titles = parse_rom_title(str(rom_path))
        items.append({
            "platform": platform,
            "rom_path": rom_path,
            "title": canonical_title,
            "alt_titles": alt_titles,
        })
        entries_for_filelist.append((platform, rom_path.name))

        # Debug logging for titles
        if alt_titles:
            preview = ", ".join(alt_titles[:4]) + ("..." if len(alt_titles) > 4 else "")
            print(f"[titles] {rom_path.name} -> title='{canonical_title}' alt_titles=[{preview}]")
        else:
            print(f"[titles] {rom_path.name} -> title='{canonical_title}' (no alts)")

    # Write a combined filelist at repo root for inspection (stub still uses per-ROM filelist)
    write_filelist(filelist_out, entries_for_filelist)

    print("Calculating metadata...")

    # Build per ROM
    total = len(items)
    for idx, item in enumerate(items, start=1):
        platform = item["platform"]
        rom_path: Path = item["rom_path"]
        hb_title: str = item["title"]
        alt_titles: List[str] = item["alt_titles"]

        # Use correct parameter order via named args (and pass alt titles)
        icon_path = find_icon_with_alts(
            platform=platform,
            primary_title=hb_title,
            alt_titles=alt_titles,
            source_name_hint=rom_path.name,
            preference=args.icon_preference,
        )

        # Prepare a fresh RomFS containing only THIS ROM
        _prepare_romfs_for_single_rom(stub_dir, platform, rom_path)

        # Build NRO
        if args.build_nro:
            nro_out = build_nro_for_rom(stub_dir, out_dir, platform, rom_path, hb_title, icon_path)
            print(f"[{idx}/{total}] Built NRO for {hb_title} -> {nro_out}")

        # Build NSP
        if args.build_nsp:
            if build_nsp_forwarder is None:
                raise SystemExit(
                    "[packer] --build-nsp is enabled but packer.build.nsp.build_nsp_forwarder is missing. "
                    "Add packer/build/nsp.py first."
                )
            nsp_out = build_nsp_forwarder(
                stub_dir=stub_dir,
                out_dir=out_dir / "nsp",
                platform=platform,
                rom_path=rom_path,
                hb_title=hb_title,
                icon_path=icon_path,
                keys_path=args.keys,
                forwarder_mode=args.forwarder,
                core_map_path=args.core_map,
                titleid_base=args.titleid_base,
            )
            print(f"[{idx}/{total}] Built NSP forwarder for {hb_title} -> {nsp_out}")

    print("[packer] Done.")


if __name__ == "__main__":
    main()
