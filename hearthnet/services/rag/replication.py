"""Phase 2 corpus replication — BitTorrent-style knowledge propagation.

When any peer ingests a document, it emits a ``rag.document.ingested`` event
that eventually arrives at every node via gossip (X02 event sync).  This module
listens for those events from *other* nodes and pulls the raw blob via
``TransferManager`` (BLAKE3 chunked, content-addressed), then re-ingests it into
the local corpus so the local ``rag.query`` can answer questions about it.

Result: every node ends up with a complete local corpus copy — making
single-best routing (Option A) eventually correct AND making federated
scatter-gather (Option B) redundantly available as a freshness hedge.

Spec:  docs/M05-rag.md §10 (corpus replication)
       docs/X02-events.md §3.1 (rag.document.ingested)
       docs/M07-file-blobs.md §4 (TransferManager)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

_log = logging.getLogger(__name__)

# Back-off between retry attempts when fetch fails.
_RETRY_DELAY_SECONDS = 15


class CorpusReplicator:
    """Background task that replicates documents from peer nodes.

    Constructor args:
        bus            — CapabilityBus (used to call rag.ingest locally)
        event_log      — EventLog (subscribed to rag.document.ingested events)
        transfer       — TransferManager (fetches BLAKE3 blobs from peers)
        peers          — PeerRegistry (resolves peer URLs from node_id)
        local_node_id  — this node's full node ID (to skip own events)
        corpus_store_fn — callable(corpus:str) → CorpusStore | None; used to
                          check has_doc before fetching (optional — saves a
                          round-trip on duplicates we already have)
    """

    def __init__(
        self,
        bus: Any,
        event_log: Any,
        transfer: Any,
        peers: Any,
        local_node_id: str,
        corpus_store_fn: Any = None,
    ) -> None:
        self._bus = bus
        self._event_log = event_log
        self._transfer = transfer
        self._peers = peers
        self._local_node_id = local_node_id
        self._corpus_store_fn = corpus_store_fn
        self._task: asyncio.Task | None = None

    def start(self) -> asyncio.Task:
        """Create and return the background asyncio Task."""
        self._task = asyncio.create_task(self.run(), name="corpus-replicator")
        return self._task

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def run(self) -> None:
        """Main event loop — never returns until cancelled."""
        _log.info("CorpusReplicator started (local_node=%s)", self._local_node_id[:16])
        try:
            async for event in self._event_log.subscribe(["rag.document.ingested"]):
                asyncio.create_task(self._handle_event(event), name="corpus-repl-event")
        except asyncio.CancelledError:
            _log.info("CorpusReplicator stopped")
            raise
        except Exception as exc:
            _log.error("CorpusReplicator crashed: %s", exc)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _handle_event(self, event: Any) -> None:
        """Process one rag.document.ingested event from a peer."""
        try:
            # Only replicate events authored by OTHER nodes.
            if getattr(event, "author", None) == self._local_node_id:
                return

            payload = event.payload or {}
            corpus: str = payload.get("corpus", "default")
            doc_cid: str | None = payload.get("doc_cid")
            blob_cid: str | None = payload.get("blob_cid")
            title: str = payload.get("title", "Untitled")
            author: str = event.author

            if not doc_cid:
                return

            # Idempotency: skip if we already have this document.
            if self._corpus_store_fn is not None:
                try:
                    store = self._corpus_store_fn(corpus)
                    if store is not None and store.has_doc(doc_cid):
                        _log.debug(
                            "replicator: already have doc_cid=%s corpus=%s — skip",
                            doc_cid[:16],
                            corpus,
                        )
                        return
                except Exception:
                    pass

            # If no blob_cid we cannot fetch — log and skip.
            if not blob_cid:
                _log.debug(
                    "replicator: event from %s has no blob_cid, cannot fetch doc_cid=%s",
                    author[:16],
                    doc_cid[:16] if doc_cid else "?",
                )
                return

            # Resolve peer source URLs for this author node.
            sources = self._peer_urls_for(author)
            if not sources:
                _log.debug("replicator: no reachable peer URL for author %s", author[:16])
                return

            # Fetch the blob via BLAKE3 chunked transfer (M07 TransferManager).
            try:
                manifest = await self._transfer.fetch(blob_cid, sources)
                raw_bytes = self._transfer.store.get(manifest.cid)
                text = raw_bytes.decode("utf-8", errors="replace")
            except Exception as exc:
                _log.warning(
                    "replicator: fetch failed blob_cid=%s from %s: %s",
                    blob_cid[:16] if blob_cid else "?",
                    sources,
                    exc,
                )
                # Retry once after a delay (e.g., peer was momentarily unavailable).
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
                try:
                    manifest = await self._transfer.fetch(blob_cid, sources)
                    raw_bytes = self._transfer.store.get(manifest.cid)
                    text = raw_bytes.decode("utf-8", errors="replace")
                except Exception as exc2:
                    _log.warning("replicator: retry also failed: %s", exc2)
                    return

            # Re-ingest locally via the bus (goes through the normal pipeline,
            # honours has_doc idempotency, emits NO new event because event_log
            # is only attached to the original RagService which will see this
            # call as local — that's correct; the ingest IS local now).
            try:
                await self._bus.call(
                    "rag.ingest",
                    (1, 0),
                    {
                        "input": {
                            "text": text,
                            "title": title,
                            "doc_cid": doc_cid,
                            "corpus": corpus,
                        },
                        "params": {"corpus": corpus},
                    },
                )
                _log.info(
                    "replicator: ingested doc_cid=%s corpus=%s from %s",
                    doc_cid[:16],
                    corpus,
                    author[:16],
                )
            except Exception as exc:
                _log.warning("replicator: ingest failed doc_cid=%s: %s", doc_cid[:16], exc)

        except Exception as exc:
            _log.warning("replicator: unhandled error in _handle_event: %s", exc)

    # ------------------------------------------------------------------
    # Peer URL resolution
    # ------------------------------------------------------------------

    def _peer_urls_for(self, node_id: str) -> list[str]:
        """Return HTTP base URLs for a peer node_id from the PeerRegistry."""
        try:
            for peer in self._peers.all():
                if peer.node_id == node_id or node_id.startswith(peer.node_id):
                    urls = []
                    for ep in getattr(peer, "endpoints", []):
                        transport = getattr(ep, "transport", "")
                        if transport in ("http", ""):
                            urls.append(f"http://{ep.host}:{ep.port}")
                    if urls:
                        return urls
        except Exception:
            pass
        return []
