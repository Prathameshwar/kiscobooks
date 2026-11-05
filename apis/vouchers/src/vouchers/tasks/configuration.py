"""Versioned types, policies and unambiguous business-date bindings."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.api.auth import Access
from vouchers.domain.configuration import (
    digest,
    explicit_approval_controls,
    intersect,
    policy_wire,
    validate_policy,
)
from vouchers.domain.registry import REGISTRY_VERSION
from vouchers.models import core as m
from vouchers.schemas.configuration import Policy
from vouchers.tasks.common import get


async def effective(
    db: AsyncSession,
    current: Access,
    type_revision_id: uuid.UUID,
    *,
    date: dt.date,
    posting_date: dt.date | None = None,
    class_id: uuid.UUID | None = None,
    live: bool = True,
) -> tuple[Policy, dict[str, Any]]:
    revision = await get(db, current, m.VoucherTypeRevision, type_revision_id)
    kind = await get(db, current, m.VoucherType, revision.type_id)
    if live and (kind.status != "ACTIVE" or kind.current_revision != revision.revision_number):
        raise ConflictError(
            "voucher type revision is retired or superseded; adopt current configuration"
        )
    # Start at the company envelope, then specialize with the type/class.
    policy = Policy(approval_required=False, self_approval_allowed=True)

    def covers(binding: m.VoucherConfigurationBinding, day: dt.date) -> bool:
        return binding.valid_from <= day and (binding.valid_to is None or day < binding.valid_to)

    def date_window(day: dt.date) -> Any:
        return and_(
            m.VoucherConfigurationBinding.valid_from <= day,
            or_(
                m.VoucherConfigurationBinding.valid_to.is_(None),
                m.VoucherConfigurationBinding.valid_to > day,
            ),
        )

    bindings = list(
        await db.scalars(
            select(m.VoucherConfigurationBinding)
            .where(
                m.VoucherConfigurationBinding.company_id == current.context.company_id,
                or_(
                    m.VoucherConfigurationBinding.type_id.is_(None),
                    m.VoucherConfigurationBinding.type_id == kind.id,
                ),
                or_(date_window(date), date_window(posting_date))
                if posting_date is not None
                else date_window(date),
            )
            .order_by(m.VoucherConfigurationBinding.id)
            .limit(65)
        )
    )
    if len(bindings) > 64:
        raise ConflictError("configuration binding bound exceeded")
    revisions = []
    scopes = set()
    # Specificity is semantic, independent of creation/UUID order.
    bindings.sort(
        key=lambda binding: (
            binding.type_id is not None,
            binding.family != "COMMON",
            str(binding.id),
        )
    )
    for binding in bindings:
        if binding.family not in {"COMMON", kind.kind}:
            continue
        selected = await get(
            db, current, m.VoucherConfigurationRevision, binding.configuration_revision_id
        )
        parent = await get(db, current, m.VoucherConfigurationProfile, selected.profile_id)
        if selected.status != "PUBLISHED" or parent.status != "ACTIVE":
            raise ConflictError("bound configuration is unavailable")
        selected_policy = Policy.model_validate(selected.policy)
        if selected_policy.schema_version == 2 and kind.kind not in {
            "JOURNAL",
            "CONTRA",
            "PAYMENT",
            "RECEIPT",
        }:
            applicable = policy_wire(selected_policy)
            applicable.pop("financial", None)
            applicable.pop("money", None)
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.schema_version == 2 and (
            kind.kind not in {"SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"}
            or kind.profile != "STANDARD"
        ):
            applicable = policy_wire(selected_policy)
            applicable.pop("invoice", None)
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.purchase_calculation is not None and (
            kind.kind != "PURCHASE" or kind.profile != "STANDARD"
        ):
            # Older profiles may carry presets outside the Purchase family; they never apply here.
            applicable = policy_wire(selected_policy)
            applicable.pop("purchase_calculation", None)
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.schema_version == 2 and (
            kind.kind != "SALES" or kind.profile != "STANDARD"
        ):
            applicable = policy_wire(selected_policy)
            applicable.pop("sales_workflow", None)
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.schema_version == 2 and (
            kind.kind != "STOCK_JOURNAL" or kind.profile != "MANUFACTURING"
        ):
            applicable = policy_wire(selected_policy)
            applicable.pop("manufacturing", None)
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.schema_version == 2 and kind.kind not in {
            "JOB_WORK_IN_ORDER",
            "JOB_WORK_OUT_ORDER",
            "MATERIAL_IN",
            "MATERIAL_OUT",
        }:
            applicable = policy_wire(selected_policy)
            applicable.pop("job_process", None)
            selected_policy = Policy.model_validate(applicable)
        document_active = covers(binding, date)
        posting_active = posting_date is not None and covers(binding, posting_date)
        if selected_policy.schema_version == 2 and (
            policy_wire(selected_policy).keys() <= {"schema_version"}
            or (
                not document_active
                and selected_policy.financial is None
                and selected_policy.money is None
            )
        ):
            continue
        if selected_policy.schema_version == 1:
            # Legacy policy and digest selection always used the document date.
            if not document_active:
                continue
            posting_active = False
        elif (
            selected_policy.financial is not None or selected_policy.money is not None
        ) and posting_date is None:
            raise ConflictError("posting date is required for dated financial configuration")
        if document_active:
            scope = (binding.type_id, binding.family, "document")
            if scope in scopes:
                raise ConflictError("ambiguous configuration bindings")
            scopes.add(scope)
        if posting_active and (
            selected_policy.financial is not None or selected_policy.money is not None
        ):
            scope = (binding.type_id, binding.family, "financial")
            if scope in scopes:
                raise ConflictError("ambiguous financial configuration bindings")
            scopes.add(scope)
        if selected_policy.schema_version == 2 and (not document_active or not posting_active):
            applicable = policy_wire(selected_policy)
            if not document_active:
                applicable = {
                    key: value
                    for key, value in applicable.items()
                    if key in {"schema_version", "financial", "money"}
                }
            if not posting_active:
                applicable.pop("financial", None)
                applicable.pop("money", None)
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.order is not None and not (
            kind.kind in {"SALES_ORDER", "PURCHASE_ORDER"}
            or (kind.kind == "STOCK_JOURNAL" and kind.profile == "REQUISITION")
        ):
            # A COMMON order envelope has no meaning for unrelated voucher kinds.
            applicable = policy_wire(selected_policy)
            applicable.pop("order")
            selected_policy = Policy.model_validate(applicable)
        if selected_policy.schema_version == 2 and policy_wire(selected_policy).keys() <= {
            "schema_version"
        }:
            continue
        policy = intersect(policy, selected_policy)
        revisions.append(str(selected.id))
    policy = intersect(policy, explicit_approval_controls(Policy.model_validate(revision.policy)))
    if class_id:
        cls = await get(db, current, m.VoucherClass, class_id)
        if cls.type_revision_id != revision.id:
            raise ValidationFailedError("class belongs to another type revision")
        policy = intersect(policy, Policy.model_validate(cls.policy))
    validate_policy(kind.kind, kind.profile, policy)
    evidence = {
        "registry_version": REGISTRY_VERSION,
        "type_revision_id": str(revision.id),
        "class_id": str(class_id) if class_id else None,
        "policy_revision_ids": revisions,
        "policy": policy_wire(policy),
        "kind": kind.kind,
        "profile": kind.profile,
    }
    evidence["company_configuration_hash"] = (
        current.context.finance.configuration_hash if current.context.finance else None
    )
    evidence["digest"] = digest(evidence)
    return policy, evidence
