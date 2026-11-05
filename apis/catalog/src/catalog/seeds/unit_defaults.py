"""Operator backfill through the same verified enrollment path as company setup."""

import argparse
import asyncio

from billing_platform.db import create_engine, create_session_factory

from catalog.tasks.source_worker import WorkerSettings, refresh_once


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    # Worker deployment settings are supplied by this explicit private env file.
    settings = WorkerSettings(_env_file=args.env_file)  # type: ignore[call-arg]

    async def backfill() -> None:
        engine = create_engine(settings.database_url)
        try:
            await refresh_once(create_session_factory(engine, guarded=True), settings, strict=True)
        finally:
            await engine.dispose()

    asyncio.run(backfill())


if __name__ == "__main__":
    main()
