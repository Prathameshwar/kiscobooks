"""Authenticated owner projection transaction, shared by HTTP and pull workers."""

import datetime as dt
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.claims import insert_candidate
from billing_platform.db.platform_models import IdempotencyKey, ProcessedMessage
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import audit_payload, emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vouchers.domain.configuration import digest
from vouchers.models import core as m
from vouchers.models.unit_sources import VoucherItemUnitProjection
from vouchers.schemas.sources import (
    ItemUnitFacts,
    MasterFact,
    PartyDrugLicenceFacts,
    RegulatoryFacts,
    SourceBundle,
)


async def apply_unit_fact(
    db: AsyncSession,
    body: SourceBundle,
    fact: MasterFact,
    values: dict[str, Any],
) -> None:
    parsed = ItemUnitFacts.model_validate(fact.facts)
    row = await db.scalar(
        select(VoucherItemUnitProjection)
        .where(
            VoucherItemUnitProjection.company_id == body.company_id,
            VoucherItemUnitProjection.source_id == fact.source_id,
        )
        .with_for_update()
    )
    hashed = digest(fact.model_dump(mode="json"))
    if row is None:
        db.add(
            VoucherItemUnitProjection(
                **values,
                source_id=fact.source_id,
                item_id=parsed.item_id,
                unit_id=parsed.unit_id,
                valid_from=parsed.valid_from,
                valid_to=parsed.valid_to,
                source_version=fact.source_version,
                facts=parsed.model_dump(mode="json"),
                content_hash=hashed,
            )
        )
    elif fact.source_version < row.source_version:
        return
    elif fact.source_version == row.source_version:
        if row.content_hash != hashed:
            raise ConflictError("unit source version has conflicting content")
    else:
        previous = ItemUnitFacts.model_validate(row.facts)
        if previous.model_dump(exclude={"valid_to"}) != parsed.model_dump(exclude={"valid_to"}) or (
            previous.valid_to is not None and previous.valid_to != parsed.valid_to
        ):
            raise ConflictError("published unit source was rewritten")
        row.valid_to = parsed.valid_to
        row.facts = parsed.model_dump(mode="json")
        row.source_version = fact.source_version
        row.content_hash = hashed
        row.row_version += 1


async def apply_regulatory_fact(
    db: AsyncSession,
    body: SourceBundle,
    fact: MasterFact,
    values: dict[str, Any],
) -> None:
    """Keep revisions indexed and immutable except the owner's dated closure/version."""
    parsed = RegulatoryFacts.model_validate(fact.facts)
    row = await db.scalar(
        select(m.VoucherItemRegulatoryProjection)
        .where(
            m.VoucherItemRegulatoryProjection.company_id == body.company_id,
            m.VoucherItemRegulatoryProjection.classification_id == fact.source_id,
        )
        .with_for_update()
    )
    hashed = digest(fact.model_dump(mode="json"))
    if row is None:
        db.add(
            m.VoucherItemRegulatoryProjection(
                **values,
                classification_id=fact.source_id,
                item_id=parsed.item_id,
                valid_from=parsed.valid_from,
                valid_to=parsed.valid_to,
                product_kind=parsed.product_kind,
                licence_class=parsed.licence_class,
                prescription_schedule=parsed.prescription_schedule,
                food_category_code=parsed.food_category_code,
                source_version=fact.source_version,
                source_sha256=parsed.source_sha256,
                reviewed_by=parsed.reviewed_by,
                reviewed_at=parsed.reviewed_at,
                content_hash=hashed,
            )
        )
    elif fact.source_version < row.source_version:
        return
    elif fact.source_version == row.source_version:
        if row.content_hash != hashed:
            raise ConflictError("regulatory source version has conflicting content")
    else:
        if (
            row.item_id != parsed.item_id
            or row.valid_from != parsed.valid_from
            or row.product_kind != parsed.product_kind
            or row.licence_class != parsed.licence_class
            or row.prescription_schedule != parsed.prescription_schedule
            or row.food_category_code != parsed.food_category_code
            or row.source_sha256 != parsed.source_sha256
            or row.reviewed_by != parsed.reviewed_by
            or row.reviewed_at != parsed.reviewed_at
            or (row.valid_to is not None and row.valid_to != parsed.valid_to)
            or (parsed.valid_to is not None and parsed.valid_to < row.valid_from)
        ):
            raise ConflictError("reviewed regulatory source was rewritten")
        row.valid_to = parsed.valid_to
        row.source_version = fact.source_version
        row.content_hash = hashed
        row.row_version += 1
        row.updated_at = utcnow()


