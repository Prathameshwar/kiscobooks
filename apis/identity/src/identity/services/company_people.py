"""Current company affiliations, independent of authorization grants."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from billing_platform.db.types import utcnow
from sqlalchemy import Select, or_, select

from identity.models import Membership, User


def company_people(company_id: uuid.UUID) -> Select[tuple[User]]:
    affiliated = current_company_memberships([company_id]).with_only_columns(Membership.user_id)
    return select(User).where(User.id.in_(affiliated), User.user_type == "tenant_user")


def current_company_memberships(company_ids: Collection[uuid.UUID]) -> Select[tuple[Membership]]:
    today = utcnow().date()
    return select(Membership).where(
        Membership.company_id.in_(company_ids),
        Membership.is_active.is_(True),
        or_(Membership.started_on.is_(None), Membership.started_on <= today),
        or_(Membership.ended_on.is_(None), Membership.ended_on >= today),
    )
