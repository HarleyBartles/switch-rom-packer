#!/usr/bin/env python3
"""
packer.py
----------
Prototype CLI to bundle a ROM into the Switch installer stub.

Usage:
    python3 packer.py /path/to/game.smc /path/to/another.rom
"""

import argparse
import shutil
import subprocess
from pathlib import Path

# Paths
ROOT = Path(__file__).parent.resolve()
STUB_DIR = ROOT / "stub"
ROMFS_DIR = STUB_DIR / "romfs"
OUT_DIR = ROOT / "out"

def build_stub_for_rom(rom_path: Path):
    rom_path = rom_path.resolve()
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return

    # Clean romfs
    if ROMFS_DIR.exists():
        shutil.rmtree(ROMFS_DIR)
    ROMFS_DIR.mkdir(parents=True)

    # Copy ROM into romfs
    target = ROMFS_DIR / rom_path.name
    shutil.copy2(rom_path, target)
    print(f"📦 Injected {rom_path.name} into romfs/")

    # Run make
    print("🔨 Building stub...")
    subprocess.run(["make", "clean"], cwd=STUB_DIR, check=True)
    subprocess.run(["make"], cwd=STUB_DIR, check=True)

    # Collect output
    OUT_DIR.mkdir(exist_ok=True)
    nro_src = STUB_DIR / "stub.nro"
    nro_out = OUT_DIR / f"{rom_path.stem}.nro"
    shutil.copy2(nro_src, nro_out)
    print(f"✅ Built {nro_out}")

def main():
    ap = argparse.ArgumentParser(description="ROM → Switch stub packer")
    ap.add_argument("roms", nargs="+", help="ROM file(s) to bundle")
    args = ap.parse_args()

    for rom in args.roms:
        build_stub_for_rom(Path(rom))

if __name__ == "__main__":
    main()
