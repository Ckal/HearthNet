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
            with urllib.request.urlopen(url, timeout=5) as r:  # nosec B310 - URL validated to http/https local host
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
            with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 - URL validated to http/https local host
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


# ---------------------------------------------------------------------------
# log  (§3.6)
# ---------------------------------------------------------------------------


@main.command()
@click.option("--follow", "-f", is_flag=True)
@click.option("--level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
@click.option("--component", default=None)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def log(follow: bool, level: str, component: str | None, host: str, port: int) -> None:
    """Stream or display recent structured log entries."""
    url = f"http://{host}:{port}/trace/recent?n=100"
    try:
        data = _http_get(url)
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)

    entries = data if isinstance(data, list) else data.get("traces", [])
    for entry in entries:
        if component and entry.get("component", "") != component:
            continue
        entry_level = entry.get("level", "INFO").upper()
        if ["DEBUG", "INFO", "WARNING", "ERROR"].index(entry_level) < ["DEBUG", "INFO", "WARNING", "ERROR"].index(level):
            continue
        ts = entry.get("ts", "?")
        msg = entry.get("message") or entry.get("capability") or json.dumps(entry)
        click.echo(f"[{ts}] {entry_level:7s} {msg}")

    if follow:
        click.echo("(follow mode: reconnect not implemented — use --no-follow for snapshot)")


# ---------------------------------------------------------------------------
# erase  (§3.10)
# ---------------------------------------------------------------------------


@main.command()
@click.option("--keep-keys", is_flag=True, help="Keep Ed25519 identity keys, erase everything else.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def erase(keep_keys: bool, yes: bool) -> None:
    """Erase all local HearthNet data.

    Exit codes: 0 erased, 2 aborted.
    """
    config_dir = Path.home() / ".hearthnet"
    if not yes:
        click.confirm(
            f"This will delete {config_dir} {'(keeping keys)' if keep_keys else ''}. Continue?",
            abort=True,
        )
    import shutil

    if not config_dir.exists():
        click.echo("Nothing to erase.")
        return

    if keep_keys:
        key_file = config_dir / "identity.key"
        key_backup = None
        if key_file.exists():
            import tempfile
            key_backup = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".key").name)
            import shutil as _sh
            _sh.copy2(key_file, key_backup)
        shutil.rmtree(config_dir)
        if key_backup and key_backup.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            _sh.move(str(key_backup), key_file)
        click.echo("Data erased (keys preserved).")
    else:
        shutil.rmtree(config_dir)
        click.echo("All HearthNet data erased.")


# ---------------------------------------------------------------------------
# rag subgroup  (§3.11)
# ---------------------------------------------------------------------------


@main.group()
def rag() -> None:
    """RAG corpus management."""


@rag.command("list")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def rag_list(host: str, port: int) -> None:
    """List available RAG corpora."""
    try:
        result = _bus_call(host, port, "rag.list_corpora", (1, 0), {})
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)
    corpora = result.get("output", result).get("corpora", [])
    if not corpora:
        click.echo("No corpora.")
        return
    for c in corpora:
        name = c.get("name", c) if isinstance(c, dict) else c
        count = c.get("doc_count", "?") if isinstance(c, dict) else "?"
        click.echo(f"  {name:<30} docs={count}")


@rag.command("ingest")
@click.argument("path", type=click.Path(exists=True))
@click.option("--corpus", default="community")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def rag_ingest(path: str, corpus: str, host: str, port: int) -> None:
    """Ingest a file or directory into a RAG corpus."""
    p = Path(path)
    files: list[Path] = list(p.rglob("*")) if p.is_dir() else [p]
    ingested = 0
    for f in files:
        if not f.is_file():
            continue
        data_b64 = __import__("base64").b64encode(f.read_bytes()).decode()
        try:
            result = _bus_call(host, port, "rag.ingest", (1, 0), {
                "input": {"corpus": corpus, "filename": f.name, "data_b64": data_b64}
            })
            err = result.get("error")
            if err:
                click.echo(f"  SKIP {f.name}: {err}")
            else:
                ingested += 1
                click.echo(f"  OK   {f.name}")
        except ConnectionError:
            click.echo(f"Node not reachable at {host}:{port}")
            sys.exit(3)
    click.echo(f"Ingested {ingested} file(s) into corpus '{corpus}'.")


@rag.command("reindex")
@click.option("--corpus", default="community")
@click.option("--embedding-model", default=None)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def rag_reindex(corpus: str, embedding_model: str | None, host: str, port: int) -> None:
    """Rebuild the vector index for a corpus."""
    body: dict = {"input": {"corpus": corpus}}
    if embedding_model:
        body["input"]["embedding_model"] = embedding_model
    try:
        result = _bus_call(host, port, "rag.reindex", (1, 0), body)
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)
    err = result.get("error")
    if err:
        click.echo(f"Reindex failed: {err}", err=True)
        sys.exit(1)
    out = result.get("output", result)
    click.echo(f"Reindexed corpus '{corpus}': {out.get('doc_count', '?')} docs.")


