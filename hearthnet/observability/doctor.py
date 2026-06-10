"""HearthNet — X03 Observability: Self-diagnostics (doctor).

Public API:
    run_all()        — run every registered check, return results
    run_one(name)    — run a single check by name
    DoctorCheck      — dataclass describing a check
    DoctorResult     — dataclass with check outcome
"""

from __future__ import annotations

import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hearthnet.config import _default_config_path, _xdg_config

# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class DoctorCheck:
    name: str
    description: str
    fix_hint: str = ""


@dataclass
class DoctorResult:
    check: DoctorCheck
    passed: bool
    message: str
    extra: dict[str, Any] = field(default_factory=dict)


# ── Check registry ───────────────────────────────────────────────────────────

_CHECK_FN: dict[str, tuple[DoctorCheck, Callable[[], DoctorResult]]] = {}


def _register(check: DoctorCheck) -> Callable:
    def _decorator(fn: Callable[[], DoctorResult]) -> Callable[[], DoctorResult]:
        _CHECK_FN[check.name] = (check, fn)
        return fn

    return _decorator


# ── Built-in checks ──────────────────────────────────────────────────────────

_KEYS_CHECK = DoctorCheck(
    name="keys_present",
    description="Check that the keys directory exists.",
    fix_hint="Run `hearthnet keys generate` to create a device key-pair.",
)


@_register(_KEYS_CHECK)
def _keys_present() -> DoctorResult:
    keys_dir = _xdg_config() / "keys"
    exists = keys_dir.is_dir()
    return DoctorResult(
        check=_KEYS_CHECK,
        passed=exists,
        message=f"Keys directory {'found' if exists else 'missing'}: {keys_dir}",
        extra={"path": str(keys_dir)},
    )


_KEYS_LOADABLE_CHECK = DoctorCheck(
    name="keys_loadable",
    description="Verify that device.pub can be read from the keys directory.",
    fix_hint="Run `hearthnet keys generate` or restore the key file.",
)


@_register(_KEYS_LOADABLE_CHECK)
def _keys_loadable() -> DoctorResult:
    pub = _xdg_config() / "keys" / "device.pub"
    try:
        data = pub.read_bytes()
        return DoctorResult(
            check=_KEYS_LOADABLE_CHECK,
            passed=True,
            message=f"device.pub read OK ({len(data)} bytes)",
            extra={"path": str(pub), "size": len(data)},
        )
    except FileNotFoundError:
        return DoctorResult(
            check=_KEYS_LOADABLE_CHECK,
            passed=False,
            message=f"device.pub not found at {pub}",
            extra={"path": str(pub)},
        )
    except OSError as exc:
        return DoctorResult(
            check=_KEYS_LOADABLE_CHECK,
            passed=False,
            message=f"Could not read device.pub: {exc}",
            extra={"path": str(pub), "error": str(exc)},
        )


_CONFIG_CHECK = DoctorCheck(
    name="config_loadable",
    description="Verify that config.toml can be parsed.",
    fix_hint="Run `hearthnet config init` or fix syntax in config.toml.",
)


@_register(_CONFIG_CHECK)
def _config_loadable() -> DoctorResult:
    cfg_path = _default_config_path()
    if not cfg_path.exists():
        return DoctorResult(
            check=_CONFIG_CHECK,
            passed=False,
            message=f"config.toml not found at {cfg_path}",
            extra={"path": str(cfg_path)},
        )
    try:
        # Attempt to parse without full config validation
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                return DoctorResult(
                    check=_CONFIG_CHECK,
                    passed=False,
                    message="No TOML parser available (tomllib/tomli missing)",
                )
        with open(cfg_path, "rb") as fh:
            tomllib.load(fh)
        return DoctorResult(
            check=_CONFIG_CHECK,
            passed=True,
            message=f"config.toml parsed OK: {cfg_path}",
            extra={"path": str(cfg_path)},
        )
    except Exception as exc:
        return DoctorResult(
            check=_CONFIG_CHECK,
            passed=False,
            message=f"config.toml parse error: {exc}",
            extra={"path": str(cfg_path), "error": str(exc)},
        )


