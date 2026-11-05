"""Read/transport adapters; native commands remain the write authority."""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.listing import Page
from billing_platform.pagination import CursorCodec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.products import Item, ProductFamily
from catalog.schemas.products import FamilyCreate, ItemQuery
from catalog.schemas.simple_products import (
    SimpleProductCreate,
    SimpleProductDetail,
    SimpleProductListItem,
    SimpleProductQuery,
)
from catalog.tasks.field_context import load_field_context
from catalog.tasks.policy_state import policy_state
from catalog.tasks.product_mode import version


@dataclass(frozen=True)
class ProductGuard:
    item_id: uuid.UUID
    revision: str
    authoring_version: int
    secret: bytes

    async def check(
        self, db: AsyncSession, actor: Actor, company: uuid.UUID, family: ProductFamily
    ) -> None:
        from catalog.tasks.product_mode import check_version

        item = await company_object(db, Item, self.item_id, company_id=company, lock=True)
        family = await company_object(db, ProductFamily, family.id, company_id=company, lock=True)
        if item.family_id != family.id:
            raise ConflictError("Product owner changed; reload before editing.")
        await assert_simple(db, company, item, family)
        await check_version(db, company, self.authoring_version)
        if decode_revision(actor, company, item.id, self.secret, self.revision) != revision_values(
            item, family
        ):
            raise ConflictError("Product changed; reload before editing.")


def revision_codec(actor: Actor, company: uuid.UUID, item: uuid.UUID, secret: bytes) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"catalog.simple-product.v1", hashlib.sha256),
        context=f"product:{actor.tenant_id}:{company}:{actor.user_id}:{item}",
        ttl_seconds=86400,
    )


def decode_revision(
    actor: Actor, company: uuid.UUID, item: uuid.UUID, secret: bytes, revision: str
) -> dict[str, Any]:
    try:
        return revision_codec(actor, company, item, secret).decode(revision)
    except ValidationFailedError as exc:
        raise ValidationFailedError(
            "Review the latest saved product before retrying.",
            fields={"revision": "The product revision is invalid or expired."},
        ) from exc


def revision_values(item: Item, family: ProductFamily) -> dict[str, Any]:
    return {
        "item": str(item.id),
        "family": str(family.id),
        "item_version": item.row_version,
        "family_version": family.row_version,
    }


async def assert_simple(
    db: AsyncSession, company: uuid.UUID, item: Item, family: ProductFamily
) -> None:
    count = await db.scalar(
        select(func.count(Item.id)).where(Item.company_id == company, Item.family_id == family.id)
    )
    if count != 1 or item.default_slot != 1 or family.structure_mode != "SIMPLE":
        raise ConflictError("This product has variant structure; use the family and SKU APIs.")


def create_input(body: SimpleProductCreate) -> FamilyCreate:
    # Public receipt identity uses the original input, never this generated internal code.
    from billing_platform.ids import uuid7

    return FamilyCreate.model_validate(
        {
            **body.model_dump(
                exclude={
                    "authoring_version",
                    "code",
                    "base_unit_id",
                    "sellable",
                    "purchasable",
                    "min_sale_quantity",
                    "custom_fields",
                    "shared_custom_fields",
                }
            ),
            "code": "P" + uuid7().hex[:29].upper(),
            "custom_fields": body.shared_custom_fields,
            "default_item": {
                "sku": body.code,
                "name": body.name,
                "base_unit_id": body.base_unit_id,
                "sellable": body.sellable,
                "purchasable": body.purchasable,
                "min_sale_quantity": body.min_sale_quantity,
                "custom_fields": body.custom_fields,
            },
        }
    )


async def read(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    item_id: uuid.UUID,
    secret: bytes,
    price_ids: list[str] | None = None,
) -> SimpleProductDetail:
    from catalog.tasks.products import detail, require_fields

    item_context = await load_field_context(db, actor, company, "catalog.item")
    family_context = await load_field_context(db, actor, company, "catalog.product_family")
    require_fields(item_context, {"family_id", "row_version"})
    require_fields(family_context, {"row_version"})
    item = await company_object(db, Item, item_id, company_id=company)
    family = await company_object(db, ProductFamily, item.family_id, company_id=company)
    # Conditional denies are checked against actual values by the native projection.
    from billing_platform.errors import PermissionDeniedError

    if not {"family_id", "row_version"} <= item_context.readable(
        {key: getattr(item, key) for key in item_context.native.fields}
    ) or "row_version" not in family_context.readable(
        {key: getattr(family, key) for key in family_context.native.fields}
    ):
        raise PermissionDeniedError("product revision dependencies are protected")
    state = await policy_state(db, actor, company)
    generation = state.generation if state else 1
    native_item = detail(item, item_context, generation).model_dump(exclude_unset=True)
    native_family = detail(family, family_context, generation).model_dump(exclude_unset=True)
    values = {
        key: value
        for key, value in native_item.items()
        if key in SimpleProductDetail.model_fields and key not in {"revision"}
    }
    if "sku" in native_item:
        values["code"] = native_item["sku"]
    for key in (
        "kind",
        "product_type_revision_id",
        "brand_id",
        "series_id",
        "model_code",
        "description",
    ):
        if key in native_family:
            values[key] = native_family[key]
    return SimpleProductDetail.model_validate(
        {
            **values,
            "shared_custom_fields": native_family.get("custom_fields", {}),
            "revision": revision_codec(actor, company, item.id, secret).encode(
                revision_values(item, family)
            ),
            "authoring_version": await version(db, company),
            "price_draft_ids": price_ids or [],
            "related": {
                key: f"/v1/companies/{company}/items/{item.id}/{suffix}"
                for key, suffix, permission in (
                    ("units", "unit-bindings", "item.read"),
                    ("barcodes", "barcodes", "item.read"),
                    ("requirements", "requirements", "item.read"),
                    ("effective_facts", "effective-facts", "item.read"),
                    ("attributes", "attribute-form", "attribute_definition.read"),
                    ("configuration", "configuration", "product_configuration.read"),
                )
                if actor.allows_scope(permission, target=ScopePath(company_id=company))
            },
        }
    )


async def list_rows(
    db: AsyncSession, actor: Actor, company: uuid.UUID, query: SimpleProductQuery, secret: bytes
) -> Page[SimpleProductListItem]:
    from catalog.tasks.products import list_rows as native_list

    data = query.model_dump(exclude_unset=True)
    if "code" in data:
        data["sku"] = data.pop("code")
    if data.get("sort") in {"code", "-code"}:
        data["sort"] = data["sort"].replace("code", "sku")
    result = await native_list(
        db,
        actor,
        company,
        ItemQuery.model_validate(data),
        secret,
        item=True,
        cursor_resource="catalog.simple_product",
    )
    return Page[SimpleProductListItem].model_validate(
        {
            **result.model_dump(),
            "items": [
                {
                    **{
                        key: value
                        for key, value in row.model_dump(exclude_unset=True).items()
                        if key in SimpleProductListItem.model_fields
                    },
                    **({"code": row.model_dump()["sku"]} if "sku" in row.model_fields_set else {}),
                }
                for row in result.items
            ],
        }
    )
