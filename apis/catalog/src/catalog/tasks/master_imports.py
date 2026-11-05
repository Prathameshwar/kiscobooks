"""Product/service and price adapters reusing Catalog's native bulk command registry."""

import uuid
from dataclasses import asdict
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.bulk import BulkRecord, resolve_references, selection_digest
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.import_contracts import ImportBatch
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.option_sources import OPTION_SOURCES
from catalog.models.bulk import BulkJobRecord
from catalog.tasks import product_import_configuration as product_configuration
from catalog.tasks.bulk_access import (
    Evidence,
    readable_evidence,
    require_bulk,
    resource_entity,
    wire,
)
from catalog.tasks.bulk_identity import identity_digest
from catalog.tasks.bulk_matching import prepare
from catalog.tasks.bulk_registry import OPERATIONS, Runtime
from catalog.tasks.field_context import load_field_context
from catalog.tasks.options import option_query
from catalog.tasks.policy_state import policy_state
from catalog.tasks.product_creation_review import configuration_fingerprint

DEFINITIONS = {
    "products": frozenset({"product_family", "item", "simple_product"}),
    "prices": frozenset(
        {
            "price_level",
            "price_plan",
            "company_pricing_policy",
            "item_price_scope",
            "item_price_numeric_revision",
            "item_price_series",
            "item_price_draft",
            "item_price",
            "item_mrp",
            "item_reference_cost",
        }
    ),
}


