"""Tests for backend logging configuration (issue #10).

These exercise the leveled/structured logging setup in isolation — no live DB,
LLM, or radio state is touched.
"""
import json
import logging

import backend_api


def test_json_formatter_emits_valid_json_with_level_and_logger():
    formatter = backend_api.JsonLogFormatter()
    record = logging.LogRecord(
        name="backend-api",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Error writing playlist: %s",
        args=("boom",),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "ERROR"
    assert payload["logger"] == "backend-api"
    assert payload["message"] == "Error writing playlist: boom"
    assert "ts" in payload


def test_json_formatter_includes_exception_traceback():
    formatter = backend_api.JsonLogFormatter()
    try:
        raise ValueError("kaboom")
    except ValueError:
        record = logging.LogRecord(
            name="backend-api",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=logging.sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))

    assert "exc_info" in payload
    assert "ValueError: kaboom" in payload["exc_info"]


def test_configure_logging_honors_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    backend_api.configure_logging()

    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_text_format_by_default(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    backend_api.configure_logging()
    handler = logging.getLogger().handlers[0]

    assert not isinstance(handler.formatter, backend_api.JsonLogFormatter)


def test_configure_logging_json_format_when_requested(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")

    backend_api.configure_logging()
    handler = logging.getLogger().handlers[0]

    assert isinstance(handler.formatter, backend_api.JsonLogFormatter)
