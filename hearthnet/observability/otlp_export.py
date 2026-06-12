"""OTLP metrics and trace export (X07 optional OpenTelemetry integration)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hearthnet.observability.federated import NodeMetricsTick

logger = logging.getLogger(__name__)

# Optional OpenTelemetry imports
try:
    from importlib.util import find_spec

    HAS_OTEL_METRICS = (
        find_spec("opentelemetry.metrics") is not None
        and find_spec("opentelemetry.exporter.otlp.proto.http.metric_exporter") is not None
    )
    if HAS_OTEL_METRICS:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # type: ignore[import]
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider  # type: ignore[import]
        from opentelemetry.sdk.metrics.export import (  # type: ignore[import]
            PeriodicExportingMetricReader,
        )
except ImportError:
    HAS_OTEL_METRICS = False

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import]
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import]
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # type: ignore[import]

    HAS_OTEL_TRACES = True
except ImportError:
    HAS_OTEL_TRACES = False


class OtlpExporter:
    """
    Sends HearthNet metrics and traces to an OTLP HTTP collector.

    Both opentelemetry-sdk and opentelemetry-exporter-otlp-proto-http are
    optional.  All methods return False / empty and log a debug message
    when the libraries are not installed.
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._meter_provider: Any = None
        self._tracer_provider: Any = None

    def _get_meter_provider(self) -> Any:
        """Lazily initialise the OTLP MeterProvider."""
        if self._meter_provider is not None:
            return self._meter_provider
        if not HAS_OTEL_METRICS:
            return None
        try:
            exporter = OTLPMetricExporter(endpoint=f"{self._endpoint}/v1/metrics")  # type: ignore[possibly-undefined]
            reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60_000)  # type: ignore[possibly-undefined]
            provider = MeterProvider(metric_readers=[reader])  # type: ignore[possibly-undefined]
            self._meter_provider = provider
            return provider
        except Exception as exc:
            logger.warning("OtlpExporter: failed to create MeterProvider: %s", exc)
            return None

    def _get_tracer_provider(self) -> Any:
        """Lazily initialise the OTLP TracerProvider."""
        if self._tracer_provider is not None:
            return self._tracer_provider
        if not HAS_OTEL_TRACES:
            return None
        try:
            exporter = OTLPSpanExporter(endpoint=f"{self._endpoint}/v1/traces")  # type: ignore[possibly-undefined]
            provider = TracerProvider()  # type: ignore[possibly-undefined]
            provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore[possibly-undefined]
            self._tracer_provider = provider
            return provider
        except Exception as exc:
            logger.warning("OtlpExporter: failed to create TracerProvider: %s", exc)
            return None

    async def export_metrics(self, tick: NodeMetricsTick) -> bool:
        """
        Export a :class:`NodeMetricsTick` as OTLP gauge metrics.

        Returns True if data was exported, False if opentelemetry is not
        installed or an error occurred.
        """
        if not HAS_OTEL_METRICS:
            logger.debug("OtlpExporter.export_metrics: opentelemetry not installed — skipping")
            return False
        provider = self._get_meter_provider()
        if provider is None:
            return False
        try:
            meter = provider.get_meter("hearthnet")  # type: ignore[union-attr]
            # Record gauges for each numeric field on the tick
            fields: dict[str, float | int | None] = {
                "active_capabilities": tick.active_capabilities,
                "events_per_min": tick.events_per_min,
                "peers_online": tick.peers_online,
                "llm_requests_total": tick.llm_requests_total,
                "rag_requests_total": tick.rag_requests_total,
                "cpu_percent": tick.cpu_percent,
                "memory_mb": tick.memory_mb,
                "online_seconds": tick.online_seconds,
                "gpu_memory_mb": tick.gpu_memory_mb,
            }
            attrs = {
                "node_id": tick.node_id,
                "community_id": tick.community_id,
            }
            for name, value in fields.items():
                if value is None:
                    continue
                g = meter.create_gauge(
                    f"hearthnet_{name}",
                    description=f"HearthNet {name}",
                )
                g.set(float(value), attrs)
            return True
        except Exception as exc:
            logger.warning("OtlpExporter.export_metrics error: %s", exc)
            return False

    async def export_traces(self, spans: list[dict]) -> bool:
        """
        Export a list of span dicts as OTLP traces.

        Each span dict should have at minimum: ``name``, ``trace_id``,
        ``span_id``, ``start_time``, ``end_time``.

        Returns True if spans were submitted, False otherwise.
        """
        if not HAS_OTEL_TRACES:
            logger.debug("OtlpExporter.export_traces: opentelemetry not installed — skipping")
            return False
        provider = self._get_tracer_provider()
        if provider is None:
            return False
        try:
            tracer = provider.get_tracer("hearthnet")  # type: ignore[union-attr]
            for span_dict in spans:
                name = span_dict.get("name", "hearthnet.span")
                with tracer.start_as_current_span(name) as span:
                    for k, v in span_dict.items():
                        if k not in ("name", "trace_id", "span_id", "start_time", "end_time"):
                            with contextlib.suppress(Exception):
                                span.set_attribute(k, str(v))
            return True
        except Exception as exc:
            logger.warning("OtlpExporter.export_traces error: %s", exc)
            return False

    async def shutdown(self) -> None:
        """Flush and shut down the underlying providers."""
        from contextlib import suppress

        if self._meter_provider is not None:
            with suppress(Exception):
                self._meter_provider.shutdown()  # type: ignore[union-attr]
        if self._tracer_provider is not None:
            with suppress(Exception):
                self._tracer_provider.shutdown()  # type: ignore[union-attr]
