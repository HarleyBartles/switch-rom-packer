from pathlib import Path
from packer.system_detect import LR
from packer.systems import load_pinned_snapshot, validate_detected_targets

ROOT = Path(__file__).resolve().parents[1]

def test_detector_only_emits_known_libretro_names():
    snapshot = load_pinned_snapshot(ROOT / "config" / "libretro_systems_snapshot.json")
    # everything the detector *could* emit must be recognized
    all_targets = set(LR.values()) | {"Unknown"}
    result = validate_detected_targets(all_targets - {"Unknown"}, snapshot)
    assert result.ok, f"Unknown targets: {sorted(result.unknown_targets)}"
