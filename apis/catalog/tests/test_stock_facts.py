"""Facts Catalog refuses to store, on every surface a tenant can name a field.

docs/catalog-warehouses.md §1 and docs/catalog-warehouse-plan.md C7.11. Catalog owns what a stock
location *is*; the quantity in it, the lot on the shelf, the count sheet and the transfer are
Accounting's. A custom field called ``on_hand`` would be a second stock balance nothing reconciles,
nothing posts from and — under CLAUDE.md §6.14 — no domain rule would ever read, so it could
disagree with the real quantity forever without anything noticing.

Two properties carry this, and both are asserted as refusals rather than as convenience:

* matching is by **whole word sequence**, so ``exception_handler`` is an ordinary name and
  ``onHand``, ``on-hand``, ``ON HAND`` and ``on_hands`` are all the same reserved fact;
* the refusal **names the fact and the field**, on the JSON body, on the import file and on a
  bulk record alike — a caller who cannot tell which column to delete learns to spell around
  the check instead of moving the data to inventory.
"""

import base64
import uuid
from typing import Any, Literal

import httpx
import pytest
from billing_platform.bulk_files import csv_document, xlsx_document
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.domain.stock_facts import (
    MESSAGE,
    assert_no_stock_fact_columns,
    assert_no_stock_facts,
    stock_fact,
    words,
)
from catalog.schemas.bulk import FileStage
from catalog.tasks.bulk_inputs import decode_stage
from tests.bulk_factories import post, run, setup
from tests.product_factories import setup_product
from tests.test_classification_api import setup_source
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")

#: The two upload formats the staged-file schema accepts.
FileKind = Literal["CSV", "XLSX"]

#: Spellings of a reserved fact, paired with the phrase each one names.
RESERVED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("on_hand", ("on", "hand")),
    ("onHand", ("on", "hand")),
    ("on-hand", ("on", "hand")),
    ("ON HAND", ("on", "hand")),
    ("on_hands", ("on", "hand")),
    ("qty_in_stock", ("in", "stock")),
    ("stock_quantities", ("stock", "quantity")),
    ("closingStock", ("closing", "stock")),
    ("openingStock", ("opening", "stock")),
    ("opening_balance_amount", ("opening", "balance")),
    ("lotNumbers", ("lot", "number")),
    ("batch_number", ("batch", "number")),
    ("expiry_date", ("expiry", "date")),
    ("expiration_date", ("expiration", "date")),
    ("mfg_date", ("mfg", "date")),
    ("lot_expiry", ("lot", "expiry")),
    ("batch_expiry", ("batch", "expiry")),
    ("manufacture_date", ("manufacture", "date")),
    ("best_before_date", ("best", "before", "date")),
    ("printed_mrp", ("printed", "mrp")),
    ("pack_mrp", ("pack", "mrp")),
    ("serialNumber", ("serial", "number")),
    ("free_quantity", ("free", "quantity")),
    ("reservedQuantity", ("reserved", "quantity")),
    ("stock_transfer_note", ("stock", "transfer")),
    ("physical_count_sheet", ("physical", "count")),
    ("cycleCount", ("cycle", "count")),
    ("stockAdjustmentReason", ("stock", "adjustment")),
)

#: Names a company may legitimately want. Half of them contain a reserved phrase's letters, and
#: half are quantities or stock words Catalog does own — a replenishment band, a location.
ORDINARY: tuple[str, ...] = (
    "exception_handler",
    "handover_note",
    "conversion_stock_keeping_unit",
    "preferred_pack_quantity",
    "reorder_quantity",
    "safety_quantity",
    "stock_location",
    "stock_keeping_note",
    "country_of_origin",
    "hsn_code",
    "status",
)


def file_stage(columns: list[str], values: list[list[str]], *, kind: FileKind = "CSV") -> FileStage:
    raw = (
        csv_document(columns, values, template=True)
        if kind == "CSV"
        else xlsx_document(columns, values)
    )
    return FileStage(format=kind, content_base64=base64.b64encode(raw).decode())


def test_a_reserved_fact_is_a_word_sequence_and_says_which_one() -> None:
    """The phrase comes back, not a boolean: the reader has to know what to rename it to."""
    for key, phrase in RESERVED:
        assert stock_fact(key) == phrase, key
    for key in ORDINARY:
        assert stock_fact(key) is None, key
    # Word splitting: separators, camel case and a crude plural all reduce to the same tokens.
    assert words("lotNumbers") == ("lot", "number")
    assert words("ON HAND") == ("on", "hand")
    assert words("stock_quantities") == ("stock", "quantity")
    assert words("exception_handler") == ("exception", "handler")
    # The rule is a word sequence, and it stops where words stop: a glued spelling with no
    # separator and no case change is one word and is not refused. Naming hygiene is all this
    # is — the guarantee that matters is CLAUDE.md §6.14, that no domain rule reads a custom
    # field whatever it is called, and it holds for every spelling.
    assert stock_fact("onhand") is None


def test_a_body_refusal_names_the_first_key_in_a_stable_order() -> None:
    assert_no_stock_facts(ORDINARY)
    assert_no_stock_facts(())
    with pytest.raises(ValidationFailedError) as refused:
        assert_no_stock_facts(["custom_fields.onHand"])
    assert refused.value.message == MESSAGE
    assert refused.value.extra["fields"] == {
        "custom_fields.onHand": "on hand is an inventory fact Catalog does not store"
    }
    # Two offenders report the same one whichever order they arrive in: a caller fixing what the
    # response named must not be handed a different name on the retry.
    for keys in (("z_on_hand", "a_lot_number"), ("a_lot_number", "z_on_hand")):
        with pytest.raises(ValidationFailedError) as pair:
            assert_no_stock_facts(keys)
        assert set(pair.value.extra["fields"]) == {"a_lot_number"}
    # A name Catalog owns natively is exempt without having to be spelled around.
    assert_no_stock_facts(["opening_stock_warehouse_id"], reserved=("opening_stock_warehouse_id",))


