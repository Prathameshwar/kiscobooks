"""Lean indexed lists with signed cursors bound to live field authority."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.pagination import CursorCodec
from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.domain.custom_values import search_text
from vouchers.models import core as m
from vouchers.models import invoice as inv
from vouchers.models.commercial import VoucherAssignment
from vouchers.models.counter import VoucherCounterContext
from vouchers.schemas.reads import ListQuery
from vouchers.tasks.access import authorize, denied, fingerprint


async def listing(
    db: AsyncSession, current: Access, model: Any, query: ListQuery, secret: bytes
) -> dict[str, Any]:
    authorize(current, "read")
    base_names = {
        "id",
        "company_id",
        "row_version",
        "status",
        "code",
        "name",
        "kind",
        "profile",
        "current_revision",
        "revision_number",
        "outlet_id",
    } & {c.name for c in model.__table__.columns}
    voucher_list = model is m.Voucher
    search = query.q.strip() if query.q is not None else None
    if search == "":
        raise ValidationFailedError("search text is empty")
    voucher_id = None
    if voucher_list and search is not None:
        try:
            voucher_id = uuid.UUID(search)
        except ValueError:
            voucher_id = None
    number_lookup = voucher_list and (
        query.issue_number is not None or (search is not None and voucher_id is None)
    )
    names = base_names | (
        {"type_id", "type_code", "kind", "document_date", "issue_number"} if voucher_list else set()
    )
    entity = "vouchers.voucher" if voucher_list else "vouchers.configuration"
    blocked = denied(current, entity, names, "read")
    if blocked & {"id", "company_id", "row_version"}:
        raise PermissionDeniedError("list identity denied")
    columns = base_names - blocked
    statement = (
        select(*(getattr(model, key).label(key) for key in sorted(columns)))
        .select_from(model)
        .where(
            model.tenant_id == current.context.tenant_id,
            model.company_id == current.context.company_id,
        )
    )
    if voucher_list:
        revision = m.VoucherRevision
        assignment = m.VoucherNumberAssignment
        voucher_type = m.VoucherType
        statement = statement.join(
            revision,
            and_(
                revision.tenant_id == model.tenant_id,
                revision.company_id == model.company_id,
                revision.voucher_id == model.id,
                revision.revision_number == model.current_revision,
            ),
        ).join(
            voucher_type,
            and_(
                voucher_type.tenant_id == model.tenant_id,
                voucher_type.company_id == model.company_id,
                voucher_type.id == model.type_id,
            ),
        )
        number_on = and_(
            assignment.tenant_id == revision.tenant_id,
            assignment.company_id == revision.company_id,
            assignment.revision_id == revision.id,
        )
        statement = (
            statement.join(assignment, number_on)
            if number_lookup
            else statement.outerjoin(assignment, number_on)
        )
        derived = {
            "type_id": model.type_id,
            "type_code": voucher_type.code,
            "kind": voucher_type.kind,
            "document_date": revision.document_date,
            "issue_number": assignment.display_number,
        }
        if not denied(current, entity, {"invoice"}, "read"):
            invoice_detail = inv.VoucherInvoiceDetail
            statement = statement.outerjoin(
                invoice_detail,
                and_(
                    invoice_detail.tenant_id == revision.tenant_id,
                    invoice_detail.company_id == revision.company_id,
                    invoice_detail.revision_id == revision.id,
                ),
            )
            # The counterparty ledger account id only, never a replicated party name: the
            # caller resolves a display name from Accounting's own authorized account read
            # (the same lookup the Purchase entry screen already uses).
            derived["party_account_id"] = invoice_detail.party_account_id
            derived["ref_number"] = invoice_detail.supplier_invoice_number
            derived["amount"] = invoice_detail.payable_total
            derived["currency"] = revision.currency
        statement = statement.add_columns(
            *(column.label(key) for key, column in derived.items() if key not in blocked)
        )
        statement = statement.where(
            revision.tenant_id == current.context.tenant_id,
            revision.company_id == current.context.company_id,
        )
    elif query.sort in {"document_date", "-document_date"}:
        raise ValidationFailedError("unsupported sort")
    for key in ("type_id", "party_id", "item_id", "document_from", "document_to", "issue_number"):
        if getattr(query, key) is not None and not voucher_list:
            raise ValidationFailedError("unsupported voucher filter")
    if query.kind is not None and not voucher_list:
        if "kind" not in base_names:
            raise ValidationFailedError("unsupported kind filter")
        if "kind" in blocked:
            raise PermissionDeniedError("filter field is not readable")
        statement = statement.where(model.kind == query.kind)
    if voucher_list:
        if query.type_id is not None:
            if "type_id" in blocked:
                raise PermissionDeniedError("filter field is not readable")
            statement = statement.where(model.type_id == query.type_id)
        if query.party_id is not None:
            if denied(current, entity, {"parties"}, "read"):
                raise PermissionDeniedError("party filter is not readable")
            statement = statement.where(
                select(m.VoucherParty.id)
                .where(
                    m.VoucherParty.tenant_id == current.context.tenant_id,
                    m.VoucherParty.company_id == current.context.company_id,
                    m.VoucherParty.revision_id == revision.id,
                    m.VoucherParty.party_id == query.party_id,
                )
                .exists()
            )
        if query.item_id is not None:
            if denied(current, entity, {"lines"}, "read") or denied(
                current, "vouchers.voucher_item", {"item_id"}, "read"
            ):
                raise PermissionDeniedError("item filter is not readable")
            statement = statement.where(
                select(m.VoucherItemDetail.id)
                .where(
                    m.VoucherItemDetail.tenant_id == current.context.tenant_id,
                    m.VoucherItemDetail.company_id == current.context.company_id,
                    m.VoucherItemDetail.revision_id == revision.id,
                    m.VoucherItemDetail.item_id == query.item_id,
                )
                .exists()
            )
        if query.kind is not None:
            if "kind" in blocked:
                raise PermissionDeniedError("filter field is not readable")
            statement = statement.where(voucher_type.kind == query.kind)
        if query.document_from is not None or query.document_to is not None:
            if "document_date" in blocked:
                raise PermissionDeniedError("filter field is not readable")
            if query.document_from is not None:
                statement = statement.where(revision.document_date >= query.document_from)
            if query.document_to is not None:
                statement = statement.where(revision.document_date <= query.document_to)
        if query.issue_number is not None:
            if "issue_number" in blocked:
                raise PermissionDeniedError("filter field is not readable")
            statement = statement.where(assignment.display_number == query.issue_number)
    if search is not None:
        if voucher_list:
            if voucher_id is None:
                if "issue_number" in blocked:
                    raise PermissionDeniedError("search field is not readable")
                statement = statement.where(
                    assignment.display_number.startswith(search, autoescape=True)
                )
            else:
                statement = statement.where(model.id == voucher_id)
        else:
            if "code" not in names:
                raise ValidationFailedError("this resource has no code-prefix search")
            if "code" in blocked:
                raise PermissionDeniedError("search field is not readable")
            statement = statement.where(model.code.startswith(search, autoescape=True))
    for key in ("status", "code"):
        value = getattr(query, key)
        if value is not None:
            if key not in names:
                raise ValidationFailedError("unsupported filter")
            if key in blocked:
                raise PermissionDeniedError("filter field is not readable")
            statement = statement.where(getattr(model, key) == value)
    if query.outlet_id is not None:
        if not hasattr(model, "outlet_id"):
            raise ValidationFailedError("unsupported outlet filter")
        if "outlet_id" in blocked:
            raise PermissionDeniedError("outlet filter is not readable")
        statement = statement.where(model.outlet_id == query.outlet_id)
    if query.assignment_role is not None or query.assignment_principal_id is not None:
        if (
            model is not m.Voucher
            or query.assignment_role is None
            or query.assignment_principal_id is None
        ):
            raise ValidationFailedError("assignment filter needs a voucher role and principal")
        if denied(current, "vouchers.voucher", {"assignments"}, "read"):
            raise PermissionDeniedError("assignment filter is not readable")
        statement = statement.where(
            select(VoucherAssignment.id)
            .join(m.VoucherRevision, m.VoucherRevision.id == VoucherAssignment.revision_id)
            .where(
                VoucherAssignment.tenant_id == current.context.tenant_id,
                VoucherAssignment.company_id == current.context.company_id,
                m.VoucherRevision.tenant_id == current.context.tenant_id,
                m.VoucherRevision.company_id == current.context.company_id,
                m.VoucherRevision.voucher_id == model.id,
                m.VoucherRevision.revision_number == model.current_revision,
                VoucherAssignment.role == query.assignment_role,
                VoucherAssignment.principal_id == query.assignment_principal_id,
            )
            .exists()
        )
    if query.counter_id is not None:
        if model is not m.Voucher:
            raise ValidationFailedError("counter filter requires vouchers")
        if denied(current, "vouchers.voucher", {"counter"}, "read"):
            raise PermissionDeniedError("counter filter is not readable")
        statement = statement.where(
            select(VoucherCounterContext.id)
            .join(m.VoucherRevision, m.VoucherRevision.id == VoucherCounterContext.revision_id)
            .where(
                VoucherCounterContext.tenant_id == current.context.tenant_id,
                VoucherCounterContext.company_id == current.context.company_id,
                m.VoucherRevision.tenant_id == current.context.tenant_id,
                m.VoucherRevision.company_id == current.context.company_id,
                m.VoucherRevision.voucher_id == model.id,
                m.VoucherRevision.revision_number == model.current_revision,
                VoucherCounterContext.counter_id == query.counter_id,
            )
            .exists()
        )
    for key, column_name in (
        ("type_revision_id", "type_revision_id"),
        ("parent_id", "type_id" if model is m.VoucherTypeRevision else "profile_id"),
    ):
        value_id = getattr(query, key)
        if value_id is not None:
            if key == "type_revision_id" and voucher_list:
                if denied(current, entity, {"type_revision_id"}, "read"):
                    raise PermissionDeniedError("filter field is not readable")
                statement = statement.where(revision.type_revision_id == value_id)
                continue
            if not hasattr(model, column_name):
                raise ValidationFailedError("unsupported parent filter")
            if denied(current, entity, {column_name}, "read"):
                raise PermissionDeniedError("filter field is not readable")
            statement = statement.where(getattr(model, column_name) == value_id)
    if query.custom_key is not None or query.custom_value is not None:
        entity = query.custom_entity
        if model is not m.Voucher or query.custom_key is None or query.custom_value is None:
            raise ValidationFailedError("custom filter requires a voucher header field and value")
        if denied(current, entity, {query.custom_key, "custom_fields"}, "read"):
            raise PermissionDeniedError("custom filter field is not readable")
        definition = await db.scalar(
            select(m.VoucherDefinitionProjection).where(
                m.VoucherDefinitionProjection.tenant_id == current.context.tenant_id,
                m.VoucherDefinitionProjection.company_id == current.context.company_id,
                m.VoucherDefinitionProjection.entity_type == entity,
                m.VoucherDefinitionProjection.field_key == query.custom_key,
            )
        )
        if definition is None or not definition.definition.get("is_searchable"):
            raise ValidationFailedError("custom field index is unavailable")
        from decimal import Decimal

        from billing_platform.custom_fields import CustomDefinition, scalar_value

        custom = CustomDefinition.model_validate(definition.definition)
        import json

        supplied: Any = query.custom_value
        if custom.data_type in {"boolean", "integer", "currency_amount", "multi_select"}:
            try:
                supplied = json.loads(query.custom_value)
            except ValueError as exc:
                raise ValidationFailedError("typed custom filter requires JSON") from exc
        try:
            value = scalar_value(
                custom, supplied, currencies=frozenset({current.context.base_currency})
            )
        except ValueError as exc:
            raise ValidationFailedError("invalid typed custom filter value") from exc
        if custom.data_type == "multi_select":
            if len(value) != 1:
                raise ValidationFailedError("membership filter requires one option")
            value = value[0]
        index = m.VoucherCustomIndex
        attr = (
            "value_number"
            if custom.data_type in {"decimal", "integer", "currency_amount"}
            else "value_bool"
            if custom.data_type == "boolean"
            else "value_date"
            if custom.data_type == "date"
            else "value_datetime_at"
            if custom.data_type == "datetime"
            else "value_text"
        )
        converted = (
            Decimal(str(value["amount"] if isinstance(value, dict) else value))
            if attr == "value_number"
            else dt.date.fromisoformat(value)
            if attr == "value_date"
            else dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if attr == "value_datetime_at"
            else value
        )

        if attr == "value_text":
            converted = search_text(str(converted), case_sensitive=custom.validation.case_sensitive)
        statement = statement.where(
            select(index.id)
            .where(
                index.tenant_id == current.context.tenant_id,
                index.company_id == current.context.company_id,
                index.voucher_id == model.id,
                index.revision_id == revision.id,
                index.entity_type == entity,
                index.field_key == query.custom_key,
                getattr(index, attr) == converted,
                index.currency == value["currency"] if isinstance(value, dict) else true(),
            )
            .exists()
        )
    codec = CursorCodec(
        secret,
        context=f"vouchers:{model.__tablename__}:{fingerprint(current)}:{query.model_dump_json(exclude={'cursor'})}",
    )
    date_sort = query.sort in {"document_date", "-document_date"}
    descending = query.sort.startswith("-")
    if date_sort and "document_date" in blocked:
        raise PermissionDeniedError("sort field is not readable")
    if query.cursor:
        try:
            values = codec.decode(query.cursor)
            last = uuid.UUID(values["id"])
            if date_sort:
                last_date = dt.date.fromisoformat(values["document_date"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValidationFailedError("invalid cursor") from exc
        if date_sort:
            statement = statement.where(
                or_(
                    revision.document_date < last_date
                    if descending
                    else revision.document_date > last_date,
                    and_(
                        revision.document_date == last_date,
                        revision.voucher_id < last if descending else revision.voucher_id > last,
                    ),
                )
            )
        else:
            statement = statement.where(model.id < last if descending else model.id > last)
    ordering = (
        (revision.document_date.desc(), revision.voucher_id.desc())
        if date_sort and descending
        else (revision.document_date, revision.voucher_id)
        if date_sort
        else (model.id.desc(),)
        if descending
        else (model.id,)
    )
    rows = (await db.execute(statement.order_by(*ordering).limit(query.limit + 1))).mappings().all()
    selected = rows[: query.limit]
    next_cursor = (
        codec.encode(
            {"id": str(selected[-1]["id"])}
            | ({"document_date": selected[-1]["document_date"].isoformat()} if date_sort else {})
        )
        if len(rows) > query.limit
        else None
    )
    return {
        "items": [dict(row) for row in selected],
        "page": {
            "limit": query.limit,
            "has_more": next_cursor is not None,
            "next_cursor": next_cursor,
        },
    }
