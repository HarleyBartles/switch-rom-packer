# packer/build/nsp.py
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .cores import load_core_map, resolve_core_so, canonical_platform

@dataclass
class NSPOptions:
    stub_dir: Path
    out_dir: Path
    platform: str
    rom_path: Path
    hb_title: str
    icon_path: Path
    keys_path: Path
    forwarder_mode: str  # "retroarch" | "nro"
    core_map_path: Optional[Path]
    titleid_base: Optional[str]  # 16-hex prefix/salt (optional)

# ---------- Main build flow ----------

def build_nsp_forwarder(
    *,
    stub_dir: Path,
    out_dir: Path,
    platform: str,
    rom_path: Path,
    hb_title: str,
    icon_path: Path,
    keys_path: Path,
    forwarder_mode: str,
    core_map_path: Optional[Path],
    titleid_base: Optional[str],
) -> Path:
    """
    Create a minimal forwarder NSP using hacBrewPack.

    Layout staged per ROM (in a temp working dir):
      work/
        control/control.nacp              (generated)
        logo/icon_AmericanEnglish.dat     (copied from icon_path)
        exefs/main + exefs/main.npdm      (template exefs you provide once)
        romfs/nextNroPath                 (forwarder target)
        romfs/nextArgv                    (forwarder argv)

    Returns the path to the resulting .nsp in out_dir.
    """
    opts = NSPOptions(
        stub_dir=stub_dir,
        out_dir=out_dir,
        platform=platform,
        rom_path=rom_path,
        hb_title=hb_title,
        icon_path=icon_path,
        keys_path=keys_path,
        forwarder_mode=forwarder_mode,
        core_map_path=core_map_path,
        titleid_base=titleid_base,
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Compute deterministic TitleID
    title_id = _compute_title_id(opts.platform, opts.rom_path, opts.titleid_base)

    # 2) Stage working directory
    work = out_dir / f".work_{title_id}"
    if work.exists():
        shutil.rmtree(work)
    (work / "control").mkdir(parents=True, exist_ok=True)
    (work / "logo").mkdir(parents=True, exist_ok=True)
    (work / "exefs").mkdir(parents=True, exist_ok=True)
    (work / "romfs").mkdir(parents=True, exist_ok=True)

    # 3) Place exefs (requires a template you provide once)
    _ensure_exefs(opts.stub_dir, work / "exefs")

    # 4) Write hacBrewPack config
    _write_hbp_config_json(
        work=work,
        title=opts.hb_title,
        author="Switch ROM Packer",
        version="1.0.0",
        title_id=title_id,
    )

    # 5) Minimal control marker (JSON placeholder for visibility)
    _write_control_nacp_json(work / "control" / "control.nacp", opts.hb_title, "Switch ROM Packer", "1.0.0", title_id)

    # 6) Icon → logo/icon_AmericanEnglish.dat
    _copy_icon(opts.icon_path, work / "logo" / "icon_AmericanEnglish.dat")

    # 7) Forwarder romfs
    next_nro, next_argv = _resolve_forwarder_targets(opts)
    _write_forwarder_romfs(work / "romfs", next_nro, next_argv)

    # 8) Invoke hacBrewPack
    hbp = _resolve_hacbrewpack_exe()
    if not hbp:
        raise SystemExit(
            "[packer] Could not find hacBrewPack executable. Expected tools/hacbrewpack/hacbrewpack "
            "or discoverable on PATH."
        )

    if not opts.keys_path.exists():
        raise SystemExit(f"[packer] prod.keys not found at: {opts.keys_path}. Use --keys to specify a path.")

    out_name = _suggest_nsp_name(opts.hb_title, title_id)
    out_path = opts.out_dir / out_name

    cmd = [str(hbp), "-k", str(opts.keys_path), "-o", str(out_path), str(work)]
    print(f"[packer] Running: {' '.join(_shell_quote(a) for a in cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        # Preserve workdir for debugging on failure
        raise SystemExit(f"[packer] hacBrewPack failed with exit code {e.returncode}")

    # Try common output shapes:
    if out_path.exists() and out_path.is_file():
        pass
    else:
        candidate = _find_first_nsp(work) or _find_first_nsp(opts.out_dir)
        if candidate:
            if out_path.exists():
                out_path.unlink()
            shutil.move(str(candidate), str(out_path))
        else:
            raise SystemExit("[packer] hacBrewPack finished but no NSP was found. Check logs and work dir.")

    # Cleanup work dir
    shutil.rmtree(work, ignore_errors=True)
    return out_path

# -------------------------
# Helpers
# -------------------------

def _compute_title_id(platform: str, rom_path: Path, titleid_base: Optional[str]) -> str:
    """
    Create a stable 16-hex TitleID.
    If titleid_base is provided:
       - If it's >= 16 hex chars, we prefix with first N chars and hash-fill the rest.
       - If it's shorter, we left-pad with zeros.
    Else:
       - Use a private range nibble '05' + 14 hex from SHA1.
    """
    h = hashlib.sha1(f"{platform}|{rom_path.name}".encode("utf-8")).hexdigest()

    if titleid_base:
        base = "".join(c for c in titleid_base.lower() if c in "0123456789abcdef")
        if len(base) >= 16:
            base = base[:16]
        else:
            base = base.zfill(16)
        tid = base
    else:
        tid = "05" + h[:14]

    if len(tid) != 16:
        tid = (tid + h)[:16]
    return tid

def _ensure_exefs(stub_dir: Path, exefs_dst: Path) -> None:
    """
    Copy a template exefs into exefs_dst.
    You must provide template files once at:
        <repo>/stub/vendor/exefs/main
        <repo>/stub/vendor/exefs/main.npdm
    This function will error if they don't exist.
    """
    vendor = stub_dir / "vendor" / "exefs"
    main = vendor / "main"
    npdm = vendor / "main.npdm"

    if not main.exists() or not npdm.exists():
        raise SystemExit(
            "[packer] exefs template missing.\n"
            f"Expected: {main} and {npdm}\n"
            "Provide loader binaries once (hbloader-style) so forwarders can be packaged."
        )

    shutil.copy2(main, exefs_dst / "main")
    shutil.copy2(npdm, exefs_dst / "main.npdm")

def _write_hbp_config_json(work: Path, title: str, author: str, version: str, title_id: str) -> None:
    cfg = {
        "title": title,
        "publisher": author,
        "version": version,
        "titleId": title_id,
    }
    with (work / "config.json").open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def _write_control_nacp_json(nacp_path: Path, title: str, author: str, version: str, title_id: str) -> None:
    nacp = {
        "title": title,
        "author": author,
        "version": version,
        "titleId": title_id,
        "_note": "Placeholder JSON for visibility; hacBrewPack will generate real control.nacp.",
    }
    with nacp_path.open("w", encoding="utf-8") as f:
        json.dump(nacp, f, ensure_ascii=False, indent=2)

def _copy_icon(src_icon: Path, dest_icon: Path) -> None:
    if not src_icon.exists():
        raise SystemExit(f"[packer] Icon not found: {src_icon}")
    shutil.copy2(src_icon, dest_icon)

def _resolve_forwarder_targets(opts: NSPOptions) -> Tuple[str, str]:
    """
    Return (nextNroPath, nextArgv) strings for romfs/.

    Modes:
      - retroarch: Launch RetroArch frontend and pass: -L <core .so> "<sdmc:/roms/.../file>"
      - nro:       Launch a specific NRO (default RetroArch frontend), argv is just the ROM path.

    SD layout assumptions:
      - RetroArch frontend: sdmc:/switch/retroarch/retroarch_switch.nro
      - Cores (.so):        sdmc:/switch/retroarch/cores/<core>.so
      - ROM:                sdmc:/roms/<platform>/<romfile>
    """
    rom_sd = f"sdmc:/roms/{opts.platform}/{opts.rom_path.name}"

    if opts.forwarder_mode == "retroarch":
        # Resolve platform → core .so via cores.py (custom or default map)
        core_map = load_core_map(opts.core_map_path)
        core_path = resolve_core_so(opts.platform, core_map)
        if not core_path:
            canon = canonical_platform(opts.platform)
            raise SystemExit(
                "[packer] No core mapping for platform: "
                f"{opts.platform!r} (canonical: {canon!r}). "
                "Add it to packer/data/cores.yml or pass --core-map."
            )

        retroarch_nro = "sdmc:/switch/retroarch/retroarch_switch.nro"
        nextNroPath = retroarch_nro
        # argv: -L <core> "<rom>"
        nextArgv = f'-L "{core_path}" "{rom_sd}"'
        return nextNroPath, nextArgv

    elif opts.forwarder_mode == "nro":
        # Generic jump to hbmenu-compatible NRO (default to RetroArch frontend)
        nextNroPath = "sdmc:/switch/retroarch/retroarch_switch.nro"
        nextArgv = f'"{rom_sd}"'
        return nextNroPath, nextArgv

    else:
        raise SystemExit(f"[packer] Unknown forwarder mode: {opts.forwarder_mode}")

def _write_forwarder_romfs(romfs_dir: Path, next_nro_path: str, next_argv: str) -> None:
    romfs_dir.mkdir(parents=True, exist_ok=True)
    (romfs_dir / "nextNroPath").write_text(next_nro_path, encoding="utf-8")
    (romfs_dir / "nextArgv").write_text(next_argv, encoding="utf-8")

def _resolve_hacbrewpack_exe() -> Optional[Path]:
    """
    Prefer vendored submodule executable; if missing, build it:
      - copy config.mk.template -> config.mk if needed
      - run `make`
    Fallback to PATH if vendored build fails.
    """
    repo_dir = Path(__file__).resolve().parents[2]
    hbproot = repo_dir / "tools" / "hacbrewpack"
    exe_name = "hacbrewpack.exe" if os.name == "nt" else "hacbrewpack"
    repo_hbp = hbproot / exe_name

    # If vendored binary already exists
    if repo_hbp.exists():
        return repo_hbp.resolve()

    makefile = hbproot / "Makefile"
    cfg = hbproot / "config.mk"
    cfg_template = hbproot / "config.mk.template"

    if makefile.exists():
        try:
            # Ensure config.mk exists
            if not cfg.exists():
                if cfg_template.exists():
                    print("[packer] Creating tools/hacbrewpack/config.mk from template...")
                    shutil.copy2(cfg_template, cfg)
                else:
                    print(f"[packer] Missing {cfg} and no template at {cfg_template}", file=sys.stderr)

            print("[packer] hacBrewPack binary not found; attempting to build via `make`...")
            subprocess.run(["make"], cwd=str(hbproot), check=True)

            if repo_hbp.exists():
                try:
                    os.chmod(repo_hbp, os.stat(repo_hbp).st_mode | 0o111)
                except Exception:
                    pass
                return repo_hbp.resolve()
        except subprocess.CalledProcessError as e:
            print(f"[packer] `make` failed (exit {e.returncode}); will try PATH.", file=sys.stderr)

    # Fallback to PATH
    exe = shutil.which(exe_name)
    return Path(exe) if exe else None

def _suggest_nsp_name(title: str, title_id: str) -> str:
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_.").strip()
    if not safe_title:
        safe_title = "Forwarder"
    return f"{safe_title} [{title_id}].nsp"

def _find_first_nsp(root: Path) -> Optional[Path]:
    for p in root.rglob("*.nsp"):
        return p
    return None

def _shell_quote(s: str) -> str:
    if os.name == "nt":
        if " " in s or "\t" in s:
            return f'"{s}"'
        return s
    else:
        if not s:
            return "''"
        if all(ch.isalnum() or ch in "@%_-+=:,./" for ch in s):
            return s
        return "'" + s.replace("'", "'\"'\"'") + "'"
