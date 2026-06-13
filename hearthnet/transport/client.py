"""HTTP client for making signed capability calls to remote nodes."""

from __future__ import annotations

import contextlib
import json
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone as _tz
UTC = _tz.utc

UTC = UTC

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _new_request_id() -> str:
    return secrets.token_hex(8)


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CallError(Exception):
    code: str
    message: str
    alt_nodes: list[str] = field(default_factory=list)

    def __post_init__(self):
        super().__init__(self.message)


class HttpClient:
    """Manages HTTP connections to one remote node. Reuses connections."""

    def __init__(
        self,
        base_url: str,
        our_node_id: str,
        community_id: str,
        signing_key=None,
        verify_ssl: bool = False,
    ):
        self._base_url = base_url.rstrip("/")
        self._our_node_id = our_node_id
        self._community_id = community_id
        self._signing_key = signing_key
        self._verify_ssl = verify_ssl
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if not HAS_HTTPX:
                raise CallError("internal_error", "httpx not installed")
            self._client = httpx.AsyncClient(verify=self._verify_ssl, timeout=30.0)
        return self._client

    async def call(
        self,
        capability: str,
        version: tuple[int, int],
        body: dict,
        *,
        timeout: float = 30.0,
    ) -> dict:
        """Make a synchronous capability call. Returns response dict."""
        client = await self._get_client()
        payload = {
            "capability": capability,
            "version": f"{version[0]}.{version[1]}",
            **body,
        }
        headers = self._make_headers(payload)
        try:
            resp = await client.post(
                f"{self._base_url}/bus/v1/call",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise CallError("http_error", str(exc)) from exc
        except Exception as exc:
            raise CallError("partition", str(exc)) from exc

    async def stream(
        self,
        capability: str,
        version: tuple[int, int],
        body: dict,
    ) -> AsyncIterator[dict]:
        """Make a streaming capability call. Yields SSE frame dicts."""
        if not HAS_HTTPX:
            raise CallError("internal_error", "httpx not installed")
        payload = {
            "capability": capability,
            "version": f"{version[0]}.{version[1]}",
            "stream": True,
            **body,
        }
        headers = self._make_headers(payload)
        headers["Accept"] = "text/event-stream"
        try:
            async with (
                httpx.AsyncClient(verify=self._verify_ssl) as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/bus/v1/call",
                    json=payload,
                    headers=headers,
                ) as resp,
            ):
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        with contextlib.suppress(json.JSONDecodeError):
                            yield json.loads(line[6:])
        except Exception as exc:
            raise CallError("partition", str(exc)) from exc

    async def fetch_manifest(self) -> dict:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self._base_url}/manifest")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise CallError("manifest_fetch_failed", str(exc)) from exc

    async def fetch_capabilities(self) -> list:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self._base_url}/bus/v1/capabilities")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise CallError("capabilities_fetch_failed", str(exc)) from exc

    async def health(self) -> dict:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self._base_url}/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise CallError("health_check_failed", str(exc)) from exc

    def _make_headers(self, payload: dict) -> dict:
        """Sign the request envelope and return X-HearthNet-* headers."""
        headers = {
            "X-HearthNet-From": self._our_node_id,
            "X-HearthNet-Community": self._community_id,
            "X-HearthNet-Request-Id": _new_request_id(),
            "X-HearthNet-Timestamp": _iso_now(),
            "Content-Type": "application/json",
        }
        if self._signing_key is not None:
            try:
                from hearthnet.identity.keys import sign_payload

                signed = sign_payload(payload, self._signing_key)
                headers["X-HearthNet-Signature"] = signed.get("signature", "")
            except Exception:
                pass
        return headers

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