_MDNS_CHECK = DoctorCheck(
    name="mdns_socket",
    description="Try to bind the mDNS multicast port (5353).",
    fix_hint="Check if another mDNS daemon (avahi, bonjour) is already running.",
)

_MDNS_PORT = 5353


@_register(_MDNS_CHECK)
def _mdns_socket() -> DoctorResult:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", _MDNS_PORT))
            sock.close()
            return DoctorResult(
                check=_MDNS_CHECK,
                passed=True,
                message=f"mDNS port {_MDNS_PORT} bindable",
                extra={"port": _MDNS_PORT},
            )
        except OSError as exc:
            sock.close()
            return DoctorResult(
                check=_MDNS_CHECK,
                passed=False,
                message=f"Cannot bind mDNS port {_MDNS_PORT}: {exc}",
                extra={"port": _MDNS_PORT, "error": str(exc)},
            )
    except Exception as exc:
        return DoctorResult(
            check=_MDNS_CHECK,
            passed=False,
            message=f"Socket error: {exc}",
            extra={"error": str(exc)},
        )


_LOG_DIR_CHECK = DoctorCheck(
    name="log_dir_writable",
    description="Check that the log directory is writable.",
    fix_hint="Ensure the process has write access to the log directory (chmod or set log_dir in config).",
)


@_register(_LOG_DIR_CHECK)
def _log_dir_writable() -> DoctorResult:
    from hearthnet.config import _xdg_data

    log_dir = _xdg_data() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        test_file = log_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return DoctorResult(
            check=_LOG_DIR_CHECK,
            passed=True,
            message=f"Log directory is writable: {log_dir}",
            extra={"path": str(log_dir)},
        )
    except OSError as exc:
        return DoctorResult(
            check=_LOG_DIR_CHECK,
            passed=False,
            message=f"Log directory not writable: {exc}",
            extra={"path": str(log_dir), "error": str(exc)},
        )


_DISK_CHECK = DoctorCheck(
    name="disk_space",
    description="Warn if available disk space is below 500 MB.",
    fix_hint="Free up disk space or move data directories to a larger volume.",
)

_DISK_WARN_BYTES = 500 * 1024 * 1024  # 500 MB


@_register(_DISK_CHECK)
def _disk_space() -> DoctorResult:
    from hearthnet.config import _xdg_data

    target = _xdg_data()
    try:
        target.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(target))
        free_mb = usage.free / (1024 * 1024)
        passed = usage.free >= _DISK_WARN_BYTES
        return DoctorResult(
            check=_DISK_CHECK,
            passed=passed,
            message=(
                f"Disk free: {free_mb:.0f} MB"
                if passed
                else f"Low disk space: {free_mb:.0f} MB free (threshold 500 MB)"
            ),
            extra={"free_bytes": usage.free, "total_bytes": usage.total, "path": str(target)},
        )
    except OSError as exc:
        return DoctorResult(
            check=_DISK_CHECK,
            passed=False,
            message=f"Could not check disk space: {exc}",
            extra={"error": str(exc)},
        )


# ── Public functions ──────────────────────────────────────────────────────────


def run_all() -> list[DoctorResult]:
    """Run all registered checks and return their results."""
    results = []
    for _check, fn in _CHECK_FN.values():
        try:
            results.append(fn())
        except Exception as exc:
            results.append(
                DoctorResult(
                    check=_check,
                    passed=False,
                    message=f"Check raised an unexpected error: {exc}",
                    extra={"error": str(exc)},
                )
            )
    return results


def run_one(name: str) -> DoctorResult:
    """Run a single check by name. Raises KeyError for unknown names."""
    entry = _CHECK_FN.get(name)
    if entry is None:
        known = ", ".join(sorted(_CHECK_FN))
        raise KeyError(f"Unknown doctor check {name!r}. Known checks: {known}")
    _check, fn = entry
    try:
        return fn()
    except Exception as exc:
        return DoctorResult(
            check=_check,
            passed=False,
            message=f"Check raised an unexpected error: {exc}",
            extra={"error": str(exc)},
        )
