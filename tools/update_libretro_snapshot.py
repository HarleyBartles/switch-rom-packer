from pathlib import Path
import sys
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packer.systems import fetch_live_libretro_folders

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="config/libretro_systems_snapshot.json")
    ap.add_argument("--cache", default=".cache/libretro_folders.json")
    ap.add_argument("--github-token", default=None)
    args = ap.parse_args()

    folders = fetch_live_libretro_folders(
        Path(args.cache), max_age_seconds=0, github_token=args.github_token
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(sorted(folders), f, indent=2)
    print(f"Wrote {len(folders)} Libretro folder names to {out}")

if __name__ == "__main__":
    main()
