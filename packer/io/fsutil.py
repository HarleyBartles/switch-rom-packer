# packer/io/fsutil.py
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Tuple, List


def ensure_dir(p: Path) -> None:
    """Create directory (and parents) if it doesn't exist."""
    Path(p).mkdir(parents=True, exist_ok=True)


def clean_dir(p: Path) -> None:
    """Delete a file/dir at path (if present) and recreate as an empty dir."""
    p = Path(p)
    if p.exists():
        if p.is_file():
            p.unlink()
        else:
            shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """
    Write text to a temporary file in the same directory and atomically replace the target.
    Prevents partial writes if the process is interrupted.
    """
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        Path(tmp).replace(path)
    finally:
        try:
            if Path(tmp).exists():
                Path(tmp).unlink()
        except Exception:
            pass


def copy_into(src: Path, dst_dir: Path) -> Path:
    """
    Copy a file into a directory (creating the directory if needed).
    Returns the destination path.
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    ensure_dir(dst_dir)
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst


def write_filelist(filelist_path: Path, entries: List[Tuple[str, str]]) -> None:
    """
    Write lines of the form '<platform> <filename>' expected by the stub.
    `entries` should be a list of (platform, filename) pairs.
    """
    lines: Iterable[str] = (f"{plat} {name}\n" for plat, name in entries)
    atomic_write_text(filelist_path, "".join(lines))
    print(f"[packer] Wrote {len(entries)} entries to {filelist_path}")