# ---------------------------------------------------------------------------
# invite subgroup  (§3.12)
# ---------------------------------------------------------------------------


@main.group()
def invite() -> None:
    """Community invite management."""


@invite.command("create")
@click.argument("node_id")
@click.option("--level", default="member", type=click.Choice(["member", "trusted", "moderator"]))
@click.option("--ttl", default=86400, type=int, help="Validity in seconds (default 24h).")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def invite_create(node_id: str, level: str, ttl: int, host: str, port: int) -> None:
    """Create an invite link for a new member."""
    try:
        result = _bus_call(host, port, "community.invite", (1, 0), {
            "input": {"invitee_node_id": node_id, "initial_level": level, "ttl_seconds": ttl}
        })
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)
    err = result.get("error")
    if err:
        click.echo(f"Invite failed: {err}", err=True)
        sys.exit(1)
    out = result.get("output", result)
    click.echo(out.get("invite_url") or json.dumps(out, indent=2))


@invite.command("redeem")
@click.argument("text_or_path")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=7080, type=int)
def invite_redeem(text_or_path: str, host: str, port: int) -> None:
    """Redeem a hearthnet:// invite link (file path or URL)."""
    p = Path(text_or_path)
    invite_text = p.read_text().strip() if p.exists() else text_or_path.strip()
    try:
        result = _bus_call(host, port, "community.redeem", (1, 0), {
            "input": {"invite_text": invite_text}
        })
    except ConnectionError:
        click.echo(f"Node not reachable at {host}:{port}")
        sys.exit(3)
    err = result.get("error")
    if err:
        click.echo(f"Redeem failed: {err}", err=True)
        sys.exit(1)
    out = result.get("output", result)
    click.echo(f"Joined community: {out.get('community_name', out)}")


# ---------------------------------------------------------------------------
# version  (§3.13)
# ---------------------------------------------------------------------------


@main.command("version")
def version_cmd() -> None:
    """Print HearthNet version and exit."""
    try:
        from importlib.metadata import version as _v
        ver = _v("hearthnet")
    except Exception:
        try:
            from hearthnet import __version__ as ver  # type: ignore[attr-defined]
        except Exception:
            ver = "dev"
    click.echo(f"hearthnet {ver}")


# ---------------------------------------------------------------------------
# config subgroup — Configuration management
# ---------------------------------------------------------------------------


@main.group()
def config() -> None:
    """Configuration management."""


