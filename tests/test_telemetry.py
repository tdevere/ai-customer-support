"""
Tests for shared/telemetry.py — achieves 100% line coverage.

Design notes
------------
- azure.monitor.opentelemetry.configure_azure_monitor is patched to prevent
  any real SDK initialisation during tests.
- opentelemetry.trace and opentelemetry.metrics are patched at the module
  level so their lazy-imported usages inside telemetry.py are intercepted.
- The module-level ``_configured`` flag is reset to False before AND after
  every test via an autouse fixture to eliminate state bleed.
"""

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

import shared.telemetry as tel

# ---------------------------------------------------------------------------
# Fixture — isolate _configured state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_configured():
    """Reset module-level _configured flag before and after each test."""
    tel._configured = False
    yield
    tel._configured = False


# ---------------------------------------------------------------------------
# configure_telemetry
# ---------------------------------------------------------------------------


def test_configure_telemetry_disabled_when_no_env_var(monkeypatch):
    """Returns False and stays unconfigured when connection string is absent."""
    monkeypatch.delenv("APPINSIGHTS_CONNECTION_STRING", raising=False)

    result = tel.configure_telemetry()

    assert result is False
    assert tel._configured is False


def test_configure_telemetry_enabled_when_env_var_present(monkeypatch):
    """Returns True and sets _configured=True when connection string is set."""
    monkeypatch.setenv(
        "APPINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=fake-key-00000000",
    )

    with patch("azure.monitor.opentelemetry.configure_azure_monitor") as mock_cam:
        result = tel.configure_telemetry()

    assert result is True
    assert tel._configured is True
    mock_cam.assert_called_once_with(
        connection_string="InstrumentationKey=fake-key-00000000"
    )


def test_configure_telemetry_idempotent(monkeypatch):
    """Second call returns False without reinvoking configure_azure_monitor."""
    monkeypatch.setenv(
        "APPINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=fake-key-00000000",
    )

    with patch("azure.monitor.opentelemetry.configure_azure_monitor") as mock_cam:
        first = tel.configure_telemetry()
        second = tel.configure_telemetry()

    assert first is True
    assert second is False
    mock_cam.assert_called_once()  # SDK called exactly once


# ---------------------------------------------------------------------------
# track_event
# ---------------------------------------------------------------------------


def test_track_event_noop_when_not_configured():
    """track_event is silent when _configured=False."""
    with patch("opentelemetry.trace.get_tracer") as mock_get_tracer:
        tel.track_event("test.event", {"key": "value"})

    mock_get_tracer.assert_not_called()


def test_track_event_emits_span_with_properties_when_configured():
    """track_event creates a span and sets attribute for each property."""
    tel._configured = True

    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value = mock_span

    with patch("opentelemetry.trace.get_tracer", return_value=mock_tracer):
        tel.track_event("conversation.started", {"user_id": "u1"})

    mock_tracer.start_as_current_span.assert_called_once_with("conversation.started")
    mock_span.set_attribute.assert_called_once_with("user_id", "u1")


def test_track_event_no_properties_when_configured():
    """track_event with no properties creates a span but sets no attributes."""
    tel._configured = True

    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value = mock_span

    with patch("opentelemetry.trace.get_tracer", return_value=mock_tracer):
        tel.track_event("simple.event")

    mock_tracer.start_as_current_span.assert_called_once_with("simple.event")
    mock_span.set_attribute.assert_not_called()


# ---------------------------------------------------------------------------
# track_metric
# ---------------------------------------------------------------------------


def test_track_metric_noop_when_not_configured():
    """track_metric is silent when _configured=False."""
    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        tel.track_metric("response_time_ms", 42.0)

    mock_get_meter.assert_not_called()


def test_track_metric_records_value_and_attributes_when_configured():
    """track_metric calls gauge.set with the correct value and attributes."""
    tel._configured = True

    mock_gauge = MagicMock()
    mock_meter = MagicMock()
    mock_meter.create_gauge.return_value = mock_gauge

    with patch("opentelemetry.metrics.get_meter", return_value=mock_meter):
        tel.track_metric("latency_ms", 123.4, {"endpoint": "/api/health"})

    mock_meter.create_gauge.assert_called_once_with("latency_ms")
    mock_gauge.set.assert_called_once_with(
        123.4, attributes={"endpoint": "/api/health"}
    )


def test_track_metric_empty_attributes_when_no_properties_given():
    """track_metric passes an empty dict as attributes when no properties supplied."""
    tel._configured = True

    mock_gauge = MagicMock()
    mock_meter = MagicMock()
    mock_meter.create_gauge.return_value = mock_gauge

    with patch("opentelemetry.metrics.get_meter", return_value=mock_meter):
        tel.track_metric("counter", 1.0)

    mock_gauge.set.assert_called_once_with(1.0, attributes={})


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_returns_logger_instance(monkeypatch):
    """get_logger returns a logging.Logger with the caller-supplied name."""
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    logger = tel.get_logger("test.module")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_get_logger_sets_level_from_env(monkeypatch):
    """get_logger honours the LOG_LEVEL env var."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    logger = tel.get_logger("test.debug.level")

    assert logger.level == logging.DEBUG


def test_get_logger_defaults_to_info_when_env_absent(monkeypatch):
    """get_logger defaults to INFO when LOG_LEVEL is not set."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    logger = tel.get_logger("test.default.level")

    assert logger.level == logging.INFO


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------


def test_timer_emits_metric_on_context_exit():
    """Timer calls track_metric with elapsed_ms >= 0 when context exits."""
    tel._configured = True

    mock_gauge = MagicMock()
    mock_meter = MagicMock()
    mock_meter.create_gauge.return_value = mock_gauge

    with patch("opentelemetry.metrics.get_meter", return_value=mock_meter):
        with tel.Timer("db.query_ms", {"table": "conversations"}):
            pass  # virtually instant

    mock_meter.create_gauge.assert_called_once_with("db.query_ms")
    recorded_value = mock_gauge.set.call_args[0][0]
    assert recorded_value >= 0


def test_timer_elapsed_is_positive_after_real_sleep():
    """Timer measures real elapsed time (>= 10 ms after a 10 ms sleep)."""
    tel._configured = True

    recorded: list = []

    def capture_metric(name, value, properties=None):
        recorded.append(value)

    with patch.object(tel, "track_metric", side_effect=capture_metric):
        with tel.Timer("sleep_ms"):
            time.sleep(0.01)

    assert len(recorded) == 1
    assert recorded[0] >= 10  # 10 ms sleep → at least 10 ms elapsed
