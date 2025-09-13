# packer/systems.py
from __future__ import annotations
from pathlib import Path
from typing import Set, List, Dict
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass

LIBRETRO_THUMBS_ROOT = (
    "https://api.github.com/repos/libretro-thumbnails/libretro-thumbnails/contents"
)
DEFAULT_CACHE_SECONDS = 7 * 24 * 3600  # 7 days

@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    unknown_targets: Set[str]
    notes: List[str]

def load_pinned_snapshot(snapshot_path: Path) -> Set[str]:
    with snapshot_path.open("r", encoding="utf-8") as f:
        items = json.load(f)
    return set(items)

def _http_get_json(url: str, headers: Dict[str, str]) -> List[dict]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8"))

def fetch_live_libretro_folders(
    cache_path: Path,
    max_age_seconds: int = DEFAULT_CACHE_SECONDS,
    github_token: str | None = None,
) -> Set[str]:
    now = time.time()
    if cache_path.exists():
        age = now - cache_path.stat().st_mtime
        if age < max_age_seconds:
            with cache_path.open("r", encoding="utf-8") as f:
                return set(json.load(f))

    headers = {"User-Agent": "switch-rom-packer/1.0"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    data = _http_get_json(LIBRETRO_THUMBS_ROOT, headers)
    folders = {item["name"] for item in data if item.get("type") == "dir"}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(sorted(folders), f, indent=2)
    tmp.replace(cache_path)
    return folders

def validate_detected_targets(
    detected_targets: Set[str],
    libretro_folders: Set[str],
) -> ValidationResult:
    unknown = {t for t in detected_targets if t not in libretro_folders}
    notes: List[str] = []
    if unknown:
        notes.append(f"Unrecognized outputs (not in Libretro): {sorted(unknown)}")
    return ValidationResult(ok=not unknown, unknown_targets=unknown, notes=notes)
