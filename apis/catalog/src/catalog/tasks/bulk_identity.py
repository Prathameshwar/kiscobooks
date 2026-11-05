"""Pin semantic owner facts while allowing authenticated no-change lease renewal."""

import hashlib
import uuid

from billing_platform.errors import ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.snapshots import MAX_RECORDS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.projections import PROJECTION_MODELS
from catalog.tasks.bulk_access import wire
from catalog.tasks.projections import require_identity_context


async def identity_digest(db: AsyncSession, company: uuid.UUID) -> str:
    # The source checkpoint lock makes this a consistent view with native writes.
    await require_identity_context(db, company)
    digest = hashlib.sha256()
    count, size = 0, 0
    for kind, model in sorted(PROJECTION_MODELS.items()):
        fields = sorted(
            set(model.__table__.columns.keys())
            - {
                "id",
                "tenant_id",
                "company_id",
                "source_version",
            }
        )
        rows = await db.scalars(
            select(model)
            .where(model.company_id == company)
            .order_by(model.source_id)
            .limit(MAX_RECORDS + 1)
        )
        for row in rows:
            encoded = canonical_json(
                {"kind": kind, "fact": {field: wire(getattr(row, field)) for field in fields}}
            )
            count, size = count + 1, size + len(encoded)
            if count > MAX_RECORDS or size > 8 * 1024 * 1024:
                raise ValidationFailedError("Identity facts exceed the bulk review bound")
            digest.update(encoded)
            digest.update(b"\n")
    return digest.hexdigest()
