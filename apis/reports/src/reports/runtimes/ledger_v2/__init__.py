"""Ledger runtime v2: complete opening labels and scoped journal drilldowns.

The immutable v1 source remains packaged for existing completed pinned queries.
"""

import hashlib
import uuid
from importlib.resources import files
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from reports.runtimes import calculation_dependencies
from reports.runtimes.ledger_v2.context import NativeContext
from reports.runtimes.ledger_v2.parameters import RunRequest
from reports.runtimes.ledger_v2.query import page

VERSION = 2


def identity() -> str:
    digest = hashlib.sha256(calculation_dependencies().encode())
    root = files("reports")
    for name in (
        "runtimes/ledger_v2/__init__.py",
        "runtimes/ledger_v2/context.py",
        "runtimes/ledger_v2/query.py",
        "runtimes/ledger_v2/source.py",
        "runtimes/ledger_v2/parameters.py",
    ):
        digest.update(
            name.encode() + b"\0" + root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
        )
    return digest.hexdigest()


async def rows(
    db: AsyncSession,
    company: uuid.UUID,
    generation: uuid.UUID,
    code: str,
    parameters: dict[str, Any],
    limit: int,
    cursor: dict[str, Any] | None,
    *,
    include_positions: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    query = RunRequest.model_validate(parameters | {"generation_id": generation, "code": code})
    context = await NativeContext.load(db, company, generation)
    return await page(db, context, query, limit, cursor, include_positions=include_positions)
