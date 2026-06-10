from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BootstrapConfig:
    peers: list[str]
    relay_url: str | None = None


_DEFAULT_PEERS: list[str] = ["relay.hearthnet.de:7080"]


def load_bootstrap(config_path: str | Path | None = None) -> BootstrapConfig:
    """Load bootstrap configuration from a JSON file, or return defaults.

    The config file is optional and its absence or any error is handled
    gracefully by returning the built-in default peers.

    Expected JSON schema::

        {
            "peers": ["host:port", ...],
            "relay_url": "https://relay.hearthnet.de"   // optional
        }
    """
    if config_path is not None:
        path = Path(config_path)
        if path.is_file():
            try:
                data: Any = json.loads(path.read_text(encoding="utf-8"))
                peers: list[str] = data.get("peers", _DEFAULT_PEERS)
                relay_url: str | None = data.get("relay_url")
                return BootstrapConfig(peers=peers, relay_url=relay_url)
            except Exception:
                pass  # fall through to defaults

    # Auto-discover relay_url from XDG config if possible
    try:
        from hearthnet.config import _default_config_path, load  # noqa: PLC0415

        cfg_file = _default_config_path()
        if cfg_file.is_file():
            cfg = load(cfg_file)
            relay_url = getattr(cfg, "relay_url", None)
            return BootstrapConfig(peers=list(_DEFAULT_PEERS), relay_url=relay_url)
    except Exception:
        pass

    return BootstrapConfig(peers=list(_DEFAULT_PEERS), relay_url=None)
