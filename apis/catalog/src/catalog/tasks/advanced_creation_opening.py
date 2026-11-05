"""Durable per-SKU opening decisions and native owner command recovery."""

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.company_context import CompanyContext
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    CommandResult,
    execute_idempotent,
)
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from voucher_execution.identifiers import IdentifierRequirement, validate_identifier_inputs

from catalog.domain.units import QuantityRule, validate_serial_rule
from catalog.models.advanced_product_creation import AdvancedProductCreation
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
from catalog.models.tax import ItemInventoryProfile
from catalog.models.units import UnitOfMeasure
from catalog.schemas.advanced_product_creation import (
    AdvancedDefinitionStatus,
    AdvancedOpeningCheck,
    AdvancedOpeningInput,
    AdvancedOpeningSubmit,
)
from catalog.schemas.configuration import AuthoringDefaultsQuery
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks.advanced_creation_steps import (
    expected,
    native_rows,
    save_sku_progress,
    sku_progress,
)
from catalog.tasks.advanced_product_creation import audit, owned, status
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_authoring import suggestions
from catalog.tasks.pricing_commands import business_date, protected
from catalog.tasks.simple_batch_preparation import prepare_batches
from catalog.tasks.simple_creation_steps import (
    OpeningPostingRejectedError,
    after_command,
    batch_preflight,
    next_command,
    opening_preflight,
    serial_entries,
)
from catalog.tasks.simple_creation_transport import (
    CreationOwners,
    OwnerRejectedError,
    ServiceUnavailableError,
)

Factory = async_sessionmaker[AsyncSession]


def complete_if_done(row: AdvancedProductCreation) -> None:
    skus = row.progress.get("skus", {})
    if all(
        skus.get(item_id, {}).get("activated")
        and skus.get(item_id, {}).get("opening_state") in {"SKIPPED", "POSTED"}
        for item_id in row.sku_ids
    ):
        row.status, row.step = "COMPLETE", "COMPLETE"
    elif all(skus.get(item_id, {}).get("activated") for item_id in row.sku_ids):
        row.status, row.step = "OPENING", "OPENING"
    else:
        row.status, row.step = "ACTIVATING", "ACTIVATE"


