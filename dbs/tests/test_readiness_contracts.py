"""Check readiness inventories in isolated service interpreters."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("service", ["identity", "accounting", "vouchers"])
def test_readiness_matches_migration_head_and_owned_models(service: str) -> None:
    python = ROOT / "apis" / service / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    result = subprocess.run(
        [
            str(python),
            "-c",
            "from alembic.config import Config; "
            "from alembic.script import ScriptDirectory; "
            f"from {service}.metadata import MIGRATION_HEAD, service_metadata; "
            "from billing_platform.db.base import Base; "
            "assert [MIGRATION_HEAD] == ScriptDirectory.from_config("
            "Config('alembic.ini')).get_heads(), 'readiness revision is stale'; "
            "owned = {mapper.local_table.name for mapper in Base.registry.mappers "
            f"if mapper.class_.__module__.startswith('{service}.')" + "}; "
            "assert owned <= set(service_metadata().tables), "
            "'readiness omits registered service tables'",
        ],
        cwd=ROOT / "dbs" / service,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
