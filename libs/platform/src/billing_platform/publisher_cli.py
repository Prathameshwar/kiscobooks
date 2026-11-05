"""Shared operator arguments and bounded outbox/dead-letter commands."""

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from billing_platform.db import create_engine, create_session_factory
from billing_platform.dead_letters import recover_dead_letters
from billing_platform.outbox_ops import inventory, retry_selected
from billing_platform.publisher import PublisherConfig


def arguments(description: str | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retry", type=uuid.UUID, nargs="+", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dead-letters", metavar="QUEUE")
    args = parser.parse_args()
    if args.apply and not args.retry:
        parser.error("--apply requires explicit --retry message IDs")
    return args


async def operate(config: PublisherConfig, args: argparse.Namespace) -> None:
    result: Any
    if args.dead_letters:
        result = await recover_dead_letters(config, args.dead_letters, args.retry, apply=args.apply)
    else:
        engine = create_engine(config.database_url)
        try:
            factory = create_session_factory(engine)
            result = (
                await retry_selected(factory, config.key.operations, args.retry, apply=args.apply)
                if args.retry
                else await inventory(
                    factory, config.key.operations, maximum_attempts=config.maximum_attempts or 12
                )
            )
        finally:
            await engine.dispose()
    print(json.dumps(result))  # noqa: T201 -- explicit sanitized operator output
