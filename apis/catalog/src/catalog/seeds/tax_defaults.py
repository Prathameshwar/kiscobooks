"""Backfill enrolled companies using the same verified source/provisioning workflow.

Run with Catalog's configured private environment file. No arbitrary tax data,
company IDs, user impersonation or migration credentials are accepted.
"""

import argparse
import asyncio

from billing_platform.db import create_engine, create_session_factory

from catalog.tasks.source_worker import WorkerSettings, refresh_once


async def backfill(settings: WorkerSettings) -> None:
    engine = create_engine(settings.database_url)
    try:
        await refresh_once(create_session_factory(engine, guarded=True), settings, strict=True)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    settings = WorkerSettings(_env_file=args.env_file)  # type: ignore[call-arg] # Private env supplies required settings.
    asyncio.run(backfill(settings))


if __name__ == "__main__":
    main()
