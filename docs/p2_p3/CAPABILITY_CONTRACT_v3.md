# HearthNet Capability Contract — Phase 3 additions (v3.0)

**Spec version:** v3.0
**Last touched:** 2026-06-09
**Builds on:** [`../phase-2/CAPABILITY_CONTRACT_v2.md`](../phase-2/CAPABILITY_CONTRACT_v2.md) (v2.0)

This document is **additive** to v2.0. Phase 3 capabilities are mostly under the `experimental.` namespace; nodes default to ignoring them unless `policy.research.enable = true`.

---

## 1. Conventions delta

### 1.1 The `experimental.` namespace

A capability of the form `experimental.<name>@<ver>` is treated specially:

- Nodes do not register experimental capabilities by default.
- The bus discovery layer (M02 / X05) excludes experimental capabilities from outbound advertisements unless the local policy opts in.
- A capability in `experimental.` MAY change its contract between minor versions without a contract bump. Callers MUST tolerate breakage.
- Once a capability is sufficiently proven and stable, it is **promoted** out of `experimental.` in a future minor contract bump. The prior `experimental.` form is then deprecated; both forms work for one minor-release window.

Promotion criteria (a soft checklist; the protocol working group, see M32, decides):
- ≥ 2 independent implementations.
- Used in production by ≥ 3 communities for ≥ 90 days.
- Open security review with no unresolved high-severity findings.
- Per-call cost (compute, latency, bytes) within a 2× factor of the budget in the capability spec.

### 1.2 Claim records (new top-level concept)

Phase 3 introduces a second persistent surface alongside the event log: the **claim graph**. Where the event log records "X did Y at T", the claim graph records "X asserts P, citing E".

```json
{
  "schema_version": 1,
  "claim_id":       "01HXR...",
  "claim_type":     "factual|preference|policy|sighting|...",
  "predicate":      {"subject":"...","verb":"...","object":"...","modifiers":{...}},
  "evidence":       [{"kind":"event_ref","value":"01HXR..."}, {"kind":"document_cid","value":"blake3:..."}],
  "asserted_by":    "ed25519:...",
  "asserted_at":    "...",
  "evidence_level": "unverified|cited|cross_referenced|attested|disputed",
  "supersedes":     ["01HXR..."],
  "signature":      "..."
}
```

Claims live in a separate Merkle-DAG store ([M30 §4](modules/M30-evidence-ebkh.md)). They are not events. Events describe what *happened*; claims describe what is *believed*.

### 1.3 New error codes (additive)

| Code | Meaning |
|------|---------|
| `experimental_disabled` | Caller asked for an experimental capability that the node has not opted into |
| `shard_unavailable` | Distributed inference: one shard host failed mid-stream |
| `pipeline_stalled` | Distributed inference: no progress within timeout |
| `fedlearn_round_quorum` | Federated learning: too few participants for this round |
| `fedlearn_diff_invalid` | Submitted LoRA diff failed schema or bounds check |
| `evidence_contradiction` | A new claim directly contradicts a previously-attested claim |
| `civdef_audit_required` | Operation rejected because civil-defence audit policy is active and the call is unsigned by an authorised role |

---

## 2. Capability namespace allocations

Promoted from "reserved" in v2.0 or introduced new:

| Prefix | Status | Defined |
|--------|--------|---------|
| `experimental.distributed_llm.*` | experimental | [M26](modules/M26-distributed-inference.md) |
| `experimental.moe.*` | experimental | [M27](modules/M27-moe-routing.md) |
| `experimental.fedlearn.*` | experimental | [M28](modules/M28-fedlearn.md) |
| `evidence.*` | stable | [M30](modules/M30-evidence-ebkh.md) |
| `civdef.*` | stable (when civdef profile active) | [M31](modules/M31-civil-defense.md) |
| `protocol.*` | stable | [M32](modules/M32-protocol-standard.md) (conformance reporting) |

---

## 3. Phase 3 capabilities