def test_an_import_header_refusal_names_every_offending_column() -> None:
    """A spreadsheet author fixing one header at a time would resubmit the file per column."""
    assert_no_stock_fact_columns(("_key", "_resource", "code", "reorder_quantity"))
    assert_no_stock_fact_columns(())
    with pytest.raises(ValidationFailedError) as refused:
        assert_no_stock_fact_columns(("_key", "on_hand", "code", "lotNumber", "safety_quantity"))
    assert refused.value.message == MESSAGE
    assert refused.value.extra["fields"] == {
        "on_hand": "on hand is an inventory fact Catalog does not store",
        "lotNumber": "lot number is an inventory fact Catalog does not store",
    }


@pytest.mark.parametrize("kind", ["CSV", "XLSX"])
def test_an_import_file_is_refused_by_column_before_a_row_is_interpreted(
    kind: FileKind,
) -> None:
    with pytest.raises(ValidationFailedError) as refused:
        decode_stage(
            file_stage(
                ["_key", "_set", "_resource", "closing_stock", "counted_quantity"],
                [["r1", "r1", "unit_of_measure", "40", "39"]],
                kind=kind,
            )
        )
    assert refused.value.message == MESSAGE
    assert set(refused.value.extra["fields"]) == {"closing_stock", "counted_quantity"}
    # A quantity Catalog does own is not a stock fact. This file is still refused — the resource
    # has no such column — but as an ordinary bad file, with no inventory fact named.
    with pytest.raises(ValidationFailedError) as ordinary:
        decode_stage(
            file_stage(
                ["_key", "_set", "_resource", "reorder_quantity"],
                [["r1", "r1", "unit_of_measure", "40"]],
                kind=kind,
            )
        )
    assert ordinary.value.message != MESSAGE and "fields" not in ordinary.value.extra


async def test_a_product_custom_field_claiming_a_stock_fact_is_refused_on_create_and_on_edit(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """The gate is one place, so it has to hold on the update path as well as the create path."""
    company, _, auth, body = await setup_product(factory, tenant_a)
    route = f"/v1/companies/{company}/product-families"
    refused = await client.post(
        route,
        headers=command_headers(auth),
        json={**body, "custom_fields": {"stockBalance": "12"}},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["message"] == MESSAGE
    assert refused.json()["error"]["fields"] == {
        "custom_fields.stockBalance": "stock balance is an inventory fact Catalog does not store"
    }
    created = await client.post(route, headers=command_headers(auth), json=body)
    assert created.status_code == 201, created.text
    family = created.json()["family"]
    edited = await client.patch(
        route + "/" + family["id"],
        headers=command_headers(auth),
        json={"expected_version": family["row_version"], "custom_fields": {"on_hand": "12"}},
    )
    assert edited.status_code == 422, edited.text
    assert edited.json()["error"]["fields"] == {
        "custom_fields.on_hand": "on hand is an inventory fact Catalog does not store"
    }


async def test_a_classification_custom_field_claiming_a_stock_fact_is_refused(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    auth = await setup_source(factory, tenant_a, company, user)
    route = f"/v1/companies/{company}/item-groups"
    body: dict[str, Any] = {"code": "A", "name": "A", "valid_from": "2020-01-01"}
    refused = await client.post(
        route,
        headers=command_headers(auth),
        json={**body, "custom_fields": {"opening_quantity": "5"}},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["message"] == MESSAGE
    assert refused.json()["error"]["fields"] == {
        "custom_fields.opening_quantity": (
            "opening quantity is an inventory fact Catalog does not store"
        )
    }
    # The check is specific, not a general suspicion of quantities: an undefined field named for
    # something Catalog does own is refused for its own reason, and no inventory fact is named.
    other = await client.post(
        route,
        headers=command_headers(auth),
        json={**body, "custom_fields": {"reorder_quantity": "5"}},
    )
    assert MESSAGE not in other.text, other.text


async def test_a_bulk_record_claiming_a_stock_fact_fails_that_record_by_name(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    """A staged JSON record has no header to check, so the write-time gate answers for it."""
    company, user, auth = await setup(factory, tenant_a)
    root = f"/v1/companies/{company}/bulk-jobs"
    job = await post(
        client,
        root,
        auth,
        "",
        {
            "format": "JSON",
            "records": [
                {
                    "key": "g1",
                    "change_set": "g1",
                    "resource": "item_group",
                    "data": {
                        "code": "G1",
                        "name": "Group one",
                        "valid_from": "2020-01-01",
                        "custom_fields": {"stock_level": "12"},
                    },
                }
            ],
        },
    )
    await post(
        client, root, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    assert await run(factory, tenant_a, company, user, job["id"]) == "FAILED"
    records = (await client.get(root + "/" + job["id"] + "/records", headers=auth)).json()["items"]
    detail = await client.get(root + "/" + job["id"] + "/records/" + records[0]["id"], headers=auth)
    assert detail.status_code == 200, detail.text
    # One record fails, and it fails naming the field: `invalid_record` is the job's own code for
    # a refused write, and the offending key travels with it into the reviewer's report.
    assert detail.json()["error_code"] == "invalid_record"
    assert detail.json()["error_fields"] == ["custom_fields.stock_level"]
