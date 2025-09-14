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


# ---------- Paths ----------
REPO_ROOT   = Path(__file__).resolve().parents[2]
FORWARDER_DIR = REPO_ROOT / "forwarder"
VENDOR_EXEFS  = REPO_ROOT / "stub" / "vendor" / "exefs"


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

    work/
      control/control.nacp            (binary, generated via nacptool)
      logo/icon_AmericanEnglish.dat   (copied from icon_path)
      exefs/main + exefs/main.npdm    (from stub/vendor/exefs; kept fresh by `forwarder install`)
      romfs/nextNroPath               (forwarder target)
      romfs/nextArgv                  (forwarder argv)
      config.json                     (metadata for reference)
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

    # Ensure vendor exefs (build forwarder + install into stub/vendor/exefs)
    _ensure_vendor_exefs()

    # 1) Deterministic TitleID
    title_id = _compute_title_id(opts.platform, opts.rom_path, opts.titleid_base)

    # 2) Stage working dir
    work = out_dir / f".work_{title_id}"
    if work.exists():
        shutil.rmtree(work)
    (work / "control").mkdir(parents=True, exist_ok=True)
    (work / "logo").mkdir(parents=True, exist_ok=True)
    (work / "exefs").mkdir(parents=True, exist_ok=True)
    (work / "romfs").mkdir(parents=True, exist_ok=True)

    # 3) ExeFS (forwarder) -> stage from vendor
    _stage_vendor_exefs(exefs_dst=work / "exefs")

    # 4) Write config.json (informational)
    _write_hbp_config_json(
        work=work,
        title=opts.hb_title,
        author="Switch ROM Packer",
        version="1.0.0",
        title_id=title_id,
    )

    # 5) Real control.nacp via nacptool
    _write_control_nacp_bin(
        nacp_path=work / "control" / "control.nacp",
        title=opts.hb_title,
        author="Switch ROM Packer",
        version="1.0.0",
        title_id=title_id,
    )

    # 6) Icon
    _copy_icon(opts.icon_path, work / "logo" / "icon_AmericanEnglish.dat")

    # 7) Forwarder romfs
    next_nro, next_argv = _resolve_forwarder_targets(opts)
    _write_forwarder_romfs(work / "romfs", next_nro, next_argv)

    # 8) hacBrewPack
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

    # Track new NSP
    before = {p.resolve() for p in opts.out_dir.glob("*.nsp")}

    cmd = [
        str(hbp),
        "-k", str(opts.keys_path),
        "--exefsdir", str(work / "exefs"),
        "--romfsdir", str(work / "romfs"),
        "--controldir", str(work / "control"),
        "--logodir", str(work / "logo"),
        "--nspdir", str(opts.out_dir),  # dir, not file
    ]
    print(f"[packer] Running: {' '.join(_shell_quote(a) for a in cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"[packer] hacBrewPack failed with exit code {e.returncode}")

    # Identify produced NSP & rename
    produced = _pick_new_nsp(opts.out_dir, before) or _find_first_nsp(work) or _find_first_nsp(opts.out_dir)
    if not produced:
        raise SystemExit("[packer] hacBrewPack finished but no NSP was found. Check logs and work dir.")

    if out_path.exists():
        out_path.unlink()
    shutil.move(str(produced), str(out_path))

    shutil.rmtree(work, ignore_errors=True)
    print(f"[packer] Wrote NSP -> {out_path}")
    return out_path

# -------------------------
# Helpers
# -------------------------
def _ensure_vendor_exefs() -> None:
    """Build forwarder and install its ExeFS into stub/vendor/exefs (idempotent)."""
    env = os.environ.copy()
    env.setdefault("DEVKITPRO", "/opt/devkitpro")
    env.setdefault("DEVKITA64", str(Path(env["DEVKITPRO"]) / "devkitA64"))
    tools_bin = str(Path(env["DEVKITPRO"]) / "tools" / "bin")
    if tools_bin not in env.get("PATH", ""):
        env["PATH"] = tools_bin + os.pathsep + env.get("PATH", "")

    # Ensure toolchain essentials are available (helpful error if not)
    switch_specs = Path(env["DEVKITPRO"]) / "libnx" / "switch.specs"
    if not switch_specs.exists():
        raise SystemExit(
            f"[packer] Missing {switch_specs}. Install/repair devkitPro libnx:\n"
            "  sudo dkp-pacman -Syu && sudo dkp-pacman -S libnx switch-dev switch-tools"
        )
    for tool in ("aarch64-none-elf-gcc", "elf2nso", "npdmtool", "nacptool"):
        if not shutil.which(tool, path=env.get("PATH", "")):
            raise SystemExit(f"[packer] Required tool '{tool}' not found on PATH (devkitPro).")

    # Build & install forwarder into vendor
    print("[packer] Ensuring forwarder vendor exefs (make install)...")
    subprocess.run(["make", "clean"], cwd=str(FORWARDER_DIR), check=False, env=env)
    subprocess.run(["make", "install"], cwd=str(FORWARDER_DIR), check=True, env=env)

    # Sanity check
    for name in ("main", "main.npdm"):
        p = VENDOR_EXEFS / name
        if not p.exists():
            raise SystemExit(f"[forwarder] install failed (missing {p})")


def _stage_vendor_exefs(exefs_dst: Path) -> None:
    """Copy vendor exefs/main + main.npdm into the staging exefs/."""
    exefs_dst.mkdir(parents=True, exist_ok=True)
    for name in ("main", "main.npdm"):
        src = VENDOR_EXEFS / name
        if not src.exists():
            raise SystemExit(f"[nsp] missing vendor exefs file: {src}")
        shutil.copy2(src, exefs_dst / name)


def _compute_title_id(platform: str, rom_path: Path, titleid_base: Optional[str]) -> str:
    h = hashlib.sha1(f"{platform}|{rom_path.name}".encode("utf-8")).hexdigest()
    if titleid_base:
        base = "".join(c for c in titleid_base.lower() if c in "0123456789abcdef")
        base = base[:16] if len(base) >= 16 else base.zfill(16)
        tid = base
    else:
        tid = "05" + h[:14]
    if len(tid) != 16:
        tid = (tid + h)[:16]
    return tid


def _write_hbp_config_json(work: Path, title: str, author: str, version: str, title_id: str) -> None:
    cfg = {"title": title, "publisher": author, "version": version, "titleId": title_id}
    with (work / "config.json").open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _resolve_nacptool() -> Optional[Path]:
    """
    Try DEVKITPRO first, then PATH.
    devkitPro installs nacptool at: $DEVKITPRO/tools/bin/nacptool
    """
    exe = "nacptool.exe" if os.name == "nt" else "nacptool"
    devkitpro = os.environ.get("DEVKITPRO")
    if devkitpro:
        candidate = Path(devkitpro) / "tools" / "bin" / exe
        if candidate.exists():
            return candidate.resolve()
    found = shutil.which(exe)
    return Path(found) if found else None


def _write_control_nacp_bin(nacp_path: Path, title: str, author: str, version: str, title_id: str) -> None:
    """
    Generate a real binary control.nacp using nacptool.
    """
    nacptool = _resolve_nacptool()
    if not nacptool:
        raise SystemExit(
            "[packer] `nacptool` not found. Install devkitPro (switch-tools) or add nacptool to PATH.\n"
            "On Debian/Ubuntu via devkitPro pacman: https://devkitpro.org/wiki/devkitPro_pacman"
        )

    nacp_dir = nacp_path.parent
    nacp_dir.mkdir(parents=True, exist_ok=True)

    # nacptool --create <title> <author> <version> <out> --titleid=<hex16> --lang=<idx>:<localizedTitle>
    cmd = [
        str(nacptool),
        "--create", title, author, version, str(nacp_path),
        f"--titleid={title_id}",
        "--lang=0:" + title,  # AmericanEnglish
    ]
    print(f"[packer] Generating control.nacp: {' '.join(_shell_quote(a) for a in cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"[packer] nacptool failed (exit {e.returncode}). Is devkitPro switch-tools installed?")

    if not nacp_path.exists() or nacp_path.stat().st_size == 0:
        raise SystemExit("[packer] control.nacp generation failed or produced empty file.")


def _copy_icon(src_icon: Path, dest_icon: Path) -> None:
    if not src_icon.exists():
        raise SystemExit(f"[packer] Icon not found: {src_icon}")
    shutil.copy2(src_icon, dest_icon)


def _resolve_forwarder_targets(opts: NSPOptions) -> Tuple[str, str]:
    rom_sd = f"sdmc:/roms/{opts.platform}/{opts.rom_path.name}"
    if opts.forwarder_mode == "retroarch":
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
        return retroarch_nro, f'-L "{core_path}" "{rom_sd}"'
    elif opts.forwarder_mode == "nro":
        # Generic jump to hbmenu-compatible NRO (default RetroArch frontend)
        return "sdmc:/switch/retroarch/retroarch_switch.nro", f'"{rom_sd}"'
    else:
        raise SystemExit(f"[packer] Unknown forwarder mode: {opts.forwarder_mode}")


def _write_forwarder_romfs(romfs_dir: Path, next_nro_path: str, next_argv: str) -> None:
    romfs_dir.mkdir(parents=True, exist_ok=True)
    (romfs_dir / "nextNroPath").write_text(next_nro_path, encoding="utf-8")
    (romfs_dir / "nextArgv").write_text(next_argv, encoding="utf-8")


def _resolve_hacbrewpack_exe() -> Optional[Path]:
    repo_dir = Path(__file__).resolve().parents[2]
    hbproot = repo_dir / "tools" / "hacbrewpack"
    exe_name = "hacbrewpack.exe" if os.name == "nt" else "hacbrewpack"
    repo_hbp = hbproot / exe_name

    if repo_hbp.exists():
        return repo_hbp.resolve()

    makefile = hbproot / "Makefile"
    cfg = hbproot / "config.mk"
    cfg_template = hbproot / "config.mk.template"

    if makefile.exists():
        try:
            if not cfg.exists() and cfg_template.exists():
                print("[packer] Creating tools/hacbrewpack/config.mk from template...")
                shutil.copy2(cfg_template, cfg)

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


def _pick_new_nsp(out_dir: Path, before_set: set[Path]) -> Optional[Path]:
    after_set = {p.resolve() for p in out_dir.glob("*.nsp")}
    new_files = list(after_set - before_set)
    if new_files:
        return max(new_files, key=lambda p: p.stat().st_mtime)
    if after_set:
        return max(after_set, key=lambda p: p.stat().st_mtime)
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
