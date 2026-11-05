"""Catalog's opt-in ready-product import, with remote preflight outside transactions."""

import hashlib
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from billing_platform.bulk import BulkRecord, selection_digest
from billing_platform.company_context import CompanyContext
from billing_platform.db import tenant_scope
from billing_platform.db.access import company_object
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.gateway import Actor
from billing_platform.import_contracts import ImportBatch
from billing_platform.import_engine import revision, scoped_job
from billing_platform.import_models import ImportTemplateSnapshot
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.barcodes import gtin_aliases
from catalog.models.simple_product_creation import SimpleProductCreation
from catalog.tasks import simple_import_definition as definition
from catalog.tasks.bulk_registry import Runtime
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.master_imports import CatalogImportAdapter
from catalog.tasks.simple_creation_steps import opening_preflight
from catalog.tasks.simple_creation_transport import CreationOwners
from catalog.tasks.simple_import_validation import validate_product
from catalog.tasks.simple_product_creation import enqueue


class SimpleCatalogImportAdapter(CatalogImportAdapter):
    def __init__(
        self,
        actor: Actor,
        company: uuid.UUID,
        factory: async_sessionmaker[AsyncSession],
        secret: bytes,
        context: CompanyContext | None,
        owners: CreationOwners,
    ) -> None:
        super().__init__(actor, company, factory, secret)
        self.definitions[definition.DEFINITION] = "Simple products ready for use"
        self.context, self.owners = context, owners
        self.opening_fields: list[dict[str, Any]] = []
        self.opening: dict[str, Any] = {}
        self.opening_error: PlatformError | None = None
        self.kind: str | None = None
        self.command_group_limit: int | None = None
        self.duplicate_codes: set[str] = set()
        self.duplicate_barcodes: set[str] = set()
        self.sale_levels: list[dict[str, Any]] = []

    def financial_context(self) -> CompanyContext:
        if self.context is None:
            raise AuthenticationRequiredError(
                "Fresh company context is required for Simple imports"
            )
        self.context.assert_current(self.actor, self.company)
        if self.context.finance is None or not self.context.finance.company_active:
            raise ConflictError("Complete company financial setup before importing products")
        return self.context

    async def snapshot(
        self, db: AsyncSession, name: str, parameters: dict[str, str]
    ) -> dict[str, Any]:
        if name != definition.DEFINITION:
            return await super().snapshot(db, name, parameters)
        return await definition.snapshot(
            db, self.actor, self.financial_context(), parameters, self.opening_fields
        )

    async def fingerprint(self, db: AsyncSession, name: str) -> str:
        native = await super().fingerprint(db, name)
        if name != definition.DEFINITION:
            return native
        context = self.financial_context()
        assert context.finance is not None
        return selection_digest({"catalog": native, "finance": context.finance.configuration_hash})

    async def readable(self, db: AsyncSession, batch: ImportBatch) -> None:
        simple = [row for row in batch.records if row.resource == definition.RESOURCE]
        if not simple:
            return await super().readable(db, batch)
        if len(simple) != len(batch.records):
            raise ValidationFailedError(
                "Simple creation imports cannot mix native command resources"
            )
        fields = set().union(*(set(row.data) for row in simple))
        await definition.require_readable(db, self.actor, self.company, fields)
        if fields & {"opening_quantity", "opening_date"}:
            quantity = next(
                (field for field in self.opening_fields if field["key"] == "quantity"), {}
            )
            if not quantity.get("readable"):
                raise PermissionDeniedError("Opening stock import fields are protected")

    async def before_import_command(
        self, action: str, body: BaseModel, job_id: uuid.UUID | None
    ) -> None:
        if action not in {"validate", "retry", "commit"} or job_id is None:
            return
        with tenant_scope(self.actor.tenant_id):
            async with self.factory() as db:
                job = await scoped_job(db, self, job_id)
                if job.definition != definition.DEFINITION:
                    return
                context = self.financial_context()
                stored = await revision(db, job)
                if stored.batch is None:
                    return
                batch = ImportBatch.model_validate(stored.batch)
                seen: set[str] = set()
                barcodes: set[str] = set()
                for row in batch.records:
                    code = str(row.data.get("code", "")).strip().upper()
                    if code and code in seen:
                        self.duplicate_codes.add(row.key)
                    seen.add(code)
                    barcode = row.data.get("barcode_value")
                    if isinstance(barcode, str) and barcode:
                        try:
                            gtin_aliases(barcode)
                        except ValidationFailedError:
                            identity = barcode
                        else:
                            identity = barcode.zfill(14)
                        if identity in barcodes:
                            self.duplicate_barcodes.add(row.key)
                        barcodes.add(identity)
                await self.readable(db, batch)
                template = await company_object(
                    db, ImportTemplateSnapshot, job.template_id, company_id=self.company
                )
                self.kind = (template.snapshot or {}).get("parameters", {}).get("kind")
                self.sale_levels = (template.snapshot or {}).get("sale_price_levels", [])
        has_opening = False
        for row in batch.records:
            try:
                amount = Decimal(str(row.data.get("opening_quantity", "0")))
                has_opening |= amount.is_finite() and amount > 0
            except (InvalidOperation, ValueError):
                continue  # Per-row schema validation retains the precise field error.
        if has_opening:
            assert context.finance is not None
            try:
                self.opening = await opening_preflight(
                    self.owners, self.company, context.finance.books_begin_date.isoformat()
                )
            except PlatformError as error:
                self.opening_error = error

    async def prepare_import(
        self,
        db: AsyncSession,
        record: BulkRecord,
        mode: str,
        results: dict[str, dict[str, Any]],
        key: str,
        *,
        validate: bool,
    ) -> dict[str, Any]:
        if record.resource != definition.RESOURCE:
            return await self.execute(db, record, mode, results, key)
        if (
            mode != "CREATE_ONLY"
            or record.action != "CREATE"
            or record.depends_on
            or record.target.id
            or record.target.code
            or record.target.record
        ):
            raise ValidationFailedError("Simple imports create independent products")
        context = self.financial_context()
        if record.key in self.duplicate_codes:
            raise ValidationFailedError(
                "Duplicate product code in the file", fields={"code": "Duplicate code"}
            )
        if record.key in self.duplicate_barcodes:
            raise ValidationFailedError(
                "Duplicate barcode in the file",
                fields={"barcode_value": "Another row uses this barcode or an equivalent GTIN"},
            )
        incoming = await definition.product_input(
            ConfigurationAccess(db, self.actor, self.company), record.data, self.sale_levels
        )
        if self.kind is not None and incoming.kind != self.kind:
            raise ValidationFailedError(
                "Type differs from the selected template",
                fields={"kind": "Choose the template type"},
            )
        if incoming.opening_quantity and self.opening_error is not None:
            raise self.opening_error
        if incoming.opening_quantity and not any(
            field.get("key") == "quantity" and field.get("writable")
            for field in self.opening_fields
        ):
            raise PermissionDeniedError("Opening quantity cannot be written")
        command_key = hashlib.sha256(key.encode()).hexdigest()
        try:
            queued = await enqueue(db, self.actor, context, incoming, command_key, self.opening)
            receipt = await db.get(SimpleProductCreation, queued.id)
            assert receipt is not None
            if validate:
                await validate_product(
                    Runtime(db, self.factory, self.actor, self.company, self.secret),
                    incoming,
                    receipt.progress,
                    "preview:" + command_key,
                )
        except ValidationFailedError as error:
            fields = error.extra.get("fields")
            if not isinstance(fields, dict):
                raise
            aliases = {
                "base_unit_id": "base_unit",
                "group_id": "group",
                "brand_id": "brand",
                "series_id": "brand_series",
                "tax": "gst_rule",
                "sku": "code",
                "barcode.value": "barcode_value",
                "barcode.symbology": "barcode_symbology",
                "initial_setup.barcodes.0.value": "barcode_value",
                "initial_setup.barcodes.0.symbology": "barcode_symbology",
                **{
                    "sale_prices." + str(level["price_level_id"]): "sale_price_"
                    + str(level["ordinal"])
                    for level in self.sale_levels
                },
            }
            raise ValidationFailedError(
                "Review the product fields",
                fields={aliases.get(field, field): value for field, value in fields.items()},
            ) from error
        return {
            "receipt_id": str(queued.id),
            "pending": not validate,
            "code": queued.code,
            "name": incoming.name,
            "opening_posted": False,
            **{
                "sale_price_" + str(level["ordinal"]): str(price.amount)
                for level in self.sale_levels
                for price in incoming.sale_prices
                if str(price.price_level_id) == str(level["price_level_id"])
            },
            **(
                {
                    "barcode_value": incoming.barcode.value,
                    "barcode_symbology": incoming.barcode.symbology,
                }
                if incoming.barcode is not None
                else {}
            ),
        }
