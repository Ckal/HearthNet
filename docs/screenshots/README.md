# HearthNet — Local node ↔ live HF Space (connection proof)

These artifacts demonstrate a **local Python HearthNet node peering with the live
Hugging Face Space** and routing real capability calls over HTTPS through the
capability bus.

Space: https://build-small-hackathon-hearthnet.hf.space

## Screenshots

| File | What it shows |
| --- | --- |
| `01-hf-space-live.png` | The live HF Space UI (HearthNet mesh view). |
| `02-connection-proof.png` | A local node peered with the Space (38 remote capabilities routable) and a real `llm.chat` + `rag.list_corpora` routed to the Space. |

## Reproduce

```powershell
# Peer a local node with the live Space and route a real llm.chat call
python scripts/connect_to_hf.py --ask "In one sentence, how do I store water safely?"

# Regenerate the proof image from live calls
python scripts/make_proof.py
```

## How the connection works

1. The local node exposes `discovery.peer.add@1.0` (added in `hearthnet/discovery/service.py`).
2. `discovery.peer.add` fetches the Space's `/manifest`, registers all remote
   capabilities into the local bus registry, and records the HTTPS endpoint.
3. When a capability (e.g. `llm.chat`) is only available remotely, the bus router
   picks the remote peer and `HttpBusTransport` (`hearthnet/bus/http_transport.py`)
   POSTs to the Space's `/bus/v1/call`.
4. The Space serves `/bus/v1/call`, `/manifest`, `/health`, and
   `/bus/v1/capabilities` via FastAPI routes mounted into the Gradio app
   (`_mount_bus_endpoints` in `app.py`).

## Notes / limitations

- **Sharing works:** `llm.chat`, `llm.complete`, `rag.query`, `rag.list_corpora`,
  `rag.federated_query`, chat, market, file, evidence, civdef, OCR, translation,
  STT/TTS, and image capabilities are all routable cross-network.
- **`embed.text` on the Space:** fails over the raw bus route with a ZeroGPU CUDA
  error. GPU ops on HF ZeroGPU only run inside Gradio's `@spaces.GPU` event path,
  not from a plain FastAPI route. This is an HF runtime constraint, not a bus bug;
  embeddings work locally and on dedicated/CPU Spaces.
- **`invite redeem` / QR codes** are a separate *community-membership* flow
  (`community.redeem`), not transport peering. Transport peering between nodes is
  done via `discovery.peer.add` as shown here.
