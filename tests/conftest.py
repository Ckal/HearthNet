from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

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


@pytest.fixture(autouse=True)
def _ensure_current_event_loop():
    """Guarantee every test starts with an open current event loop.

    Python 3.13 no longer auto-creates an event loop on demand, and
    ``asyncio.run()`` resets the current loop to ``None`` when it exits. Many
    sync tests in this suite call ``asyncio.get_event_loop().run_until_complete``
    or build coroutines via ``asyncio.gather(...)`` outside a running loop, both
    of which require a current loop to exist. Without this fixture those tests
    fail or pass purely depending on the order in which test files happen to
    run. Setting a fresh loop per test makes the suite order-independent.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        try:
            loop.close()
        finally:
            # Leave an open loop set as current for any teardown/collection
            # work that runs between this test and the next one's setup.
            asyncio.set_event_loop(asyncio.new_event_loop())
