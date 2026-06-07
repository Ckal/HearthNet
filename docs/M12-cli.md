# M12 — CLI

**Spec version:** v1.0
**Depends on:** X04 (config), M01 (identity), M03 (bus, via IPC), X03 (observability for doctor), `click`
**Depended on by:** Users; packaging

---

## 1. Responsibility

Provide the `hearthnet` command. Each subcommand is small, scriptable, exit-code-correct. The CLI either:

- Runs in **standalone mode**: does not need a running node (init, doctor on cold disk, export, erase)
- Talks to a **running node** over local HTTP (`status`, `caps`, `log`, `trace`), bypassing the UI

The CLI never imports a service module. For node-state queries it uses the bus's HTTP API on `127.0.0.1:7080` like any other client.

---

## 2. File layout

```
hearthnet/
├── cli.py              # Click app, all subcommands
├── __main__.py         # `python -m hearthnet` → cli.main()
└── doctor.py           # re-export from X03 for `hearthnet doctor`
```

Installed as console script in `pyproject.toml`:

```toml
[project.scripts]
hearthnet = "hearthnet.cli:main"
```

---

## 3. Subcommands

### 3.1 `hearthnet init`

```
hearthnet init [--name NAME] [--profile PROFILE] [--non-interactive]
```

Bootstraps a new node:

1. Resolves XDG paths, creates dirs
2. Generates keypair if absent (M01)
3. Writes default `config.toml`
4. Interactive prompts (unless `--non-interactive`):
   - Display name
   - Profile (auto-detected from hardware)
   - Create or join community
5. If create: builds genesis community manifest, writes it, prints invite QR to terminal (Unicode block art) and saves PNG
6. If join: prompts for invite text, redeems

Exits 0 on success, 2 on user abort, 1 on error.

### 3.2 `hearthnet run`

```
hearthnet run [--config PATH] [--no-ui] [--debug]
```

Starts the node:

