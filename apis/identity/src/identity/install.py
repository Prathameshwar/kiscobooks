"""Install/update Identity's schema and all shipped defaults in one command.

Run during platform installation/deployment, never from request handlers or API startup.
The target database must exist; its URL comes from IDENTITY_DATABASE_URL.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config
from billing_platform.db import create_engine, create_session_factory
from billing_platform.reference.seed import seed_reference

from identity.seeds.business_classifications import seed_business_classifications
from identity.seeds.installation import seed_installation
from identity.seeds.pricing import seed_pricing
from identity.seeds.regional import seed_regional_defaults
from identity.seeds.roles import seed_system_roles

_MIGRATIONS = Path(__file__).resolve().parents[4] / "dbs/identity"


async def seed_installation_defaults(url: str) -> None:
    """All default rows commit together; a failed seed leaves no partial defaults."""
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as session, session.begin():
            await seed_reference(session, managed=True)
            await seed_regional_defaults(session)
            await seed_system_roles(session)
            await seed_business_classifications(session)
            await seed_installation(session)
            await seed_pricing(session)
    finally:
        await engine.dispose()


def install_identity(url: str) -> None:
    """Migrate first, then seed. Re-running safely completes interrupted installations."""
    config = Config(str(_MIGRATIONS / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    asyncio.run(seed_installation_defaults(url))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    url = os.environ.get("IDENTITY_DATABASE_URL")
    if not url:
        parser.error("set IDENTITY_DATABASE_URL to the intended existing database")
    install_identity(url)
    print("Identity schema, reference data, roles, classifications and pricing are ready.")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