| Name | Stability | Stream? | Trust required | Section |
|------|-----------|---------|----------------|---------|
| `experimental.distributed_llm.chat@1.0` | experimental | yes | member + research opt-in | §4.1 |
| `experimental.distributed_llm.shard.advertise@1.0` | experimental | no | trusted + research opt-in | §4.2 |
| `experimental.distributed_llm.shard.serve@1.0` | experimental | yes | trusted + research opt-in | §4.3 |
| `experimental.moe.route@1.0` | experimental | no | member + research opt-in | §4.4 |
| `experimental.moe.expert.register@1.0` | experimental | no | self + research opt-in | §4.5 |
| `experimental.moe.expert.handoff@1.0` | experimental | yes | as configured | §4.6 |
| `experimental.fedlearn.round.start@1.0` | experimental | no | anchor + research opt-in | §4.7 |
| `experimental.fedlearn.round.participate@1.0` | experimental | yes | member + research opt-in | §4.8 |
| `experimental.fedlearn.round.aggregate@1.0` | experimental | no | round coordinator | §4.9 |
| `experimental.fedlearn.lora.publish@1.0` | experimental | no | anchor | §4.10 |
| `evidence.claim.assert@1.0` | stable | no | member | §4.11 |
| `evidence.claim.dispute@1.0` | stable | no | member | §4.12 |
| `evidence.claim.attest@1.0` | stable | no | trusted | §4.13 |
| `evidence.claim.query@1.0` | stable | no | member | §4.14 |
| `evidence.provenance.trace@1.0` | stable | no | member | §4.15 |
| `civdef.alert.publish@1.0` | stable | no | authorised KatS role | §4.16 |
| `civdef.role.register@1.0` | stable | no | anchor (with role-cert) | §4.17 |
| `civdef.audit.export@1.0` | stable | yes | authorised auditor | §4.18 |
| `protocol.conformance.report@1.0` | stable | no | self | §4.19 |
| `protocol.version.list@1.0` | stable | no | unknown | §4.20 |

---

## 4. Per-capability specifications

### 4.1 `experimental.distributed_llm.chat@1.0`

Like `llm.chat@2.0` but the inference is sharded across multiple shard-server nodes. The caller's node acts as the orchestrator and streams tokens back to the user.

**Request:**
```json
{
  "params": {
    "model": "Qwen2.5-7B-Instruct",
    "sharding": "auto",
    "fallback_to_local": true
  },
  "input": {
    "messages": [...]
  }
}
```

**Stream frames:** same as `llm.chat@2.0` (`token_delta`, `done`), plus diagnostic frames:

```
event: shard_status
data: {"shards":[
  {"shard_id":"Qwen2.5-7B:0-7","host":"ed25519:...","status":"online","latency_ms":4},
  {"shard_id":"Qwen2.5-7B:8-15","host":"ed25519:...","status":"online","latency_ms":7}
]}

event: shard_failover
data: {"failed_shard":"Qwen2.5-7B:8-15","replacement":"Qwen2.5-7B:8-15@other_host"}
```

**Errors:** `shard_unavailable`, `pipeline_stalled`, `experimental_disabled`.

### 4.2 `experimental.distributed_llm.shard.advertise@1.0`

A node informs the bus that it is willing to serve a specific shard range.

**Request:**
```json
{
  "params": {},
  "input": {
    "shard_id":      "Qwen2.5-7B:0-7",
    "model_id":      "Qwen2.5-7B-Instruct",
    "layer_range":   [0, 7],
    "max_concurrent_streams": 2,
    "vram_required_mb": 6800
  }
}
```

Emits `experimental.shard.advertised` into the event log. Other nodes can then call `experimental.distributed_llm.shard.serve` on us to use the shard.

### 4.3 `experimental.distributed_llm.shard.serve@1.0`

Tensor-passing inner call. Not normally invoked by user code — used by orchestrators only. See [X08](cross-cutting/X08-tensor-transport.md) for the wire format.

### 4.4 `experimental.moe.route@1.0`

Decide which expert (model, human, service) to route a request to.

**Request:**
```json
{
  "params": {},
  "input": {
    "request_summary": "User asks about Sankt Martins parade route in Issum, 2026.",
    "tags":            ["local_knowledge","event_planning"],
    "top_k":           3
  }
}
```

**Response:**
```json
{
  "output": {
    "routes": [
      {"expert_id":"human:ed25519:...", "kind":"human", "score":0.91, "name":"Maria K."},
      {"expert_id":"corpus:niederrhein-events", "kind":"service", "score":0.74, "endpoint":"rag.query@1.0"},
      {"expert_id":"model:llama3-70b-instruct", "kind":"model", "score":0.41}
    ],
    "rationale": "Sankt Martins is a local cultural event; humans with annotated knowledge of Issum specifically score highest."
  },
  "meta": {"ms": 28}
}
```

### 4.5 `experimental.moe.expert.register@1.0`

A node (or a human via their node) declares itself an expert on some topics.

