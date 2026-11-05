"""Expendable job process with a parent-enforced deadline on every Celery pool."""

import json
import os
import subprocess
import sys
import uuid
from typing import Any

from reports.config import Settings


def lane_seconds(settings: Settings, lane: str) -> int:
    return {
        "SHORT": 60,
        "BULK": max(settings.export_timeout_seconds, settings.bulk_timeout_seconds) + 60,
        "RENDER": 90,
    }[lane]


def command(scope: tuple[uuid.UUID, uuid.UUID, uuid.UUID], seconds: float) -> list[str]:
    return [
        str(getattr(sys, "_base_executable", sys.executable))
        if sys.platform == "win32"
        else sys.executable,
        "-m",
        "reports.tasks.job_child",
        *(str(key) for key in scope),
        str(seconds),
    ]


def environment() -> dict[str, str]:
    values = dict(os.environ)
    if sys.platform == "win32":
        # Invoke the interpreter directly, bypassing Windows' venv redirector process.
        # CPython uses this launcher variable to retain the active venv/site-packages.
        # Killing a redirector alone would leave its real interpreter running.
        values["__PYVENV_LAUNCHER__"] = sys.executable
    return values


def configuration(settings: Settings) -> str:
    # Pydantic masks SecretStr by default. Send real credentials only over the child's
    # private stdin, never argv, logs or a temporary configuration file.
    def encode(value: Any) -> str:
        from pydantic import SecretStr

        return value.get_secret_value() if isinstance(value, SecretStr) else str(value)

    return json.dumps(settings.model_dump(mode="python"), default=encode)


def run(settings: Settings, scope: tuple[uuid.UUID, uuid.UUID, uuid.UUID], lane: str) -> None:
    seconds = lane_seconds(settings, lane)
    try:
        result = subprocess.run(  # noqa: S603 -- fixed module/UUID arguments; no caller command.
            command(scope, seconds),
            input=configuration(settings).encode(),
            env=environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=seconds,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps the child before raising, including on Windows.
        raise TimeoutError("report job exceeded its lane deadline") from None
    if result.returncode == 124:
        raise TimeoutError("report job exceeded its lane deadline")
    if result.returncode != 0:
        raise RuntimeError("report child failed")
