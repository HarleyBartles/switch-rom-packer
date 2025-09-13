from pathlib import Path
from packer.system_detect import LR
from packer.systems import load_pinned_snapshot

ROOT = Path(__file__).resolve().parents[1]

def test_snapshot_contains_common_systems():
    snapshot = load_pinned_snapshot(ROOT / "config" / "libretro_systems_snapshot.json")
    must_have = {
        "Nintendo - Super Nintendo Entertainment System",
        "Sega - Mega Drive - Genesis",
        "Sony - PlayStation",
    }
    assert must_have.issubset(snapshot), "Snapshot missing common systems."

def test_all_lr_values_are_strings():
    for code, name in LR.items():
        assert isinstance(name, str) and name, f"Bad LR mapping for {code}: {name!r}"