```json
{
  "params": {},
  "input": {
    "expert_kind":      "human",
    "topics":           ["sankt_martins","niederrhein_local_history"],
    "availability":     {"weekdays_19_21_local": true},
    "consent_to_route": true
  }
}
```

### 4.6 `experimental.moe.expert.handoff@1.0`

When a route to a human expert is chosen, this capability hands the conversation off to the expert's UI (typically: chat thread invite, optional E2E).

```json
{
  "params": {},
  "input": {
    "expert_id":         "human:ed25519:...",
    "context_summary":   "...",
    "permitted_replies": ["text","attachment"],
    "deadline_minutes":  60
  }
}
```

### 4.7 `experimental.fedlearn.round.start@1.0`

Anchor opens a federated learning round.

```json
{
  "params": {},
  "input": {
    "round_id":         "01HXR...",
    "base_model":       "Qwen2.5-3B-Instruct",
    "lora_config":      {"r":16,"alpha":32,"target_modules":["q_proj","v_proj"]},
    "training_corpus":  "niederrhein-emergency",
    "min_participants": 3,
    "max_minutes":      120,
    "objective":        "next_token_loss",
    "dp_noise_scale":   0.0
  }
}
```

### 4.8 `experimental.fedlearn.round.participate@1.0`

A node opts into a round and streams its computed LoRA diff back.

**Stream frames:**
```
event: phase
data: {"phase":"training","step":0,"total":200}

event: phase
data: {"phase":"training","step":200,"total":200}

event: diff
data: {"lora_diff_cid":"blake3:...","examples_seen":4321,"loss_end":0.84}
```

### 4.9 `experimental.fedlearn.round.aggregate@1.0`

Coordinator aggregates submitted diffs (FedAvg, weighted by `examples_seen`).

```json
{
  "params": {},
  "input": {
    "round_id":  "01HXR...",
    "diff_cids": ["blake3:...","blake3:...","blake3:..."]
  }
}
```

**Response:** `{"output":{"aggregated_lora_cid":"blake3:...","participants_used":3,"dropped":[]},"meta":{...}}`

### 4.10 `experimental.fedlearn.lora.publish@1.0`

After aggregation, the anchor publishes the new LoRA to the community.

```json
{
  "params": {},
  "input": {
    "round_id":            "01HXR...",
    "aggregated_lora_cid": "blake3:...",
    "base_model":          "Qwen2.5-3B-Instruct",
    "version":             "niederrhein-emergency-v3"
  }
}
```

Emits `experimental.fedlearn.lora.published` event. Nodes that have opted into the corpus' LoRA can pull the new version.

### 4.11 `evidence.claim.assert@1.0`

Assert a claim into the claim graph.

**Request:**
```json
{
  "params": {},
  "input": {
    "claim_type":   "factual",
    "predicate":    {"subject":"<Brunnen 12 Issum>","verb":"yields","object":"<200L/h drinkable water>"},
    "evidence":     [
      {"kind":"event_ref","value":"01HXR..."},
      {"kind":"document_cid","value":"blake3:..."}
    ],
    "ttl_days":     365
  }
}
```

**Response:** `{"output":{"claim_id":"01HXR...","evidence_level":"cited"},"meta":{...}}`

### 4.12 `evidence.claim.dispute@1.0`

```json
{"params":{},"input":{"claim_id":"01HXR...","reason":"...","counter_evidence":[...]}}
```

### 4.13 `evidence.claim.attest@1.0`

Trusted member adds an attestation, raising the claim's evidence level.

```json
{"params":{},"input":{"claim_id":"01HXR...","attestation":"I confirmed personally on 2026-06-08"}}
```

A claim becomes `attested` after `policy.evidence.attestations_required_for_attested` distinct trusted attestations (default 3).

### 4.14 `evidence.claim.query@1.0`

```json
{
  "params": {},
  "input": {
    "predicate_pattern": {"subject":"<Brunnen 12 Issum>","verb":"*"},
    "min_evidence_level":"cited",
    "limit": 20
  }
}
```

### 4.15 `evidence.provenance.trace@1.0`

Walk the evidence chain backwards.

```json
{
  "params": {},
  "input": {"claim_id":"01HXR...","max_depth":8}
}
```

**Response:** a DAG of `{claim_id, predicate, evidence_summary, asserted_by, asserted_at, evidence_level}` nodes.

### 4.16 `civdef.alert.publish@1.0`

