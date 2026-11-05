from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.authz import Grant, Scope
from billing_platform.db import tenant_scope
from billing_platform.errors import PermissionDeniedError
from billing_platform.gateway import Actor
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.projections import CustomFieldDefinitionProjection
from catalog.tasks.field_context import custom_definition, load_field_context
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.projections import activate_snapshot, fact_values
from tests.source_factories import all_facts, snapshot
from tests.test_api import headers


async def test_metadata_uses_authoritative_subject_policies_and_current_sources(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    route = f"/v1/companies/{company}/entities/catalog.unit_of_measure/field-set"
    auth = headers(company, permission="unit.read", tenant=tenant_a, user=user)
    assert (await client.get(route)).status_code == 401
    assert (
        await client.get(route, headers=headers(uuid7(), permission="unit.read"))
    ).status_code == 403
    assert (await client.get(route, headers=auth)).status_code == 503
    facts = all_facts(company, user)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, facts))
    response = await client.get(route, headers=auth)
    assert response.status_code == 200, response.text
    fields = {field["key"]: field for field in response.json()["fields"]}
    assert fields["name"]["writable"] is False
    assert fields["symbol"]["writable"] is False
    assert fields["row_version"]["writable"] is False
    assert (await client.get(route + "?unexpected=true", headers=auth)).status_code == 422
    unknown = route.replace("catalog.unit_of_measure", "catalog.unknown")
    assert (await client.get(unknown, headers=auth)).status_code == 422
    read_deny = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **next(row.data for row in facts if row.kind == "field_policy"),
            "subject_type": "user",
            "subject_id": str(user),
            "field_key": "symbol",
            "access": "read",
        },
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, (*facts, read_deny), version=3))
    response = await client.get(route, headers=auth)
    assert response.status_code == 200
    assert "symbol" not in {field["key"] for field in response.json()["fields"]}
    assert all(field["writable"] is False for field in response.json()["fields"])
    managing = await client.get(
        route,
        headers=headers(
            company, permission=["unit.read", "unit.manage"], tenant=tenant_a, user=user
        ),
    )
    descriptors = {field["key"]: field for field in managing.json()["fields"]}
    assert descriptors["code"]["writable"] is True
    assert descriptors["name"]["writable"] is False
    assert descriptors["row_version"]["writable"] is False
    deactivated = tuple(
        SnapshotRecord(kind="user", id=user, data={"status": "suspended"})
        if row.kind == "user"
        else row
        for row in facts
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, deactivated, version=4))
    assert (await client.get(route, headers=auth)).status_code == 403


def source_actor(tenant: uuid.UUID, company: uuid.UUID, user: uuid.UUID) -> Actor:
    return Actor(
        tenant,
        user,
        grants=(Grant(frozenset({"unit.read"}), Scope("company", company), dt.date(2000, 1, 1)),),
    )


async def test_conditional_field_checks_cannot_unlock_their_own_denied_change(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    policy = next(row for row in facts if row.kind == "field_policy")
    conditional = SnapshotRecord(
        kind="field_policy",
        id=policy.id,
        data={**policy.data, "condition": {"field": "name", "cmp": "eq", "value": "Locked"}},
    )
    allow = SnapshotRecord(
        kind="field_policy",
        id=uuid7(),
        data={
            **conditional.data,
            "effect": "allow",
            "scope_type": "company",
            "scope_id": str(company),
        },
    )
    records = tuple(conditional if row.kind == "field_policy" else row for row in facts)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, records))
            context = await load_field_context(
                db, source_actor(tenant_a, company, user), company, "catalog.unit_of_measure"
            )
            assert len(context.rules()) == 1 and context.rules({"name": "Other"}) == ()
            with pytest.raises(PermissionDeniedError):
                context.assert_writable(
                    frozenset({"name"}), before={"name": "Locked"}, after={"name": "Unlocked"}
                )
            context.assert_writable(
                frozenset({"name"}), before={"name": "Old"}, after={"name": "New"}
            )
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, (*records, allow), version=3))
            context = await load_field_context(
                db, source_actor(tenant_a, company, user), company, "catalog.unit_of_measure"
            )
            assert (
                len(context.rules()) == 1
            )  # conditional allow never broadens list/metadata visibility
            assert len(context.rules({"name": "Locked"})) == 2


