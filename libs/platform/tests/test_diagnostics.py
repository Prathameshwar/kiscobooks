import json
import logging

import pytest

from billing_platform.diagnostics import log_failure, safe_trace_id


@pytest.mark.parametrize("value", [None, "", "SQL private value", "a" * 31, "a" * 33, "z" * 32])
def test_diagnostic_trace_rejects_arbitrary_input(value: str | None) -> None:
    assert safe_trace_id(value) is None


def test_diagnostic_contains_only_safe_context(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("diagnostic-test")
    try:
        raise RuntimeError("private password and SQL values")
    except RuntimeError as exc:
        log_failure(logger, service="catalog", event="http.failed", error=exc, trace_id="A" * 32)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    payload = json.loads(record.getMessage())
    assert set(payload) == {"occurred_at", "service", "event", "error_type", "trace_id"}
    assert payload["error_type"] == "RuntimeError" and payload["trace_id"] == "A" * 32
    assert record.exc_info is None and record.stack_info is None
    assert "private" not in record.getMessage()


def test_diagnostic_rejects_untrusted_names_and_normalizes_exception_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("diagnostic-test")
    for service, event in (("invalid service", "failed"), ("catalog", "invalid\nevent")):
        with pytest.raises(ValueError):
            log_failure(logger, service=service, event=event, error=RuntimeError("private"))
    exception_type = type("untrusted exception name", (Exception,), {})
    log_failure(logger, service="catalog", event="failed", error=exception_type("private"))
    payload = json.loads(caplog.records[-1].getMessage())
    assert payload["error_type"] == "Exception" and payload["trace_id"] is None
