# Retro ROM → Switch NSP Packer

A command-line utility that converts classic ROMs (NES/SNES/Genesis/…​) into installable Nintendo Switch titles.

- Each generated **NRO** wraps a single ROM using a tiny libnx stub.
- On first launch the stub copies the ROM to `/roms/<platform>/` on SD.
- (Planned) Build **NSP** forwarders to launch RetroArch with the ROM.
- Designed to batch through large libraries with minimal config.

> **Project status:** Early WIP (Sep 13, 2025). Working libnx stub + Python packer pipeline for per-ROM NROs is in place; NSP build/forwarder flow and icon auto-fetch are next.

---

## Quick start

### Requirements

- **devkitPro + libnx** installed and on `PATH`.
- **Python 3.10+** for the packer.
- **Pillow** (installed via requirements.txt) for generating fallback icons.
- A working **Makefile** in `stub/` (provided) that accepts:
  - `APP_TITLE`, `APP_AUTHOR`, `APP_VERSION`, `ICON`
  - `ROMFS` folder contents (autopopulated by the packer)

### Build a batch of NROs

```bash
# Example:
python3 packer.py ~/rom_input/
```

**Notes:**

- `rom_root` is the **positional first argument** (e.g. `~/rom_input/`).
- `--build-nro` is **on by default**; you don’t need to pass it.
- `--stub-dir`, `--output-dir`, and `--filelist-out` all have sensible defaults.
- The packer writes a `filelist.txt` into the stub’s RomFS (platform + filename)
  which the stub reads to copy the ROM to `/roms/<platform>/<romfile>` at first launch.

---

## How it works

1. **packer.py** discovers ROMs under `rom_root`, infers platform (simple rules for now), then:
   - Generates a per-ROM stub **RomFS** with a `filelist.txt`.
   - Calls the stub **Makefile** to produce a per-ROM **NRO** with dynamic title and icon.  
     If no icon is provided, a fallback initials-based JPEG is generated automatically.
   - Writes outputs to the chosen `--output-dir`.

2. **stub/** (libnx) boots, reads `filelist.txt`, and performs a one-time copy to the SD card.

3. **Planned**: Use **hacBrewPack** to produce **NSPs**, and emit RetroArch **forwarder NSPs** so installed titles show up on the HOME menu and launch directly into the game.

---

## Setup

It’s recommended to use a Python virtual environment to keep dependencies isolated.

```bash
# create a venv in the project root (only once)
python3 -m venv .venv

# activate it
# on Linux/macOS:
source .venv/bin/activate
# on Windows (PowerShell):
.venv\Scripts\Activate.ps1

# install dependencies into the venv
pip install -r requirements.txt
```

---

## Usage (packer.py)

```
usage: packer.py [-h] [--build-nro/--no-build-nro]
                 [--stub-dir STUB_DIR] [--output-dir OUTPUT_DIR]
                 [--filelist-out FILELIST_OUT]
                 rom_root
```

- `rom_root` (positional): directory containing your ROMs.
- `--build-nro` (default **enabled**): produce NROs via the stub Makefile. Use `--no-build-nro` to disable.
- `--no-build-nro`: use to disable NRO output.
- `--stub-dir`: path to the libnx stub (default: `./stub`).
- `--output-dir`: directory for generated NROs (sensible default).
- `--filelist-out`: where to write the stub’s `filelist.txt` (default aligns with stub layout).
- `--debug-icons`: enable additional logging during icon lookup.
- `--icon-preference` (default **logos**): choose icon preference. options [**boxarts**, **logos**]

> Current platforms and icon rules are intentionally minimal; see the roadmap for what’s next.

---

## Development

- The Makefile is wired so the packer can set `APP_TITLE/APP_AUTHOR/APP_VERSION/ICON`
  and populate **RomFS** for each ROM build automatically.
- Tests and simple fixtures live under `test/`.

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Roadmap

### ✅ Done / baseline

- **libnx stub** that reads `filelist.txt` and copies to `/roms/<platform>/<romfile>`.
- **Python packer** that:
  - Takes `rom_root` as positional arg.
  - Defaults `--build-nro` to **on**.
  - Provides sensible defaults for `--stub-dir`, `--output-dir`, `--filelist-out`.
  - Integrates with the Makefile (RomFS auto-population, dynamic titles, optional icon).
  - Generates fallback initials icons when none are provided.

### 🚧 In progress / next up

1. **NSP build integration**
   - Wire up **hacBrewPack** from the packer to emit per-ROM NSPs.
   - Create a **RetroArch forwarder NSP** flow: install a small forwarder that launches RetroArch and immediately boots the copied ROM with the correct core.

2. **Icon pipeline**
   - Auto-fetch a square icon per game from a **FOSS game DB** (no restrictive rate limits; API key OK).
   - Embed icon into the **NRO** now; reuse it later for **NSPs**.
   - If no icon is found, the packer falls back to a generated initials-based JPEG.
   - Caching and a simple override mechanism (drop `*.png` alongside the ROM to force a specific icon).

3. **Platform detection & metadata**
   - Expand platform inference rules (by folder name and filename suffixes).
   - Optional manifest file to pin platform/core when heuristics are ambiguous.

4. **RetroArch core mapping**
   - Maintain a simple map: `<platform> -> <core name>`.
   - Allow per-title overrides.

5. **Quality & DX**
   - Dry-run mode, better logging, progress bars for big batches.
   - Structured outputs + summary table at the end (counts, failures).
   - CI checks (format, lint, stub compiles).

### 📌 Nice-to-haves

- Optional content-hash de-duplication (skip rebuild if ROM+settings unchanged).
- Simple HTML report of a batch (titles, platforms, icon hits/misses).
- Pluggable “icon providers” (try multiple FOSS sources in order).

### ❓ Out of scope (for now)

- Live scraping of non-FOSS or rate-limited sources.
- Multi-ROM compilations in a single title (e.g., collections).

---

## Known limitations

- No NSP output yet — forwarder flow is planned but not implemented.
- Platform detection is heuristic and may need manual overrides for edge cases.
- Icon auto-fetch is not fully implemented; fallback initials icons are generated,
  or icons can be supplied manually per build.

---

## FAQ

**Q: Can I just run `python3 packer.py ~/rom_input/` without extra flags?**  
Yes. That’s the intended default path: it builds NROs using sensible defaults.

**Q: Where do ROMs end up on the SD card?**  
On first run the stub copies them to `/roms/<platform>/<romfile>`.

**Q: Will these show up as installable titles on HOME?**  
Not yet. That’s what the NSP + forwarder pipeline will enable.

---

## License

[MIT](LICENSE)
