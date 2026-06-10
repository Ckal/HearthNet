# HearthNet Phase 1 Task Plan

## Scope

Phase 1 turns the existing HearthNet concept into a deployable Hugging Face Space that demonstrates the system of concern, controller, facades, and capability-bus pattern described in `docs/`.

The Space must make the value clear in one minute:

- nearby nodes discover each other;
- capabilities are announced and routed through the bus;
- RAG, chat, marketplace, and emergency flows continue in local/offline mode;
- the UI shows topology, health, routing decisions, and phase boundaries;
- quality gates can be run locally with `ruff`, `bandit`, `pylint`, `mypy`, and `pytest`.

## Architecture Tasks

- [x] Import the Hugging Face Space into the local workspace.
- [x] Read docs and extract Phase 1 requirements.
- [x] Preserve the existing browser mesh prototype as supporting material.
- [x] Create Python package layout aligned with the docs.
- [x] Model the system of concern as local-first community AI resilience.
- [x] Add a controller that owns demo state and exposes UI-facing operations.
- [x] Add facades for mesh, AI/RAG, community, and emergency workflows.
- [x] Add a capability bus that registers services and routes requests by health and score.
- [x] Add simulated discovery and peer manifests.
- [x] Add deterministic demo data for anchor, hearth, and spark profiles.

## Product/UI Tasks

- [x] Build a Hugging Face-compatible Gradio `app.py`.
- [x] Create first-screen dashboard with topology, health, and emergency mode.
- [x] Add Ask/RAG interaction that returns cited local knowledge.
- [x] Add trace output showing UI -> bus -> service routing.
- [x] Add community marketplace and chat panels.
- [x] Add onboarding/demo controls for online/offline and failover scenarios.
- [x] Make Phase 1/2/3 boundaries explicit without overclaiming unfinished work.

## Quality Tasks

- [x] Add `pyproject.toml` with ruff, pytest, mypy, and pylint config.
- [x] Add runtime and dev requirements.
- [x] Add focused tests for routing, failover, emergency mode, and controller snapshots.
- [x] Run `ruff`.
- [x] Run `bandit`.
- [x] Run `pylint`.
- [x] Run `mypy`.
- [x] Run `pytest`.

## Deployment Tasks

- [x] Verify Space metadata in `README.md`.
- [x] Ensure `app_file: app.py` exists and imports cleanly.
- [x] Commit Phase 1 implementation.
- [x] Push to `https://huggingface.co/spaces/build-small-hackathon/HearthNet`.
- [x] Confirm remote status after push.

## Later Phases

- [ ] Phase 2: real transport, relay tier, websocket/DHT/federation, encryption, mobile-native flows.
- [ ] Phase 3: protocol standardization, civil-defense evidence workflows, LoRa beacons, federated learning, distributed inference.
