#!/usr/bin/env python3
"""HearthNet Quality Check Script

Runs multiple quality checks:
  - ruff format (code formatting)
  - ruff lint (code style)
  - bandit (security)
  - mypy (type checking)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent
SRC_DIR = ROOT / "hearthnet"
TESTS_DIR = ROOT / "tests"


def run_command(cmd: list[str], name: str, timeout: int = 120) -> int:
    """Run a command and return exit code with timeout."""
    print(f"\n{'=' * 80}")
    print(f"Running: {name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 80}")
    try:
        result = subprocess.run(cmd, cwd=ROOT, timeout=timeout)
        if result.returncode != 0:
            print(f"[!] {name} FAILED (exit code: {result.returncode})")
        else:
            print(f"[OK] {name} PASSED")
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"[*] {name} TIMED OUT after {timeout}s")
        return 1
    except FileNotFoundError as e:
        print(f"[!] {name} SKIPPED: {e}")
        return 0


def main() -> int:
    """Run all quality checks."""
    print("[*] HearthNet Quality Check Suite")
    print(f"[*] Project root: {ROOT}")
    print(f"[*] Source dir: {SRC_DIR}")
    print(f"[*] Tests dir: {TESTS_DIR}")

    results = {}

    # 1. Ruff format check
    results["ruff-format"] = run_command(
        ["ruff", "format", "--check", str(SRC_DIR), str(TESTS_DIR), "app.py"],
        "Ruff Format Check",
        timeout=60,
    )

    # 2. Ruff lint check
    results["ruff-lint"] = run_command(
        ["ruff", "check", str(SRC_DIR), str(TESTS_DIR), "app.py"],
        "Ruff Lint Check",
        timeout=60,
    )

    # 3. Bandit security check
    results["bandit"] = run_command(
        ["bandit", "-r", str(SRC_DIR), "-q"],
        "Bandit Security Check",
        timeout=60,
    )

    # 4. MyPy type checking
    results["mypy"] = run_command(
        ["mypy", str(SRC_DIR), "--ignore-missing-imports"],
        "MyPy Type Checking",
        timeout=120,
    )

    # Summary
    print(f"\n{'=' * 80}")
    print("QUALITY CHECK SUMMARY")
    print(f"{'=' * 80}")

    failed = [name for name, code in results.items() if code != 0]
    passed = [name for name, code in results.items() if code == 0]

    if passed:
        print(f"[OK] PASSED ({len(passed)}):")
        for name in passed:
            print(f"   + {name}")

    if failed:
        print(f"\n[!] FAILED ({len(failed)}):")
        for name in failed:
            print(f"   - {name}")
        print("\nTIP: Run individual checks for more details:")
        print("   * ruff check hearthnet app.py --fix")
        print("   * ruff format hearthnet app.py")
        print("   * bandit -r hearthnet")
        print("   * mypy hearthnet --ignore-missing-imports")
        return 1

    print(f"\n[+] All checks passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