@config.command("show")
def config_show() -> None:
    """Display current HearthNet configuration."""
    try:
        from build.shared.first_run import get_config_file, load_config

        config = load_config()
        config_file = get_config_file()

        click.echo("📋 HearthNet Configuration")
        click.echo(f"Location: {config_file}")
        click.echo("")

        for key, value in config.items():
            if isinstance(value, bool):
                value_str = "✅ Yes" if value else "❌ No"
            else:
                value_str = str(value)
            click.echo(f"  {key:<20} : {value_str}")
    except Exception as exc:
        click.echo(f"❌ Failed to load config: {exc}", err=True)
        sys.exit(1)


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Update a configuration value."""
    try:
        from build.shared.first_run import load_config, save_config

        config = load_config()

        # Type conversion
        if value.lower() in ("true", "yes", "1"):
            config[key] = True
        elif value.lower() in ("false", "no", "0"):
            config[key] = False
        elif value.isdigit():
            config[key] = int(value)
        else:
            config[key] = value

        if save_config(config):
            click.echo(f"✅ Config updated: {key} = {config[key]}")
        else:
            sys.exit(1)
    except Exception as exc:
        click.echo(f"❌ Failed to update config: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# model subgroup — LLM Model management
# ---------------------------------------------------------------------------


@main.group()
def model() -> None:
    """LLM model management."""


@model.command("download")
@click.argument("model_id")
@click.option("--cache", type=click.Path(), default=None, help="Custom cache directory")
def model_download(model_id: str, cache: str | None) -> None:
    """Download and cache an LLM model from HuggingFace Hub."""
    try:
        from build.shared.download_model import download_model, get_model_path, is_model_cached

        if is_model_cached(model_id):
            click.echo(f"✅ Model already cached: {get_model_path(model_id)}")
            return

        click.echo(f"📥 Downloading model: {model_id}")
        click.echo("   (This may take several minutes depending on model size)")

        success = download_model(model_id, destination=Path(cache) if cache else None)

        if success:
            model_path = get_model_path(model_id)
            click.echo(f"✅ Model downloaded and cached at: {model_path}")
        else:
            click.echo("❌ Failed to download model", err=True)
            sys.exit(1)
    except Exception as exc:
        click.echo(f"❌ Error: {exc}", err=True)
        sys.exit(1)


@model.command("list")
def model_list() -> None:
    """List cached models."""
    try:
        from build.shared.download_model import get_model_cache_dir

        cache_dir = get_model_cache_dir()

        if not cache_dir.exists() or not list(cache_dir.iterdir()):
            click.echo("📦 No cached models found.")
            click.echo(f"   Cache location: {cache_dir}")
            return

        click.echo("📦 Cached Models:")
        click.echo("")

        for model_dir in sorted(cache_dir.iterdir()):
            if not model_dir.is_dir():
                continue

            size_mb = sum(
                f.stat().st_size for f in model_dir.rglob("*") if f.is_file()
            ) / (1024 * 1024)

            file_count = len(list(model_dir.rglob("*")))

            click.echo(f"  📁 {model_dir.name}")
            click.echo(f"     Size: {size_mb:.1f} MB  Files: {file_count}")
    except Exception as exc:
        click.echo(f"❌ Error: {exc}", err=True)
        sys.exit(1)


@model.command("info")
@click.argument("model_id")
def model_info(model_id: str) -> None:
    """Get information about a model."""
    try:
        from build.shared.download_model import get_model_info

        info = get_model_info(model_id)

        click.echo(f"📊 Model Information: {model_id}")
        click.echo("")

        for key, value in info.items():
            if key == "size_mb":
                click.echo(f"  Size: {value:.1f} MB")
            elif key == "cached":
                cached_str = "✅ Yes" if value else "❌ No"
                click.echo(f"  Cached: {cached_str}")
            elif key == "path" and value:
                click.echo(f"  Path: {value}")
            elif key not in ("model_id",):
                click.echo(f"  {key}: {value}")
    except Exception as exc:
        click.echo(f"❌ Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# doctor enhancement — Added model and backend checks
# ---------------------------------------------------------------------------


@main.command("health")
@click.option("--detailed", is_flag=True, help="Show detailed diagnostics")
def health(detailed: bool) -> None:
    """Quick health check of HearthNet installation."""
    checks_passed = 0
    checks_failed = 0

    # 1. Python version
    import sys
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 12):
        click.echo(f"✅ Python: {py_version}")
        checks_passed += 1
    else:
        click.echo(f"❌ Python: {py_version} (requires 3.12+)")
        checks_failed += 1

    # 2. Key dependencies
    deps = ["click", "gradio", "transformers", "torch", "fastapi"]
    for dep in deps:
        try:
            __import__(dep)
            click.echo(f"✅ {dep}: installed")
            checks_passed += 1
        except ImportError:
            click.echo(f"❌ {dep}: NOT installed")
            checks_failed += 1

    # 3. Model cache
    try:
        from build.shared.download_model import get_model_cache_dir, is_model_cached
        from build.shared.first_run import load_config

        config = load_config()
        model_id = config.get("model_id", "HuggingFaceTB/SmolLM2-135M-Instruct")

        if is_model_cached(model_id):
            click.echo(f"✅ Model: {model_id} (cached)")
            checks_passed += 1
        else:
            click.echo(f"⚠️  Model: {model_id} (not cached, will download on first run)")
            if detailed:
                cache_dir = get_model_cache_dir()
                click.echo(f"     Cache location: {cache_dir}")
    except Exception:
        click.echo("⚠️  Model: could not verify")

    # 4. GPU support
    try:
        import torch
        has_gpu = torch.cuda.is_available()
        if has_gpu:
            gpu_name = torch.cuda.get_device_name(0)
            click.echo(f"✅ GPU: {gpu_name}")
            checks_passed += 1
        else:
            click.echo("ℹ️  GPU: not available (CPU mode)")
    except Exception:
        click.echo("ℹ️  GPU: could not detect")

    # Summary
    click.echo("")
    total = checks_passed + checks_failed
    if checks_failed == 0:
        click.echo(f"✅ All checks passed ({checks_passed}/{total})")
        sys.exit(0)
    else:
        click.echo(f"❌ {checks_failed} check(s) failed ({checks_passed}/{total} passed)")
        sys.exit(1)


# ---------------------------------------------------------------------------
# _bus_call helper (used by several commands above)
# ---------------------------------------------------------------------------


def _bus_call(host: str, port: int, capability: str, version: tuple, body: dict) -> dict:
    """POST to /bus/v1/call and return parsed JSON. Raises ConnectionError on failure."""
    payload = {
        "capability": capability,
        "version": f"{version[0]}.{version[1]}",
        **body,
    }
    return _http_post(f"http://{host}:{port}/bus/v1/call", json.dumps(payload))
