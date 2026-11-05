"""Seed legacy-company advanced mode from an explicit Identity company roster.

Run under an operator account during the coordinated rollout window. Read the
connection from CATALOG_DATABASE_URL; never accept credentials in CLI arguments.
The default is a dry run. Existing configuration is never overwritten.
"""

import argparse
import asyncio
import os
import uuid
from pathlib import Path

from billing_platform.db import create_engine, create_session_factory

from catalog.tasks.product_mode_seed import LegacyRoster, seed


async def run(args: argparse.Namespace) -> None:
    roster = LegacyRoster.model_validate_json(args.manifest.read_text(encoding="utf-8-sig"))
    engine = create_engine(os.environ["CATALOG_DATABASE_URL"])
    try:
        count = await seed(create_session_factory(engine), roster, args.operator, apply=args.apply)
        print(f"{'Seeded' if args.apply else 'Would seed'} {count} legacy companies")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--operator", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))
