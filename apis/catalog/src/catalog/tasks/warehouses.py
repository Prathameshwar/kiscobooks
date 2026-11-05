"""Location master spec, built-in provisioning and the company location configuration.

The master itself rides the shared classification pipeline; the configuration singleton
rides the shared company-locked command helpers, exactly as the tax area does. Both keep
the built-in Main and internal-transit rows out of client reach.
"""

import uuid

from billing_platform.errors import NotFoundError
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.warehouses import (
    assert_additional_locations,
    assert_code_available,
    assert_kind,
    location_mode,
)
from catalog.models.classification import CatalogPolicyState
from catalog.models.pricing import PricingRow
from catalog.models.warehouse_groups import WarehouseGroup, WarehouseGroupAssignment
from catalog.models.warehouses import CompanyWarehouseConfiguration, Warehouse
from catalog.schemas.warehouses import (
    ConfigurationBootstrap,
    WarehouseConfigurationDetail,
    WarehouseCreate,
    WarehouseDetail,
    WarehouseListItem,
)
from catalog.tasks.classification import Classification, DatedEdge
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.field_context import MANAGE_PERMISSIONS, FieldContext
from catalog.tasks.policy_state import policy_state
from catalog.tasks.pricing_commands import PricingWork, protected

#: A location's dated primary group. The relation is the location's, not the group's — one
#: open interval per location, and a location with no open interval belongs to no group, so
#: the target is `NOT NULL` and clearing a membership opens nothing. Writing it needs
#: authority over the location *and* `warehouse_group.manage` over the grouping.
PRIMARY_GROUP = DatedEdge(
    WarehouseGroupAssignment,
    "catalog.warehouse_group_assignment",
    "warehouse_id",
    "group_id",
    WarehouseGroup,
    nullable_target=False,
    permission="warehouse_group.manage",
)
WAREHOUSE = Classification(
    Warehouse,
    "catalog.warehouse",
    "warehouse",
    WarehouseCreate,
    WarehouseDetail,
    WarehouseListItem,
    frozenset({"code", "is_active", "kind", "is_system"}),
    membership=PRIMARY_GROUP,
)
#: The command framework resolves a receipt's row against this tuple; only the singleton is
#: reachable that way, since the master itself is written through the classification pipeline.
LOCATION_MODELS: tuple[type[PricingRow], ...] = (CompanyWarehouseConfiguration,)


async def ensure_locations(work: PricingWork) -> CompanyWarehouseConfiguration:
    """Provision Main, internal transit, their operation policies and the configuration row.

    Once per company. Called under the company policy lock, so two concurrent bootstraps
    serialize and the second one finds the configuration row already present. The unique
    reserved code is the schema-level backstop for the same rule.

    The built-in operation policies are provisioned on the existing-row path too: a company
    bootstrapped before those shipped would otherwise have a Main that is allowed to do
    nothing, over a configuration Catalog created itself.
    """
    for model in (Warehouse, CompanyWarehouseConfiguration):
        await work.access.context(model, MANAGE_PERMISSIONS["catalog." + model.__tablename__])
        await protected(work.access, model)
    from catalog.tasks.warehouse_foundation import locations

    context = await work.access.context(Warehouse)
    config = await locations(
        work.db,
        work.company,
        timezone=context.company.timezone,
        source_version=context.source_version,
        create=work.new,
    )
    await work.access.require(config)
    # Deferred: the operation-policy commands import this module for provisioning, the same
    # shape as `prepare_location`'s import from here.
    from catalog.tasks.warehouse_operations import ensure_policies

    await ensure_policies(work, config)
    return config


async def bootstrap(
    work: PricingWork, body: ConfigurationBootstrap, object_id: uuid.UUID | None
) -> PricingRow:
    """Command handler: provisioning is derived, so the body carries nothing."""
    return await ensure_locations(work)


async def prepare_location(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    state: CatalogPolicyState,
    row: Warehouse,
    context: FieldContext,
) -> None:
    """Create-time gate for a client-created location, plus bootstrap catch-up.

    ``is_system`` is assigned rather than left to the column default: a Python-side
    default is only applied at flush, and the create path reads the value before then to
    decide field authority and the audit change set.

    The catch-up provisioning is not re-authorized on an idempotency replay, and does not
    need to be: a replay runs no mutation at all, and the response is re-projected through
    the caller's current read policy.
    """
    row.is_system = False
    assert_kind(row.kind, system=False)
    assert_code_available(row.code, system=False)
    assert_additional_locations(context.features)
    await ensure_locations(PricingWork(ConfigurationAccess(db, actor, company), state))


async def configuration(
    db: AsyncSession, actor: Actor, company: uuid.UUID
) -> WarehouseConfigurationDetail:
    """The company's location configuration, or 404 until it is provisioned.

    This read is where a defaults change gets its expectations, so ``source_version`` is the
    live Identity checkpoint the write compares against — the stored provisioning checkpoint
    answers a different question and travels under its own name.
    """
    access = ConfigurationAccess(db, actor, company)
    context = await access.context(CompanyWarehouseConfiguration)
    row = await db.scalar(
        select(CompanyWarehouseConfiguration).where(
            CompanyWarehouseConfiguration.company_id == company
        )
    )
    if row is None:
        raise NotFoundError("company location configuration is not provisioned")
    values = await access.values(row)
    readable = context.readable(values)
    state = await policy_state(db, actor, company)
    provisioned = {"provisioned_source_version": values["source_version"]}
    return WarehouseConfigurationDetail.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            **{
                key: value
                for key, value in values.items()
                if key in readable and key != "source_version"
            },
            **(provisioned if "source_version" in readable else {}),
            "location_mode": location_mode(context.features),
            "policy_generation": state.generation if state else 1,
            "source_version": context.source_version,
        }
    )
