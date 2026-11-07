import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "create_databases.py"


def test_database_creation_script_reports_invalid_names_without_inline_code_errors() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "BILL_PROVISION_DATABASE_NAMES": '["identity; DROP DATABASE mysql"]',
            "BILL_PROVISION_MYSQL_USER": "root",
            "BILL_PROVISION_MYSQL_PASSWORD": "unused",
            "BILL_PROVISION_MYSQL_HOST": "localhost",
            "BILL_PROVISION_MYSQL_PORT": "3306",
        }
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 1
    assert "Configured service database names are invalid." in result.stderr
    assert "SyntaxError" not in result.stderr


def test_database_names_must_be_nonempty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILL_PROVISION_DATABASE_NAMES", '["identity", 3]')
    namespace = runpy.run_path(str(SCRIPT))

    with pytest.raises(RuntimeError, match="Configured service database names are invalid"):
        namespace["_database_names"]()
