from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

from .fsutil import atomic_write_text


def write_filelist(filelist_path: Path, entries: Iterable[Tuple[str, str]]) -> None:
    """
    Write lines of the form '<platform> <filename>' expected by the stub.
    
    Args:
        filelist_path: destination file path
        entries: iterable of (platform, filename) pairs
    """
    lines = (f"{plat} {fname}\n" for plat, fname in entries)
    atomic_write_text(filelist_path, "".join(lines))
    print(f"[packer] Wrote {len(list(entries))} entries to {filelist_path}")
