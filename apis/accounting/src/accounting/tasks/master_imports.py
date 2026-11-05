"""Accounting party adapters for the reusable import mechanism."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.bulk import BulkRecord, resolve_references, selection_digest
from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.field_policy import denied_fields
from billing_platform.import_contracts import ImportBatch
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.models.masters import AccountingSetup, Record
from accounting.resources import BY_NAME
from accounting.schemas.masters import ExpectedVersion
from accounting.schemas.party_opening import ReadyPartyCreate
from accounting.tasks.access import authority_fingerprint, authorize, readable, rules
from accounting.tasks.commands import mutate_master, setup_lock
from accounting.tasks.party_ledger import activate_role_with_ledger
from accounting.tasks.ready_party_import import READY_PARTY_ROLES, create_ready_party

RESOURCES = frozenset(
    {
        "party",
        "party_role",
        "party_address",
        "party_address_use",
        "party_contact",
        "party_contact_use",
        "party_tax_registration",
        "party_drug_licence",
        "party_identifier",
        "party_registration_address",
        "party_bank_account",
        "party_commercial_type_membership",
        "party_accounting_policy",
        "party_credit_policy",
    }
)


class AccountingImportAdapter:
    namespace = "accounting"

    def __init__(self, access: Access, settings: Settings) -> None:
        self.access, self.settings = access, settings
        self.actor, self.company = access.actor, access.context.company_id
        self.definitions = {"parties": "Customers, suppliers and related party masters"}

    async def authorize(self, db: AsyncSession, *, write: bool) -> None:
        self.access.context.assert_current(self.actor, self.company)
        self.actor.require_scope(
            "accounting.import.manage", target=ScopePath(company_id=self.company)
        )

    async def lock(self, db: AsyncSession) -> None:
        state = await db.scalar(
            select(AccountingSetup)
            .where(AccountingSetup.company_id == self.company)
            .with_for_update()
        )
        if state is None:
            raise ConflictError("initialize Accounting before importing")

    def check_resource(self, resource: str) -> None:
        if resource in READY_PARTY_ROLES:
            self.check_resource("party")
            self.check_resource("party_role")
            # The ready import always creates the party's ledger account too.
            for action in ("manage", "read"):
                authorize(self.access, BY_NAME["account"], action)
            return
        if resource not in RESOURCES:
            raise ValidationFailedError("resource is outside the party import definition")
        spec = BY_NAME[resource]
        authorize(self.access, spec, "manage")
        authorize(self.access, spec, "read")
        if denied_fields(
            set(spec.create.model_fields) | set(spec.detail.model_fields),
            rules=rules(self.access, spec, None),
            access="read",
            target=ScopePath(company_id=self.company),
        ):
            # Exact input downloads cannot redact protected columns. A job requires
            # full read authority for its native resource, including conditional denies.
            raise PermissionDeniedError("import requires readable native resource fields")

    async def snapshot(
        self, db: AsyncSession, definition: str, parameters: dict[str, str]
    ) -> dict[str, Any]:
        if definition != "parties" or set(parameters) - {"resource", "role"}:
            raise ValidationFailedError("unknown party import configuration")
        if parameters.get("role", "CUSTOMER") not in {"CUSTOMER", "SUPPLIER"}:
            raise ValidationFailedError("choose CUSTOMER or SUPPLIER")
        names = [parameters["resource"]] if "resource" in parameters else sorted(RESOURCES)
        schemas: dict[str, Any] = {}
        options: dict[str, Any] = {}
        for name in names:
            try:
                self.check_resource(name)
            except PermissionDeniedError:
                if "resource" in parameters:
                    raise
                continue
            if (
                name in READY_PARTY_ROLES
                and parameters.get("role", READY_PARTY_ROLES[name]) != READY_PARTY_ROLES[name]
            ):
                raise ValidationFailedError("ready party resource and role differ")
            spec = BY_NAME["party" if name in READY_PARTY_ROLES else name]
            # A plain party row is never created here: a party always arrives with its role and
            # ledger account, through the ready customer/supplier resources.
            commands: list[tuple[str, type[BaseModel]]] = [
                *([] if name == "party" else [("CREATE", spec.create)]),
                ("UPDATE", spec.update),
            ]
            if name in READY_PARTY_ROLES:
                # Ready customers and suppliers also accept the optional opening-balance columns.
                commands = [("CREATE", ReadyPartyCreate)]
            elif spec.lifecycle == "status":
                commands.extend([("ACTIVATE", ExpectedVersion), ("DEACTIVATE", ExpectedVersion)])
            for action, model in commands:
                schema = model.model_json_schema()
                for layout in self.access.context.layouts:
                    if layout.get("entity_type") == "accounting." + spec.name and layout.get(
                        "is_required"
                    ):
                        field = layout["field_key"]
                        if field in schema["properties"] and field not in schema.setdefault(
                            "required", []
                        ):
                            schema["required"].append(field)
                if "role" in schema["properties"] and parameters.get("role"):
                    schema["properties"]["role"]["enum"] = [parameters["role"]]
                schemas[name + ":" + action] = schema
            for field, target in spec.references.items():
                target_spec = BY_NAME.get(target)
                if target_spec is None or not hasattr(target_spec.model, "code"):
                    continue
                try:
                    authorize(self.access, target_spec, "read")
                    if not {"id", "code", "status"} <= readable(self.access, target_spec):
                        continue
                except PermissionDeniedError:
                    continue
                option_model = target_spec.model
                statement = select(option_model.id, option_model.code).where(
                    option_model.company_id == self.company
                )
                if hasattr(option_model, "status"):
                    statement = statement.where(option_model.status == "ACTIVE")
                found = list(
                    (await db.execute(statement.order_by(option_model.id).limit(201))).all()
                )
                options[name + "." + field] = {
                    "items": [{"id": str(row[0]), "code": row[1]} for row in found[:200]],
                    "truncated": len(found) > 200,
                    "resource": target_spec.path,
                }
        if not schemas:
            raise PermissionDeniedError("no authorized party import resources")
        return {
            "version": 1,
            "parameters": parameters,
            "schemas": schemas,
            "options": options,
            "features": sorted(self.access.context.features),
            "layouts": list(self.access.context.layouts),
            "instructions": (
                "Create parties with the supplier/customer resources: they create and "
                "activate the identity, its role and its ledger account together. A plain "
                "party row can only be updated, activated or deactivated; activating a "
                "party_role also creates its ledger account. "
                "Optional opening_* columns hold an opening balance (opening_amount with "
                "opening_balance_type DR, CR, TO_RECEIVE or TO_PAY) for the company opening "
                "declaration, held against that ledger account; they post nothing. "
                "Keep parties and children in one _set for atomicity. "
                "Dates are ISO text, money is exact text, "
                "references are IDs or staged $ref objects."
            ),
        }

    async def fingerprint(self, db: AsyncSession, definition: str) -> str:
        generation = await db.scalar(
            select(AccountingSetup.generation).where(AccountingSetup.company_id == self.company)
        )
        return selection_digest(
            {
                "generation": generation,
                "authority": authority_fingerprint(self.access),
                "features": sorted(self.access.context.features),
                "layouts": list(self.access.context.layouts),
                "currencies": sorted(self.access.context.allowed_currencies),
                "registrations": list(self.access.context.registrations),
            }
        )

    async def readable(self, db: AsyncSession, batch: ImportBatch) -> None:
        for record in batch.records:
            self.check_resource(record.resource)

    async def execute(
        self,
        db: AsyncSession,
        record: BulkRecord,
        mode: str,
        results: dict[str, dict[str, Any]],
        key: str,
    ) -> dict[str, Any]:
        self.check_resource(record.resource)
        if record.resource in READY_PARTY_ROLES:
            return await create_ready_party(db, self.access, self.settings, record, mode, results)
        spec = BY_NAME[record.resource]
        if record.target.external_key:
            raise ValidationFailedError("party import supports explicit ID/code/staged targets")
        target = None
        if record.target.record:
            target = await company_object(
                db,
                spec.model,
                uuid.UUID(
                    str(
                        resolve_references(
                            {"$ref": record.target.record, "field": record.target.field}, results
                        )
                    )
                ),
                company_id=self.company,
            )
        if record.target.id:
            target = await company_object(db, spec.model, record.target.id, company_id=self.company)
        if record.target.code:
            if not hasattr(spec.model, "code"):
                raise ValidationFailedError("resource has no code identity")
            matches = list(
                await db.scalars(
                    select(spec.model)
                    .where(
                        spec.model.company_id == self.company,
                        spec.model.code == record.target.code,
                    )
                    .limit(2)
                )
            )
            if len(matches) > 1 or (matches and matches[0].code != record.target.code):
                raise ConflictError("use an exact unambiguous code")
            matched = matches[0] if matches else None
            if record.target.id and (matched is None or target is None or matched.id != target.id):
                raise ConflictError("target identities disagree")
            target = matched
        action = ("UPDATE" if target else "CREATE") if record.action == "AUTO" else record.action
        if (
            action not in {"CREATE", "UPDATE", "ACTIVATE", "DEACTIVATE"}
            or (mode == "CREATE_ONLY" and action != "CREATE" and not record.target.record)
            or (mode == "UPDATE_ONLY" and action == "CREATE")
        ):
            raise ConflictError("action differs from the selected import mode")
        if (action == "CREATE") != (target is None):
            raise ConflictError("target identity conflicts with requested action")
        if spec.name == "party" and action == "CREATE":
            raise ConflictError(
                "create customers and suppliers with the ready import: "
                "a party always arrives with its role and ledger account"
            )
        data = resolve_references(record.data, results)
        data.update(dict.fromkeys(record.clear_fields))
        if target is None and record.target.code:
            if data.get("code", record.target.code) != record.target.code:
                raise ConflictError("creation code differs from target")
            data["code"] = record.target.code
        if target is not None:
            if data.get("expected_version", target.row_version) != target.row_version:
                raise ConflictError("target version changed")
            data["expected_version"] = target.row_version
        await setup_lock(db, self.access)
        schema = (
            spec.create
            if action == "CREATE"
            else spec.update
            if action == "UPDATE"
            else ExpectedVersion
        )
        body = schema.model_validate(data)
        row: Record
        if spec.name == "party_role" and action == "ACTIVATE" and target is not None:
            # A role never goes live without its ledger account.
            row = await activate_role_with_ledger(
                db,
                self.access,
                self.settings,
                role_id=target.id,
                expected_version=ExpectedVersion.model_validate(data).expected_version,
            )
        else:
            row = await mutate_master(
                db,
                self.access,
                spec,
                action.lower(),
                body,
                self.settings,
                target.id if target else None,
            )
        await db.flush()
        return {"id": str(row.id)}