async def apply_party_drug_fact(
    db: AsyncSession,
    body: SourceBundle,
    fact: MasterFact,
    values: dict[str, Any],
) -> None:
    parsed = PartyDrugLicenceFacts.model_validate(fact.facts)
    row = await db.scalar(
        select(m.VoucherPartyDrugLicenceProjection)
        .where(
            m.VoucherPartyDrugLicenceProjection.company_id == body.company_id,
            m.VoucherPartyDrugLicenceProjection.licence_id == fact.source_id,
        )
        .with_for_update()
    )
    hashed = digest(fact.model_dump(mode="json"))
    if row is None:
        db.add(
            m.VoucherPartyDrugLicenceProjection(
                **values,
                licence_id=fact.source_id,
                party_id=parsed.party_id,
                address_id=parsed.address_id,
                licence_form=parsed.licence_form,
                licence_number=parsed.licence_number,
                valid_from=parsed.valid_from,
                valid_to=parsed.valid_to,
                source_version=fact.source_version,
                source_sha256=parsed.source_sha256,
                reviewed_by=parsed.reviewed_by,
                reviewed_at=parsed.reviewed_at,
                content_hash=hashed,
            )
        )
    elif fact.source_version < row.source_version:
        return
    elif fact.source_version == row.source_version:
        if row.content_hash != hashed:
            raise ConflictError("drug licence source version has conflicting content")
    else:
        if (
            row.party_id != parsed.party_id
            or row.address_id != parsed.address_id
            or row.licence_form != parsed.licence_form
            or row.licence_number != parsed.licence_number
            or row.valid_from != parsed.valid_from
            or row.source_sha256 != parsed.source_sha256
            or row.reviewed_by != parsed.reviewed_by
            or row.reviewed_at != parsed.reviewed_at
            or (row.valid_to is not None and row.valid_to != parsed.valid_to)
        ):
            raise ConflictError("reviewed drug licence source was rewritten")
        row.valid_to = parsed.valid_to
        row.source_version = fact.source_version
        row.content_hash = hashed
        row.row_version += 1
        row.updated_at = utcnow()


def links_party(stored: m.VoucherMasterEvidence, incoming: MasterFact) -> bool:
    """Whether an account republished at its stored version only adds the ``party_id`` link.

    Account evidence replicated before Accounting published party links has no ``party_id`` key,
    and a bill whose ledger lacks it is refused until the evidence is repaired. Republishing the
    ledger at the same version is the natural repair, so this one additive upgrade is allowed:
    the stored facts lack the key, the incoming facts are identical in every other key and carry
    it, and the status is unchanged. Anything else at the same version stays a conflict.
    """
    return (
        incoming.entity_type == "account"
        and "party_id" not in stored.facts
        and "party_id" in incoming.facts
        and stored.status == incoming.status
        and {key: value for key, value in incoming.facts.items() if key != "party_id"}
        == stored.facts
    )


