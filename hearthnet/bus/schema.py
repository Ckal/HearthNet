"""JSON Schema validation for capability requests/responses."""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    import jsonschema as _jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    _jsonschema = None  # type: ignore[assignment]
    HAS_JSONSCHEMA = False

from hearthnet.bus.capability import CapabilityDescriptor


class SchemaValidator:
    """JSON Schema validation with caching. No-op if jsonschema not installed."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}  # cache_key -> unused (validate is stateless)

    def validate_request(self, descriptor: CapabilityDescriptor, body: dict) -> None:
        """Validate request body against descriptor's request_schema.

        Raises ValueError if invalid.
        """
        if not HAS_JSONSCHEMA or not descriptor.request_schema:
            return
        key = f"req:{descriptor.name}:{descriptor.version_str}"
        self._validate(descriptor.request_schema, body, key)

    def validate_response(self, descriptor: CapabilityDescriptor, response: dict) -> None:
        """Validate response against response_schema.

        Raises ValueError if invalid.
        """
        if not HAS_JSONSCHEMA or not descriptor.response_schema:
            return
        key = f"resp:{descriptor.name}:{descriptor.version_str}"
        self._validate(descriptor.response_schema, response, key)

    def validate_stream_frame(self, descriptor: CapabilityDescriptor, frame: dict) -> None:
        """Validate a streaming frame."""
        if not HAS_JSONSCHEMA or not descriptor.stream_schema:
            return
        key = f"stream:{descriptor.name}:{descriptor.version_str}"
        self._validate(descriptor.stream_schema, frame, key)

    def _validate(self, schema: dict, instance: dict, cache_key: str) -> None:
        if not HAS_JSONSCHEMA or _jsonschema is None:
            return
        try:
            _jsonschema.validate(instance, schema)
        except _jsonschema.ValidationError as exc:
            raise ValueError(f"Schema validation failed: {exc.message}") from exc


def compute_schema_hash(descriptor_partial: dict) -> str:
    """SHA-256 (or BLAKE3 if available) over canonical-JSON of descriptor."""
    canonical = json.dumps(descriptor_partial, sort_keys=True, separators=(",", ":")).encode()
    try:
        import blake3  # type: ignore[import]

        return "blake3:" + blake3.blake3(canonical).hexdigest()
    except ImportError:
        return "sha256:" + hashlib.sha256(canonical).hexdigest()
