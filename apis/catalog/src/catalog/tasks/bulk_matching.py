"""Exact, authorized target resolution and frozen ordinary command inputs."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.bulk import BulkRecord, resolve_references, selection_digest
from billing_platform.db.access import company_object
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from sqlalchemy import select

from catalog.models import MasterExternalKey
from catalog.models.bulk import BulkJobRecord
from catalog.tasks.bulk_access import native, resource_entity
from catalog.tasks.bulk_registry import OPERATIONS, Operation, Runtime, operation
from catalog.tasks.field_context import load_field_context
from catalog.tasks.policy_state import policy_state


async def exact_target(
    runtime: Runtime, record: BulkRecord, model: type[Any], results: dict[str, dict[str, Any]]
) -> Any:
    context = await load_field_context(
        runtime.db, runtime.actor, runtime.company, resource_entity(record.resource)
    )
    target = record.target
    if target.record:
        key = resolve_references({"$ref": target.record, "field": target.field}, results)
        return await company_object(
            runtime.db, model, uuid.UUID(str(key)), company_id=runtime.company
        )
    matches: list[Any] = []
    if target.id:
        matches.append(
            await company_object(runtime.db, model, target.id, company_id=runtime.company)
        )
    if target.code:
        field = "sku" if record.resource in {"item", "simple_product"} else "code"
        if not hasattr(model, field):
            raise ValidationFailedError("resource does not support code matching")
        if field not in context.readable():
            raise PermissionDeniedError("target code is protected")
        code_matches = list(
            await runtime.db.scalars(
                select(model)
                .where(model.company_id == runtime.company, getattr(model, field) == target.code)
                .limit(2)
            )
        )
        if len(code_matches) > 1:
            raise ValidationFailedError("target code is ambiguous; use an ID or external key")
        match = code_matches[0] if code_matches else None
        if match is not None and getattr(match, field) != target.code:
            raise ValidationFailedError("target code must use its exact canonical spelling")
        matches.append(match)
    if target.external_key:
        external = await load_field_context(
            runtime.db, runtime.actor, runtime.company, "catalog.master_external_key"
        )
        if (
            not {"source_namespace", "external_key", "target_id", "entity_type", "is_active"}
            <= external.readable()
        ):
            raise PermissionDeniedError("external target identity is protected")
        link = await runtime.db.scalar(
            select(MasterExternalKey).where(
                MasterExternalKey.company_id == runtime.company,
                MasterExternalKey.entity_type == resource_entity(record.resource),
                MasterExternalKey.source_namespace == target.external_system,
                MasterExternalKey.external_key == target.external_key,
                MasterExternalKey.is_active.is_(True),
            )
        )
        if link is not None and (
            link.source_namespace != target.external_system
            or link.external_key != target.external_key
            or not native(link).keys() <= external.readable(native(link))
        ):
            raise PermissionDeniedError("external target identity is unavailable")
        matches.append(
            await company_object(runtime.db, model, link.target_id, company_id=runtime.company)
            if link
            else None
        )
    if matches and any(
        (value.id if value is not None else None)
        != (matches[0].id if matches[0] is not None else None)
        for value in matches
    ):
        raise ValidationFailedError("supplied target identities do not agree")
    row = matches[0] if matches else None
    if row is not None and not native(row).keys() <= context.readable(native(row)):
        raise PermissionDeniedError("target fields are protected")
    return row


async def prepare(
    runtime: Runtime,
    stored: BulkJobRecord,
    mode: str,
    results: dict[str, dict[str, Any]],
    *,
    reviewed: bool,
) -> tuple[Operation, Any, uuid.UUID | None, dict[str, Any] | None]:
    record = BulkRecord.model_validate(stored.normalized_input)
    if reviewed and stored.prepared_input is None:
        raise ConflictError("record has no reviewed input")
    action = (
        stored.prepared_input["action"] if reviewed and stored.prepared_input else record.action
    )
    possible = (
        [operation(record.resource, action)]
        if action != "AUTO"
        else [
            op
            for (resource, candidate), op in OPERATIONS.items()
            if resource == record.resource
            and candidate
            in (
                {"CREATE"}
                if mode == "CREATE_ONLY"
                else {"UPDATE"}
                if mode == "UPDATE_ONLY"
                else {"CREATE", "UPDATE"}
            )
        ]
    )
    if not possible:
        raise ValidationFailedError("resource cannot be imported")
    # Require write authority before looking up an ID or code. AUTO chooses only
    # among operations for which the actor has current authority after resolution.
    for candidate in possible:
        for permission in candidate.permissions:
            runtime.actor.require_scope(permission, target=ScopePath(company_id=runtime.company))
    row = await exact_target(runtime, record, possible[0].model, results)
    if action == "AUTO":
        if mode == "CREATE_ONLY" and row is not None:
            raise ConflictError("CREATE_ONLY target already exists")
        if mode == "UPDATE_ONLY" and row is None:
            raise NotFoundError("UPDATE_ONLY target was not found")
        action = "UPDATE" if row is not None else "CREATE"
    op = operation(record.resource, action)
    if mode == "CREATE_ONLY" and op.requires_target and not record.target.record:
        raise ConflictError("CREATE_ONLY cannot change an existing target")
    if mode == "UPDATE_ONLY" and not op.requires_target:
        raise ConflictError("UPDATE_ONLY cannot create a new target")
    for permission in op.permissions:
        runtime.actor.require_scope(permission, target=ScopePath(company_id=runtime.company))
    if op.requires_target and row is None:
        raise NotFoundError("command target was not found")
    if not op.requires_target and row is not None:
        raise ConflictError("creation target already exists")
    if not op.requires_target and (record.target.id or record.target.external_key):
        raise ValidationFailedError(
            "new targets require native code data; external keys use an explicit assignment"
        )
    target_id = row.id if row is not None else None
    if reviewed and not record.target.record and target_id != stored.target_id:
        raise ConflictError("reviewed target identity changed")
    data = resolve_references(record.data, results)
    data.update(dict.fromkeys(record.clear_fields))
    if not op.requires_target and record.target.code:
        if data.get("code", record.target.code) != record.target.code:
            raise ValidationFailedError("target and creation codes differ")
        data["code"] = record.target.code
    if row is not None and "expected_version" in op.schema.model_fields:
        expected = (
            stored.expected_version if reviewed and not record.target.record else row.row_version
        )
        if "expected_version" in data and data["expected_version"] != expected:
            raise ConflictError("supplied target version changed")
        data["expected_version"] = expected
    state = await policy_state(runtime.db, runtime.actor, runtime.company, lock=True)
    assert state is not None
    if "expected_generation" in op.schema.model_fields:
        data["expected_generation"] = state.generation
    if "expected_source_version" in op.schema.model_fields:
        context = await load_field_context(
            runtime.db, runtime.actor, runtime.company, resource_entity(record.resource)
        )
        data["expected_source_version"] = context.source_version
    changes = data.get("changes")
    if record.resource == "tax_release" and isinstance(changes, list) and len(changes) <= 100:
        guard = {key: data[key] for key in ("expected_generation", "expected_source_version")}
        data["changes"] = [
            {**change, "definition": {**change["definition"], **guard}}
            if isinstance(change, dict) and isinstance(change.get("definition"), dict)
            else change
            for change in changes
        ]
    product_evidence = {}
    if record.resource == "simple_product":
        from catalog.models.products import ProductFamily
        from catalog.tasks.product_mode import check_version, version
        from catalog.tasks.simple_products import revision_codec, revision_values

        mode_version = (
            stored.prepared_input["authoring_version"]
            if reviewed and stored.prepared_input
            else await version(runtime.db, runtime.company)
        )
        await check_version(runtime.db, runtime.company, mode_version)
        if "authoring_version" in data and data["authoring_version"] != mode_version:
            raise ConflictError("Product authoring mode changed; review import again.")
        data["authoring_version"] = mode_version
        product_evidence["authoring_version"] = mode_version
        if row is not None:
            family = await company_object(
                runtime.db, ProductFamily, row.family_id, company_id=runtime.company
            )
            revision = (
                stored.prepared_input["product_revision"]
                if reviewed and stored.prepared_input and not record.target.record
                else revision_codec(runtime.actor, runtime.company, row.id, runtime.secret).encode(
                    revision_values(row, family)
                )
            )
            data.setdefault("revision", revision)
            product_evidence["product_revision"] = revision
    body = op.schema.model_validate(data)
    before = native(row) if row is not None else None
    if not reviewed:
        stored.target_id = target_id if not record.target.record else None
        stored.expected_version = (
            getattr(row, "row_version", None)
            if row is not None and not record.target.record
            else None
        )
        stored.prepared_input = {"action": action, **product_evidence}
        identity = (
            str(target_id)
            if target_id
            else record.target.record or data.get("code") or data.get("sku")
        )
        child = (
            data["item"]["sku"]
            if action == "CREATE_VARIANT"
            else data["value"]
            if action == "CREATE_BARCODE"
            else data["barcode_id"]
            if action == "BARCODE_STATE"
            else data["code"]
            if action in {"BIND_UNIT", "REVISE_UNIT"}
            else None
        )
        stored.target_key = (
            selection_digest([record.resource, action, identity, child])
            if identity is not None
            else None
        )
    return op, body, target_id, before