@pytest.mark.parametrize(
    ("kind", "count"),
    [
        ("group_member", 1001),
        ("role_assignment", 1001),
        ("field_policy", 1001),
        ("custom_definition", 257),
        ("field_config", 513),
        ("feature", 1001),
    ],
)
async def test_subject_and_field_resolution_rejects_excessive_source_sets(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, kind: str, count: int
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    template = next(row for row in facts if row.kind == kind)
    records = [row for row in facts if row.kind != kind]
    for number in range(count):
        data = {**template.data}
        if kind in {"role_assignment", "field_policy"}:
            data.update(subject_type="user", subject_id=str(user))
        if kind in {"field_policy", "custom_definition", "field_config"}:
            data["entity_type"] = "catalog.unit_of_measure"
        if kind == "feature":
            data["feature_key"] = f"feature_{number}"
        records.append(SnapshotRecord(kind=kind, id=uuid7(), data=data))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, tuple(records)))
            with pytest.raises(IdentitySourceUnavailableError):
                await load_field_context(
                    db, source_actor(tenant_a, company, user), company, "catalog.unit_of_measure"
                )


async def test_invalid_sources_fail_closed_and_tenant_mismatch_is_denied(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, facts))
            with pytest.raises(PermissionDeniedError):
                await load_field_context(
                    db, source_actor(uuid7(), company, user), company, "catalog.unit_of_measure"
                )
        cases: list[tuple[str, dict[str, Any]]] = [
            ("company", {"status": "closed"}),
            ("field_policy", {"field_key": "unknown"}),
            ("field_policy", {"condition": {"field": "unknown", "cmp": "empty"}}),
            ("custom_definition", {"entity_type": "catalog.unit_of_measure"}),
        ]
        for version, (kind, change) in enumerate(cases, 3):
            changed = tuple(
                SnapshotRecord(kind=row.kind, id=row.id, data={**row.data, **change})
                if row.kind == kind
                else row
                for row in facts
            )
            async with factory.begin() as db:
                await activate_snapshot(db, snapshot(tenant_a, company, changed, version=version))
                with pytest.raises(
                    PermissionDeniedError if kind == "company" else IdentitySourceUnavailableError
                ):
                    await load_field_context(
                        db,
                        source_actor(tenant_a, company, user),
                        company,
                        "catalog.unit_of_measure",
                    )
    definition = next(row for row in facts if row.kind == "custom_definition")
    row = CustomFieldDefinitionProjection(
        tenant_id=tenant_a,
        company_id=company,
        source_id=definition.id,
        source_version=2,
        **fact_values(definition),
    )
    assert custom_definition(row).key == "cf_note"


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        ("boolean", "false", False),
        ("multi_select", '["A"]', ["A"]),
        (
            "currency_amount",
            '{"amount":"1.25","currency":"INR"}',
            {"amount": "1.25", "currency": "INR"},
        ),
    ],
)
def test_custom_source_decodes_typed_defaults(kind: str, raw: str, expected: Any) -> None:
    company = uuid7()
    source = next(row for row in all_facts(company, uuid7()) if row.kind == "custom_definition")
    data = fact_values(source)
    data.update(
        data_type=kind,
        default_value=raw,
        options={"choices": [{"value": "A", "label": "A"}]} if kind == "multi_select" else None,
    )
    row = CustomFieldDefinitionProjection(**data)
    assert custom_definition(row).default_value == expected


async def test_custom_feature_gate_and_layout_requiredness_are_enforced(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    rows = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "entity_type": "catalog.item_group",
                **({"is_required": True} if row.kind == "field_config" else {}),
            },
        )
        if row.kind in {"custom_definition", "field_config"}
        else row
        for row in facts
    )
    current = Actor(
        tenant_a,
        user,
        grants=(
            Grant(frozenset({"item_group.read"}), Scope("company", company), dt.date(2000, 1, 1)),
        ),
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, rows))
            context = await load_field_context(db, current, company, "catalog.item_group")
            assert context.definitions[0].validation.required is True
        gated = tuple(
            SnapshotRecord(
                kind=row.kind,
                id=row.id,
                data={
                    **row.data,
                    "requires_feature": "disabled_feature",
                },
            )
            if row.kind == "custom_definition"
            else row
            for row in rows
        )
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, gated, version=3))
            context = await load_field_context(db, current, company, "catalog.item_group")
            assert context.definitions[0].is_active is False
            assert not any(field.source == "custom" for field in context.fields)


def test_unknown_custom_option_configuration_is_rejected() -> None:
    row = next(row for row in all_facts(uuid7(), uuid7()) if row.kind == "custom_definition")
    source = CustomFieldDefinitionProjection(
        **{**fact_values(row), "options": {"unrecognized": True}}
    )
    with pytest.raises(ValueError):
        custom_definition(source)


