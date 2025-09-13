# Switch Rom Packer Utility — Roadmap

This project aims to make it simple to **pack ROMs into installable Switch titles (NSPs)**, with proper system detection, icons, and RetroArch forwarder integration.  

---

## ✅ Phase 0: Foundations (done / in progress)
- [x] Working **libnx stub** reads `filelist.txt` from RomFS and copies ROMs into `/roms/<system>/<rom>`.
- [x] `packer.py` orchestrator:
  - Scans ROMs automatically
  - Detects system type
  - Writes `filelist.txt` with correct **Libretro thumbnails folder names**
  - Builds per-ROM NROs with dynamic hbmenu titles (and optional icons).
- [x] **Makefile** updated to accept `APP_TITLE`, `APP_AUTHOR`, `APP_VERSION`, `ICON`.
- [x] **Validation + snapshot** of Libretro system folder names, with tests.

---

## 🛠 Phase 1: NSP Forwarder Pipeline
- [ ] Integrate **hacBrewPack** to build valid NSPs.
- [ ] Automate per-ROM forwarder generation:
  - Each ROM = its own NSP forwarder
  - Forwarder launches RetroArch with correct core/system.
- [ ] Support optional **custom icons** (downloaded automatically).
- [ ] Verify NSPs install and launch cleanly on Switch hardware.

---

## 🎨 Phase 2: UX Improvements
- [ ] **Auto-fetch game icons/artwork**:
  - Primary: [Libretro thumbnails repo](https://github.com/libretro-thumbnails/libretro-thumbnails).
  - Fallback: free/open game databases (Screenscraper, MobyGames, IGDB FOSS forks).
- [ ] Embed icons directly into NRO/NSP at build time.
- [ ] Add progress + summary output (packed, skipped, failed).
- [ ] Add `--dry-run` mode for safety.

---

## 📦 Phase 3: Retro System Expansion
- [ ] Extend system detection to more consoles (WonderSwan, MSX, Amstrad CPC, etc.).
- [ ] Validate expanded systems against Libretro snapshot.
- [ ] Unit tests for new detection heuristics (magic bytes, extensions, folder hints).

---

## 🚀 Phase 4: Distribution & Polish
- [ ] Write `README.md` usage guide.
- [ ] Provide Dockerfile or installer script for easy setup.
- [ ] CI pipeline:
  - Run tests
  - Verify packer builds
  - Optionally auto-update Libretro snapshot.

---

## 🔮 Phase 5: Optional / Stretch Goals
- [ ] **PlayStation Vita support**:
  - Add `.vpk` / `.pkg` detection.
  - Use custom folder name (`Sony - PlayStation Vita`) since Libretro thumbnails has no Vita.
  - Forwarder support if feasible (though Switch likely won’t emulate Vita well).
- [ ] Support for other **non-Libretro platforms** (DOSBox, ScummVM, ports).
- [ ] Advanced features:
  - Batch forwarders (one NSP with multiple ROMs).
  - Metadata scraping (game descriptions, publisher info, etc.).

---

## Summary

**Short-term**: get per-ROM NSP forwarders working.  
**Medium-term**: add icons/artwork and polish the UX.  
**Long-term**: expand to more systems, then explore Vita and other stretch targets.
