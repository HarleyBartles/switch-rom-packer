#!/usr/bin/env python3
"""
packer.py
Scan ROMs, auto-detect their systems, emit Libretro folder names,
and by default build per-ROM NRO forwarders using your libnx stub.

Typical usage:
  python3 packer.py ~/rom_input/

Defaults:
- Builds per-ROM NROs (disable with --no-build-nro)
- Stub dir: ./stub
- Output dir: ./out
- filelist.txt: ./filelist.txt
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
from typing import List, Set

from icons import get_icon_file
from packer.system_detect import detect_libretro_folder
from packer.systems import (
    load_pinned_snapshot,
    fetch_live_libretro_folders,
    validate_detected_targets,
)

# --- Allowed extensions (same as before) ---
ALLOWED_EXTS = {
    ".nes", ".fds", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".vb",
    ".z64", ".n64", ".v64", ".ndd",
    ".nds", ".dsi", ".3ds", ".cci", ".cxi",
    ".bs", ".st", ".min",
    ".gcm", ".iso", ".wad", ".wud", ".wux",
    ".sg", ".sms", ".gg", ".md", ".bin", ".gen", ".smd",
    ".chd", ".cue", ".32x",
    ".cdi", ".gdi", ".naomi", ".pico",
    ".m3u", ".pbp", ".cso",
    ".ngp", ".ngc", ".npc", ".pce", ".sgx",
    ".a26", ".a52", ".a78", ".lnx", ".vec",
    ".d64", ".t64", ".prg", ".adf", ".ipf",
}
IGNORE_EXTS = {
    ".srm", ".sav", ".state", ".st0", ".st1", ".st2",
    ".cfg", ".ini", ".db", ".xml", ".json",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".txt", ".nfo", ".diz", ".md",
}

@dataclass
class BuildConfig:
    rom_root: Path
    filelist_out: Path
    validate_systems: bool
    snapshot_path: Path
    cache_path: Path
    github_token: str | None
    build_nro: bool
    stub_dir: Path
    output_dir: Path
    app_author: str
    app_version: str
    icon_dir: Path | None
    app_title_template: str
    dry_run: bool
    debug_icons: bool = False


# ---------- utility ----------

def find_roms(root: Path) -> List[Path]:
    roms: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in IGNORE_EXTS:
            continue
        if ext in ALLOWED_EXTS:
            roms.append(p)
    return sorted(roms)


def safe_title_from_filename(p: Path) -> str:
    title = p.stem
    for needle in ("[", "]", "(", ")", "{", "}", "_", " - "):
        title = title.replace(needle, " ")
    title = " ".join(title.split())
    return title[:128] if len(title) > 128 else title


def ensure_dir(d: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] mkdir -p {d}")
        return
    d.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] copy {src} -> {dst}")
        return
    ensure_dir(dst.parent, dry_run=False)
    shutil.copy2(src, dst)


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] write {path} ({len(content)} bytes)")
        return
    ensure_dir(path.parent, dry_run=False)
    path.write_text(content, encoding="utf-8")


def run_make_with_stub(
    stub_dir: Path,
    app_title: str,
    app_author: str,
    app_version: str,
    dry_run: bool,
    platform_bucket: str = "",
    alt_titles: list[str] = None,
    debug_icons: bool = False,
) -> Path:
    target_name = stub_dir.name
    nro_path = stub_dir / f"{target_name}.nro"

    env = os.environ.copy()
    env["APP_TITLE"] = app_title
    env["APP_AUTHOR"] = app_author
    env["APP_VERSION"] = app_version

    icon_arg = None
    if platform_bucket:
        # 1) fetch (cached) icon as a file (png/jpg — we don't care)
        fetched_icon = get_icon_file(app_title, platform_bucket, alt_titles or [], debug=debug_icons)

        # 2) re-encode into a local stub icon.jpg (RGB, 256x256)
        local_icon = stub_dir / "icon.jpg"
        if not dry_run:
            img = Image.open(fetched_icon)
            # enforce 256x256 RGB JPEG without alpha
            if img.size != (256, 256):
                img = img.convert("RGBA")
                side = max(img.width, img.height)
                canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                canvas.paste(img, ((side - img.width)//2, (side - img.height)//2))
                img = canvas.resize((256, 256), Image.LANCZOS)
            img = img.convert("RGB")
            img.save(local_icon, format="JPEG", quality=92)
        else:
            print(f"[dry-run] write {local_icon} (JPEG 256x256)")

        # 3) pass icon *by name* on the make cmdline (relative to stub_dir)
        icon_arg = "ICON=icon.jpg"
        if debug_icons:
            print(f"[icons] using local stub icon: {local_icon}")

    if dry_run:
        if icon_arg:
            print(f"[dry-run] (cd {stub_dir}) make clean {icon_arg} && make {icon_arg}")
        else:
            print(f"[dry-run] (cd {stub_dir}) make clean && make")
        return nro_path

    # IMPORTANT: pass ICON on the command line
    if icon_arg:
        subprocess.run(["make", "clean", icon_arg], cwd=str(stub_dir), check=True, env=env)
        subprocess.run(["make", icon_arg], cwd=str(stub_dir), check=True, env=env)
    else:
        subprocess.run(["make", "clean"], cwd=str(stub_dir), check=True, env=env)
        subprocess.run(["make"], cwd=str(stub_dir), check=True, env=env)

    if not nro_path.exists():
        raise RuntimeError(f"Expected NRO not found: {nro_path}")
    return nro_path

# ---------- core flow ----------

def build_filelist_and_optionally_nro(cfg: BuildConfig) -> None:
    if cfg.build_nro and not cfg.stub_dir.exists():
        raise SystemExit(f"Stub dir not found: {cfg.stub_dir}")

    roms = find_roms(cfg.rom_root)
    if not roms:
        print("[packer] No ROMs found.")
        return

    detected_targets: Set[str] = set()
    lines: List[str] = []

    for rom in roms:
        platform_folder = detect_libretro_folder(rom)
        detected_targets.add(platform_folder)
        lines.append(f"{platform_folder}\t{rom.name}")

    write_text(cfg.filelist_out, "\n".join(lines) + "\n", cfg.dry_run)
    print(f"[packer] Wrote {len(lines)} entries to {cfg.filelist_out}")

    if cfg.validate_systems:
        if cfg.snapshot_path.exists():
            libretro_folders = load_pinned_snapshot(cfg.snapshot_path)
        else:
            libretro_folders = fetch_live_libretro_folders(cfg.cache_path, github_token=cfg.github_token)
        result = validate_detected_targets(detected_targets, libretro_folders)
        for note in result.notes:
            print(f"[systems] {note}")
        if not result.ok:
            raise SystemExit(2)

    if cfg.build_nro:
        out_nro_dir = cfg.output_dir / "nro"
        ensure_dir(out_nro_dir, cfg.dry_run)
        stub_romfs = cfg.stub_dir / "romfs"

        for idx, rom in enumerate(roms, 1):
            platform_folder = detect_libretro_folder(rom)
            app_title = cfg.app_title_template.format(
                title=safe_title_from_filename(rom),
                system=platform_folder,
                filename=rom.name,
            )

            if not cfg.dry_run:
                if stub_romfs.exists():
                    shutil.rmtree(stub_romfs)
                stub_romfs.mkdir(parents=True, exist_ok=True)
            else:
                print(f"[dry-run] reset {stub_romfs}")

            write_text(stub_romfs / "filelist.txt", f"{platform_folder}\t{rom.name}\n", cfg.dry_run)
            copy_file(rom, stub_romfs / rom.name, cfg.dry_run)

            # icon handling
            stub_icon = cfg.stub_dir / "icon.png"
            icon_path = None
            if cfg.icon_dir:
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    cand = cfg.icon_dir / f"{rom.stem}{ext}"
                    if cand.exists():
                        icon_path = cand
                        break
            if icon_path:
                copy_file(icon_path, stub_icon, cfg.dry_run)
            elif stub_icon.exists() and not cfg.dry_run:
                stub_icon.unlink()

            raw_title = rom.stem
            alt_titles = [raw_title]
            if "(" in raw_title and raw_title.endswith(")"):
                alt_titles.append(raw_title[: raw_title.rfind("(")].strip())
            alt_titles.append(raw_title.replace("_", " ").replace("-", " "))

            nro_src = run_make_with_stub(
                cfg.stub_dir,
                app_title,
                cfg.app_author,
                cfg.app_version,
                cfg.dry_run,
                platform_bucket=platform_folder,
                alt_titles=alt_titles,
                debug_icons=cfg.debug_icons,
            )

            safe_name = "".join(ch for ch in app_title if ch.isalnum() or ch in (" ", "-", "_")).strip() or "app"
            nro_dst = out_nro_dir / f"{safe_name}.nro"
            if cfg.dry_run:
                print(f"[dry-run] copy {nro_src} -> {nro_dst}")
            else:
                shutil.copy2(nro_src, nro_dst)
            print(f"[{idx}/{len(roms)}] Built NRO for {rom.name} -> {nro_dst}")

    print("[packer] Done.")


# ---------- CLI ----------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Switch ROM packer: detect systems and (by default) build NRO forwarders."
    )
    p.add_argument("rom_root", nargs="?", default=".",
                   help="Directory to scan for ROMs (recursively). Default: current dir")
    p.add_argument("--filelist-out", default="filelist.txt", help="Output consolidated filelist path.")
    p.add_argument("--validate-systems", action="store_true", help="Validate detected platforms against Libretro.")
    p.add_argument("--libretro-snapshot", default="config/libretro_systems_snapshot.json",
                   help="Pinned offline list of Libretro folders.")
    p.add_argument("--libretro-cache", default=".cache/libretro_folders.json",
                   help="Cache for live Libretro folder list (GitHub API).")
    p.add_argument("--github-token", default=None, help="Optional GitHub token (raise API rate limit).")

    p.add_argument("--no-build-nro", dest="build_nro", action="store_false",
                   help="Disable building per-ROM NROs (default is enabled).")
    p.set_defaults(build_nro=True)

    p.add_argument("--stub-dir", default="./stub", help="Path to your libnx stub project (Makefile).")
    p.add_argument("--output-dir", default="./out", help="Where to place outputs. Default: ./out")
    p.add_argument("--app-author", default="switch-rom-packer", help="NACP author metadata.")
    p.add_argument("--app-version", default="0.1.0", help="NACP version metadata.")
    p.add_argument("--icon-dir", default=None,
                   help="Optional folder containing per-ROM icons named <romstem>.png/.jpg/.jpeg/.webp.")
    p.add_argument("--app-title-template",
                   default="{title}",
                   help="hbmenu title template: {title}, {system}, {filename}")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing/copying/building.")
    p.add_argument("--debug-icons", action="store_true",
               help="Print which icon candidates matched and their confidence scores.")

    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    cfg = BuildConfig(
        rom_root=Path(args.rom_root).expanduser().resolve(),
        filelist_out=Path(args.filelist_out).resolve(),
        validate_systems=args.validate_systems,
        snapshot_path=Path(args.libretro_snapshot).resolve(),
        cache_path=Path(args.libretro_cache).resolve(),
        github_token=args.github_token,
        build_nro=args.build_nro,
        stub_dir=Path(args.stub_dir).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve(),
        app_author=args.app_author,
        app_version=args.app_version,
        icon_dir=Path(args.icon_dir).expanduser().resolve() if args.icon_dir else None,
        app_title_template=args.app_title_template,
        dry_run=args.dry_run,
        debug_icons=args.debug_icons,
    )

    try:
        build_filelist_and_optionally_nro(cfg)
    except subprocess.CalledProcessError as e:
        print(f"[error] make failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
