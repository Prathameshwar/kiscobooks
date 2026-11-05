import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.handling import HandlingProfileRevision
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.returns import ReturnPolicyRevision
from catalog.models.warranties import WarrantyPolicyRevision
from tests.commercial_factories import auth
from tests.handling_factories import seed_profile
from tests.inventory_factories import seed_template
from tests.return_factories import seed_policy as seed_return
from tests.test_api import headers
from tests.test_classification_api import create
from tests.warranty_factories import seed_policy as seed_warranty

Revision = (
    InventoryProfileTemplateRevision
    | WarrantyPolicyRevision
    | ReturnPolicyRevision
    | HandlingProfileRevision
)
Seed = Callable[
    [async_sessionmaker[AsyncSession], uuid.UUID, uuid.UUID], Awaitable[tuple[uuid.UUID, uuid.UUID]]
]


@dataclass(frozen=True)
class ProfileCase:
    field: str
    route: str
    permission: str
    model: type[Revision]
    seed: Seed


CASES = (
    ProfileCase(
        "inventory_template_revision_id",
        "inventory-templates",
        "inventory_profile_template",
        InventoryProfileTemplateRevision,
        seed_template,
    ),
    ProfileCase(
        "warranty_revision_id",
        "warranty-policies",
        "warranty_policy",
        WarrantyPolicyRevision,
        seed_warranty,
    ),
    ProfileCase(
        "return_policy_revision_id",
        "return-policies",
        "return_policy",
        ReturnPolicyRevision,
        seed_return,
    ),
    ProfileCase(
        "handling_revision_id",
        "handling-profiles",
        "handling_profile",
        HandlingProfileRevision,
        seed_profile,
    ),
)
GOODS = {"inventory_modes": ["STOCK"], "tracking_modes": ["NONE"], "unit_dimensions": ["COUNT"]}


async def setup_type(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    case: ProfileCase,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str], str, str, uuid.UUID]:
    company, user = uuid7(), uuid7()
    await auth(factory, tenant, company, user)
    current = headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            "product_type.read",
            "product_type.manage",
            "product_type.publish",
            case.permission + ".read",
            case.permission + ".manage",
            case.permission + ".publish",
        ],
    )
    product_type = await create(
        client, company, current, "product-types", {"code": "TYPE", "name": "Type", "kind": "GOODS"}
    )
    assert product_type.status_code == 201, product_type.text
    parent, revision = await case.seed(factory, tenant, company)
    prefix = f"/v1/companies/{company}/"
    return (
        company,
        user,
        current,
        prefix + "product-types/" + product_type.json()["id"],
        prefix + case.route + "/" + str(parent),
        revision,
    )


async def publish_seed(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    case: ProfileCase,
    revision_id: uuid.UUID,
) -> None:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            row = await db.get(case.model, revision_id)
            assert isinstance(row, Revision)
            row.published_at = utcnow()
