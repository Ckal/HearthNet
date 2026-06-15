"""scripts/check_deps_sync.py — assert requirements.txt covers pyproject.toml deps.

Run in CI:  python scripts/check_deps_sync.py
Exit 0 = in sync.  Exit 1 = missing packages listed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _pkg_name(spec: str) -> str:
    """Strip version constraints and extras, return normalised package name."""
    name = re.split(r"[>=<!;\[]", spec.strip())[0].strip()
    return name.lower().replace("-", "_").replace(".", "_")


def _pyproject_deps() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text()
    in_deps = False
    deps: list[str] = []
    for line in text.splitlines():
        if line.strip() == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if line.strip() == "]":
                break
            dep = line.strip().strip('",').strip()
            if dep:
                deps.append(dep)
    return deps


def _requirements_names() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    names: set[str] = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        names.add(_pkg_name(line))
    return names


def main() -> int:
    pyproject_deps = _pyproject_deps()
    req_names = _requirements_names()
    missing: list[str] = []
    for dep in pyproject_deps:
        if _pkg_name(dep) not in req_names:
            missing.append(dep)
    if missing:
        print("ERROR: pyproject.toml deps missing from requirements.txt:")
        for m in missing:
            print(f"  {m}")
        return 1
    print(f"OK: all {len(pyproject_deps)} pyproject.toml deps present in requirements.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