class CatalogImportAdapter:
    namespace = "catalog"

    def __init__(
        self,
        actor: Actor,
        company: uuid.UUID,
        factory: async_sessionmaker[AsyncSession],
        secret: bytes,
    ) -> None:
        self.actor, self.company, self.factory, self.secret = actor, company, factory, secret
        self.definitions = {
            "products": "Products and services",
            "prices": "Prices and pricing masters",
        }

    async def authorize(self, db: AsyncSession, *, write: bool) -> None:
        await require_bulk(
            db, self.actor, self.company, "catalog.bulk.manage" if write else "catalog.bulk.read"
        )

    async def lock(self, db: AsyncSession) -> None:
        await policy_state(db, self.actor, self.company, lock=True)

    async def snapshot(
        self, db: AsyncSession, definition: str, parameters: dict[str, str]
    ) -> dict[str, Any]:
        context_keys = (
            {"as_of", "product_type_revision_id", "group_id", "_configuration"}
            if definition == "products"
            else set()
        )
        if definition not in DEFINITIONS or set(parameters) - {
            "resource",
            "kind",
            *context_keys,
        }:
            raise ValidationFailedError("unknown Catalog import definition/configuration")
        if parameters.get("kind", "GOODS") not in {"GOODS", "SERVICE"}:
            raise ValidationFailedError("choose GOODS or SERVICE")
        resources = (
            {parameters["resource"]} if "resource" in parameters else DEFINITIONS[definition]
        )
        if definition == "products":
            from catalog.tasks.product_mode import read

            product_mode = await read(db, self.actor, self.company)
            advanced = product_mode.product_family_sku_enabled
            mode_resources = {"product_family", "item"} if advanced else {"simple_product"}
            if "resource" not in parameters:
                resources = mode_resources
            elif not resources <= mode_resources:
                raise ConflictError("Product structure changed; download a current template.")
        if not resources <= DEFINITIONS[definition]:
            raise ValidationFailedError("resource is outside the selected import definition")
        configuration = (
            await product_configuration.configuration(db, self.actor, self.company, parameters)
            if definition == "products" and resources != {"item"}
            else None
        )
        template_parameters = dict(parameters)
        if definition == "products":
            signature = selection_digest(
                {
                    "mode_version": product_mode.row_version,
                    "configuration": configuration_fingerprint(configuration)
                    if configuration is not None
                    else None,
                }
            )
            if parameters.get("_configuration") not in {None, signature}:
                raise ConflictError(
                    "Product configuration changed; download a current template "
                    "and review your file."
                )
            template_parameters["_configuration"] = signature
            if configuration is not None:
                template_parameters["as_of"] = str(configuration.as_of)
        schemas, fields, options = {}, {}, {}
        for resource in sorted(resources):
            try:
                context = await load_field_context(
                    db, self.actor, self.company, resource_entity(resource)
                )
            except PermissionDeniedError:
                if "resource" in parameters:
                    raise
                continue
            if not set(context.native.fields) <= context.readable():
                raise PermissionDeniedError("import requires readable native resource fields")
            fields[resource] = wire(
                [
                    {
                        key: value.model_dump(mode="json")
                        if isinstance(value, BaseModel)
                        else value
                        for key, value in asdict(field).items()
                    }
                    for field in context.fields
                    if field.source == "native" or "custom_field:" + field.key in context.readable()
                ]
            )
            shared_context = None
            if resource == "simple_product":
                shared_context = await load_field_context(
                    db, self.actor, self.company, "catalog.product_family"
                )
                if not set(shared_context.native.fields) <= shared_context.readable():
                    raise PermissionDeniedError(
                        "simple import requires readable product dependencies"
                    )
                simple_fields = []
                for field in fields[resource]:
                    if field["source"] == "custom":
                        simple_fields.append({**field, "key": "custom_fields." + field["key"]})
                    elif field["key"] in {
                        "sku",
                        "name",
                        "base_unit_id",
                        "sellable",
                        "purchasable",
                        "min_sale_quantity",
                    }:
                        simple_fields.append(
                            {**field, "key": "code" if field["key"] == "sku" else field["key"]}
                        )
                for field in shared_context.fields:
                    if (
                        field.source == "custom"
                        and "custom_field:" + field.key in shared_context.readable()
                    ):
                        simple_fields.append(
                            {**wire(asdict(field)), "key": "shared_custom_fields." + field.key}
                        )
                    elif field.source == "native" and field.key in {
                        "kind",
                        "product_type_revision_id",
                        "brand_id",
                        "series_id",
                        "model_code",
                        "description",
                    }:
                        simple_fields.append(wire(asdict(field)))
                fields[resource] = simple_fields
            for (name, action), op in OPERATIONS.items():
                if name != resource:
                    continue
                try:
                    for permission in op.permissions:
                        self.actor.require_scope(
                            permission, target=ScopePath(company_id=self.company)
                        )
                except PermissionDeniedError:
                    continue
                schema = op.schema.model_json_schema()
                if resource == "simple_product":
                    schema["required"] = [
                        key
                        for key in schema.get("required", [])
                        if key not in {"revision", "authoring_version"}
                    ]
                    schema["properties"].pop("authoring_version", None)
                    schema["properties"].pop("revision", None)
                if (
                    resource in {"product_family", "simple_product"}
                    and action == "CREATE"
                    and parameters.get("kind")
                ):
                    schema["properties"]["kind"]["enum"] = [parameters["kind"]]
                for field in [
                    *context.fields,
                    *(shared_context.fields if shared_context is not None else []),
                ]:
                    field_key = (
                        "code" if resource == "simple_product" and field.key == "sku" else field.key
                    )
                    if (
                        field.required
                        and field.source == "native"
                        and field_key in schema["properties"]
                        and field_key not in schema.setdefault("required", [])
                    ):
                        schema["required"].append(field_key)
                schema["x-custom-fields"] = [
                    field.model_dump(mode="json")
                    for field in context.definitions
                    if field.is_active and "custom_field:" + field.key in context.readable()
                ]
                if shared_context is not None:
                    schema["x-shared-custom-fields"] = [
                        field.model_dump(mode="json")
                        for field in shared_context.definitions
                        if field.is_active
                        and "custom_field:" + field.key in shared_context.readable()
                    ]
                if definition == "products":
                    product_configuration.template_schema(
                        schema,
                        configuration,
                        action,
                        parameters,
                        simple=resource == "simple_product",
                    )
                schemas[resource + ":" + action] = schema
        if not schemas:
            raise PermissionDeniedError("no authorized Catalog import resources")
        for source, source_spec in OPTION_SOURCES.items():
            if source_spec.parent_source is not None:
                options[source] = {
                    "endpoint": "/v1/companies/{company_id}/option-sources/" + source,
                    "requires_parent": True,
                }
                continue
            try:
                statement, _ = await option_query(db, self.actor, self.company, source, None)
            except PermissionDeniedError:
                continue
            found = list((await db.execute(statement.limit(201))).mappings())
            options[source] = {
                "items": [wire(dict(row)) for row in found[:200]],
                "truncated": len(found) > 200,
            }
        return {
            "version": 1,
            "parameters": template_parameters,
            "schemas": schemas,
            "fields": fields,
            "options": options,
            **(
                {
                    "product_configuration": product_configuration.guide(
                        configuration, advanced=advanced
                    )
                }
                if configuration is not None
                else {}
            ),
            "instructions": (
                "Simple products use one code/name and the returned product ID. "
                "Use exact native commands. Family CREATE supports GOODS and SERVICE "
                "and includes default_item JSON. Prices use their native "
                "scope/series/draft/publication lifecycle. Use $ref for related staged IDs; "
                "publish only through explicit PUBLISH rows. "
                "Configuration and version guards are derived by the importer. "
                "Required product options must be completed before activation; "
                "physical batches, serials and opening stock use their native workflows."
            ),
        }

    async def fingerprint(self, db: AsyncSession, definition: str) -> str:
        state = await policy_state(db, self.actor, self.company, lock=True)
        assert state is not None
        return selection_digest(
            {"generation": state.generation, "identity": await identity_digest(db, self.company)}
        )

    async def readable(self, db: AsyncSession, batch: ImportBatch) -> None:
        allowed = set().union(*DEFINITIONS.values())
        for resource in {row.resource for row in batch.records}:
            if resource not in allowed:
                raise ValidationFailedError("resource is outside the supported master imports")
            context = await load_field_context(
                db, self.actor, self.company, resource_entity(resource)
            )
            if not set(context.native.fields) <= context.readable() or any(
                "custom_field:" + field.key not in context.readable()
                for field in context.definitions
            ):
                raise PermissionDeniedError("import data requires readable resource fields")
            if resource == "simple_product":
                shared = await load_field_context(
                    db, self.actor, self.company, "catalog.product_family"
                )
                if not set(shared.native.fields) <= shared.readable() or any(
                    "custom_field:" + field.key not in shared.readable()
                    for field in shared.definitions
                ):
                    raise PermissionDeniedError(
                        "import data requires readable shared product fields"
                    )

    async def execute(
        self,
        db: AsyncSession,
        record: BulkRecord,
        mode: str,
        results: dict[str, dict[str, Any]],
        key: str,
    ) -> dict[str, Any]:
        if record.resource in DEFINITIONS["products"]:
            from catalog.tasks.product_mode import read

            advanced = (await read(db, self.actor, self.company)).product_family_sku_enabled
            if (record.resource == "simple_product") == advanced:
                raise ConflictError("Product structure changed; download a current template.")
            if (
                record.resource != "item"
                and record.action in {"AUTO", "CREATE"}
                and mode != "UPDATE_ONLY"
            ):
                data = await product_configuration.creation_data(
                    db, self.actor, self.company, resolve_references(record.data, results)
                )
                record = record.model_copy(update={"data": data})
        stored = BulkJobRecord(
            normalized_input=record.model_dump(mode="json"),
            prepared_input=None,
            target_id=None,
            target_key=None,
            expected_version=None,
        )
        runtime = Runtime(db, self.factory, self.actor, self.company, self.secret)
        with Evidence(db) as captured:
            op, body, target, _ = await prepare(runtime, stored, mode, results, reviewed=False)
            if (
                record.resource in {"simple_product", "product_family"}
                and op.action == "UPDATE"
                and target is not None
            ):
                await product_configuration.update_options(
                    db,
                    self.actor,
                    self.company,
                    record.resource,
                    target,
                    body.model_dump(exclude_unset=True),
                )
            output = await op.call(runtime, body, target, key)
            await readable_evidence(db, self.actor, self.company, captured.pins())
            result: dict[str, Any] = {"created": captured.named_created()}
            for field, value in output.items():
                if field == "id" or field.endswith("_id"):
                    try:
                        result[field] = str(uuid.UUID(str(value)))
                    except ValueError:
                        continue
            if "id" not in result:
                created = captured.named_created().get(record.resource)
                if created:
                    result["id"] = created
                elif target is not None:
                    result["id"] = str(target)
            return result
