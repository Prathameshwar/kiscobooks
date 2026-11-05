"""Allowlisted failure diagnostics: no exception text, traceback, request or SQL values."""

from __future__ import annotations

import json
import logging
import re

from billing_platform.db.types import utcnow


def safe_trace_id(value: str | None) -> str | None:
    return value if value is not None and re.fullmatch(r"[0-9a-fA-F]{32}", value) else None


def log_failure(
    logger: logging.Logger,
    *,
    service: str,
    event: str,
    error: Exception,
    trace_id: str | None = None,
) -> None:
    """Emit a single JSON diagnostic using code-owned names and sanitized correlation.

    A caller must not append exc_info or the original exception/request to this record.
    The actual error text can contain passwords, SQL parameters or protected field values.
    """
    if any(not re.fullmatch(r"[a-z][a-z0-9_.-]{0,119}", name) for name in (service, event)):
        raise ValueError("diagnostic names must be bounded code-owned identifiers")
    error_type = type(error).__name__
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", error_type):
        error_type = "Exception"
    payload = {
        "occurred_at": utcnow().isoformat(),
        "service": service,
        "event": event,
        "error_type": error_type,
        "trace_id": safe_trace_id(trace_id),
    }
    logger.error("%s", json.dumps(payload, sort_keys=True, separators=(",", ":")))
