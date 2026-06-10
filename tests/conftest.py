from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Allow nested asyncio event loops so that sync tests using asyncio.run() can
# coexist with @pytest.mark.asyncio tests managed by pytest-asyncio.
# Needed for Python 3.13 + pytest-asyncio 0.26 where loop teardown is strict.
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass
