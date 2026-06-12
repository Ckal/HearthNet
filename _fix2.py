"""Fix remaining missed patterns."""
from pathlib import Path

ROOT = Path(r"C:\Users\Chris4K\Projekte\HearthNet")

# config.py - B104 second occurrence
p = ROOT / "hearthnet/config.py"
text = p.read_text(encoding="utf-8")
text = text.replace(
    '            host=str(transport_raw.get("host", "0.0.0.0")),',
    '            host=str(transport_raw.get("host", "0.0.0.0")),  # nosec B104 - intentional: LAN mesh node',
    1,
)
p.write_text(text, encoding="utf-8")
print("config.py B104 patched")

# test_components_real.py - first B017 (FrozenInstanceError line)
p2 = ROOT / "tests/test_components_real.py"
text2 = p2.read_text(encoding="utf-8")
for i, line in enumerate(text2.splitlines(), 1):
    if "pytest.raises(Exception)" in line:
        print(i, repr(line))
