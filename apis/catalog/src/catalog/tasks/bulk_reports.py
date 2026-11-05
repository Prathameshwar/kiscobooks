"""Actor-bound expiring download tickets; every download still checks current fields."""

import hashlib
import hmac

from billing_platform.gateway import Actor
from billing_platform.pagination import CursorCodec

from catalog.models.bulk import BulkJob


def report_codec(secret: bytes, actor: Actor, job: BulkJob) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.bulk.report.v1", hashlib.sha256),
        context=f"bulk-report:{actor.tenant_id}:{job.company_id}:{actor.user_id}:{job.id}",
        ttl_seconds=300,
    )