Civil-defence-grade alert. Differs from `emergency.publish@1.0` (Phase 1) in that the caller must hold a `civdef.role` credential and the alert is signed for legal-evidence retention.

```json
{
  "params": {},
  "input": {
    "client_id":       "01HXR...",
    "severity":        "warning|alert|emergency|extreme",
    "category":        "weather|fire|chemical|flood|infrastructure|other",
    "title":           "Stromausfall Issum Mitte",
    "body":            "...",
    "areas":           [{"polygon":"<geojson>"}],
    "issued_by_role":  "thw_ortsverband_geldern",
    "audit_evidence":  [{"kind":"role_certificate","value":"..."}]
  }
}
```

### 4.17 `civdef.role.register@1.0`

Anchor registers a community member as holding an authorised KatS role.

```json
{
  "params": {},
  "input": {
    "subject":         "ed25519:...",
    "role":            "thw_helfer|drk_sanitaeter|feuerwehr|katastrophenschutzbeauftragter",
    "role_certificate_cid": "blake3:...",
    "expires_at":      "2027-01-01T00:00:00Z"
  }
}
```

### 4.18 `civdef.audit.export@1.0`

Stream the audit trail for a time range — used by KatS auditors.

```json
{
  "params": {},
  "input": {"from":"2026-04-01T00:00:00Z","to":"2026-06-01T00:00:00Z"}
}
```

**Stream frames:** one frame per audit record; signed batches every 1000 records for tamper evidence.

### 4.19 `protocol.conformance.report@1.0`

Generate a conformance report against the [X09](cross-cutting/X09-conformance-suite.md) suite.

```json
{
  "params": {},
  "input": {"suite_version":"3.0"}
}
```

**Response:** `{"output":{"report_cid":"blake3:...","passed":214,"failed":3,"skipped":17},"meta":{...}}`

### 4.20 `protocol.version.list@1.0`

Returns the contract versions this node supports and the conformance suite versions it has passed.

```json
{
  "output": {
    "contract_versions": ["1.0","2.0","3.0"],
    "conformance_passed": [{"suite":"3.0","report_cid":"blake3:..."}],
    "implementation": {"name":"hearthnet-py","version":"0.7.2","commit":"abc123"}
  }
}
```

---

## 5. Wire format additions

### 5.1 Tensor transport (binary)

For `experimental.distributed_llm.shard.serve@1.0` only. WebSocket frames carry **binary payloads** with a 16-byte header:

```
+---------------+---------------+---------------+
|  4B chunk_id  |  4B chunk_seq |  4B total_seq |
|  2B flags     |  2B reserved  |
+---------------+---------------+---------------+
|             tensor chunk (≤ 1 MB)             |
+-----------------------------------------------+
```

`flags`:
- `0x0001` LAST (this is the final chunk of the message)
- `0x0002` COMPRESSED (zstd-compressed; only when payload ≥ `TENSOR_COMPRESSION_THRESHOLD_BYTES`)
- `0x0004` FP16 (else FP32)

See [X08](cross-cutting/X08-tensor-transport.md) for the protocol.

### 5.2 Claim records

Claims are stored in their own Merkle-DAG; they reference events but are not events. A claim record header:

```
X-HearthNet-Claim: 01HXR...
X-HearthNet-Claim-Asserted-By: ed25519:...
```

Claim records flow through the same transport but with `Content-Type: application/vnd.hearthnet.claim+json`.

### 5.3 Civil-defence audit signatures

`civdef.*` capability calls always require both a per-call signature (per X01) **and** a `civdef.role` credential reference in headers:

```
X-HearthNet-CivDef-Role: thw_helfer
X-HearthNet-CivDef-Role-Cert: blake3:...
```

Without these, the call returns `civdef_audit_required`.

---

## 6. Manifests

### 6.1 Node manifest delta

```json
{
  "contract_version": "3.0",
  "experimental_capabilities_enabled": false,
  "civdef_profile": {
    "active": false,
    "authority": "",
    "audit_endpoint": ""
  },
  "research_opt_in": {
    "fedlearn": false,
    "distributed_inference": false,
    "moe_human_routing": false
  }
}
```

A node with `experimental_capabilities_enabled=false` does not advertise any `experimental.*` capabilities.

### 6.2 Community policy delta

```yaml
research:
  enable: false
  enabled_capabilities: []

fedlearn:
  participate: false
  share_compute_with_federated: false
  dp_noise_scale_min: 0.0

civdef:
  active: false
  authority: ""   # e.g. "Kreis Kleve Bevölkerungsschutz"
  audit_export_to: ""

evidence:
  attestations_required_for_attested: 3
  default_claim_ttl_days: 365
  retain_disputed_claims_days: 1825
```