async def local_preflight(
    db: AsyncSession,
    actor: Actor,
    context: CompanyContext,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    opening: AdvancedOpeningInput,
) -> tuple[SimpleCreationInput | None, list[dict[str, Any]], Decimal, set[str]]:
    company = context.company_id
    context.assert_current(actor, company)
    actor.require_scope("item.update", target=ScopePath(company_id=company))
    creation = await owned(db, actor, company, creation_id)
    if not sku_progress(creation, item_id).get("activated"):
        raise ConflictError("Activate this SKU before deciding its opening stock")
    family, item = await native_rows(db, creation, company, item_id, lock=False)
    if item.status != "ACTIVE":
        raise ConflictError("Only an active SKU can receive opening stock")
    if opening.decision == "SKIP":
        return None, [], Decimal(0), set()
    if family.kind != "GOODS":
        raise ValidationFailedError("Services do not have opening stock")
    if context.finance is None or "inventory" not in context.features:
        raise ConflictError("Complete company inventory and financial setup before stock opening")
    assert opening.opening_date is not None
    today = business_date(context.finance.timezone)
    if opening.opening_date != context.finance.books_begin_date or opening.opening_date > today:
        raise ConflictError("Opening stock must use the company books-begin date")
    access = ConfigurationAccess(db, actor, company)
    await protected(access, ItemUnitBinding)
    await protected(access, ItemUnitRevision)
    base_revisions = list(
        await db.scalars(
            select(ItemUnitRevision)
            .join(ItemUnitBinding, ItemUnitBinding.id == ItemUnitRevision.binding_id)
            .where(
                ItemUnitBinding.company_id == company,
                ItemUnitBinding.item_id == item_id,
                ItemUnitBinding.usage_role == "BASE",
                ItemUnitRevision.valid_from <= opening.opening_date,
                (ItemUnitRevision.valid_to.is_(None))
                | (ItemUnitRevision.valid_to >= opening.opening_date),
            )
            .limit(2)
        )
    )
    if len(base_revisions) != 1:
        raise ConflictError("The base unit must be effective on the books-begin date")
    await access.reference(ItemUnitBinding, base_revisions[0].binding_id)
    await access.require(base_revisions[0])
    await protected(access, ItemInventoryProfile)
    profile = await db.scalar(
        select(ItemInventoryProfile).where(
            ItemInventoryProfile.company_id == company,
            ItemInventoryProfile.item_id == item_id,
        )
    )
    if profile is None:
        raise ConflictError("An active stock inventory profile is required for opening")
    await access.require(profile)
    if profile.lot_tracking != bool(opening.batches):
        raise ValidationFailedError("Opening batches must match the SKU inventory profile")
    count = len(opening.serials) + sum(len(row.serials) for row in opening.batches)
    total = (
        sum((row.opening_quantity for row in opening.batches), Decimal(0))
        if opening.batches
        else opening.opening_quantity
    )
    if profile.serial_tracking and Decimal(count) != total:
        raise ValidationFailedError("Enter one serial or IMEI set for each physical opening unit")
    if not profile.serial_tracking and count:
        raise ValidationFailedError("Serial or IMEI entry is disabled for this SKU")
    company_types: set[str] = set()
    if profile.serial_tracking:
        base_unit = await access.reference(UnitOfMeasure, item.base_unit_id)
        if base_unit.quantity_increment != 1:
            raise ValidationFailedError("Serial tracking requires whole physical base units")
        validate_serial_rule(
            base_unit.dimension,
            QuantityRule(
                base_revisions[0].quantity_decimal_places,
                base_revisions[0].quantity_increment,
            ),
        )
        if profile.identifier_profile_id is None:
            raise ConflictError("Complete the SKU's identifier profile")
        identifier_profile = await access.reference(
            IdentifierProfile, profile.identifier_profile_id
        )
        if not identifier_profile.is_active or identifier_profile.normalization_version != 1:
            raise ConflictError("Choose an active supported identifier profile")
        await protected(access, IdentifierProfileRequirement)
        requirements = list(
            await db.scalars(
                select(IdentifierProfileRequirement)
                .where(
                    IdentifierProfileRequirement.company_id == company,
                    IdentifierProfileRequirement.profile_id == identifier_profile.id,
                )
                .order_by(IdentifierProfileRequirement.identifier_type)
                .limit(3)
            )
        )
        if not 1 <= len(requirements) <= 2:
            raise ConflictError("Complete the SKU's serial identifier requirements")
        native = []
        for requirement in requirements:
            await access.require(requirement)
            native.append(
                IdentifierRequirement.model_validate(
                    {key: getattr(requirement, key) for key in IdentifierRequirement.model_fields}
                )
            )
            if requirement.namespace_rule == "COMPANY":
                company_types.add(requirement.identifier_type)
        seen: set[tuple[str, str]] = set()
        for _, _, serial in serial_entries_for_opening(opening):
            for value, normalized in validate_identifier_inputs(native, serial.identifiers):
                identity = value.identifier_type, normalized
                if identity in seen:
                    raise ValidationFailedError("This serial or IMEI appears on another unit")
                seen.add(identity)
    request = SimpleCreationInput.model_validate(
        {
            "kind": "GOODS",
            "name": item.name,
            "base_unit_id": item.base_unit_id,
            "batch_enabled": bool(opening.batches),
            "opening_date": opening.opening_date,
            "opening_quantity": opening.opening_quantity,
            "purchase_price": opening.purchase_price,
            "batches": opening.batches,
            "serials": opening.serials,
        }
    )
    plans: list[dict[str, Any]] = []
    if opening.batches:
        defaults = await suggestions(
            access,
            AuthoringDefaultsQuery(
                as_of=today,
                kind="GOODS",
                family_id=family.id,
                item_id=item.id,
                product_type_revision_id=family.product_type_revision_id,
                unit_id=item.base_unit_id,
                currency=context.base_currency,
            ),
        )
        plans = await prepare_batches(access, defaults, request, today, opening.opening_date)
    return request, plans, total, company_types


