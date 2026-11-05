"""Owner-scoped maintenance entry point; no public cleanup API or stored actor token."""

import argparse
import asyncio
import json
import os
import uuid
from collections.abc import Awaitable, Callable

from billing_platform.db import create_engine, create_session_factory
from billing_platform.import_cleanup import cleanup_imports


def main(
    namespace: str, cleanup: Callable[..., Awaitable[dict[str, int]]] = cleanup_imports
) -> None:
    parser = argparse.ArgumentParser(description="Expire retained import payloads and history")
    parser.add_argument("--tenant", type=uuid.UUID, required=True)
    parser.add_argument("--company", type=uuid.UUID, required=True)
    parser.add_argument("--limit", type=int, default=50, choices=range(1, 101))
    args = parser.parse_args()

    async def run() -> dict[str, int]:
        engine = create_engine(os.environ[namespace.upper() + "_DATABASE_URL"])
        try:
            return await cleanup(
                create_session_factory(engine, guarded=True),
                args.tenant,
                args.company,
                namespace,
                limit=args.limit,
            )
        finally:
            await engine.dispose()

    try:
        print(json.dumps(asyncio.run(run()), sort_keys=True))  # noqa: T201 - maintenance result only
    except Exception as exc:
        raise SystemExit("Import cleanup failed: " + type(exc).__name__) from None
