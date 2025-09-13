from __future__ import annotations
import io, os
from pathlib import Path
from typing import Iterable
from PIL import Image, ImageDraw, ImageFont
from providers.libretro_thumbs import fetch_icon_256_png

# Cache folder (~/.switch-rom-packer/cache/icons or override with env var)
CACHE_DIR = (
    Path(os.environ.get("SRP_ICON_CACHE", ""))
    if os.environ.get("SRP_ICON_CACHE")
    else (Path.home() / ".switch-rom-packer" / "cache" / "icons")
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in s.strip())[:140]

def _placeholder_256(title: str) -> bytes:
    img = Image.new("RGBA", (256, 256), (34, 34, 42, 255))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    initials = "".join([w[0] for w in title.split()[:3] if w and w[0].isalnum()]).upper() or "?"
    bbox = d.textbbox((0, 0), initials, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((256 - w) // 2, (256 - h) // 2), initials, fill=(230, 230, 235, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # no optimize, keep raw RGBA
    return buf.getvalue()

def get_icon_file(
    title: str,
    playlist_name: str,
    alt_titles: Iterable[str] = (),
    debug: bool = False
) -> Path:
    key = f"{playlist_name}__{title}"
    out = CACHE_DIR / f"{_slug(key)}.png"
    if out.exists() and out.stat().st_size > 0:
        if debug:
            print(f"[icons] cache hit: {out}")
        return out
    data, debug_info = fetch_icon_256_png(title, playlist_name, alt_titles, debug=debug)
    if not data:
        data = _placeholder_256(title)
        if debug:
            print(f"[icons] placeholder used for: {title}")
    else:
        if debug and debug_info:
            match = debug_info.get("match")
            score = debug_info.get("score")
            print(f"[icons] matched '{match}' (score {score:.3f})" if score is not None else f"[icons] matched '{match}'")
    out.write_bytes(data)
    return out
