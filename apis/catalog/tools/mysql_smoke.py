"""Run Catalog migrations and real concurrent commands in a newly created local test schema.

CATALOG_TEST_MYSQL_SERVER_URL must name a loopback development server, without a database.
Only the random catalog_test_ schema created by this process is dropped.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import Connection, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from catalog.config import Settings
from catalog.main import create_app
from catalog.metadata import MIGRATION_HEAD, TABLES, service_metadata
from catalog.models import MasterAlias
from tests.conftest import ACTOR_SECRET
from tests.test_commercial_api import command_headers
from tests.test_master_reference_boundaries import test_foreign_owner_mapping_and_usage_are_scoped
from tests.test_master_references import (
    setup_owner,
    test_master_reference_identity_lifecycle_and_exact_resolution,
)

ROOT = Path(__file__).resolve().parents[3]
#: How far down the reversibility traversal may unwind. ``0131`` refuses ``downgrade`` on purpose:
#: the check constraint it replaced cannot be restored without deciding what becomes of the integer
#: measurements written under the new one. So the roundtrip stops *above* that revision rather than
#: at ``base``; every revision from ``0132`` up is still unwound and replayed on the real engine.
REVERSIBLE_FLOOR = "0131"


async def schema(server: str, database: str, *, create: bool) -> None:
    if re.fullmatch(r"catalog_test_[0-9a-f]{32}", database) is None:
        raise ValueError("invalid isolated test schema")
    engine = create_async_engine(server, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            if create:
                await connection.execute(
                    text(
                        f"CREATE DATABASE `{database}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
            else:
                await connection.execute(text(f"DROP DATABASE `{database}`"))
    finally:
        await engine.dispose()


async def verify(url: str) -> dict[str, object]:
    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.router.lifespan_context(app):
            async with app.state.engine.connect() as connection:

                def differences(sync: Connection) -> list[object]:
                    return list(
                        compare_metadata(MigrationContext.configure(sync), service_metadata())
                    )

                drift = await connection.run_sync(differences)
                if drift:
                    raise AssertionError(f"migration/model drift: {drift}")
                version = await connection.scalar(text("SELECT VERSION()"))
            factory = app.state.session_factory
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://catalog.test",
            ) as client:
                for family, payload in (
                    ("aliases", {"alias": "  Stra\u00dfe  Parts  "}),
                    (
                        "external-keys",
                        {"source_namespace": "legacy.erp", "external_key": "000AbC  42"},
                    ),
                ):
                    await test_master_reference_identity_lifecycle_and_exact_resolution(
                        client, factory, uuid7(), family, payload
                    )
                    await test_foreign_owner_mapping_and_usage_are_scoped(
                        client, factory, uuid7(), uuid7(), family, payload
                    )
                from tests.test_products import test_simple_product_roundtrip

                for kind in ("GOODS", "SERVICE"):
                    await test_simple_product_roundtrip(client, factory, uuid7(), kind)
                from tests.test_configuration import (
                    test_configuration_publication_resolution_and_replay,
                )
                from tests.test_product_authoring import (
                    test_explicit_variants_are_unique_and_atomic,
                    test_product_assignments_units_barcodes_and_protected_lists,
                    test_service_configuration_adoption_and_stale_preview,
                )
                from tests.test_product_definition_mutations import (
                    test_classification_replacement_overlap_and_native_attribute_invariants,
                )
                from tests.test_product_definition_reads import (
                    test_all_definition_detail_and_history_routes_are_protected_and_typed,
                )
                from tests.test_product_definition_storage import (
                    test_all_nineteen_definition_tables_isolate_tenants_and_foreign_references,
                )
                from tests.test_product_quantities import (
                    test_alternate_and_measured_entries_obey_sku_base_grid,
                )

                for workflow in (
                    test_alternate_and_measured_entries_obey_sku_base_grid,
                    test_all_definition_detail_and_history_routes_are_protected_and_typed,
                    test_classification_replacement_overlap_and_native_attribute_invariants,
                    test_configuration_publication_resolution_and_replay,
                    test_explicit_variants_are_unique_and_atomic,
                    test_product_assignments_units_barcodes_and_protected_lists,
                    test_service_configuration_adoption_and_stale_preview,
                ):
                    await workflow(client, factory, uuid7())
                await test_all_nineteen_definition_tables_isolate_tenants_and_foreign_references(
                    factory, uuid7(), uuid7()
                )
                from tests.test_pricing_concurrency import (
                    test_concurrent_price_publication_and_replay,
                )
                from tests.test_pricing_resolution import (
                    test_live_estimate_recipe_and_floor_retain_sources,
                    test_mrp_recipe_and_tax_basis_fail_closed,
                    test_purchase_resolution_reports_reference_terms,
                    test_regular_price_resolution_uses_exact_per_n_and_volume_quantity,
                )
                from tests.test_pricing_storage import test_all_pricing_tables_are_tenant_isolated

                for pricing_workflow in (
                    test_regular_price_resolution_uses_exact_per_n_and_volume_quantity,
                    test_live_estimate_recipe_and_floor_retain_sources,
                    test_mrp_recipe_and_tax_basis_fail_closed,
                    test_purchase_resolution_reports_reference_terms,
                    test_concurrent_price_publication_and_replay,
                ):
                    await pricing_workflow(client, factory, uuid7())
                await test_all_pricing_tables_are_tenant_isolated(factory, uuid7(), uuid7())
                from tests.test_policy_release_api import (
                    test_a_release_delivers_catalogs_own_manifest_and_never_the_callers,
                    test_a_release_is_pending_until_billing_says_it_enforces_that_revision,
                    test_releases_and_acknowledgements_are_tenant_isolated,
                    test_retiring_a_location_needs_both_halves_of_the_fence,
                )
                from tests.test_warehouse_api import (
                    test_bootstrap_provisions_one_built_in_set_and_replays,
                    test_client_location_create_catches_up_provisioning_and_guards_reserved_rows,
                )
                from tests.test_warehouse_concurrency import (
                    test_bootstrap_replay_under_concurrency_has_one_effect,
                    test_concurrent_bootstrap_provisions_exactly_one_built_in_set,
                    test_concurrent_first_locations_share_one_provisioned_set,
                )
                from tests.test_warehouse_groups import (
                    test_dated_reparent_preserves_historical_rollups,
                    test_grouping_tables_are_tenant_isolated,
                )
                from tests.test_warehouse_operations import (
                    test_a_publish_supersedes_the_revision_in_force_and_keeps_the_trail,
                    test_activity_defaults_only_reach_locations_allowed_to_serve_them,
                    test_operation_policies_are_tenant_isolated,
                )
                from tests.test_warehouse_policies import (
                    test_a_product_policy_narrows_a_location_and_the_view_composes_it,
                    test_a_stocked_product_blocks_the_locations_retirement,
                    test_product_location_policies_are_tenant_isolated,
                    test_replenishment_bands_are_stated_whole_and_land_on_the_unit_grid,
                )
                from tests.test_warehouse_storage import test_location_tables_are_tenant_isolated

                # Stock-location definitions on the real engine, where SQLite cannot speak for
                # them: DECIMAL(19,4) bands come back as Decimal, dated group intervals and
                # revision windows survive the server's own date and datetime handling, and the
                # first-location race contends for a genuine company row lock.
                for location_workflow in (
                    test_bootstrap_provisions_one_built_in_set_and_replays,
                    test_client_location_create_catches_up_provisioning_and_guards_reserved_rows,
                    test_concurrent_bootstrap_provisions_exactly_one_built_in_set,
                    test_concurrent_first_locations_share_one_provisioned_set,
                    test_bootstrap_replay_under_concurrency_has_one_effect,
                    test_a_publish_supersedes_the_revision_in_force_and_keeps_the_trail,
                    test_activity_defaults_only_reach_locations_allowed_to_serve_them,
                    test_dated_reparent_preserves_historical_rollups,
                    test_a_product_policy_narrows_a_location_and_the_view_composes_it,
                    test_replenishment_bands_are_stated_whole_and_land_on_the_unit_grid,
                    test_a_stocked_product_blocks_the_locations_retirement,
                    test_a_release_delivers_catalogs_own_manifest_and_never_the_callers,
                    test_a_release_is_pending_until_billing_says_it_enforces_that_revision,
                    test_retiring_a_location_needs_both_halves_of_the_fence,
                ):
                    await location_workflow(client, factory, uuid7())
                await test_location_tables_are_tenant_isolated(factory, uuid7(), uuid7())
                await test_grouping_tables_are_tenant_isolated(factory, uuid7(), uuid7())
                for location_isolation in (
                    test_operation_policies_are_tenant_isolated,
                    test_product_location_policies_are_tenant_isolated,
                    test_releases_and_acknowledgements_are_tenant_isolated,
                ):
                    await location_isolation(client, factory, uuid7(), uuid7())
                from tests.test_product_boundaries import (
                    test_foreign_product_patch_reference_is_scope_error_before_database_flush,
                )

                await test_foreign_product_patch_reference_is_scope_error_before_database_flush(
                    client, factory, uuid7()
                )
                from time import perf_counter

                from catalog.models.products import Item, ProductFamily
                from tests.product_factories import setup_product

                benchmark_tenant = uuid7()
                (
                    benchmark_company,
                    benchmark_user,
                    benchmark_auth,
                    benchmark_body,
                ) = await setup_product(factory, benchmark_tenant)
                with tenant_scope(benchmark_tenant):
                    async with factory.begin() as db:
                        families = [
                            ProductFamily(
                                id=uuid7(),
                                tenant_id=benchmark_tenant,
                                company_id=benchmark_company,
                                code=f"BENCH{index:04d}",
                                name=f"Benchmark {index:04d}",
                                kind="GOODS",
                                product_type_revision_id=uuid.UUID(
                                    benchmark_body["product_type_revision_id"]
                                ),
                            )
                            for index in range(2000)
                        ]
                        db.add_all(families)
                        await db.flush()
                        db.add_all(
                            Item(
                                tenant_id=benchmark_tenant,
                                company_id=benchmark_company,
                                family_id=family.id,
                                default_slot=1,
                                sku=family.code,
                                name=family.name,
                                base_unit_id=uuid.UUID(
                                    benchmark_body["default_item"]["base_unit_id"]
                                ),
                                sellable=True,
                                purchasable=True,
                            )
                            for family in families
                        )
                seen: set[str] = set()
                timings: list[float] = []
                next_cursor: str | None = None
                for _ in range(10):
                    parameters = {"limit": "200", "sort": "sku"}
                    if next_cursor is not None:
                        parameters["cursor"] = next_cursor
                    started = perf_counter()
                    page = await client.get(
                        f"/v1/companies/{benchmark_company}/items",
                        headers=benchmark_auth,
                        params=parameters,
                    )
                    timings.append(round((perf_counter() - started) * 1000, 3))
                    assert page.status_code == 200, page.text
                    rows = page.json()["items"]
                    assert len(rows) == 200
                    assert not seen.intersection(row["id"] for row in rows)
                    seen.update(row["id"] for row in rows)
                    next_cursor = page.json()["page"]["next_cursor"]
                assert len(seen) == 2000 and next_cursor is None
                tenant = uuid7()
                company, _, current, owner, _ = await setup_owner(client, factory, tenant)
                route = owner + "/aliases"
                results = await asyncio.gather(
                    *(
                        client.post(route, headers=command_headers(current), json={"alias": value})
                        for value in ("Concurrent", "CONCURRENT")
                    )
                )
                assert sorted(row.status_code for row in results) == [201, 409], [
                    row.text for row in results
                ]
                retry = command_headers(current)
                results = await asyncio.gather(
                    *(
                        client.post(route, headers=retry, json={"alias": "Retried"})
                        for _ in range(2)
                    )
                )
                assert all(row.status_code == 201 for row in results), [row.text for row in results]
                assert results[0].json()["id"] == results[1].json()["id"]
                with tenant_scope(tenant):
                    async with factory() as db:
                        assert await db.scalar(select(func.count(MasterAlias.id))) == 2
                    async with factory.begin() as db:
                        db.add_all(
                            MasterAlias(
                                tenant_id=tenant,
                                company_id=company,
                                entity_type="catalog.brand",
                                target_id=uuid.UUID(owner.rsplit("/", 1)[1]),
                                alias=f"Bulk {index:04d}",
                                canonical_value=f"bulk {index:04d}",
                                normalization_version=1,
                            )
                            for index in range(2000)
                        )
                    # Diagnostic SQL uses a connection with explicit tenant/company binds.
                    async with app.state.engine.connect() as plan_connection:
                        plan = (
                            (
                                await plan_connection.execute(
                                    text(
                                        "EXPLAIN FORMAT=TRADITIONAL "
                                        "SELECT id, alias, canonical_value "
                                        "FROM master_alias "
                                        "WHERE tenant_id=:tenant AND company_id=:company "
                                        "AND entity_type=:entity AND target_id=:target "
                                        "AND canonical_value LIKE :prefix "
                                        "ORDER BY canonical_value,id LIMIT 51"
                                    ),
                                    {
                                        "tenant": tenant.bytes,
                                        "company": company.bytes,
                                        "entity": "catalog.brand",
                                        "target": uuid.UUID(owner.rsplit("/", 1)[1]).bytes,
                                        "prefix": "bulk 00%",
                                    },
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert plan["key"] is not None and plan["type"] in {"ref", "range"}, dict(
                            plan
                        )
                page = await client.get(
                    route, headers=current, params={"q": "Bulk 00", "limit": 50}
                )
                assert page.status_code == 200, page.text
                assert len(page.json()["items"]) == 50
                assert page.json()["items"][0]["alias"] == "Bulk 0000"
                next_page = await client.get(
                    route,
                    headers=current,
                    params={
                        "q": "Bulk 00",
                        "limit": 50,
                        "cursor": page.json()["page"]["next_cursor"],
                    },
                )
                assert next_page.status_code == 200 and len(next_page.json()["items"]) == 50
                assert next_page.json()["items"][0]["alias"] == "Bulk 0050"
                assert next_page.json()["page"]["next_cursor"] is None
                from tools.pricing_benchmark import benchmark

                pricing_measurement = await benchmark(
                    client, factory, benchmark_tenant, benchmark_company, benchmark_user
                )
        return {
            "server_version": version,
            "tables": len(TABLES),
            "head": MIGRATION_HEAD,
            "schema_drift": [],
            "pricing_workflows": 5,
            "pricing_tenant_isolation_tables": 17,
            "reference_workflows": 2,
            "scope_workflows": 2,
            "concurrency_races": 2,
            "indexed_alias_rows": 2000,
            "product_workflows": 2,
            "location_workflows": 14,
            "location_tenant_isolation_tables": 12,
            "configuration_authoring_adoption_workflows": 7,
            "definition_tenant_isolation_tables": 19,
            "product_reference_scope_check": "passed",
            "draft_sku_benchmark": {"rows": 2000, "pages": 10, "page_ms": timings},
            "pricing_benchmark": pricing_measurement,
        }
    finally:
        await app.state.engine.dispose()


async def verify_fmcg_sources(url: str) -> dict[str, object]:
    """Test new channel/food data after the older-schema downgrade traversal."""
    from tests.test_pricing_resolution import (
        test_sale_channel_price_precedes_generic_and_other_channels_fall_back,
    )
    from tests.test_regulatory_classification import (
        test_food_classification_requires_category_and_reaches_signed_source,
    )

    app = create_app(Settings(database_url=url, actor_signing_secret=SecretStr(ACTOR_SECRET)))
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://catalog.test",
            ) as client:
                factory = app.state.session_factory
                await test_sale_channel_price_precedes_generic_and_other_channels_fall_back(
                    client, factory, uuid7()
                )
                await test_food_classification_requires_category_and_reaches_signed_source(
                    client, factory, uuid7()
                )
        return {"fmcg_channel_and_food_native_workflows": 2}
    finally:
        await app.state.engine.dispose()


def run_verifier(
    verifier: Callable[[str], Coroutine[Any, Any, dict[str, object]]],
    *,
    roundtrip: bool = True,
    post_replay_verifier: Callable[[str], Coroutine[Any, Any, dict[str, object]]] | None = None,
) -> None:
    server = os.environ["CATALOG_TEST_MYSQL_SERVER_URL"]
    parsed = make_url(server)
    if (
        parsed.drivername != "mysql+asyncmy"
        or parsed.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed.database
    ):
        raise ValueError("test server must be loopback and must not select an existing database")
    database = "catalog_test_" + uuid.uuid4().hex
    test_url = parsed.set(database=database).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "dbs/catalog/alembic.ini"))
    previous = os.environ.get("CATALOG_DATABASE_URL")
    created = False
    try:
        asyncio.run(schema(server, database, create=True))
        created = True
        os.environ["CATALOG_DATABASE_URL"] = test_url
        command.upgrade(cfg, "head")
        result = asyncio.run(verifier(test_url))
        if roundtrip:
            command.downgrade(cfg, REVERSIBLE_FLOOR)
            command.upgrade(cfg, "head")
            # Second traversal validates DDL reversibility; first tests business behavior.
            result["roundtrip"] = f"upgrade/head, downgrade/{REVERSIBLE_FLOOR}, upgrade/head"
        else:
            result["roundtrip"] = "not requested; upgrade/head only"
        if post_replay_verifier is not None:
            result.update(asyncio.run(post_replay_verifier(test_url)))
        print(json.dumps(result, sort_keys=True))
    finally:
        if previous is None:
            os.environ.pop("CATALOG_DATABASE_URL", None)
        else:
            os.environ["CATALOG_DATABASE_URL"] = previous
        if created:
            asyncio.run(schema(server, database, create=False))


def main() -> None:
    run_verifier(verify, post_replay_verifier=verify_fmcg_sources)


if __name__ == "__main__":
    main()
