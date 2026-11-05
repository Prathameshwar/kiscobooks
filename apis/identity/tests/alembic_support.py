"""Driving `dbs/identity`'s Alembic chain from the test suite.

The migration tree deliberately lives outside this package (CLAUDE.md §4), so
one helper resolves the path rather than every test re-deriving it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import Script, ScriptDirectory

#: apis/identity/tests -> apis/identity -> apis -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DBS_DIR = REPO_ROOT / "dbs" / "identity"
ALEMBIC_INI = DBS_DIR / "alembic.ini"
VERSIONS_DIR = DBS_DIR / "versions"


def alembic_config(database_url: str | None = None) -> Config:
    """An Alembic ``Config`` for this service's tree.

    ``script_location`` is set absolutely rather than relying on the process cwd,
    because pytest runs from ``apis/identity`` and the ini says ``.``.
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(DBS_DIR))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def revisions() -> list[Script]:
    """Every revision, oldest first."""
    script_dir = ScriptDirectory.from_config(alembic_config())
    return list(reversed(list(script_dir.walk_revisions())))


def revision_source(script: Script) -> str:
    return Path(script.path).read_text(encoding="utf-8")


def docker_available() -> bool:
    """Whether a container runtime is reachable.

    Testcontainers raises a long way into setup when it is not, which reads as a
    test failure rather than an unmet prerequisite.
    """
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        completed = subprocess.run(  # noqa: S603  fixed argv, no shell
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0