---

## 7. Events (additive to v2.0 §7.1)

```
experimental.shard.advertised
experimental.shard.retired
experimental.fedlearn.round.opened
experimental.fedlearn.round.closed
experimental.fedlearn.lora.published
experimental.moe.expert.registered
experimental.moe.expert.unregistered
evidence.claim.asserted
evidence.claim.disputed
evidence.claim.attested
evidence.claim.superseded
civdef.alert.published
civdef.role.registered
civdef.role.revoked
civdef.audit.exported
protocol.conformance.reported
```

### Selected schemas

#### `evidence.claim.asserted`

```json
{
  "claim_id":     "01HXR...",
  "claim_type":   "factual",
  "predicate":    {...},
  "asserted_by":  "ed25519:...",
  "evidence_level": "cited",
  "claim_payload_cid": "blake3:..."
}
```

The event references the full claim record by CID; the claim itself lives in the claim store (M30 §4).

#### `civdef.alert.published`

```json
{
  "client_id":     "01HXR...",
  "severity":      "alert",
  "category":      "infrastructure",
  "title":         "Stromausfall Issum Mitte",
  "issued_by":     "ed25519:...",
  "issued_by_role":"thw_ortsverband_geldern",
  "areas":         [{...}]
}
```

#### `experimental.fedlearn.lora.published`

```json
{
  "round_id":            "01HXR...",
  "base_model":          "Qwen2.5-3B-Instruct",
  "aggregated_lora_cid": "blake3:...",
  "version":             "niederrhein-emergency-v3",
  "participants":        5,
  "objective":           "next_token_loss",
  "dp_noise_scale":      0.0
}
```

---

## 8. Pub-sub topics (additive)

| Topic | Producer | Subscriber |
|-------|----------|------------|
| `experimental.shard.advertised` | shard host | orchestrators |
| `experimental.fedlearn.round.opened.<round_id>` | coordinator | members |
| `experimental.moe.expert.registered` | expert | router |
| `evidence.claim.<claim_id>.changed` | asserter / disputer | watchers |
| `civdef.alert.<area_hash>` | civdef caller | members in area |

---

## 9. Errors — complete Phase 3 set

(additive to v2.0 §9)

| Code | When |
|------|------|
| `experimental_disabled` | Caller asked for an experimental capability the node has not opted into |
| `shard_unavailable` | A required shard host failed mid-pipeline |
| `pipeline_stalled` | No progress within `DISTRIBUTED_SHARD_HEALTH_TIMEOUT_S` |
| `fedlearn_round_quorum` | Round closed for lack of participants |
| `fedlearn_diff_invalid` | Submitted diff failed schema or norm bounds |
| `evidence_contradiction` | A new claim directly contradicts an attested claim; explicit override needed |
| `civdef_audit_required` | Operation rejected because civdef profile is active and call is not properly signed |
| `civdef_role_invalid` | Civdef role credential is missing, expired, or revoked |
| `conformance_failed` | A `protocol.*` operation depends on a passed conformance suite that this node has not passed |

---

## 10. Compatibility

- v3 contract nodes are backward-compatible with v2 nodes: v2 nodes simply do not see `experimental.*` capabilities and do not understand claim records (the relevant event types are skipped on replay).
- A v3 community must include at least one anchor that has passed the `protocol.conformance.report@1.0` suite at level 3.0, otherwise capabilities under `civdef.*` and the claim graph features remain inert (the spec calls this **degraded v3**; everything else still works).
- Promotion of an `experimental.X` to `X` is a normal v3 minor contract bump; the experimental form remains registered for one minor cycle.

---

## 11. Glossary additions

| Term | Meaning |
|------|---------|
| Shard | One contiguous range of transformer layers, served by one node |
| Pipeline | The chain of shards that produces a single LLM forward-pass |
| Expert | A routable subsystem (model, service, or human) that can answer a class of requests |
| Round | A federated-learning training session bounded in time |
| Diff | A LoRA delta tensor produced by one round participant |
| Claim | A signed assertion of a predicate, with evidence, in the claim graph |
| Attestation | A signed endorsement by a trusted member that a claim is correct |
| KatS | Katastrophenschutz — German civil protection |
| Conformance | The property of an implementation passing the X09 suite at a stated level |
