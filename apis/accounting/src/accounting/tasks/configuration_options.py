"""Bounded signed choices using native owner/field authority, never raw beneficiaries."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.listing import Page, SortColumn, apply_search, fetch_page, resolve_sort
from billing_platform.pagination import CursorCodec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.resources import BY_PATH
from accounting.schemas.configuration import OptionQuery, OptionSource, ReferenceOption
from accounting.tasks.access import authority_fingerprint, authorize, readable
from accounting.tasks.commands import require_metadata
from accounting.tasks.party_role_queries import active_party_role


def authorize_options(current: Access, source: OptionSource) -> None:
    current.context.assert_current(current.actor, current.context.company_id)
    if source in {"countries", "currencies", "states"}:
        if not any(
            current.actor.allows_scope(
                f"accounting.{family}.read", target=ScopePath(company_id=current.context.company_id)
            )
            for family in (
                "party",
                "account",
                "group",
                "bank",
                "tax",
                "policy",
                "withholding",
                "charges",
            )
        ):
            raise PermissionDeniedError("Accounting reference read access is required")
    else:
        authorize(current, BY_PATH[source], "read")


async def options(
    db: AsyncSession, current: Access, source: OptionSource, query: OptionQuery, secret: bytes
) -> Page[ReferenceOption]:
    authorize_options(current, source)
    if (query.company_currency or query.base_only) and source != "currencies":
        raise ValidationFailedError("company currency restrictions require currency choices")
    iso = source in {"countries", "currencies", "states"}
    if iso:
        model: Any = {"countries": Country, "currencies": Currency, "states": State}[source]
        identity, label = model.code, model.name
        allowed = frozenset({"code", "name", "country_code"})
        code = model.code
    else:
        spec = BY_PATH[source]
        model = spec.model
        allowed = readable(current, spec)
        label_key = next(
            (
                key
                for key in ("name", "label", "registration_type", "scheme", "kind", "deductee_type")
                if key in spec.detail.model_fields
            ),
            None,
        )
        if label_key is None:
            raise ValidationFailedError("this resource has no reference label")
        required = {label_key}
        if "code" in spec.detail.model_fields:
            required.add("code")
        if not required <= allowed:
            raise PermissionDeniedError("reference labels are protected")
        identity, label = model.id, getattr(model, label_key)
        code = model.code if "code" in spec.detail.model_fields else label
    await require_metadata(db, current)
    suffixes = {
        "withholding-rates": ("valid_from", "rate_percent"),
        "party-tax-registrations": ("registration_number", "valid_from"),
        "party-identifiers": ("valid_from",),
    }.get(source, ())
    if source == "withholding-rates" and not set(suffixes) <= allowed:
        raise PermissionDeniedError("reference terms are protected")
    suffixes = tuple(key for key in suffixes if key in allowed)
    selected = [identity.label("id"), label.label("name"), code.label("code")]
    selected.extend(getattr(model, key).label(key) for key in suffixes)
    stmt = select(*selected)
    if not iso:
        stmt = stmt.where(model.company_id == current.context.company_id)
        if hasattr(model, "status"):
            if "status" not in allowed:
                raise PermissionDeniedError("reference lifecycle is protected")
            stmt = (
                stmt.where(model.status == query.status)
                if query.status and not query.value
                else stmt.where(model.status.in_(["DRAFT", "ACTIVE"]))
                if not query.value
                else stmt
            )
        elif query.status:
            raise ValidationFailedError("this reference does not support a status filter")
    else:
        if not query.value:
            stmt = stmt.where(model.is_active.is_(True))
            if source == "currencies" and (query.company_currency or query.base_only):
                currencies = {current.context.base_currency}
                if (
                    query.company_currency
                    and not query.base_only
                    and "multi_currency" in current.context.features
                ):
                    currencies.update(current.context.allowed_currencies)
                stmt = stmt.where(model.code.in_(currencies))
        if query.status:
            raise ValidationFailedError("ISO references do not support master lifecycle filters")
    if source == "withholding-sections" and not query.value:
        from accounting.domain.withholding import FEATURES

        if "kind" not in allowed:
            raise PermissionDeniedError("withholding kind is protected")
        stmt = stmt.where(
            model.kind.in_(
                [kind for kind, feature in FEATURES.items() if feature in current.context.features]
            )
        )
    for key in (
        "party_id",
        "account_id",
        "country_code",
        "kind",
        "role",
        "currency_mode",
        "scheme",
    ):
        value = getattr(query, key)
        if value is not None:
            if source == "parties" and key == "role":
                condition = active_party_role(current, model.id, value)
                # Exact hydration retains historical identities; new selections
                # still require the matching active role and readable evidence.
                if not query.value:
                    stmt = stmt.where(condition)
                continue
            if not hasattr(model, key):
                raise ValidationFailedError("unsupported reference filter")
            if key not in allowed:
                raise PermissionDeniedError("reference filter field is protected")
            stmt = stmt.where(getattr(model, key) == value)
    if source == "states" and query.country_code is None:
        raise ValidationFailedError("state choices require a country")
    if query.value:
        try:
            exact = query.value if iso else uuid.UUID(query.value)
        except ValueError as error:
            raise ValidationFailedError("invalid reference identifier") from error
        stmt = stmt.where(identity == exact)
    stmt = apply_search(
        stmt, query.q, columns={"code": code, "name": label}, readable=frozenset({"code", "name"})
    )
    terms = resolve_sort(
        query.sort,
        default="id",
        columns={"id": SortColumn(identity.label("id"), "text" if iso else "uuid")},
        readable=frozenset({"id"}),
        supported=frozenset({("id",), ("-id",)}),
    )
    context = canonical_json(
        {
            "source": source,
            "tenant": str(current.actor.tenant_id),
            "company": str(current.context.company_id),
            "authority": authority_fingerprint(current),
            "company_settings": {
                "base_currency": current.context.base_currency,
                "currencies": sorted(current.context.allowed_currencies),
                "features": sorted(current.context.features),
            },
            "query": query.model_dump(mode="json", exclude={"cursor"}),
        }
    ).decode()
    return await fetch_page(
        db,
        stmt,
        query=query,
        terms=terms,
        codec=CursorCodec(secret, context=context),
        project=lambda row: ReferenceOption(
            value=str(row["id"]),
            label=" · ".join(
                [str(row["name"]), *(str(row[key]) for key in suffixes if row[key] is not None)]
            ),
            code=row["code"],
        ),
    )