1. Loads config (X04)
2. Configures observability (X03)
3. Loads keypair (M01) — refuses if missing
4. Verifies community manifest present — if not, redirects to init
5. Composes the node (see [`node.py` in the package layout](#5-the-orchestrator-nodepy))
6. Blocks until SIGINT / SIGTERM

`--no-ui` skips Gradio (useful for headless anchor / RPi).
`--debug` raises log level to debug.

### 3.3 `hearthnet status`

```
hearthnet status [--json]
```

Connects to local node at `127.0.0.1:7080`. Reports:

- Our node ID + display name + profile
- Community ID + name + member count
- Online state (online/degraded/offline) + duration in this state
- Peers visible (count + summaries)
- Registered local capabilities (count + names)
- In-flight calls
- Event log head Lamport
- Disk usage (blobs + events)

Exits 0 if reachable, 3 if not reachable, 1 on bad response.

### 3.4 `hearthnet caps`

```
hearthnet caps [--remote-only | --local-only] [--name PATTERN]
```

Lists capability entries. Columns: `name`, `version`, `stability`, `node`, `model/params`, `health`, `p50ms`, `in_flight`.

### 3.5 `hearthnet call`

```
hearthnet call NAME[@VERSION] --body '<json>' [--stream]
```

Make a one-shot capability call. Useful for scripting and testing.

```
hearthnet call llm.chat@1.0 --stream \
  --body '{"params":{"model":"qwen2.5-7b-instruct"},"input":{"messages":[{"role":"user","content":"Hi"}]}}'
```

Streams to stdout. Non-zero exit code reflects wire error code (mapped: see [CONTRACT §9](../CAPABILITY_CONTRACT.md)).

### 3.6 `hearthnet log`

```
hearthnet log [--follow] [--level LEVEL] [--component NAME]
```

Tails the structured log file. With `--follow`, behaves like `tail -F` and filters live.

### 3.7 `hearthnet trace`

```
hearthnet trace recent [N] [--capability NAME]
```

Pulls the trace ring buffer via `/trace/recent`. Pretty-prints last N traces.

### 3.8 `hearthnet doctor`

```
hearthnet doctor [--check NAME]
```

Runs X03's self-diagnostics (`run_all` or `run_one`). Coloured terminal output:

```
✔  keys_present          /home/christof/.local/share/hearthnet/keys/device.ed25519
✔  keys_loadable         Ed25519, 32 bytes
✘  mdns_socket           Port 5353 in use by avahi-daemon
     → fix: sudo systemctl stop avahi-daemon
...
```

Exit code: 0 if all pass, 1 if any fail, 2 if doctor itself crashed.

### 3.9 `hearthnet export`

```
hearthnet export [--out PATH]
```

Exports all local data for this user (GDPR right-to-export):

- Public manifest
- Our authored events
- Our chat history
- Our pinned files (CIDs + filenames)
- Our marketplace posts
- Settings (without secrets)

Output: a signed ZIP at `<PATH>` (default `~/hearthnet-export-<date>.zip`).

### 3.10 `hearthnet erase`

```
hearthnet erase [--keep-keys] [--yes]
```

Erases local state. Prompts thrice. With `--keep-keys`, retains the device key (allowing rejoin later).

Order of erase:

1. Stop running node (best-effort over IPC)
2. Wipe `<DATA>/communities/<id>/` (events, manifests, snapshots)
3. Wipe `<DATA>/blobs/` (unless pinned with `--keep-blobs`)
4. Wipe `<CACHE>/embeddings/`
5. Wipe `<LOG>` (unless `--keep-logs`)
6. Wipe `<DATA>/keys/` unless `--keep-keys`
7. Print summary

### 3.11 `hearthnet rag`

```
hearthnet rag list
hearthnet rag ingest PATH --corpus NAME
hearthnet rag reindex --corpus NAME [--embedding-model MODEL]
```

Local CLI for RAG operations. Calls `rag.list_corpora`, `rag.ingest`, and (for reindex) a privileged local-only flow that re-embeds an existing corpus.

### 3.12 `hearthnet invite`

```
hearthnet invite create --node-id NODEID --level LEVEL --ttl HOURS
hearthnet invite redeem TEXT_OR_PATH
```

CLI equivalents of the M13 onboarding flows. Useful for headless anchors.

### 3.13 `hearthnet version`

Prints `__version__`, contract version, Python version, OS. One line.

---

## 4. CLI architecture (Click)

```python
# hearthnet/cli.py
import click

@click.group()
@click.option("--config", type=click.Path(), help="Path to config.toml")
@click.pass_context
def main(ctx, config):
    ctx.obj = load_config(Path(config) if config else None)

@main.command()
@click.option("--name")
...
def init(...): ...

# ... etc. Each subcommand is its own function.
```

Each command function is < 40 lines and delegates to module-level helpers in the same file. Tests can call the helpers directly without invoking Click runtime.

---

## 5. The orchestrator (`node.py`)

The CLI's `run` subcommand calls into `hearthnet.node.start`. This is not strictly part of M12 but is documented here for completeness because it's the central wiring point.

```python
# hearthnet/node.py
async def start(config: Config) -> None:
    # 1. observability
    observability.logging.configure(config.observability)
    observability.metrics.configure(config.observability)

    # 2. identity
    kp = identity.keys.load_or_generate(config.identity.keys_dir)

    # 3. community check (M13 redirect if missing)
    if config.community.community_id is None:
        await onboarding.run_blocking(config, kp)         # writes config; restart cycle
        return

    # 4. core state
    event_log = events.EventLog(config.community.state_dir / "events.sqlite",
                                config.community.community_id)
    snapshot_store = events.SnapshotStore(config.community.state_dir / "snapshots",
                                          config.community.community_id)
    replay_engine = events.ReplayEngine(event_log)
    community_manifest = identity.manifest.load_or_regenerate(...)

    # 5. blobs
    blob_store = blobs.BlobStore(config.file.blobs_dir, gc_threshold=config.file.gc_threshold)

    # 6. transport + bus
    pinned = transport.PinnedCerts(...)
    http_client = transport.HttpClient(kp, kp.node_id_full, config.community.community_id, pinned)
    bus = CapabilityBus(kp.node_id_full, config.community.community_id, config.bus,
                        http_client, lambda: community_manifest)

    # 7. peer registry + discovery
    peer_registry = discovery.PeerRegistry(kp.node_id_full, config.community.community_id)
    mdns_announcer = discovery.MdnsAnnouncer(...)
    mdns_browser   = discovery.MdnsBrowser(peer_registry, config.community.community_id)
    udp_announcer  = discovery.UdpAnnouncer(...)
    udp_listener   = discovery.UdpListener(peer_registry, config.community.community_id)

    # 8. services
    services_list = []
    if config.embedding:
        services_list.append(EmbeddingService(config.embedding))
    if config.llm.backends:
        services_list.append(LlmService(config.llm))
    if config.rag.enabled:
        services_list.append(RagService(config.rag, bus, blob_store, event_log, lambda: community_manifest))
    if config.file:
        services_list.append(FileService(config.file, blob_store, event_log))
    if config.market.enabled:
        services_list.append(MarketplaceService(config.market, bus, event_log, replay_engine, kp,
                                                lambda: community_manifest))
    if config.chat.enabled:
        services_list.append(ChatService(config.chat, bus, event_log, replay_engine, peer_registry, kp,
                                         kp.node_id_full))

    for s in services_list:
        bus.register_service(s)
        await s.start()

    # 9. emergency detector
    state_bus = emergency.StateBus()
    detector  = emergency.Detector(config.emergency, bus, state_bus)

    # 10. transport server
    http_server = transport.HttpServer(config.transport, kp, bus,
                                       event_sync=events.SyncServer(event_log),
                                       community_manifest_provider=lambda: community_manifest)

    # 11. UI
    ui_app = ui.build_ui(bus, state_bus, config.ui,
                         node_id_short=kp.node_id_short, community_name=community_manifest.name)

    # 12. wire peer events → bus
    peer_registry.subscribe(...).on_event(bus.on_peer_added, bus.on_peer_updated, bus.on_peer_removed)

    # 13. periodic manifest publish
    publisher = ManifestPublisher(kp, community_manifest_provider=...,  bus=bus,
                                  peer_registry=peer_registry, interval_seconds=MANIFEST_REPUBLISH_INTERVAL_SECONDS)

    # 14. periodic sync
    syncer = events.SyncClient(event_log, http_client)
    sync_loop = PeriodicTask(lambda: syncer.run_round(peer_registry), interval_seconds=300)

    # 15. run everything
    await asyncio.gather(
        http_server.run(),
        mdns_announcer.start(), mdns_browser.start(),
        udp_announcer.run(), udp_listener.run(),
        detector.run(),
        publisher.run(),
        sync_loop.run(),
        ui_app.launch_async(),
    )
```

This is the canonical wiring. Anything that looks different across modules is wrong.

---

## 6. Exit code reference

| Code | Meaning |
|------|---------|
| 0    | Success |
| 1    | Generic error (see stderr) |
| 2    | User aborted / bad usage |
| 3    | No running node (for commands needing IPC) |
| 4    | Auth / signature failure |
| 5    | Disk full / capacity exceeded |

---

## 7. Configuration

The CLI reads the same `config.toml` as the daemon. `--config` overrides the path.

---

## 8. Tests

### Unit (per subcommand handler)
- `test_init_writes_config_and_keys`
- `test_status_against_mock_node_returns_table`
- `test_call_streams_stdout_then_zero`
- `test_doctor_exit_code_reflects_failures`
- `test_erase_keep_keys`

### Integration
- `test_full_init_then_run_then_status` — spawn subprocess, await readiness, query
- `test_call_returns_nonzero_on_wire_error`
- `test_export_zip_is_signed_and_parseable`

---

## 9. Cross-references

| What | Where |
|------|-------|
| Self-diagnostics | [X03 §6](../cross-cutting/X03-observability.md) |
| Onboarding helpers | [M13](M13-onboarding.md) |
| Bus introspection endpoints | [M03 §3.7](M03-bus.md), [X01 §3.2](../cross-cutting/X01-transport.md) |
| Trace ring buffer endpoint | [X01 §3.2](../cross-cutting/X01-transport.md), [X03 §5](../cross-cutting/X03-observability.md) |
| Config | [X04](../cross-cutting/X04-config.md) |

---

## 10. Open questions

1. **Daemon mode on Linux** — `systemd` user unit? Ship one in packaging? Phase 1.5.
2. **Windows service / macOS LaunchAgent** — Phase 2.
3. **Shell completion** — Click supports it; ship completions for bash/zsh/fish.
4. **Progress bars for ingest / fetch** — `rich` progress; nice but optional.
