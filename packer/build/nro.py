from __future__ import annotations

import os
import re
import subprocess
import sys
import hashlib
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont  # Pillow
from packer.io.fsutil import clean_dir


def _ensure_256_jpeg(src: Path, dest: Path) -> Path:
    try:
        img = Image.open(src).convert("RGB")
        # cover-fit & center-crop to 256
        w, h = img.size
        size = 256
        scale = max(size / max(w, 1), size / max(h, 1))
        nw, nh = int(w * scale), int(h * scale)
        img = img.resize((nw, nh), Image.LANCZOS)
        left = (nw - size) // 2
        top = (nh - size) // 2
        img = img.crop((left, top, left + size, top + size))
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, format="JPEG", quality=92)
        return dest
    except Exception:
        return src


def _sanitize_title_for_filename(title: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9 _.\-]", "", title)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe or "app"


def _initials_from_title(title: str, max_chars: int = 2) -> str:
    articles = {"the", "a", "an"}
    words = [w for w in re.split(r"\W+", title) if w]
    if words and words[0].lower() in articles and len(words) > 1:
        words = words[1:]

    initials = []
    for w in words:
        for ch in w:
            if ch.isalnum():
                initials.append(ch.upper())
                break
        if len(initials) >= max_chars:
            break

    if len(initials) < max_chars:
        for ch in title:
            if ch.isalnum():
                c = ch.upper()
                if c not in initials:
                    initials.append(c)
            if len(initials) >= max_chars:
                break

    return "".join(initials[:max_chars]) or "SR"


def _deterministic_bg(title: str) -> Tuple[int, int, int]:
    h = int(hashlib.sha1(title.encode("utf-8")).hexdigest()[:6], 16)
    r = 64 + (h & 0xFF) // 2
    g = 64 + ((h >> 8) & 0xFF) // 2
    b = 64 + ((h >> 16) & 0xFF) // 2
    return (r, g, b)


def _ensure_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _generate_initials_icon_jpeg(dest: Path, title: str, size: int = 256) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    bg = _deterministic_bg(title)
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)

    initials = _initials_from_title(title, 2)
    font = _ensure_font(size=int(size * 0.48))

    try:
        bbox = draw.textbbox((0, 0), initials, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = draw.textsize(initials, font=font)

    luminance = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    fg = (20, 20, 20) if luminance > 140 else (235, 235, 235)

    x = (size - tw) // 2
    y = (size - th) // 2

    # subtle shadow
    draw.text((x + 1, y + 1), initials, font=font, fill=(0, 0, 0))
    draw.text((x, y), initials, font=font, fill=fg)

    img.save(dest, format="JPEG", quality=92)
    print(f"[icons] generated initials icon: {dest} ({initials})")
    return dest


def _is_valid_icon(path: Path) -> bool:
    try:
        if not Path(path).exists():
            return False
        sig = Path(path).read_bytes()[:2]
        return sig == b"\xFF\xD8"  # JPEG magic
    except Exception:
        return False


def _resolve_icon_env(stub_dir: Path, icon_path: Optional[Path], hb_title: str) -> str:
    """
    Return a filesystem path to a JPEG icon to pass as APP_ICON.
    - If icon_path is a valid JPEG, just return it (no copy into stub/).
    - Otherwise, generate initials into stub/icon.jpg and return that.
    """
    if icon_path and icon_path.exists() and _is_valid_icon(icon_path):
        # If not guaranteed 256x256 JPEG, normalize into stub/icon.jpg
        normalized = stub_dir / "icon.jpg"
        out = _ensure_256_jpeg(icon_path, normalized)
        
        print(f"[icons] using ICON file: {out}")
        return str(out)

    # Fallback: generate deterministic initials icon in stub
    dest = stub_dir / "icon.jpg"
    _generate_initials_icon_jpeg(dest, hb_title, size=256)
    return str(dest)


def build_nro_for_rom(
    stub_dir: Path,
    out_dir: Path,
    platform: str,
    rom_path: Path,
    hb_title: str,
    icon_path: Optional[Path],
    *,
    author: str = "Switch Rom Packer",
    version: str = "1.0.0",
    make_clean: bool = True,
) -> Path:
    stub_dir = Path(stub_dir)
    out_dir = Path(out_dir)
    romfs_dir = stub_dir / "romfs"

    # 1) Clean first, so we don't lose icon/romfs later.
    if make_clean:
        print("clean ...")
        subprocess.run(["make", "clean"], cwd=stub_dir, check=False, env=os.environ.copy())

    # 2) Prepare RomFS after clean.
    if not romfs_dir.exists():
        clean_dir(romfs_dir)

    dest_rom = romfs_dir / rom_path.name
    if not dest_rom.exists():
        dest_rom.write_bytes(rom_path.read_bytes())

    # 3) Resolve APP_* env (icon AFTER clean so it survives).
    env = os.environ.copy()
    env["APP_TITLE"] = hb_title
    env["APP_AUTHOR"] = author
    env["APP_VERSION"] = version

    # IMPORTANT: point APP_ICON at a stable path (cache) when possible.
    env["APP_ICON"] = _resolve_icon_env(stub_dir, icon_path, hb_title)
    print(f"[icons] using provided icon -> {env['APP_ICON']}")

    # 4) Build
    rc = subprocess.run(["make"], cwd=stub_dir, env=env)
    if rc.returncode != 0:
        print(f"[error] make failed with exit code {rc.returncode}")
        sys.exit(rc.returncode)

    # 5) Move resulting NRO
    nro_dir = out_dir / "nro"
    nro_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _sanitize_title_for_filename(hb_title)
    nro_out = nro_dir / f"{safe_title}.nro"

    built = stub_dir / "stub.nro"
    if not built.exists():
        print(f"[error] expected built NRO not found: {built}")
        sys.exit(2)

    try:
        built.replace(nro_out)
    except Exception:
        nro_out.write_bytes(built.read_bytes())
        built.unlink(missing_ok=True)

    return nro_out
