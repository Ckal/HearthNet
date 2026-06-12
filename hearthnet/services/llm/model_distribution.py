"""M07/M26 — Model Weight Distribution Service.

Spec: docs/M07-file-blobs.md (blob transport)
      docs/p2_p3/M26-distributed-inference.md (model sharding)
Impl-ref: impl_ref.md §7 (BlobStore), §26 (distributed inference)

Allows nodes to:
  - Advertise which model weights they hold locally
  - Query peers for available models
  - Pull a model from a peer node using chunked blob transfer (M07)
  - Resume interrupted downloads

Transfer model is analogous to BitTorrent content addressing:
  1. model.advertise — broadcast CID + model metadata to the mesh
  2. model.list      — query any node for its available models
  3. model.pull      — request chunked download from a peer's BlobStore
  4. model.status    — check progress of an in-progress pull

After download, the service can optionally register the model with a local
Ollama instance (if available) or place it in a llama.cpp models directory.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from hearthnet.bus.capability import CapabilityDescriptor, RouteRequest


@dataclass
class ModelRecord:
    """A model weight file held by this node."""

    name: str  # human name, e.g. "llama3.2:3b" or "qwen2.5-3b-q4_k_m"
    family: str  # "llama", "qwen", "mistral", …
    format: str  # "gguf", "safetensors", "ollama"
    size_bytes: int
    cid: str  # BLAKE3 content ID (from BlobStore)
    path: str  # absolute local path to the weight file
    context_length: int = 4096
    quantization: str = ""
    requires_internet: bool = False


@dataclass
class PullJob:
    job_id: str
    model_name: str
    source_node: str
    cid: str
    total_chunks: int
    received_chunks: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None

    @property
    def progress(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return self.received_chunks / self.total_chunks

    @property
    def is_done(self) -> bool:
        return self.received_chunks >= self.total_chunks or self.error is not None


class ModelDistributionService:
    """Registers model.advertise / model.list / model.pull / model.status capabilities.

    Instantiate with a reference to the local blob store and an optional path
    where model weight files are scanned (e.g. Ollama's ~/.ollama/models or
    llama.cpp's models/ directory).
    """

    name = "model_distribution"
    version = "1.0"

    def __init__(
        self,
        store,  # BlobStore
        models_dir: Path | None = None,
        bus=None,
    ) -> None:
        self._store = store
        self._models_dir = Path(models_dir) if models_dir else None
        self._bus = bus
        self._local_models: dict[str, ModelRecord] = {}
        self._pull_jobs: dict[str, PullJob] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Scan local model files and register them in the blob store."""
        await self._scan_local_models()

    async def _scan_local_models(self) -> None:
        """Scan models_dir for GGUF files and Ollama manifest dirs."""
        if self._models_dir and self._models_dir.exists():
            for path in self._models_dir.rglob("*.gguf"):
                await self._register_file(path)
        # Auto-discover from Ollama manifest if available
        ollama_manifests = Path.home() / ".ollama" / "models" / "manifests"
        if ollama_manifests.exists():
            for manifest_file in ollama_manifests.rglob("*"):
                if manifest_file.is_file():
                    with contextlib.suppress(Exception):
                        await self._register_ollama_manifest(manifest_file)

    async def _register_file(self, path: Path) -> None:
        """Hash a local GGUF file and add it to our model registry."""
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, path.read_bytes)
        manifest = await loop.run_in_executor(None, self._store.put, data, path.name)
        family = _family_from_name(path.stem)
        record = ModelRecord(
            name=path.stem,
            family=family,
            format="gguf",
            size_bytes=len(data),
            cid=manifest.cid,
            path=str(path),
            quantization=_quant_from_name(path.stem),
        )
        self._local_models[record.name] = record

    async def _register_ollama_manifest(self, manifest_file: Path) -> None:
        """Parse an Ollama manifest and register the model without copying weights."""
        raw = json.loads(manifest_file.read_text())
        config = raw.get("config", {})
        model_name = "/".join(manifest_file.parts[-2:])  # library/name
        family = config.get("model_family", _family_from_name(model_name))
        size = sum(layer.get("size", 0) for layer in raw.get("layers", []))
        # Use sha256 digest of the manifest as CID placeholder
        cid = "sha256:" + hashlib.sha256(manifest_file.read_bytes()).hexdigest()[:32]
        record = ModelRecord(
            name=model_name,
            family=family,
            format="ollama",
            size_bytes=size,
            cid=cid,
            path=str(manifest_file),
        )
        self._local_models[record.name] = record

    # ------------------------------------------------------------------
    # Capability handlers
    # ------------------------------------------------------------------

    def capabilities(self) -> list[tuple]:
        return [
            (
                CapabilityDescriptor(
                    name="model.advertise",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=4,
                    trust_required="member",
                    timeout_seconds=10,
                    idempotent=True,
                ),
                self.handle_advertise,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="model.list",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=8,
                    trust_required="member",
                    timeout_seconds=10,
                    idempotent=True,
                ),
                self.handle_list,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="model.pull",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=2,
                    trust_required="trusted",
                    timeout_seconds=3600,  # large models take time
                    idempotent=False,
                ),
                self.handle_pull,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="model.chunk_read",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=4,
                    trust_required="trusted",
                    timeout_seconds=60,
                    idempotent=True,
                ),
                self.handle_chunk_read,
                None,
            ),
            (
                CapabilityDescriptor(
                    name="model.status",
                    version=(1, 0),
                    stability="beta",
                    params={},
                    max_concurrent=8,
                    trust_required="member",
                    timeout_seconds=5,
                    idempotent=True,
                ),
                self.handle_status,
                None,
            ),
        ]

    async def handle_advertise(self, req: RouteRequest) -> dict:
        """Return this node's local model list for peer discovery."""
        return {
            "output": {
                "models": [
                    {
                        "name": r.name,
                        "family": r.family,
                        "format": r.format,
                        "size_bytes": r.size_bytes,
                        "cid": r.cid,
                        "context_length": r.context_length,
                        "quantization": r.quantization,
                    }
                    for r in self._local_models.values()
                ]
            },
            "meta": {"node_model_count": len(self._local_models)},
        }

    async def handle_list(self, req: RouteRequest) -> dict:
        """List models available on this node (alias for advertise)."""
        return await self.handle_advertise(req)

    async def handle_chunk_read(self, req: RouteRequest) -> dict:
        """Serve one chunk of a model file.

        input: {cid: str, chunk_index: int}
        output: {chunk_index, data_b64, chunk_cid, is_last}
        """
        inp = req.body.get("input", {})
        cid = inp.get("cid", "")
        chunk_index = int(inp.get("chunk_index", 0))

        if not self._store.has(cid):
            return {"error": "not_found", "message": f"Model blob {cid} not found"}

        manifest = self._store.get_manifest(cid)
        if chunk_index >= len(manifest.chunks):
            return {"error": "bad_request", "message": f"chunk_index {chunk_index} out of range"}

        chunk_ref = manifest.chunks[chunk_index]
        chunk_data = self._store.get_chunk(chunk_ref.cid)
        return {
            "output": {
                "chunk_index": chunk_index,
                "data_b64": base64.b64encode(chunk_data).decode(),
                "chunk_cid": chunk_ref.cid,
                "is_last": chunk_index == len(manifest.chunks) - 1,
                "total_chunks": len(manifest.chunks),
            },
            "meta": {},
        }

    async def handle_pull(self, req: RouteRequest) -> dict:
        """Pull a model from a peer node using chunked blob transfer.

        input:
          model_name: str       — model to pull (must exist on source_node)
          source_node: str      — node_id of the provider
          dest_dir: str         — local directory to save the model file (optional)

        output:
          job_id: str           — poll model.status with this ID
          message: str
        """
        if self._bus is None:
            return {
                "error": "bus_not_available",
                "message": "Bus not set on ModelDistributionService",
            }

        inp = req.body.get("input", {})
        model_name = inp.get("model_name", "")
        source_node = inp.get("source_node", "")
        dest_dir = inp.get("dest_dir")

        if not model_name or not source_node:
            return {"error": "bad_request", "message": "model_name and source_node are required"}

        # Step 1: query the source node's model list to get the CID
        try:
            list_result = await self._bus.call(
                "model.list",
                (1, 0),
                {"input": {}},
            )
        except Exception as exc:
            return {"error": "peer_unreachable", "message": str(exc)}

        models = list_result.get("output", {}).get("models", [])
        target = next((m for m in models if m["name"] == model_name), None)
        if target is None:
            return {
                "error": "not_found",
                "message": f"Model '{model_name}' not found on {source_node}. Available: {[m['name'] for m in models]}",
            }

        cid = target["cid"]
        import uuid

        job_id = f"pull:{uuid.uuid4().hex[:12]}"

        # Step 2: get manifest from source to learn total_chunks
        try:
            chunk0 = await self._bus.call(
                "model.chunk_read",
                (1, 0),
                {"input": {"cid": cid, "chunk_index": 0}},
            )
        except Exception as exc:
            return {"error": "transfer_error", "message": f"Cannot read first chunk: {exc}"}

        total_chunks = chunk0.get("output", {}).get("total_chunks", 1)
        job = PullJob(
            job_id=job_id,
            model_name=model_name,
            source_node=source_node,
            cid=cid,
            total_chunks=total_chunks,
        )
        self._pull_jobs[job_id] = job

        # Step 3: pull chunks in background
        save_dir = (
            Path(dest_dir)
            if dest_dir
            else (self._models_dir or Path.home() / ".hearthnet" / "models")
        )
        self._background_pull_task = asyncio.create_task(
            self._pull_chunks(job, cid, total_chunks, save_dir, model_name, first_chunk_data=chunk0)
        )

        return {
            "output": {
                "job_id": job_id,
                "message": f"Pulling '{model_name}' from {source_node} ({total_chunks} chunks). Use model.status to track progress.",
                "total_chunks": total_chunks,
            },
            "meta": {},
        }

    async def _pull_chunks(
        self,
        job: PullJob,
        cid: str,
        total_chunks: int,
        save_dir: Path,
        model_name: str,
        first_chunk_data: dict,
    ) -> None:
        """Background task: download all chunks, reassemble, save to disk."""
        save_dir.mkdir(parents=True, exist_ok=True)
        chunks: list[bytes] = []

        try:
            # Chunk 0 already fetched
            first_out = first_chunk_data.get("output", {})
            chunks.append(base64.b64decode(first_out["data_b64"]))
            job.received_chunks = 1

            for idx in range(1, total_chunks):
                result = await self._bus.call(
                    "model.chunk_read",
                    (1, 0),
                    {"input": {"cid": cid, "chunk_index": idx}},
                )
                out = result.get("output", {})
                if "error" in result:
                    job.error = result.get("message", "chunk read error")
                    return
                chunks.append(base64.b64decode(out["data_b64"]))
                job.received_chunks = idx + 1

            # Reassemble
            data = b"".join(chunks)
            suffix = ".gguf" if model_name.endswith(".gguf") else ".gguf"
            safe_name = model_name.replace("/", "_").replace(":", "_")
            dest = save_dir / f"{safe_name}{suffix}"
            dest.write_bytes(data)

            # Register in our local store
            manifest = self._store.put(data, filename=dest.name)
            family = _family_from_name(safe_name)
            record = ModelRecord(
                name=model_name,
                family=family,
                format="gguf",
                size_bytes=len(data),
                cid=manifest.cid,
                path=str(dest),
                quantization=_quant_from_name(safe_name),
            )
            self._local_models[record.name] = record
            job.finished_at = time.time()

        except Exception as exc:
            job.error = str(exc)

    async def handle_status(self, req: RouteRequest) -> dict:
        """input: {job_id: str} → pull job status"""
        job_id = req.body.get("input", {}).get("job_id", "")
        if job_id not in self._pull_jobs:
            # Also return list of all active jobs if no job_id
            return {
                "output": {
                    "jobs": [
                        {
                            "job_id": j.job_id,
                            "model_name": j.model_name,
                            "source_node": j.source_node,
                            "progress": j.progress,
                            "received_chunks": j.received_chunks,
                            "total_chunks": j.total_chunks,
                            "is_done": j.is_done,
                            "error": j.error,
                            "elapsed_s": time.time() - j.started_at,
                        }
                        for j in self._pull_jobs.values()
                    ]
                },
                "meta": {},
            }
        j = self._pull_jobs[job_id]
        return {
            "output": {
                "job_id": j.job_id,
                "model_name": j.model_name,
                "source_node": j.source_node,
                "progress": j.progress,
                "received_chunks": j.received_chunks,
                "total_chunks": j.total_chunks,
                "is_done": j.is_done,
                "error": j.error,
                "elapsed_s": time.time() - j.started_at,
                "finished_at": j.finished_at,
            },
            "meta": {},
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _family_from_name(name: str) -> str:
    name_lower = name.lower()
    for family in (
        "llama",
        "qwen",
        "mistral",
        "gemma",
        "phi",
        "minicpm",
        "nemotron",
        "falcon",
        "mpt",
        "bloom",
        "gpt",
        "deepseek",
        "yi",
        "vicuna",
    ):
        if family in name_lower:
            return family
    return "unknown"


def _quant_from_name(name: str) -> str:
    for q in ("q2_k", "q3_k_m", "q4_0", "q4_k_m", "q5_k_m", "q6_k", "q8_0", "f16", "f32", "bf16"):
        if q in name.lower():
            return q
    return ""