@pytest.mark.parametrize("kind", ["decimal", "uuid", "date"])
async def test_field_policy_conditions_use_native_and_custom_types(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, kind: str
) -> None:
    company, user, group = uuid7(), uuid7(), uuid7()
    entity = "catalog.item_group" if kind == "decimal" else "catalog.item_group_parent"
    facts = all_facts(company, user)
    rows = []
    for row in facts:
        data = dict(row.data)
        if row.kind in {"custom_definition", "field_config"}:
            data["entity_type"] = "catalog.item_group"
            if row.kind == "custom_definition":
                data["data_type"] = "decimal"
        if row.kind == "field_policy":
            field, cmp, value = (
                ("custom_field:cf_note", "gt", "5")
                if kind == "decimal"
                else ("group_id", "eq", str(group))
                if kind == "uuid"
                else ("valid_from", "eq", "2020-01-01")
            )
            data.update(
                entity_type=entity,
                field_key="name" if kind == "decimal" else "parent_group_id",
                subject_type="user",
                subject_id=str(user),
                condition={"field": field, "cmp": cmp, "value": value},
            )
        rows.append(SnapshotRecord(kind=row.kind, id=row.id, data=data))
    current = Actor(
        tenant_a,
        user,
        grants=(
            Grant(frozenset({"item_group.read"}), Scope("company", company), dt.date(2000, 1, 1)),
        ),
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, tuple(rows)))
            context = await load_field_context(db, current, company, entity)
            values = {
                "custom_field:cf_note": "10",
                "group_id": group,
                "valid_from": dt.date(2020, 1, 1),
            }
            with pytest.raises(PermissionDeniedError):
                context.assert_writable(
                    frozenset({"name" if kind == "decimal" else "parent_group_id"}),
                    before=values,
                    after=values,
                )


@pytest.mark.parametrize("value", ["bad", "1.00001", True, "NaN"])
async def test_invalid_numeric_policy_constants_fail_source_resolution(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, value: Any
) -> None:
    company, user = uuid7(), uuid7()
    facts = all_facts(company, user)
    rows = tuple(
        SnapshotRecord(
            kind=row.kind,
            id=row.id,
            data={
                **row.data,
                "condition": {"field": "quantity_increment", "cmp": "gt", "value": value},
            },
        )
        if row.kind == "field_policy"
        else row
        for row in facts
    )
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, rows))
            with pytest.raises(IdentitySourceUnavailableError):
                await load_field_context(
                    db, source_actor(tenant_a, company, user), company, "catalog.unit_of_measure"
                )


def test_typed_policy_constants_preserve_bigints_and_numeric_membership() -> None:
    from billing_platform.custom_fields import condition_matches

    from catalog.tasks.field_context import condition_scalar, condition_tree

    numeric = frozenset({"numerator", "quantity_increment"})
    tree = condition_tree(
        {
            "op": "and",
            "rules": [
                {"field": "quantity_increment", "cmp": "in", "value": ["1", "2"]},
                {"field": "numerator", "cmp": "gt", "value": "9007199254740992"},
            ],
        },
        numeric,
    )
    assert condition_matches(
        tree,
        {
            "quantity_increment": condition_scalar("quantity_increment", "1.0000", numeric),
            "numerator": condition_scalar("numerator", 9007199254740993, numeric),
        },
    )
    assert (
        condition_tree({"field": "quantity_increment", "cmp": "empty"}, numeric)["cmp"] == "empty"
    )
    invalid_values: tuple[Any, ...] = (
        True,
        [],
        "bad",
        "9" * 129,
        "1.5",
        "NaN",
        "9223372036854775808",
        "1e1000000",
    )
    for value in invalid_values:
        with pytest.raises(ValueError):
            condition_scalar("numerator", value, numeric)
    with pytest.raises(ValueError):
        condition_tree({"field": "quantity_increment", "cmp": "matches", "value": "x"}, numeric)
    identity = uuid7()
    assert condition_scalar("external", identity, numeric) == str(identity)
    assert condition_scalar("external", dt.date(2026, 1, 1), numeric) == "2026-01-01"


def test_custom_defaults_reject_numeric_json_amounts() -> None:
    from catalog.tasks.field_context import custom_default

    with pytest.raises(ValueError):
        custom_default("currency_amount", '{"amount":1.2,"currency":"INR"}')


async def test_fresh_checkpoint_cannot_replace_missing_company_fact(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    from sqlalchemy import select

    from catalog.models.projections import CompanyProjection

    company, user = uuid7(), uuid7()
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await activate_snapshot(db, snapshot(tenant_a, company, all_facts(company, user)))
            row = await db.scalar(
                select(CompanyProjection).where(CompanyProjection.company_id == company)
            )
            assert row is not None
            await db.delete(row)
            await db.flush()
            with pytest.raises(IdentitySourceUnavailableError):
                await load_field_context(
                    db, source_actor(tenant_a, company, user), company, "catalog.unit_of_measure"
                )
