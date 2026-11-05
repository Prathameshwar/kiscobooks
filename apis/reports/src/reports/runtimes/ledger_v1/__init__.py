"""Retained ledger runtime v1. Keep its source files when introducing later runtimes.

Financial behavior changes require a new package/version; completed runs dispatch here.
Shared database guards, authorization and Decimal primitives remain centrally maintained.
"""

import hashlib
import uuid
from importlib.resources import files
from typing import Any

from billing_platform.errors import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from reports.runtimes import calculation_dependencies
from reports.runtimes.ledger_v1.context import NativeContext
from reports.runtimes.ledger_v1.parameters import RunRequest
from reports.runtimes.ledger_v1.query import page

VERSION = 1


def identity() -> str:
    digest = hashlib.sha256()
    digest.update(calculation_dependencies().encode())
    root = files(__package__)
    for name in ("__init__.py", "context.py", "parameters.py", "query.py", "source.py"):
        source = root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode() + b"\0" + source + b"\0")
    return digest.hexdigest()


async def rows(
    db: AsyncSession,
    company: uuid.UUID,
    generation: uuid.UUID,
    code: str,
    parameters: dict[str, Any],
    limit: int,
    cursor: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        query = RunRequest.model_validate(parameters | {"generation_id": generation, "code": code})
    except ValueError as exc:
        raise ConflictError(
            "retained ledger parameters are incompatible with their runtime"
        ) from exc
    context = await NativeContext.load(db, company, generation)
    return await page(db, context, query, limit, cursor)