async def apply_bundle(
    factory: async_sessionmaker[AsyncSession], body: SourceBundle, issuer: str
) -> dict[str, Any]:
    if body.definitions and issuer != "identity":
        raise ValidationFailedError("Identity owns custom definitions")
    allowed = {
        "catalog": {
            "item",
            "item_transaction_policy",
            "item_unit_revision",
            "unit",
            "item_regulatory_classification",
        },
        "accounting": {"party", "party_drug_licence", "broker_party", "account", "fiscal_period"},
        "identity": {"salesperson", "company"},
    }[issuer]
    if any(fact.entity_type not in allowed for fact in body.masters):
        raise ValidationFailedError("master facts must come from their owner")
    with tenant_scope(body.tenant_id):
        async with factory() as db, db.begin():
            guard_values = {
                "id": uuid7(),
                "tenant_id": body.tenant_id,
                "company_id": body.company_id,
                "generation": 1,
                "row_version": 1,
            }
            await insert_candidate(db, m.VoucherCompanyGuard, guard_values)
            guard = await db.scalar(
                select(m.VoucherCompanyGuard)
                .where(m.VoucherCompanyGuard.company_id == body.company_id)
                .with_for_update()
            )
            if guard is None:
                raise ConflictError("company guard unavailable")
            guard.generation += 1
            consumer = "vouchers.sources." + issuer + ":" + str(body.company_id)
            existing = await db.get(ProcessedMessage, (consumer, body.message_id))
            receipt = await db.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.endpoint == consumer,
                    IdempotencyKey.key_value == str(body.message_id),
                )
            )
            hashed_body = digest(body.model_dump(mode="json"))
            if existing:
                if receipt is None or receipt.request_hash != hashed_body:
                    raise ConflictError("source message identity has conflicting content")
                return {"replayed": True}
            db.add(
                IdempotencyKey(
                    id=uuid7(),
                    tenant_id=body.tenant_id,
                    endpoint=consumer,
                    key_value=str(body.message_id),
                    request_hash=hashed_body,
                    state="completed",
                    response_status=200,
                    response_body={},
                    expires_at=dt.datetime(2099, 1, 1, tzinfo=dt.UTC),
                )
            )

            def values() -> dict[str, Any]:
                return {
                    "id": uuid7(),
                    "tenant_id": body.tenant_id,
                    "company_id": body.company_id,
                    "row_version": 1,
                }

            for fact in body.definitions:
                definition = fact.definition
                if (
                    definition.option_source_key not in {None, "items", "parties", "voucher_types"}
                    or definition.depends_on_key
                ):
                    raise ValidationFailedError("unsupported dynamic option dependency")
                if (
                    definition.is_searchable
                    and definition.data_type in {"text", "select", "auto_number"}
                    and definition.validation.max_length > 200
                ):
                    raise ValidationFailedError("searchable definition exceeds index width")
                row = await db.scalar(
                    select(m.VoucherDefinitionProjection)
                    .where(
                        m.VoucherDefinitionProjection.company_id == body.company_id,
                        m.VoucherDefinitionProjection.entity_type == fact.entity_type,
                        m.VoucherDefinitionProjection.field_key == definition.key,
                    )
                    .with_for_update()
                )
                wire = definition.model_dump(mode="json")
                presentation = fact.presentation.model_dump(mode="json")
                hashed = digest({"definition": wire, "presentation": presentation})
                if row is None:
                    row = m.VoucherDefinitionProjection(
                        **values(),
                        entity_type=fact.entity_type,
                        field_key=definition.key,
                        source_version=fact.source_version,
                        definition=wire,
                        presentation=presentation,
                        content_hash=hashed,
                    )
                    db.add(row)
                elif fact.source_version < row.source_version:
                    continue
                elif fact.source_version == row.source_version:
                    if row.content_hash != hashed:
                        raise ConflictError("definition version has conflicting content")
                elif row.used_at and row.content_hash != hashed:
                    prior = await db.scalar(
                        select(m.VoucherFieldAdoption).where(
                            m.VoucherFieldAdoption.company_id == body.company_id,
                            m.VoucherFieldAdoption.definition_id == row.id,
                            m.VoucherFieldAdoption.source_version == fact.source_version,
                        )
                    )
                    if prior:
                        if prior.content_hash != hashed:
                            raise ConflictError("adoption version has conflicting content")
                    else:
                        db.add(
                            m.VoucherFieldAdoption(
                                **values(),
                                definition_id=row.id,
                                source_version=fact.source_version,
                                status="PENDING",
                                definition=wire,
                                presentation=presentation,
                                content_hash=hashed,
                            )
                        )
                else:
                    row.source_version = fact.source_version
                    row.definition = wire
                    row.presentation = presentation
                    row.content_hash = hashed
                    row.row_version += 1
            for master_fact in body.masters:
                if master_fact.entity_type == "item_unit_revision":
                    await apply_unit_fact(db, body, master_fact, values())
                    continue
                if master_fact.entity_type == "item_regulatory_classification":
                    await apply_regulatory_fact(db, body, master_fact, values())
                    continue
                if master_fact.entity_type == "party_drug_licence":
                    await apply_party_drug_fact(db, body, master_fact, values())
                    continue
                master_row = await db.scalar(
                    select(m.VoucherMasterEvidence)
                    .where(
                        m.VoucherMasterEvidence.company_id == body.company_id,
                        m.VoucherMasterEvidence.owner == issuer,
                        m.VoucherMasterEvidence.entity_type == master_fact.entity_type,
                        m.VoucherMasterEvidence.source_id == master_fact.source_id,
                    )
                    .with_for_update()
                )
                hashed = digest(master_fact.model_dump(mode="json"))
                if master_row is None:
                    db.add(
                        m.VoucherMasterEvidence(
                            **values(),
                            owner=issuer,
                            **master_fact.model_dump(),
                            content_hash=hashed,
                        )
                    )
                elif master_fact.source_version < master_row.source_version:
                    continue
                elif master_fact.source_version == master_row.source_version:
                    if master_row.content_hash != hashed:
                        # The original signed item/unit feed carried no facts. Allow
                        # its one-time additive upgrade; populated evidence never
                        # changes at the same version, except that account evidence
                        # gains the ``party_id`` link Accounting began publishing later
                        # (see links_party). Item versions remain the Catalog row
                        # version used by existing voucher references.
                        upgraded = (
                            master_row.facts == {}
                            and master_fact.entity_type in {"item", "unit"}
                            and bool(master_fact.facts)
                            and master_row.status == master_fact.status
                        ) or links_party(master_row, master_fact)
                        if not upgraded:
                            raise ConflictError("master version has conflicting content")
                        master_row.facts = master_fact.facts
                        master_row.content_hash = hashed
                        master_row.row_version += 1
                else:
                    master_row.source_version = master_fact.source_version
                    master_row.status = master_fact.status
                    master_row.facts = master_fact.facts
                    master_row.content_hash = hashed
                    master_row.row_version += 1
            await db.flush()
            if any(fact.entity_type == "company" for fact in body.masters):
                from vouchers.schemas.sources import CompanyDefaultsFacts
                from vouchers.tasks.company_defaults import ensure_defaults

                # Use the accepted projection, including when an old snapshot arrived late.
                company = await db.scalar(
                    select(m.VoucherMasterEvidence).where(
                        m.VoucherMasterEvidence.company_id == body.company_id,
                        m.VoucherMasterEvidence.owner == "identity",
                        m.VoucherMasterEvidence.entity_type == "company",
                        m.VoucherMasterEvidence.source_id == body.company_id,
                    )
                )
                if company is not None and company.status == "ACTIVE":
                    facts = CompanyDefaultsFacts.model_validate(company.facts)
                    features = frozenset(
                        key for key, enabled in facts.model_dump().items() if enabled
                    )
                    await ensure_defaults(db, body.company_id, features)
            for entity in ("vouchers.voucher", "vouchers.voucher_item"):
                from billing_platform.custom_fields import CustomDefinition, validate_definitions

                rows = list(
                    await db.scalars(
                        select(m.VoucherDefinitionProjection)
                        .where(
                            m.VoucherDefinitionProjection.company_id == body.company_id,
                            m.VoucherDefinitionProjection.entity_type == entity,
                        )
                        .limit(129)
                    )
                )
                native = (
                    frozenset({"document_date", "currency", "mode", "narration"})
                    if entity == "vouchers.voucher"
                    else frozenset({"actual_quantity", "billed_quantity", "item_id", "unit_id"})
                )
                validate_definitions(
                    tuple(CustomDefinition.model_validate(row.definition) for row in rows),
                    native_fields=native,
                    option_sources=frozenset({"items", "parties", "voucher_types"}),
                )
            db.add(ProcessedMessage(consumer_name=consumer, message_id=body.message_id))
            event = "vouchers.source.applied"
            emit(
                db,
                aggregate_type="vouchers.source",
                aggregate_id=body.message_id,
                event_type=event,
                tenant_id=body.tenant_id,
                payload=audit_payload(
                    action=event,
                    entity_type="vouchers.source",
                    entity_id=body.message_id,
                    actor_user_id=None,
                    company_id=body.company_id,
                    category="system",
                )
                | {"actor_type": "system"},
            )
    return {"replayed": False}
