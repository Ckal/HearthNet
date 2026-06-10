"""HearthNet CLI — `hearthnet` command."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import zipfile
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _validate_local_url(url: str) -> None:
    """Raise ValueError if the URL is not a local node URL (security boundary)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme must be http/https, got: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if host not in _ALLOWED_HOSTS:
        raise ValueError(
            f"CLI only connects to local node. Got host: {host!r}. "
            "Use --base-url http://localhost:<port> to override."
        )


def _http_get(url: str) -> dict:
    _validate_local_url(url)
    try:
        import httpx

        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except ImportError:
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return json.loads(r.read().decode())
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc)) from exc
    except Exception as exc:
        msg = str(exc).lower()
        if any(kw in msg for kw in ("connect", "refused", "unreachable", "network")):
            raise ConnectionError(str(exc)) from exc
        raise


def _http_post(url: str, body: str) -> dict:
    _validate_local_url(url)
    try:
        import httpx

        resp = httpx.post(
            url, content=body, headers={"Content-Type": "application/json"}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except ImportError:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            url,
            data=body.encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc)) from exc
    except Exception as exc:
        msg = str(exc).lower()
        if any(kw in msg for kw in ("connect", "refused", "unreachable", "network")):
            raise ConnectionError(str(exc)) from exc
        raise


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--config", "config_path", type=click.Path(), default=None, help="Path to config.toml"
)
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    """HearthNet — community-owned local AI mesh."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config_path) if config_path else None


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@main.command()
@click.option("--name", default=None, help="Display name for this node")
@click.option(
    "--profile",
    type=click.Choice(["anchor", "hearth", "spark"]),
    default="hearth",
)
@click.option("--non-interactive", is_flag=True)
def init(name: str | None, profile: str, non_interactive: bool) -> None:
    """Bootstrap a new HearthNet node. Generates keypair, writes config."""
    config_dir = Path.home() / ".hearthnet"
    config_dir.mkdir(parents=True, exist_ok=True)
    keys_dir = config_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)

    if not name and not non_interactive:
        name = click.prompt("Node display name", default=f"HearthNode-{os.urandom(2).hex()}")
    elif not name:
        name = f"HearthNode-{os.urandom(2).hex()}"

    try:
        from hearthnet.identity import load_or_generate

        kp = load_or_generate(keys_dir)
        click.echo(f"Node ID  : {kp.node_id_full}")
        click.echo(f"Short ID : {kp.node_id_short}")
    except Exception as exc:
        click.echo(f"Warning: could not generate keypair ({exc}). Skipping.", err=True)

    config_file = config_dir / "config.toml"
    if not config_file.exists():
        config_file.write_text(
            f'[node]\nname = "{name}"\nprofile = "{profile}"\n\n[identity]\nkeys_dir = "{keys_dir}"\n'
        )
        click.echo(f"Config written to {config_file}")
    else:
        click.echo(f"Config already exists at {config_file} — not overwritten.")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@main.command()
@click.option("--no-ui", is_flag=True, help="Run without Gradio UI")
@click.option("--debug", is_flag=True)
@click.pass_context
def run(ctx: click.Context, no_ui: bool, debug: bool) -> None:
    """Start the HearthNet node."""
    if debug:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    click.echo("HearthNet node starting…")

    if not no_ui:
        try:
            from app import demo  # type: ignore[import]

            demo.launch()
        except Exception as exc:
            click.echo(f"Could not start Gradio UI: {exc}", err=True)
            click.echo("Try `hearthnet run --no-ui` to start without UI.")
            sys.exit(1)
    else:
        click.echo("Running in headless mode. Press Ctrl+C to stop.")
        try:
            asyncio.run(_headless())
        except KeyboardInterrupt:
            click.echo("Shutting down.")


async def _headless() -> None:
    while True:
        await asyncio.sleep(3600)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@main.command()
@click.option("--json", "as_json", is_flag=True)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
@click.pass_context
def status(ctx: click.Context, as_json: bool, host: str, port: int) -> None:
    """Show node status (requires a running node)."""
    url = f"http://{host}:{port}/health"
    try:
        data = _http_get(url)
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Status   : {data.get('status', 'unknown')}")
        click.echo(f"Node ID  : {data.get('node_id', 'N/A')}")
        click.echo(f"Version  : {data.get('version', 'N/A')}")
        extras = {k: v for k, v in data.items() if k not in ("status", "node_id", "version")}
        for k, v in extras.items():
            click.echo(f"{k:<10}: {v}")


# ---------------------------------------------------------------------------
# caps
# ---------------------------------------------------------------------------


@main.command()
@click.option("--remote-only", is_flag=True)
@click.option("--local-only", is_flag=True)
@click.option("--name", "name_pattern", default=None)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def caps(
    remote_only: bool,
    local_only: bool,
    name_pattern: str | None,
    host: str,
    port: int,
) -> None:
    """List capability entries."""
    url = f"http://{host}:{port}/bus/v1/capabilities"
    try:
        data = _http_get(url)
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)

    entries = data if isinstance(data, list) else data.get("capabilities", [])

    if remote_only:
        entries = [e for e in entries if not e.get("local", False)]
    elif local_only:
        entries = [e for e in entries if e.get("local", False)]

    if name_pattern:
        entries = [e for e in entries if name_pattern.lower() in e.get("name", "").lower()]

    if not entries:
        click.echo("No capabilities found.")
        return

    click.echo(f"{'NAME':<30} {'VERSION':<10} {'STABILITY':<12} {'LOCAL'}")
    click.echo("-" * 60)
    for entry in entries:
        click.echo(
            f"{entry.get('name', '?'):<30} "
            f"{entry.get('version', '?'):<10} "
            f"{entry.get('stability', '?'):<12} "
            f"{'yes' if entry.get('local') else 'no'}"
        )


# ---------------------------------------------------------------------------
# call
# ---------------------------------------------------------------------------


@main.command()
@click.argument("capability")
@click.option("--body", default="{}", help="JSON body")
@click.option("--stream", is_flag=True)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def call(capability: str, body: str, stream: bool, host: str, port: int) -> None:
    """Make a one-shot capability call."""
    # Validate body is valid JSON before sending
    try:
        json.loads(body)
    except json.JSONDecodeError as exc:
        click.echo(f"Invalid JSON body: {exc}", err=True)
        sys.exit(1)

    url = f"http://{host}:{port}/bus/v1/call"
    payload = json.dumps({"capability": capability, "body": json.loads(body)})
    try:
        result = _http_post(url, payload)
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)

    click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@main.command()
@click.option("--check", default=None, help="Run specific check by name")
def doctor(check: str | None) -> None:
    """Run self-diagnostics."""
    try:
        from hearthnet.observability.doctor import run_all, run_one

        if check:
            results = [run_one(check)]
        else:
            results = run_all()
        all_passed = all(r.passed for r in results)
        for r in results:
            icon = "✔" if r.passed else "✘"
            click.echo(f"  {icon}  {r.check.name:<25} {r.message}")
            if not r.passed and r.check.fix_hint:
                click.echo(f"       → fix: {r.check.fix_hint}")
        sys.exit(0 if all_passed else 1)
    except Exception as exc:
        click.echo(f"doctor crashed: {exc}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------


@main.command()
@click.argument("n", default=20, type=int)
@click.option("--capability", default=None)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def trace(n: int, capability: str | None, host: str, port: int) -> None:
    """Show recent call traces."""
    url = f"http://{host}:{port}/trace/recent?n={n}"
    if capability:
        url += f"&capability={capability}"
    try:
        data = _http_get(url)
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)

    entries = data if isinstance(data, list) else data.get("traces", [])
    if not entries:
        click.echo("No traces found.")
        return

    for entry in entries:
        ts = entry.get("ts", "?")
        cap = entry.get("capability", "?")
        dur = entry.get("duration_ms", "?")
        ok = "OK" if entry.get("success", True) else "ERR"
        click.echo(f"  [{ts}] {cap:<30} {dur:>6}ms  {ok}")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@main.command()
@click.option("--out", type=click.Path(), default=None)
def export(out: str | None) -> None:
    """Export all local data (GDPR right-to-export)."""
    config_dir = Path.home() / ".hearthnet"
    out_path = Path(out) if out else Path.cwd() / "hearthnet-export.zip"

    try:
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if config_dir.exists():
                for item in config_dir.rglob("*"):
                    # Skip private key material
                    if item.suffix in (".key", ".pem") or item.name.startswith("signing"):
                        continue
                    if item.is_file():
                        zf.write(item, item.relative_to(config_dir.parent))
            # Add a manifest of what was exported
            manifest = {
                "export_version": 1,
                "exported_from": str(config_dir),
                "contains": "node config, identity (public parts only)",
            }
            zf.writestr("EXPORT_MANIFEST.json", json.dumps(manifest, indent=2))
        click.echo(f"Exported to {out_path}")
    except Exception as exc:
        click.echo(f"Export failed: {exc}", err=True)
        sys.exit(1)
