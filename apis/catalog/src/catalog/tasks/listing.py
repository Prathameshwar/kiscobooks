"""Bind Catalog list cursors to the current verified actor and policy generation."""

import hashlib
import hmac
import uuid

from billing_platform.gateway import Actor
from billing_platform.listing import ListQuery
from billing_platform.pagination import CursorCodec, cursor_context

from catalog.tasks.field_context import FieldContext


def cursor_codec(
    secret: bytes,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    context: FieldContext,
    query: ListQuery,
) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.cursor.v1", hashlib.sha256),
        context=cursor_context(
            resource=entity,
            tenant_id=actor.tenant_id,
            company_id=company,
            actor_id=actor.user_id,
            authority_version=str(context.source_version)
            + ":"
            + ",".join(sorted(context.readable())),
            query={**query.model_dump(mode="json", exclude={"cursor"}), "schema": 1},
        ),
    )