def serial_entries_for_opening(
    opening: AdvancedOpeningInput,
) -> list[tuple[int | None, int, Any]]:
    if opening.batches:
        return [
            (batch_index, index, serial)
            for batch_index, batch in enumerate(opening.batches)
            for index, serial in enumerate(batch.serials)
        ]
    return [(None, index, serial) for index, serial in enumerate(opening.serials)]


async def advanced_serial_preflight(
    owners: CreationOwners,
    company: uuid.UUID,
    request: SimpleCreationInput,
    company_types: set[str],
) -> None:
    entries = serial_entries(request)
    if not entries:
        return
    root = f"/v1/companies/{company}"
    metadata = await owners.call(
        "accounting", "GET", root + "/stock-tracking/serials/field-set?action=prepare"
    )
    fields = {value["key"]: value for value in metadata["fields"]}
    needed = {"item_id", "identifiers", "reason"} | (
        {"lot_id"} if request.batch_enabled else set()
    )
    if any(
        key not in fields or not fields[key]["readable"] or not fields[key]["writable"]
        for key in needed
    ):
        raise PermissionDeniedError("Serial field access does not allow these details")
    inputs: list[dict[str, Any]] = []
    paths: list[str] = []
    for batch_index, index, serial in entries:
        prefix = "" if batch_index is None else f"batches.{batch_index}."
        for slot, value in enumerate(serial.identifiers):
            if value.identifier_type in company_types:
                inputs.append(value.model_dump(mode="json"))
                paths.append(prefix + f"serials.{index}.identifiers.{slot}.value")
    if inputs:
        try:
            await owners.call(
                "accounting",
                "POST",
                root + "/stock-tracking/serials/check-identifiers",
                {"identifiers": inputs},
            )
        except OwnerRejectedError as error:
            error.extra["fields"] = {
                paths[int(key.split(".")[1])]: message
                for key, message in error.extra.get("fields", {}).items()
                if key.startswith("identifiers.")
                and key.split(".")[1].isdigit()
                and int(key.split(".")[1]) < len(paths)
            }
            raise


