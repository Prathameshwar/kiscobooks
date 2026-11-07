"""Bounded native actions. Persist each exact command before sending it."""

import uuid
from typing import Any

from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7

from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.tasks.simple_creation_transport import CreationOwners, OwnerRejectedError


def serial_entries(request: SimpleCreationInput) -> list[tuple[int | None, int, Any]]:
    if request.batch_enabled:
        return [
            (batch_index, index, entry)
            for batch_index, batch in enumerate(request.batches)
            for index, entry in enumerate(batch.serials)
        ]
    return [(None, index, entry) for index, entry in enumerate(request.serials)]


async def serial_preflight(
    owners: CreationOwners, company: uuid.UUID, request: SimpleCreationInput
) -> None:
    entries = serial_entries(request)
    if not entries:
        return
    root = f"/v1/companies/{company}"
    metadata = await owners.call(
        "accounting", "GET", root + "/stock-tracking/serials/field-set?action=prepare"
    )
    fields = {value["key"]: value for value in metadata["fields"]}
    required = {"item_id", "identifiers", "reason"} | (
        {"lot_id"} if request.batch_enabled else set()
    )
    if any(
        key not in fields or not fields[key]["readable"] or not fields[key]["writable"]
        for key in required
    ):
        raise PermissionDeniedError("Serial field access does not allow the entered details")
    options = await owners.call(
        "catalog",
        "GET",
        root
        + "/simple-product-creations/options?kind=GOODS"
        + ("&group_id=" + str(request.group_id) if request.group_id else ""),
    )
    company_types = {
        row["identifier_type"]
        for row in options["serial"]["requirements"]
        if row["namespace_rule"] == "COMPANY"
    }
    inputs, paths = [], []
    for batch_index, index, entry in entries:
        prefix = "" if batch_index is None else f"batches.{batch_index}."
        for slot, value in enumerate(entry.identifiers):
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


class OpeningPostingRejectedError(ConflictError):
    """The owner has confirmed that this attempt ended without a posting effect."""


async def batch_preflight(
    owners: CreationOwners, company: uuid.UUID, request: SimpleCreationInput
) -> None:
    if not request.batches:
        return
    metadata = await owners.call(
        "accounting",
        "GET",
        f"/v1/companies/{company}/stock-tracking/batches/field-set?action=prepare",
    )
    fields = {value["key"]: value for value in metadata["fields"]}
    required = {"item_id", "code", "reason"}
    for entry in request.batches:
        if entry.expires_on is not None:
            required.add("expires_on")
        if entry.manufactured_on is not None:
            required.add("manufactured_on")
        if entry.mrp is not None:
            required.update({"mrp_amount", "mrp_currency", "mrp_unit_id"})
    if any(
        key not in fields or not fields[key]["readable"] or not fields[key]["writable"]
        for key in required
    ):
        raise PermissionDeniedError("Batch field access does not allow the entered details")


async def opening_preflight(
    owners: CreationOwners,
    company: uuid.UUID,
    date: str,
    warehouse_id: uuid.UUID | None = None,
    *,
    require_cost_capture: bool = False,
) -> dict[str, Any]:
    if require_cost_capture:
        metadata = await owners.call(
            "accounting", "GET", f"/v1/companies/{company}/stock/openings/capture-fields"
        )
        fields = {field["key"]: field for field in metadata["fields"]}
        if any(
            key not in fields or not fields[key]["readable"] or not fields[key]["writable"]
            for key in ("quantity", "received_value", "opening")
        ):
            raise PermissionDeniedError("Opening valuation capture must be readable and writable")
    root = f"/v1/companies/{company}"
    ready = await owners.call("accounting", "GET", root + "/stock/openings/readiness")
    if ready.get("blockers"):
        if "EXECUTION_UNCONFIRMED" in ready["blockers"]:
            raise ConflictError(
                "An earlier stock posting is still being confirmed. "
                "Save the product without opening stock, or retry the opening shortly. "
                "Contact support if confirmation remains pending."
            )
        raise ConflictError("Company opening setup is not ready: " + ", ".join(ready["blockers"]))
    capabilities = await owners.call("vouchers", "GET", root + "/voucher-capabilities")
    if not capabilities.get("stock_execution"):
        raise ConflictError("Stock posting must be enabled before entering product opening stock")
    types = await owners.call(
        "vouchers",
        "GET",
        root + "/voucher-types?code=STK_OPEN&kind=STOCK_JOURNAL&status=ACTIVE&limit=2",
    )
    if len(types["items"]) != 1 or types["items"][0].get("profile") != "OPENING":
        raise ConflictError("The default opening stock voucher type is unavailable")
    identity = types["items"][0]["id"]
    definition = await owners.call("vouchers", "GET", root + "/voucher-types/" + identity)
    effective = await owners.call(
        "vouchers",
        "GET",
        root + f"/voucher-types/{identity}/effective-configuration?date={date}&posting_date={date}",
    )
    if effective["policy"].get("approval_required", True):
        raise ConflictError(
            "The opening voucher configuration requires approval; "
            "disable approval for immediate simple-product openings"
        )
    warehouse = await owners.call("catalog", "GET", root + "/warehouse-configuration")
    location = (
        str(warehouse_id)
        if warehouse_id is not None
        else warehouse.get("default_opening_warehouse_id") or warehouse.get("main_warehouse_id")
    )
    if not location or not definition.get("revision_id"):
        raise ConflictError("Complete the default opening warehouse and voucher setup")
    return {"warehouse_id": location, "type_revision_id": definition["revision_id"]}


