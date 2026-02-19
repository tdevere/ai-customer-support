"""
Telemetry helpers for the AAN Customer Support system.

Wraps azure-monitor-opentelemetry so the rest of the codebase can call
configure_telemetry(), track_event(), and track_metric() without caring
whether Application Insights is configured in the current environment.

All public functions are safe no-ops when APPINSIGHTS_CONNECTION_STRING is
absent or configure_telemetry() has not been called.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

# Module-level flag — tests reset this between cases to prevent state bleed.
_configured: bool = False
_logger = logging.getLogger(__name__)


def configure_telemetry() -> bool:
    """
    Initialise the Azure Monitor OpenTelemetry SDK.

    Returns True when telemetry was enabled by this call, False when it was
    already configured or the APPINSIGHTS_CONNECTION_STRING env var is empty.

    Idempotent — safe to call at module level (e.g. in function_app.py).
    """
    global _configured

    if _configured:
        return False

    connection_string = os.getenv("APPINSIGHTS_CONNECTION_STRING", "")
    if not connection_string:
        return False

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=connection_string)
        _configured = True
        _logger.info("Azure Monitor telemetry configured")
        return True
    except Exception as exc:  # pragma: no cover
        _logger.warning("Failed to configure Azure Monitor telemetry: %s", exc)
        return False


def track_event(
    name: str,
    properties: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Emit a named event (OpenTelemetry span) to Application Insights.

    No-op when telemetry is not configured.

    :param name: Event / span name, e.g. ``"conversation.started"``.
    :param properties: Optional key-value pairs attached as span attributes.
    """
    if not _configured:
        return

    try:
        import opentelemetry.trace as trace

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span(name) as span:
            if properties:
                for key, value in properties.items():
                    span.set_attribute(key, str(value))
    except Exception as exc:  # pragma: no cover
        _logger.debug("track_event failed: %s", exc)


def track_metric(
    name: str,
    value: float,
    properties: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record a gauge metric via OpenTelemetry.

    No-op when telemetry is not configured.

    :param name:  Metric name, e.g. ``"response_time_ms"``.
    :param value: Numeric measurement.
    :param properties: Optional key-value dimension attributes.
    """
    if not _configured:
        return

    try:
        import opentelemetry.metrics as metrics

        meter = metrics.get_meter(__name__)
        gauge = meter.create_gauge(name)
        gauge.set(value, attributes=properties or {})
    except Exception as exc:  # pragma: no cover
        _logger.debug("track_metric failed: %s", exc)


def get_logger(name: str) -> logging.Logger:
    """
    Return a :class:`logging.Logger` whose level is driven by *LOG_LEVEL*.

    Using this helper keeps log levels consistent with the application
    configuration across every module.

    :param name: Logger name — typically ``__name__`` of the caller.
    """
    logger = logging.getLogger(name)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    return logger


class Timer:
    """
    Context manager that measures wall-clock elapsed time and calls
    :func:`track_metric` with the result in milliseconds on exit.

    Example::

        with Timer("db.query_ms", {"table": "conversations"}):
            result = await cosmos_client.query(...)
    """

    def __init__(
        self,
        metric_name: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.metric_name = metric_name
        self.properties = properties
        self._start: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *_: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        track_metric(self.metric_name, elapsed_ms, self.properties)