async def preflight(
    factory: Factory,
    actor: Actor,
    context: CompanyContext,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    opening: AdvancedOpeningInput,
    owners: CreationOwners,
) -> tuple[AdvancedOpeningCheck, SimpleCreationInput | None, dict[str, Any]]:
    company = context.company_id
    with tenant_scope(actor.tenant_id):
        async with factory() as db:
            request, plans, total, company_types = await local_preflight(
                db, actor, context, creation_id, item_id, opening
            )
    if request is None:
        return (
            AdvancedOpeningCheck(
                item_id=item_id,
                opening_date=None,
                warehouse_id=None,
                total_quantity=Decimal(0),
                batch_count=0,
                serial_count=0,
            ),
            None,
            {},
        )
    await batch_preflight(owners, company, request)
    await advanced_serial_preflight(owners, company, request, company_types)
    assert opening.opening_date is not None
    capture = await owners.call(
        "accounting", "GET", f"/v1/companies/{company}/stock/openings/capture-fields"
    )
    quantity_field = next(
        (field for field in capture.get("fields", []) if field.get("key") == "quantity"), None
    )
    if quantity_field is None or not (
        quantity_field.get("readable") and quantity_field.get("writable")
    ):
        raise PermissionDeniedError("Opening quantity is protected by Accounting")
    owner_options = await opening_preflight(
        owners, company, opening.opening_date.isoformat(), opening.warehouse_id
    )
    try:
        warehouse = opening.warehouse_id or uuid.UUID(owner_options["warehouse_id"])
        type_revision_id = str(uuid.UUID(owner_options["type_revision_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ServiceUnavailableError("Opening owner returned incomplete setup") from exc
    if opening.warehouse_id is not None:
        location = await owners.call(
            "catalog", "GET", f"/v1/companies/{company}/warehouses/{warehouse}"
        )
        if location.get("id") != str(warehouse) or location.get("is_active") is not True:
            raise ConflictError("Select an active opening warehouse")
    assert context.finance is not None
    progress = {
        "today": business_date(context.finance.timezone).isoformat(),
        "opening_date": opening.opening_date.isoformat(),
        "currency": context.base_currency,
        "warehouse_id": str(warehouse),
        "type_revision_id": type_revision_id,
        "batch_plan": plans,
        "receipts": [],
    }
    return (
        AdvancedOpeningCheck(
            item_id=item_id,
            opening_date=opening.opening_date,
            warehouse_id=warehouse,
            total_quantity=total,
            batch_count=len(request.batches),
            serial_count=len(serial_entries(request)),
        ),
        request,
        progress,
    )


async def submit(
    factory: Factory,
    actor: Actor,
    context: CompanyContext,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AdvancedOpeningSubmit,
    key: str,
    owners: CreationOwners,
) -> CommandResult[AdvancedDefinitionStatus]:
    company = context.company_id
    identity = CommandIdentity(
        actor.tenant_id,
        company,
        actor.user_id,
        "catalog.advanced_product_creation.opening",
        key,
        {
            "creation_id": str(creation_id),
            "item_id": str(item_id),
            "body": body.model_dump(mode="json", exclude_unset=True),
        },
    )
    with tenant_scope(actor.tenant_id):
        async with factory() as db:
            prior = sku_progress(await owned(db, actor, company, creation_id), item_id)
            already_saved = prior.get("opening_key") == key
    opening_progress: dict[str, Any]
    if already_saved:
        check = AdvancedOpeningCheck(
            item_id=item_id,
            opening_date=None,
            warehouse_id=None,
            total_quantity=Decimal(0),
            batch_count=0,
            serial_count=0,
        )
        request, opening_progress = None, {}
    else:
        check, request, opening_progress = await preflight(
            factory, actor, context, creation_id, item_id, body.opening, owners
        )

    async def authorize(db: AsyncSession, receipt: dict[str, Any] | None) -> None:
        await owned(db, actor, company, creation_id)
        actor.require_scope("item.update", target=ScopePath(company_id=company))

    async def mutate(db: AsyncSession) -> CommandReceipt:
        row = await owned(db, actor, company, creation_id, lock=True)
        expected(row, body.expected_creation_version)
        entry = sku_progress(row, item_id)
        if not entry.get("activated") or entry.get("opening_state") not in (None, "NOT_REQUESTED"):
            raise ConflictError("Opening decision was already saved; reload its progress")
        _, item = await native_rows(db, row, company, item_id)
        if item.status != "ACTIVE":
            raise ConflictError("SKU activation changed; review opening again")
        if request is None:
            entry.update(opening_state="SKIPPED", opening_step="COMPLETE", opening_key=key)
        else:
            step = "BATCH" if request.batches else "SERIAL" if request.serials else "OPENING"
            entry.update(
                opening_state="IN_PROGRESS",
                opening_step=step,
                opening_key=key,
                opening_request=request.model_dump(mode="json", exclude_unset=True),
                opening_progress=opening_progress,
            )
        save_sku_progress(row, item_id, entry)
        complete_if_done(row)
        row.row_version += 1
        row.updated_at, row.updated_by = utcnow(), actor.user_id
        audit(db, row, actor, "update")
        await db.flush()
        return CommandReceipt(200, {"id": str(row.id), "quantity": str(check.total_quantity)})

    async def render(db: AsyncSession, receipt: dict[str, Any]) -> AdvancedDefinitionStatus:
        return status(await owned(db, actor, company, uuid.UUID(receipt["id"])))

    return await execute_idempotent(
        factory, identity, authorize=authorize, mutate=mutate, render=render, timeout_seconds=30
    )


async def advance(
    factory: Factory,
    actor: Actor,
    context: CompanyContext,
    creation_id: uuid.UUID,
    item_id: uuid.UUID,
    owners: CreationOwners,
) -> AdvancedDefinitionStatus:
    company = context.company_id
    context.assert_current(actor, company)
    actor.require_scope("item.update", target=ScopePath(company_id=company))
    token = uuid7()
    with tenant_scope(actor.tenant_id):
        async with factory() as db, db.begin():
            row = await owned(db, actor, company, creation_id, lock=True)
            entry = sku_progress(row, item_id)
            if entry.get("opening_state") != "IN_PROGRESS" or (
                row.lease_expires_at and row.lease_expires_at > utcnow()
            ):
                return status(row)
            row.lease_token, row.lease_expires_at = token, utcnow() + dt.timedelta(seconds=90)
            request = SimpleCreationInput.model_validate(entry["opening_request"])
            progress = dict(entry["opening_progress"])
            step = str(entry["opening_step"])
        opening_identity = uuid.uuid5(creation_id, str(item_id))
        try:
            pending = progress.get("pending")
            if pending is None:
                pending = await next_command(
                    owners, company, opening_identity, step, request, progress, item_id
                )
                if pending is not None:
                    parts = (
                        creation_id,
                        item_id,
                        step,
                        progress.get("batch_index", 0),
                        progress.get("serial_index", 0),
                        progress.get("attempt", 0),
                    )
                    pending["key"] = hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()
                    async with factory() as db, db.begin():
                        row = await owned(db, actor, company, creation_id, lock=True)
                        if row.lease_token != token:
                            return status(row)
                        latest = sku_progress(row, item_id)
                        progress["pending"] = pending
                        latest["opening_progress"] = progress
                        save_sku_progress(row, item_id, latest)
                        row.row_version += 1
                        row.updated_at, row.updated_by = utcnow(), actor.user_id
                        audit(db, row, actor, "update")
            result = (
                await owners.call(
                    pending["service"], "POST", pending["path"], pending["body"], pending["key"]
                )
                if pending
                else None
            )
            async with factory() as db, db.begin():
                row = await owned(db, actor, company, creation_id, lock=True)
                if row.lease_token != token:
                    return status(row)
                if pending is None:
                    row.lease_token, row.lease_expires_at = None, None
                    return status(row)
                latest = sku_progress(row, item_id)
                if pending and result is not None:
                    next_step, _ = after_command(step, request, progress, pending, result)
                    progress.setdefault("receipts", []).append(
                        {
                            "step": step,
                            "service": pending["service"],
                            "key": pending["key"],
                            "id": result.get("id"),
                            "operation_id": result.get("operation_id"),
                        }
                    )
                    progress.pop("pending", None)
                    latest["opening_step"] = next_step
                    if next_step == "COMPLETE":
                        latest["opening_state"] = "POSTED"
                        latest["opening_control_id"] = progress.get("control_id")
                        latest["opening_voucher_id"] = progress.get("voucher_id")
                        latest["opening_operation_id"] = progress.get("operation_id")
                latest["opening_progress"] = progress
                save_sku_progress(row, item_id, latest)
                complete_if_done(row)
                row.lease_token, row.lease_expires_at = None, None
                row.row_version += 1
                row.updated_at, row.updated_by = utcnow(), actor.user_id
                audit(db, row, actor, "update")
                return status(row)
        except Exception as error:
            with tenant_scope(actor.tenant_id):
                async with factory() as db, db.begin():
                    row = await owned(db, actor, company, creation_id, lock=True)
                    if row.lease_token == token:
                        latest = sku_progress(row, item_id)
                        if isinstance(error, OpeningPostingRejectedError) or (
                            isinstance(error, OwnerRejectedError) and error.definite
                        ):
                            progress = dict(latest["opening_progress"])
                            progress.pop("pending", None)
                            progress["attempt"] = progress.get("attempt", 0) + 1
                            latest["opening_progress"] = progress
                            if isinstance(error, OpeningPostingRejectedError):
                                latest["opening_step"] = "POST"
                                progress.pop("operation_id", None)
                            save_sku_progress(row, item_id, latest)
                            row.row_version += 1
                            row.updated_at, row.updated_by = utcnow(), actor.user_id
                            audit(db, row, actor, "update")
                        row.lease_token, row.lease_expires_at = None, None
            raise
