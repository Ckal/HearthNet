# HearthNet — Security Findings & Fixes

*Audit date: June 15, 2026*

---

## CRITICAL — Fixed ✅

### SEC-1: NVIDIA API Key Exposed in Frontend HTML

**Severity:** Critical  
**Status:** Fixed in commit (June 15, 2026)

**What happened:**  
`app_nemotron.py` and `hearthnet/ui/tabs/nemotron.py` both passed the live API key
as the `value=` parameter of a `gr.Textbox` component:

```python
# VULNERABLE (before fix)
api_key_box = gr.Textbox(
    label="🔑 NVIDIA API Key",
    value=_NVIDIA_KEY,          # ← actual secret sent to browser
    type="password",
    ...
)
```

Gradio serializes all component initial values into the page's JavaScript state
(`window.__gradio_state__` / WebSocket init message). Even though the field is
rendered as `type="password"` (dots in the UI), the underlying value is present in:
- The page source (`view-source:`)
- The Network tab → WS frames or the initial `/info` response
- `document.querySelector('[data-testid=...]').value` in the Console tab

**How to reproduce (before fix):**
1. Open the Nemotron Space in Chrome
2. Open DevTools → Network tab
3. Reload page; inspect the first Gradio WebSocket frame or `/__/info` response
4. Search for `nvapi-` — the full key appears in plaintext

**Fix applied:**
```python
# SAFE (after fix)
api_key_box = gr.Textbox(
    label="🔑 NVIDIA API Key",
    value="",                   # ← always empty; key stays server-side
    type="password",
    placeholder="nvapi-... leave blank if NVIDIA_API_KEY env var is set",
)
```

The server-side handlers already fall back to the env var:
```python
key = api_key.strip() or _NVIDIA_KEY   # env var used if textbox is empty
```
So if `NVIDIA_API_KEY` is set as a Space secret, users never need to type it.

**Files changed:**
- `app_nemotron.py:288` — `value=_NVIDIA_KEY` → `value=""`
- `hearthnet/ui/tabs/nemotron.py:100` — `value=api_key_env` → `value=""`

---

## MEDIUM — Action Required

### SEC-2: API Key Typed by User Travels as Plaintext in POST Body

**Severity:** Medium  
**Status:** Mitigated by HTTPS, not yet end-to-end encrypted

If a user manually types an API key into the textbox (e.g. when running locally
over HTTP), the key is sent in the Gradio WebSocket message body when the button
is clicked. On HF Spaces this is HTTPS so the transport is encrypted. On local
HTTP it is not.

**Recommendation:**  
For local deployments, document that the API key textbox is for development only.
For production, always use `NVIDIA_API_KEY` env var (Space secret) and leave
the textbox empty. Add a warning label when the Space is detected as HTTP:

```python
is_https = os.getenv("SPACE_HOST", "").startswith("https")
if not is_https:
    gr.Markdown("⚠ Running over HTTP — use env var, not the key textbox")
```

### SEC-3: Rate Limiting Not Enforced on Capability Bus Endpoints

**Severity:** Medium  
**Status:** Open — `RateLimiter` class implemented but not wired

`hearthnet/bus/backpressure.py` contains a working `RateLimiter(max_calls, window_seconds)`.
The FastAPI routes at `/bus/v1/call`, `/relay/v1/join`, `/relay/v1/send` are publicly
accessible with no rate limiting. A malicious client can:
- Exhaust ZeroGPU quota by spamming `llm.chat` calls
- Flood the relay hub roster with fake node registrations

**How to fix:**
```python
# In app.py, _mount_bus_endpoints():
from hearthnet.bus.backpressure import RateLimiter

_limiter = RateLimiter(max_calls=60, window_seconds=60)

@app.middleware("http")
async def _rate_limit_middleware(request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if request.url.path.startswith(("/bus/v1", "/relay/v1")):
        if not _limiter.allow(client_ip):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "rate_limited"}, status_code=429)
    return await call_next(request)
```

### SEC-4: Capability Token Expiry Not Enforced

**Severity:** Medium  
**Status:** Open — `exp` field stored but never checked

M16 capability tokens (`hearthnet/tokens/`) store an `exp` (expiry) timestamp
in the JWT-like structure, but the router (`hearthnet/bus/router.py`) never
validates it before routing a call. An expired token continues to work indefinitely.

**How to fix:**
```python
# In hearthnet/bus/router.py, before routing:
import time
token_exp = getattr(token, "exp", None)
if token_exp and time.time() > token_exp:
    raise PermissionError("capability token expired")
```

### SEC-5: `trust_remote_code=True` in Florence2 Backend

**Severity:** Medium  
**Status:** Partially mitigated — allowlist added (June 12 security audit)

`hearthnet/services/image/backends/florence2.py` loads the Florence2 model with
`trust_remote_code=True`. The allowlist restricts which model IDs are permitted,
but if a mesh peer can influence `MODEL_ID` via a capability call, arbitrary code
execution is possible.

**Recommendation:**  
Pin the Florence2 model to a known-good hash in `pyproject.toml` or hardcode
the model ID rather than reading it from a bus payload.

---

## LOW — Informational

### SEC-6: Mesh Node URL Visible in Frontend

**Severity:** Low  
**Status:** Acceptable — not a secret

`app_nemotron.py:421` passes `value=_MESH_NODE` to a visible (non-password)
textbox. `HEARTHNET_NODE` is a public Space URL, not a credential. This is
intentional so users can see which node they are pushing to.

**No action required** unless the node URL is considered sensitive.

### SEC-7: Relay Roster is Publicly Readable

**Severity:** Low  
**Status:** By design — open mesh

`GET /relay/v1/roster` returns the full list of connected nodes with their
`node_id`, `display_name`, `community_id`, and `capabilities`. There is no
authentication on this endpoint.

**Acceptable for a public hackathon mesh.** For a production deployment,
consider requiring a community token to read the roster.

### SEC-8: SQLite Event Log Has No Encryption at Rest

**Severity:** Low  
**Status:** Open

The SQLite databases at `~/.hearthnet/corpora/*.db` and the relay roster DB
store conversation history, RAG documents, and node rosters in plaintext.

**Recommendation for production:** Use SQLCipher or encrypt sensitive fields
before writing to the DB.

---

## General Security Principles to Follow

1. **Never pass secrets as Gradio `value=`** — they go into page state.
   Always use `value=""` and read env vars server-side.

2. **`type="password"` only hides visually** — it does not encrypt the value
   in the WebSocket or page source.

3. **HF Space secrets** are the correct mechanism. Set `NVIDIA_API_KEY`,
   `MODAL_ENDPOINT`, `HEARTHNET_NODE` as Space secrets — they are injected
   as env vars at runtime and never appear in the repo or page HTML.

4. **HTTPS is mandatory** for any textbox that accepts credentials.
   Local dev over HTTP should use env vars only, never the textbox.

5. **Rate-limit all public endpoints** before opening the Space to external traffic.