async def next_command(
    owners: CreationOwners,
    company: uuid.UUID,
    identity: uuid.UUID,
    step: str,
    request: SimpleCreationInput,
    progress: dict[str, Any],
    item_id: uuid.UUID | None,
    tenant_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    root = f"/v1/companies/{company}"

    def command(service: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return {"service": service, "path": root + path, "body": body}

    if step == "CREATE":
        return command("catalog", "/products", progress["create"])
    assert item_id is not None
    product = f"/items/{item_id}"
    if step in {"NUMERIC", "MRP"}:
        facts = await owners.call(
            "catalog", "GET", root + product + "/effective-facts?as_of=" + progress["today"]
        )
        base = next(unit for unit in facts["units"] if unit["usage_role"] == "BASE")
        configuration = facts["configuration"]
        body = {
            "item_id": str(item_id),
            "unit_revision_id": base["revision_id"],
            "currency": progress["currency"],
            "valid_from": progress["today"],
            "expected_generation": configuration["policy_generation"],
            "expected_source_version": configuration["source_version"],
        }
        if step == "NUMERIC":
            return command(
                "catalog",
                "/price-numeric-revisions",
                body | {"price_decimal_places": progress["price_places"]},
            )
        if progress.get("numeric_id"):
            numeric = progress["numeric_id"]
        else:
            draft = await owners.call(
                "catalog", "GET", root + "/price-drafts/" + progress["drafts"][0]
            )
            numeric = draft["numeric_revision_id"]
        return command(
            "catalog",
            "/product-mrps",
            body
            | {
                "numeric_revision_id": numeric,
                "amount": str(request.mrp),
                "price_basis_quantity": "1",
                "jurisdiction": progress["jurisdiction"],
                "tax_basis": "INCLUSIVE",
                "source_reference": "Product creation " + str(identity),
            },
        )
    if step == "PUBLISH":
        index = progress.get("published", 0)
        if index >= len(progress["drafts"]):
            return None
        draft_id = progress["drafts"][index]
        preview = await owners.call("catalog", "GET", root + f"/price-drafts/{draft_id}/preview")
        if not preview.get("publishable", True):
            raise ConflictError("The entered price does not satisfy product pricing configuration")
        return command(
            "catalog",
            f"/price-drafts/{draft_id}/publish",
            {
                "expected_version": preview["row_version"],
                "expected_generation": preview["policy_generation"],
                "expected_source_version": preview["source_version"],
            },
        )
    if step == "ACTIVATE":
        preview = await owners.call(
            "catalog", "POST", root + product + "/activation-preview", {"as_of": progress["today"]}
        )
        if not preview["eligible"]:
            raise ConflictError("Product setup is incomplete: " + ", ".join(preview["missing"]))
        return command(
            "catalog",
            product + "/activate",
            {
                key: preview[key]
                for key in (
                    "as_of",
                    "expected_version",
                    "expected_family_version",
                    "preview_token",
                )
            },
        )
    if step == "BATCH":
        entry = request.batches[progress.get("batch_index", 0)]
        return command(
            "accounting",
            "/stock-tracking/batches",
            {
                "item_id": str(item_id),
                "code": entry.code,
                "manufactured_on": entry.manufactured_on.isoformat()
                if entry.manufactured_on
                else None,
                "expires_on": entry.expires_on.isoformat() if entry.expires_on else None,
                "mrp_amount": str(entry.mrp) if entry.mrp is not None else None,
                "mrp_currency": progress["currency"] if entry.mrp is not None else None,
                "mrp_unit_id": str(request.base_unit_id) if entry.mrp is not None else None,
                "reason": "Batch entered with product creation",
            },
        )
    if step == "BATCH_PRICES":
        facts = await owners.call(
            "catalog", "GET", root + product + "/effective-facts?as_of=" + progress["today"]
        )
        base = next(unit for unit in facts["units"] if unit["usage_role"] == "BASE")
        index = progress.get("batch_index", 0)
        return command(
            "catalog",
            "/batch-prices",
            {
                "item_id": str(item_id),
                "lot_id": progress["batch_ids"][index],
                "unit_revision_id": base["revision_id"],
                "valid_from": progress["today"],
                "prices": progress["batch_plan"][index]["prices"],
                "expected_generation": facts["configuration"]["policy_generation"],
                "expected_source_version": facts["configuration"]["source_version"],
            },
        )
    if step == "SERIAL":
        batch_index, _, entry = serial_entries(request)[progress.get("serial_index", 0)]
        return command(
            "accounting",
            "/stock-tracking/serials",
            {
                "item_id": str(item_id),
                "lot_id": progress["batch_ids"][batch_index] if batch_index is not None else None,
                "identifiers": [value.model_dump(mode="json") for value in entry.identifiers],
                "reason": "Serial opening unit entered with product creation",
            },
        )
    if step == "OPENING":
        progress["source_delivery"] = getattr(owners, "source_delivery", None) is not None
        facts = await owners.call(
            "catalog", "GET", root + product + "/effective-facts?as_of=" + progress["opening_date"]
        )
        base = next(unit for unit in facts["units"] if unit["usage_role"] == "BASE")
        entries = (
            [
                (index, entry)
                for index, entry in enumerate(request.batches)
                if entry.opening_quantity
            ]
            if request.batch_enabled
            else [(None, request)]
        )
        lines = []
        for index, entry in entries:
            capture = {
                "source_key": "product-"
                + str(identity)
                + ("-" + str(index) if index is not None else ""),
                "entered_unit_id": str(request.base_unit_id),
                "unit_revision_id": base["revision_id"],
                "entered_quantity": str(entry.opening_quantity),
                "cost_mode": "RATE",
                "unit_cost": str(entry.valuation_cost),
                "priced_quantity": "1",
                "history_known": False,
            }
            calculation = await owners.call(
                "accounting",
                "POST",
                root + "/stock/openings/calculate",
                {
                    "stock_date": progress["opening_date"],
                    "item_id": str(item_id),
                    "warehouse_id": progress["warehouse_id"],
                    "opening": capture,
                },
            )
            line = {
                "line_id": str(uuid7()),
                "item_id": str(item_id),
                "warehouse_id": progress["warehouse_id"],
                "quantity": calculation["base_quantity"],
                "received_value": calculation["received_value"],
                "opening": capture,
            }
            if index is not None:
                line["lot_id"] = progress["batch_ids"][index]
            if entry.serials:
                line["unit_ids"] = [
                    progress["serial_ids"][serial_index]
                    for serial_index, (batch_index, _, _) in enumerate(serial_entries(request))
                    if batch_index == index
                ]
            lines.append(line)
        return command(
            "accounting",
            f"/stock/openings/products/{item_id}",
            {
                "stock_date": progress["opening_date"],
                "currency": progress["currency"],
                "opening_mode": "COMBINED",
                "lines": lines,
                "reason": "Opening stock entered with product creation",
            },
        )
    if step == "SOURCE":
        if tenant_id is None:
            raise ConflictError("Product source scope is unavailable")
        return {
            "service": "source",
            "path": "/internal/v1/sources",
            "body": await owners.item_source_bundle(tenant_id, company, item_id, identity),
        }
    if step == "VOUCHER":
        current = await owners.call(
            "catalog", "GET", root + product + "/effective-facts?as_of=" + progress["opening_date"]
        )
        manifest = progress["manifest"]
        return command(
            "vouchers",
            "/vouchers",
            {
                "type_revision_id": progress["type_revision_id"],
                "document_date": progress["opening_date"],
                "posting_date": progress["opening_date"],
                "stock_date": progress["opening_date"],
                "mode": "ITEMS",
                "currency": progress["currency"],
                "stock": manifest
                | {"action": "OPENING", "opening_control_id": progress["control_id"]},
                "lines": [
                    {
                        "line_key": line["line_id"],
                        "item": {
                            "item_id": str(item_id),
                            "item_version": current["item_version"],
                            "unit_id": str(request.base_unit_id),
                            "actual_quantity": line["quantity"],
                            "billed_quantity": "0",
                        },
                    }
                    for line in manifest["lines"]
                ],
            },
        )
    if step in {"SUBMIT", "ISSUE", "POST"}:
        voucher = await owners.call("vouchers", "GET", root + "/vouchers/" + progress["voucher_id"])
        expected = {"ISSUE": "APPROVED", "POST": "ISSUED"}.get(step)
        if expected and voucher["status"] != expected:
            raise ConflictError(
                "The opening voucher requires review under its current configuration"
            )
        return command(
            "vouchers",
            f"/vouchers/{progress['voucher_id']}/{step.lower()}",
            {"expected_version": voucher["row_version"]},
        )
    if step == "FINALIZE":
        voucher = await owners.call("vouchers", "GET", root + "/vouchers/" + progress["voucher_id"])
        if voucher["status"] != "POSTED":
            operation = await owners.call(
                "vouchers", "GET", root + "/voucher-operations/" + progress["operation_id"]
            )
            if operation["status"] in {"REJECTED", "CANCELLED"}:
                raise OpeningPostingRejectedError(
                    "Opening posting needs attention: "
                    + str(operation.get("rejection_code") or operation["status"])
                )
            return None
        control = await owners.call(
            "accounting", "GET", root + f"/stock/openings/{progress['control_id']}/reconciliation"
        )
        if control["blockers"]:
            return None
        return command(
            "accounting",
            f"/stock/openings/{progress['control_id']}/finalize",
            {
                "expected_version": control["expected_version"],
                "manifest_hash": control["manifest_hash"],
                "reason": "Product opening posted through the native stock voucher",
            },
        )
    raise ConflictError("Unknown product creation step")


def after_command(
    step: str,
    body: SimpleCreationInput,
    progress: dict[str, Any],
    command: dict[str, Any],
    result: dict[str, Any],
) -> tuple[str, uuid.UUID | None]:
    item_id = None
    if step == "CREATE":
        item_id = uuid.UUID(result["id"])
        progress["drafts"] = result.get("price_draft_ids", [])
        step = ("MRP" if progress["drafts"] else "NUMERIC") if body.mrp is not None else "PUBLISH"
    elif step == "NUMERIC":
        progress["numeric_id"] = result["id"]
        step = "MRP"
    elif step == "MRP":
        step = "PUBLISH"
    elif step == "PUBLISH":
        progress["published"] = progress.get("published", 0) + 1
    elif step == "ACTIVATE":
        step = (
            "BATCH"
            if body.batch_enabled and body.batches
            else "SERIAL"
            if serial_entries(body)
            else "OPENING"
            if body.has_opening
            else "COMPLETE"
        )
    elif step == "BATCH":
        progress["batch_ids"] = [*progress.get("batch_ids", []), result["id"]]
        step = "BATCH_PRICES"
    elif step == "BATCH_PRICES":
        progress["batch_index"] = progress.get("batch_index", 0) + 1
        step = (
            "BATCH"
            if progress["batch_index"] < len(body.batches)
            else "SERIAL"
            if serial_entries(body)
            else "OPENING"
            if body.has_opening
            else "COMPLETE"
        )
    elif step == "SERIAL":
        progress["serial_ids"] = [*progress.get("serial_ids", []), result["id"]]
        progress["serial_index"] = progress.get("serial_index", 0) + 1
        step = "SERIAL" if progress["serial_index"] < len(serial_entries(body)) else "OPENING"
    elif step == "OPENING":
        progress.update(control_id=result["id"], manifest=command["body"])
        step = "SOURCE" if progress.get("source_delivery") else "VOUCHER"
    elif step == "SOURCE":
        progress["source_delivered"] = True
        step = "VOUCHER"
    elif step == "VOUCHER":
        progress["voucher_id"] = result["id"]
        step = "SUBMIT"
    elif step == "SUBMIT":
        step = "ISSUE"
    elif step == "ISSUE":
        step = "POST"
    elif step == "POST":
        progress["operation_id"] = result["operation_id"]
        step = "FINALIZE"
    elif step == "FINALIZE":
        progress["opening_posted"] = True
        step = "COMPLETE"
    return step, item_id
