"""Test Python 3.10 compatibility.

Python 3.11+ added datetime.UTC, but HF Spaces runs Python 3.10.
This test ensures we use timezone.utc instead of UTC import.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def test_no_direct_utc_import():
    """Ensure no files import UTC directly from datetime.
    
    UTC was added in Python 3.11. HF Spaces uses Python 3.10.
    All datetime.UTC references must use timezone.utc instead.
    
    Valid:
        from datetime import timezone
        UTC = timezone.utc
    
    Invalid:
        from datetime import UTC
        from datetime import UTC, datetime
    """
    if sys.version_info >= (3, 11):
        # Python 3.11+ allows UTC import, but we standardize on timezone.utc
        pass

    repo_root = Path(__file__).parent.parent
    hearthnet_dir = repo_root / "hearthnet"
    
    invalid_files = []
    
    # Pattern to detect direct UTC imports from datetime
    utc_import_pattern = re.compile(
        r'from\s+datetime\s+import\s+.*\bUTC\b'
    )
    
    for py_file in hearthnet_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        
        # Skip if file uses timezone.utc (correct pattern)
        if "timezone.utc" in content and utc_import_pattern.search(content):
            # Has both - might be a transition, check carefully
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if utc_import_pattern.search(line):
                    # This is the problematic line
                    invalid_files.append(f"{py_file.relative_to(repo_root)}:{i}: {line.strip()}")
        elif utc_import_pattern.search(content):
            # Has UTC import without timezone.utc - definitely wrong
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if utc_import_pattern.search(line):
                    invalid_files.append(f"{py_file.relative_to(repo_root)}:{i}: {line.strip()}")
    
    assert not invalid_files, (
        f"Found {len(invalid_files)} file(s) with direct UTC imports from datetime.\n"
        "Use 'from datetime import timezone' and 'UTC = timezone.utc' instead:\n"
        + "\n".join(invalid_files)
    )
