"""Voucher bulk import: stage, native dry-run validation, one draft per voucher on commit.

Validation and commit advance in bounded steps inside authenticated requests, so every
voucher is checked and written with the uploader's current signed authority and field
policy. Remote owner calls (master lookup, invoice calculation) never hold a transaction.
"""

import asyncio
import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from billing_platform.bulk import selection_digest
from billing_platform.bulk_files import TableRow, read_csv, read_xlsx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.idempotency import (
    CommandIdentity,
    CommandReceipt,
    canonical_json,
    execute_idempotent,
)
from billing_platform.import_journal import StepBudget
from billing_platform.pagination import CursorCodec
from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only
from voucher_execution.invoice import InvoiceCalculationDetail, InvoicePolicy, InvoicePreviewCommand

from vouchers.api.auth import Access
from vouchers.domain import import_checks as checks
from vouchers.domain import import_kinds as kinds
from vouchers.domain import import_money as money
from vouchers.domain import imports as rules
from vouchers.domain.documents import fiscal_start
from vouchers.models import core as m
from vouchers.models import imports as im
from vouchers.models.invoice import VoucherInvoiceDetail, VoucherSupplyDetail
from vouchers.schemas.configuration import Policy
from vouchers.schemas.documents import VoucherInput
from vouchers.schemas.owners import Owner
from vouchers.tasks import custom_fields, documents
from vouchers.tasks import import_history as journal
from vouchers.tasks.access import authorize, denied, fingerprint
from vouchers.tasks.common import audit, command, get, values
from vouchers.tasks.configuration import effective
from vouchers.tasks.master_lookup import lookup
from vouchers.tasks.master_lookup import owner_for as owner_for

STEP = 20
JOB_TTL = dt.timedelta(days=7)
REPORT_TTL = 300
OPTIONAL_NATIVE = frozenset({"class_id", "posting_date", "narration", "references"})
TRANSIENT = ("request is busy", "request is already in progress")
FILE_MEDIA = {
    "CSV": "text/csv",
    "TSV": "text/tab-separated-values",
    "JSON": "application/json",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_FILE = 8 * 1024 * 1024
# Native fields whose read-deny hides the uploaded cells and the computed amounts.
CONTENT_FIELDS = frozenset(
    {"invoice", "financial", "parties", "narration", "references", "custom_fields"}
)
Preview = Callable[[Owner, InvoicePreviewCommand], Awaitable[InvoiceCalculationDetail]]
Lookup = Callable[..., Awaitable[rules.Resolution]]


def require(current: Access, *actions: str) -> None:
    for action in actions:
        authorize(current, action)


def today(current: Access) -> dt.date:
    finance = current.context.finance
    if finance is None or not finance.company_active:
        raise ConflictError("active company calendar context is required")
    return utcnow().astimezone(ZoneInfo(finance.timezone)).date()


async def import_type(
    db: AsyncSession, current: Access, type_id: uuid.UUID
) -> tuple[m.VoucherType, m.VoucherTypeRevision]:
    kind = await get(db, current, m.VoucherType, type_id)
    if (
        kind.kind not in kinds.KINDS
        or kind.profile not in kinds.PROFILES[kind.kind]
        or kind.status != "ACTIVE"
    ):
        raise ConflictError(
            "import supports active Purchase, Sales, Credit/Debit Note, Payment, Receipt, "
            "Contra and Journal types (standard profile; advance for payments and receipts)"
        )
    revision = await db.scalar(
        select(m.VoucherTypeRevision).where(
            m.VoucherTypeRevision.company_id == current.context.company_id,
            m.VoucherTypeRevision.type_id == kind.id,
            m.VoucherTypeRevision.revision_number == kind.current_revision,
        )
    )
    if revision is None:
        raise ConflictError("voucher type has no current revision")
    if kind.kind == "PURCHASE":
        policy = Policy.model_validate(revision.policy)
        if (
            policy.default_mode != "ACCOUNTS"
            or "ACCOUNTS" not in policy.allowed_modes
            or "ITEMS" in policy.required_sections
        ):
            # Imported Purchase lines are account/service supplies; a product or mixed type would
            # create drafts that could never be submitted.
            raise ConflictError(
                "Purchase import supports account and service bill types; "
                "product and mixed bills cannot be imported yet"
            )
    return kind, revision


async def shape_for(
    db: AsyncSession,
    current: Access,
    revision: m.VoucherTypeRevision,
    kind: str,
    *,
    document_date: dt.date | None = None,
    posting_date: dt.date | None = None,
    class_id: uuid.UUID | None = None,
) -> tuple[rules.Template, frozenset[str]]:
    """Template columns from the type's effective configuration and live field policy."""
    day = document_date or today(current)
    policy, _ = await effective(
        db, current, revision.id, date=day, posting_date=posting_date or day, class_id=class_id
    )
    fields = set(kinds.required(kind) | OPTIONAL_NATIVE)
    # A field the actor may not read or write is never offered (VIM01).
    blocked = frozenset(
        denied(current, "vouchers.voucher", fields, "write")
        | denied(current, "vouchers.voucher", fields, "read")
    )
    allowed = policy.header_field_keys
    custom = [
        rules.CustomColumn(row.key, row.data_type)
        for row in await custom_fields.definitions(db, current, "vouchers.voucher")
        if row.is_active
        and row.data_type != "auto_number"
        and (allowed is None or row.key in allowed)
        and not denied(current, "vouchers.voucher", {row.key}, "write")
        and not denied(current, "vouchers.voucher", {row.key}, "read")
    ]
    try:
        return kinds.template(kind, blocked, custom), OPTIONAL_NATIVE - blocked
    except PermissionError as error:
        raise PermissionDeniedError(str(error)) from error


def template_document(
    shape: rules.Template, file_format: str, code: str, kind: str = "PURCHASE"
) -> tuple[bytes, str, str]:
    from billing_platform.bulk_files import csv_document, xlsx_workbook

    name = f"{kind.lower().replace('_', '-')}-import-{code}"
    header, line = rules.examples(shape)
    if file_format in {"CSV", "TSV"}:
        raw = csv_document(
            shape.flat(),
            rules.flat_examples(shape),
            template=True,
            marker=rules.MARKER,
            delimiter="\t" if file_format == "TSV" else ",",
        )
        return raw, FILE_MEDIA[file_format], name + "." + file_format.lower()
    if file_format == "XLSX":
        raw = xlsx_workbook(
            [
                ("vouchers", shape.names("header"), header),
                ("lines", shape.names("line"), line),
                ("instructions", ["field", "required", "description"], rules.instructions(shape)),
            ],
            marker=rules.MARKER,
        )
        return raw, FILE_MEDIA["XLSX"], name + ".xlsx"
    names = shape.names("line")
    example = {
        key: value for key, value in zip(shape.names("header"), header[0], strict=True) if value
    } | {
        "lines": [
            {
                key: value
                for key, value in zip(names, line[0], strict=True)
                if value and key != "import_key"
            }
        ]
    }
    raw = json.dumps(
        {"schema_version": rules.SCHEMA_VERSION, "vouchers": [example]}, indent=2
    ).encode()
    return raw, "application/json", name + ".json"


def tables(rows: list[TableRow]) -> dict[str, list[tuple[int, dict[str, str]]]]:
    result: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for row in rows:
        if row.sheet != "instructions" and any(
            cell.value and cell.kind != "text" for cell in row.cells.values()
        ):
            raise ValidationFailedError("import identifiers, dates and decimals require text cells")
        result.setdefault(row.sheet, []).append(
            (row.number, {key: cell.value for key, cell in row.cells.items()})
        )
    return result


def headers_of(grouped: dict[str, list[tuple[int, dict[str, str]]]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for sheet, rows in grouped.items():
        seen: dict[str, None] = {}
        for _, cells in rows:
            seen |= dict.fromkeys(cells)
        result[sheet] = list(seen)
    return result


def decode(
    file_format: str, content: str | None, document: Any, shape: rules.Template
) -> tuple[bytes, list[rules.Staged]]:
    """L1/L3 parsing; file-level problems reject the upload before anything is stored."""
    if file_format == "JSON":
        if document is None or content is not None:
            raise ValidationFailedError("JSON uploads send the document field only")
        try:
            raw = canonical_json(document, maximum_bytes=MAX_FILE)
        except (TypeError, ValueError) as error:
            raise ValidationFailedError("JSON document must use text values only") from error
        staged, issues = rules.group_json(document, shape)
    else:
        if content is None or document is not None:
            raise ValidationFailedError("file uploads send content_base64 only")
        try:
            raw = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValidationFailedError("content_base64 is not valid base64") from error
        try:
            rows = (
                read_csv(raw, marker=rules.MARKER, delimiter="\t" if file_format == "TSV" else ",")
                if file_format in {"CSV", "TSV"}
                else read_xlsx(raw, marker=rules.MARKER)
            )
        except ValueError as error:
            raise ValidationFailedError(f"file rejected: {error}") from error
        grouped = tables(rows)
        names = headers_of(grouped)
        if file_format in {"CSV", "TSV"}:
            staged, issues = rules.group_flat(grouped.get("CSV", []), names.get("CSV", []), shape)
        else:
            staged, issues = rules.group_sheets(grouped, names, shape)
    if issues:
        raise ValidationFailedError(
            "file does not match the import template",
            fields={
                f"{issue.sheet}!{issue.row}:{issue.column or '-'}": issue.code
                for issue in issues[:20]
            },
        )
    return raw, staged


def new[T: m.Record](model: type[T], current: Access, **fields: Any) -> T:
    return model(**(values(current) | {"row_version": 1} | fields))


def job_audit(db: AsyncSession, current: Access, job: im.VoucherImportJob, action: str) -> None:
    audit(
        db,
        current,
        "import_job",
        job.id,
        action,
        changes={
            "state": job.state,
            "voucher_count": job.voucher_count,
            "created_count": job.created_count,
            "failed_count": job.failed_count,
        },
    )


async def job_command(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    permissions: tuple[str, ...],
    operation: str,
    key: str,
    request: dict[str, Any],
    mutate: Callable[[AsyncSession], Awaitable[CommandReceipt]],
    render: Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> Any:
    require(current, *permissions)

    async def auth(db: AsyncSession, refs: dict[str, Any] | None) -> None:
        require(current, *permissions)

    async def apply(db: AsyncSession) -> CommandReceipt:
        db.info["voucher_actor"] = current.actor.user_id
        return await mutate(db)

    return await execute_idempotent(
        factory,
        CommandIdentity(
            current.actor.tenant_id,
            current.context.company_id,
            current.actor.user_id,
            "vouchers.import." + operation,
            key,
            request,
        ),
        authorize=auth,
        mutate=apply,
        render=render,
        timeout_seconds=60,
    )


async def job_rows(
    db: AsyncSession,
    current: Access,
    job_id: uuid.UUID,
    *,
    states: tuple[str, ...] = (),
    lock: bool = False,
    limit: int | None = None,
) -> list[im.VoucherImportRow]:
    statement = (
        select(im.VoucherImportRow)
        .where(
            im.VoucherImportRow.company_id == current.context.company_id,
            im.VoucherImportRow.job_id == job_id,
        )
        .order_by(im.VoucherImportRow.ordinal)
    )
    if states:
        statement = statement.where(im.VoucherImportRow.state.in_(states))
    if limit is not None:
        statement = statement.limit(limit)
    if lock:
        statement = statement.with_for_update()
    return list(await db.scalars(statement))


def count(job: im.VoucherImportJob, rows: list[im.VoucherImportRow]) -> None:
    states = Counter(row.state for row in rows)
    job.valid_count, job.warning_count = states["VALID"], states["WARNING"]
    job.invalid_count = states["INVALID"]
    job.created_count, job.failed_count = states["CREATED"], states["FAILED"]


async def scoped_job(
    db: AsyncSession, current: Access, job_id: uuid.UUID, *, lock: bool = False, owner: bool = True
) -> im.VoucherImportJob:
    job = await get(db, current, im.VoucherImportJob, job_id, lock=lock)
    if owner and job.actor_user_id != current.actor.user_id:
        raise PermissionDeniedError("import jobs are private to their uploader")
    return job


async def stage(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    key: str,
    *,
    type_id: uuid.UUID,
    file_format: str,
    content: str | None,
    document: Any,
    duplicate_rule: str = "DATE_NUMBER_PARTY",
    template_id: uuid.UUID | None = None,
    render: Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> Any:
    require(current, "import.manage", "create")
    try:
        source = content or canonical_json(document, maximum_bytes=MAX_FILE).decode()
    except (TypeError, ValueError) as error:
        raise ValidationFailedError("JSON document must use text values only") from error
    request = {
        "type_id": str(type_id),
        "format": file_format,
        "duplicate_rule": duplicate_rule,
        "template_id": str(template_id) if template_id else None,
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }

    async def mutate(db: AsyncSession) -> CommandReceipt:
        await expire(db, current)
        kind, revision = await import_type(db, current, type_id)
        if duplicate_rule not in kinds.DUPLICATE_RULES.get(kind.kind, ("DATE_NUMBER_PARTY",)):
            raise ValidationFailedError("this duplicate rule applies to purchase imports only")
        parameters: dict[str, Any] = {}
        if template_id is not None:
            from vouchers.schemas.imports import TemplateSnapshotInput
            from vouchers.tasks.import_extensions import checked_template

            template = await checked_template(db, current, template_id, type_id)
            assert template.snapshot is not None
            parameters = TemplateSnapshotInput.model_validate(
                template.snapshot["parameters"]
            ).model_dump(exclude={"voucher_type_id"})
        shape, _ = await shape_for(db, current, revision, kind.kind, **parameters)
        raw, staged = await asyncio.to_thread(decode, file_format, content, document, shape)
        expires = utcnow() + JOB_TTL
        sha = hashlib.sha256(raw).hexdigest()
        job = new(
            im.VoucherImportJob,
            current,
            actor_user_id=current.actor.user_id,
            kind=kind.kind,
            type_id=kind.id,
            type_revision_id=revision.id,
            source_format=file_format,
            schema_version=rules.SCHEMA_VERSION,
            state="STAGED",
            on_error="STOP",
            duplicate_rule=duplicate_rule,
            input_sha256=sha,
            voucher_count=len(staged),
            expires_at=expires,
        )
        db.add(job)
        await db.flush()
        db.add(
            new(
                im.VoucherImportArtifact,
                current,
                job_id=job.id,
                media_type=FILE_MEDIA[file_format],
                content_sha256=sha,
                byte_count=len(raw),
                content=raw,
                expires_at=expires,
            )
        )
        identities: dict[tuple[str, ...], str] = {}
        invalid = 0
        for item in staged:
            parsed, issues = kinds.parse(kind.kind, item, shape)
            if parsed is not None:
                for identity, column, code in kinds.file_identities(
                    kind.kind, parsed, duplicate_rule
                ):
                    if identity in identities:
                        sheet, row = item.rows[0]
                        issues.append(
                            rules.Issue(
                                sheet,
                                row,
                                column,
                                code,
                                f"repeats {identities[identity]} in this file",
                                "L3",
                            )
                        )
                    identities.setdefault(identity, item.import_key)
            db.add(
                new(
                    im.VoucherImportRow,
                    current,
                    job_id=job.id,
                    import_key=item.import_key[:64],
                    ordinal=item.ordinal,
                    state="INVALID" if issues else "STAGED",
                    source_input={"header": item.header, "lines": item.lines},
                    source_rows=[list(position) for position in item.rows],
                    errors=[issue.as_dict() for issue in issues[: rules.MAX_ERRORS]],
                    error_count=min(len(issues), rules.MAX_ERRORS),
                )
            )
            invalid += bool(issues)
        job.invalid_count = invalid
        await db.flush()
        await journal.capture_revision(db, current, job, raw, template_id)
        job_audit(db, current, job, "stage")
        return CommandReceipt(202, {"id": str(job.id)})

    return await job_command(
        factory, current, ("import.manage", "create"), "stage", key, request, mutate, render
    )


def reset_validation(row: im.VoucherImportRow) -> bool:
    """Stage-time (lexical/grouping) failures are final; native results are recomputed."""
    if row.state == "CREATED":
        return False
    staged = [error for error in row.errors if error.get("layer") in {"L2", "L3"}]
    if row.state == "INVALID" and staged:
        return False
    row.state = "STAGED"
    row.errors = staged
    row.error_count = len(staged)
    row.prepared_input = None
    row.configuration_hash = None
    row.computed_payable = row.computed_tax_total = row.supplier_difference = None
    row.declared_total = None
    row.currency = None
    row.row_version += 1
    return True


async def transition(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    key: str,
    job_id: uuid.UUID,
    action: str,
    body: dict[str, Any],
    render: Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> Any:
    """validate / commit / cancel state changes; each is idempotent on its key."""
    permissions = {
        "validate": ("import.manage", "create"),
        "commit": ("import.commit", "create"),
        "cancel": ("import.manage",),
    }[action]

    async def mutate(db: AsyncSession) -> CommandReceipt:
        job = await scoped_job(db, current, job_id, lock=True)
        if job.row_version != body["expected_version"]:
            raise ConflictError("import job changed; reload before retrying")
        if job.expires_at <= utcnow():
            raise ConflictError("import job has expired; upload the file again")
        rows = await job_rows(db, current, job.id, lock=True)
        if action == "validate":
            if job.state not in {"STAGED", "READY", "PARTIAL", "FAILED"}:
                raise ConflictError("only staged or validated jobs can be validated")
            for row in rows:
                reset_validation(row)
            job.state, job.selection_digest = "VALIDATING", None
            await journal.begin(db, current, job, "VALIDATE")
            count(job, rows)
        elif action == "commit":
            if job.state != "READY" or job.selection_digest != body["selection_digest"]:
                raise ConflictError("validation results changed; review and validate again")
            excluded = set(body["exclude_keys"])
            if excluded - {row.import_key for row in rows}:
                raise ValidationFailedError("excluded keys must belong to this job")
            selected = 0
            for row in rows:
                if row.state in {"VALID", "WARNING"} and row.import_key in excluded:
                    row.state = "NOT_SELECTED"
                    row.row_version += 1
                elif row.state in {"VALID", "WARNING"}:
                    selected += 1
            if not selected:
                raise ConflictError("no valid vouchers are selected for import")
            job.state, job.on_error = "COMMITTING", body["on_error"]
            await journal.begin(db, current, job, "COMMIT")
        else:
            if job.state in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
                raise ConflictError("finished import jobs cannot be cancelled")
            for row in rows:
                if row.state in {"STAGED", "VALID", "WARNING"}:
                    row.state = "NOT_SELECTED"
                    row.row_version += 1
            job.state = "CANCELLED"
            # Drafts a concurrent commit step created stay; the counts say so.
            count(job, rows)
            await journal.close(db, current, job)
        job.row_version += 1
        job_audit(db, current, job, action)
        return CommandReceipt(200, {"id": str(job.id)})

    request = {"id": str(job_id), "action": action, "body": body}
    return await job_command(factory, current, permissions, action, key, request, mutate, render)


async def preview_owner(
    owner: Owner, command_body: InvoicePreviewCommand
) -> InvoiceCalculationDetail:
    from voucher_execution.transport import ExecutionClient

    async with httpx.AsyncClient(timeout=15) as transport:
        client = ExecutionClient(
            transport, owner.origin, owner.key_id, owner.secret.get_secret_value().encode()
        )
        return await client.preview(command_body)


async def default_lookup(
    owner: Owner, tenant: uuid.UUID, company: uuid.UUID, **codes: Any
) -> rules.Resolution:
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        return await lookup(client, owner, tenant, company, **codes)


def failure(error: Exception, sheet: str, row: int, layer: str = "L5") -> rules.Issue:
    """Safe native error: code and owner-written message only, never submitted values."""
    if isinstance(error, ValidationError):
        first = error.errors(include_input=False, include_url=False)[0]
        where = ".".join(str(part) for part in first["loc"])
        return rules.Issue(sheet, row, None, "invalid_content", f"{where}: {first['type']}", layer)
    if isinstance(error, PermissionDeniedError):
        return rules.Issue(sheet, row, None, "permission_denied", error.message, layer)
    if isinstance(error, PlatformError):
        code = (
            "master_unavailable"
            if "master evidence" in error.message
            else "conflict"
            if isinstance(error, ConflictError)
            else "validation_failed"
        )
        return rules.Issue(sheet, row, None, code, error.message, layer)
    raise error


GONE = ("CANCELLED", "REVERSED")
SETTLED = ("POSTED", "CANCELLED", "REVERSED")
# A consumption probe's owner balance is trusted at commit for this long after validation.
BALANCE_TTL = dt.timedelta(hours=1)


def live(statement: Any, *, unposted: bool = False) -> Any:
    """Current revisions of vouchers that still count.

    ``unposted`` keeps only drafts whose amounts the owner does not know yet: posted ones and
    those with a posting in flight (the owner counts prepared executions) are excluded.
    """
    revision, voucher, operation = m.VoucherRevision, m.Voucher, m.VoucherOperation
    statement = statement.join(
        voucher,
        and_(
            voucher.tenant_id == revision.tenant_id,
            voucher.company_id == revision.company_id,
            voucher.id == revision.voucher_id,
            voucher.current_revision == revision.revision_number,
        ),
    ).where(voucher.status.not_in(SETTLED if unposted else GONE))
    if unposted:
        statement = statement.where(
            ~select(operation.id)
            .where(
                operation.company_id == voucher.company_id,
                operation.voucher_id == voucher.id,
                operation.purpose == "POST",
                operation.status == "PENDING",
            )
            .exists()
        )
    return statement


def on_revision(model: Any) -> Any:
    revision = m.VoucherRevision
    return and_(
        revision.tenant_id == model.tenant_id,
        revision.company_id == model.company_id,
        revision.id == model.revision_id,
    )


def kind_types(current: Access, kind: str) -> Any:
    return select(m.VoucherType.id).where(
        m.VoucherType.company_id == current.context.company_id, m.VoucherType.kind == kind
    )


def ci(db: AsyncSession, column: Any) -> Any:
    """Case-insensitive comparison: MySQL's _ci collation already is (and keeps the index);
    other engines (SQLite in tests) compare lowered text."""
    return column if db.bind.dialect.name in {"mysql", "mariadb"} else func.lower(column)


async def found_identity(
    db: AsyncSession, current: Access, item: dict[str, Any], exclude: uuid.UUID | None
) -> bool:
    """Whether another live voucher already carries this probe's identity."""
    company = current.context.company_id
    detail, revision, party = VoucherInvoiceDetail, m.VoucherRevision, m.VoucherParty
    voucher = m.Voucher
    name = item["probe"]
    if name in {"bill", "bill_year"}:
        statement = live(
            select(voucher.id).select_from(detail).join(revision, on_revision(detail))
        ).where(
            detail.company_id == company,
            ci(db, detail.supplier_invoice_number) == item["number"],
        )
        if name == "bill":
            statement = statement.where(
                detail.supplier_invoice_date == dt.date.fromisoformat(item["date"])
            )
        else:
            statement = statement.where(
                detail.supplier_invoice_date.between(
                    dt.date.fromisoformat(item["start"]), dt.date.fromisoformat(item["end"])
                ),
                detail.supplier_invoice_date != dt.date.fromisoformat(item["other_than"]),
            )
        if item.get("rule") == "DATE_NUMBER_ACCOUNT":
            statement = statement.where(detail.party_account_id == uuid.UUID(item["account_id"]))
        elif item.get("rule") != "DATE_NUMBER":
            statement = statement.join(
                party,
                and_(
                    on_revision(party),
                    party.role == "SUPPLIER",
                    party.party_id == uuid.UUID(item["party_id"]),
                ),
            )
    elif name == "external":
        reference = m.VoucherReference
        statement = live(
            select(voucher.id).select_from(reference).join(revision, on_revision(reference))
        ).where(
            reference.company_id == company,
            reference.purpose == "EXTERNAL",
            ci(db, reference.reference) == item["reference"],
            voucher.type_id.in_(kind_types(current, item["kind"])),
        )
        if item.get("party_id"):
            statement = statement.join(
                party, and_(on_revision(party), party.party_id == uuid.UUID(item["party_id"]))
            )
    elif name == "instrument":
        tender, entry = m.VoucherTender, m.VoucherAccountDetail
        statement = live(
            select(voucher.id)
            .select_from(tender)
            .join(
                entry,
                and_(
                    entry.tenant_id == tender.tenant_id,
                    entry.company_id == tender.company_id,
                    entry.revision_id == tender.revision_id,
                    entry.line_key == tender.line_key,
                ),
            )
            .join(revision, on_revision(tender))
        ).where(
            tender.company_id == company,
            ci(db, tender.reference) == item["reference"],
            entry.account_id == uuid.UUID(item["account_id"]),
        )
        if item["group"] == "CHEQUE":
            statement = statement.where(tender.mode == "CHEQUE", entry.side == item["side"])
            if item.get("date"):
                statement = statement.where(
                    tender.instrument_date == dt.date.fromisoformat(item["date"]),
                    tender.amount == Decimal(item["value"]),
                )
        else:
            statement = statement.where(tender.mode.not_in(["CHEQUE", "CASH"]))
    elif name == "signature":
        return await signature_found(db, current, item, exclude)
    else:
        raise ValueError("unsupported identity probe")
    if exclude is not None:
        statement = statement.where(voucher.id != exclude)
    return await db.scalar(statement.limit(1)) is not None


async def signature_found(
    db: AsyncSession, current: Access, item: dict[str, Any], exclude: uuid.UUID | None
) -> bool:
    """Same kind, document date, and ledger/side/amount multiset (money or invoice party)."""
    revision, voucher = m.VoucherRevision, m.Voucher
    types = kind_types(current, item["kind"])
    day = dt.date.fromisoformat(item["date"])
    if item.get("family") == "invoice":
        detail, supply = VoucherInvoiceDetail, VoucherSupplyDetail
        statement = (
            live(
                select(revision.id, detail.party_account_id, func.sum(supply.amount))
                .select_from(detail)
                .join(revision, on_revision(detail))
                .join(supply, on_revision(supply))
            )
            .where(
                detail.company_id == current.context.company_id,
                revision.document_date == day,
                voucher.type_id.in_(types),
                detail.party_account_id == uuid.UUID(item["entries"][0][0]),
            )
            .group_by(revision.id, detail.party_account_id)
        )
        if exclude is not None:
            statement = statement.where(voucher.id != exclude)
        for _, account, total in await db.execute(statement.limit(500)):
            if checks.signature([(str(account), "PARTY", total)]) == item["entries"]:
                return True
        return False
    entry = m.VoucherAccountDetail
    statement = live(
        select(entry.revision_id, entry.account_id, entry.side, entry.amount)
        .select_from(entry)
        .join(revision, on_revision(entry))
    ).where(
        entry.company_id == current.context.company_id,
        revision.document_date == day,
        voucher.type_id.in_(types),
    )
    if exclude is not None:
        statement = statement.where(voucher.id != exclude)
    grouped: dict[uuid.UUID, list[tuple[str, str, Decimal]]] = {}
    for revision_id, account, side, amount in await db.execute(statement.limit(2000)):
        grouped.setdefault(revision_id, []).append((str(account), side, amount))
    return any(checks.signature(rows) == item["entries"] for rows in grouped.values())


async def consumed(
    db: AsyncSession, current: Access, item: dict[str, Any], exclude: uuid.UUID | None = None
) -> Decimal:
    """Amounts unposted drafts already take from the probe's limited balance."""
    revision, voucher = m.VoucherRevision, m.Voucher
    if item["probe"] == "entitlement":
        supply, line, detail = VoucherSupplyDetail, m.VoucherLine, VoucherInvoiceDetail
        statement = live(
            select(func.coalesce(func.sum(supply.amount), 0))
            .select_from(supply)
            .join(revision, on_revision(supply))
            .join(
                line,
                and_(
                    line.tenant_id == supply.tenant_id,
                    line.company_id == supply.company_id,
                    line.id == supply.line_id,
                ),
            )
            .join(
                detail,
                and_(
                    detail.tenant_id == supply.tenant_id,
                    detail.company_id == supply.company_id,
                    detail.revision_id == supply.revision_id,
                ),
            ),
            unposted=True,
        ).where(
            supply.company_id == current.context.company_id,
            detail.source_invoice_id == uuid.UUID(item["source_id"]),
            line.line_key == uuid.UUID(item["line_key"]),
        )
    else:
        instruction = m.VoucherBillInstruction
        target = uuid.UUID(item["item_id"])
        statement = live(
            select(func.coalesce(func.sum(instruction.amount), 0))
            .select_from(instruction)
            .join(revision, on_revision(instruction)),
            unposted=True,
        ).where(
            instruction.company_id == current.context.company_id,
            (instruction.debt_item_id == target) | (instruction.credit_item_id == target),
        )
    if exclude is not None:
        statement = statement.where(voucher.id != exclude)
    return Decimal(await db.scalar(statement) or 0)


async def evaluate(
    db: AsyncSession,
    current: Access,
    probes: list[dict[str, Any]],
    sheet: str,
    number: int,
    *,
    exclude: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], list[rules.Issue]]:
    """Check probes against existing vouchers; consumption probes get their net remaining."""
    kept, issues = [], []
    for item in probes:
        code, text = checks.message(item)
        issue = rules.Issue(sheet, number, checks.column(item), code, text, "L6", item["severity"])
        if item["probe"] in checks.CONSUMPTION:
            used = await consumed(db, current, item, exclude)
            remaining = Decimal(item["owner_remaining"]) - used
            if Decimal(item["amount"]) > remaining:
                issues.append(issue)
            kept.append(
                item | {"remaining": format(remaining, "f"), "checked_at": utcnow().isoformat()}
            )
            continue
        if await found_identity(db, current, item, exclude):
            issues.append(issue)
        kept.append(item)
    return kept, issues


def invoice_probes(
    parsed: rules.Parsed,
    masters: dict[str, Any],
    body: dict[str, Any],
    rule: str,
    year: Callable[[dt.date], tuple[dt.date, dt.date]],
) -> list[dict[str, Any]]:
    party_id = str(masters["party"][0])
    account_id = str(masters["ledger"].source_id)
    if parsed.kind == "PURCHASE":
        assert parsed.supplier_invoice_number and parsed.supplier_invoice_date
        number = parsed.supplier_invoice_number.strip().casefold()
        start, end = year(parsed.supplier_invoice_date)
        day = parsed.supplier_invoice_date.isoformat()
        return [
            checks.probe(
                "bill",
                "error",
                rule=rule,
                party_id=party_id,
                account_id=account_id,
                number=number,
                date=day,
            ),
            checks.probe(
                "bill_year",
                "warning",
                party_id=party_id,
                start=start.isoformat(),
                end=end.isoformat(),
                number=number,
                other_than=day,
            ),
        ]
    result: list[dict[str, Any]] = []
    if parsed.kind == "SALES":
        if parsed.source_reference:
            result.append(
                checks.probe(
                    "external",
                    "error",
                    kind="SALES",
                    column="source_reference",
                    reference=parsed.source_reference.strip().casefold(),
                )
            )
        else:
            total = sum((line.amount for line in parsed.lines), start=Decimal(0))
            result.append(
                checks.probe(
                    "signature",
                    "warning",
                    kind="SALES",
                    family="invoice",
                    date=parsed.document_date.isoformat(),
                    entries=checks.signature([(account_id, "PARTY", total)]),
                )
            )
        return result
    if parsed.return_reference:
        result.append(
            checks.probe(
                "external",
                "error",
                kind=parsed.kind,
                party_id=party_id,
                column="return_reference",
                reference=parsed.return_reference.strip().casefold(),
            )
        )
    for line in parsed.lines:
        source: rules.OriginalLine = masters["original"]["lines"][line.line_no]
        result.append(
            checks.probe(
                "entitlement",
                "error",
                source_id=str(masters["original"]["source_id"]),
                line_key=str(source.line_key),
                amount=format(line.amount, "f"),
                owner_remaining=format(source.remaining, "f"),
            )
        )
    for allocation in body["invoice"].get("allocations", []):
        bill: rules.OpenBill = masters["bill"]
        result.append(
            checks.probe(
                "allocation",
                "error",
                item_id=allocation["debt"]["item_id"],
                column="original_invoice_number"
                if parsed.kind == "CREDIT_NOTE"
                else "original_bill_number",
                amount=allocation["amount"],
                owner_remaining=format(bill.remaining, "f"),
            )
        )
    return result


async def master_versions(
    db: AsyncSession, current: Access, ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Local account evidence versions (the native write checks them exactly)."""
    if not ids:
        return {}
    return {
        row.source_id: int(row.source_version)
        for row in await db.scalars(
            select(m.VoucherMasterEvidence).where(
                m.VoucherMasterEvidence.company_id == current.context.company_id,
                m.VoucherMasterEvidence.owner == "accounting",
                m.VoucherMasterEvidence.entity_type == "account",
                m.VoucherMasterEvidence.source_id.in_(ids),
            )
        )
    }


async def validate_step(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    job_id: uuid.UUID,
    *,
    lookup_owner: Owner | None,
    execution_owner: Owner | None,
    resolve: Lookup = default_lookup,
    preview: Preview = preview_owner,
) -> None:
    """Validate the next bounded chunk; the job becomes READY when nothing is left."""
    require(current, "import.manage", "create")
    tenant, company = current.actor.tenant_id, current.context.company_id
    lookup_from = owner_for(lookup_owner, tenant, company)
    if current.authority is None or current.context.finance is None:
        raise ConflictError("validation requires current financial authority")
    finance = current.context.finance
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            job = await scoped_job(db, current, job_id)
            actionable(job)
            if job.state != "VALIDATING":
                return
            start_version, rule, kind = job.row_version, job.duplicate_rule, job.kind
            rows = await job_rows(db, current, job.id, states=("STAGED",), limit=STEP)
            revision = await get(db, current, m.VoucherTypeRevision, job.type_revision_id)
            voucher_type = await get(db, current, m.VoucherType, revision.type_id)
            shape, include = await shape_for(db, current, revision, kind)
            review_context = await definition_digest(db, current)
            classes = {
                row.code.casefold(): row.id
                for row in await db.scalars(
                    select(m.VoucherClass).where(
                        m.VoucherClass.company_id == company,
                        m.VoucherClass.type_revision_id == revision.id,
                    )
                )
            }
            work = [
                (
                    row.id,
                    rules.Staged.from_stored(
                        row.import_key, row.ordinal, row.source_input, row.source_rows
                    ),
                )
                for row in rows
            ]
    invoice_family = kinds.family(kind) == "INVOICE"
    calculator = (
        owner_for(execution_owner, tenant, company, "invoice calculation")
        if invoice_family
        else None
    )
    docs: list[tuple[uuid.UUID, Any, list[rules.Issue], tuple[str, int]]] = []
    for row_id, staged in work:
        # A column denied after upload is refused, never silently dropped.
        drift = rules.unexpected(staged, shape)
        doc, issues = (None, drift) if drift else kinds.parse(kind, staged, shape)
        docs.append((row_id, doc, issues, staged.rows[0]))
    codes: dict[str, set[Any]] = {
        "party_codes": set(),
        "party_gstins": set(),
        "account_codes": set(),
    }
    for _, doc, _, _ in docs:
        if doc is None:
            continue
        if invoice_family:
            if doc.party_code:
                codes["party_codes"].add(doc.party_code)
            if doc.party_gstin:
                codes["party_gstins"].add(doc.party_gstin)
            codes["account_codes"] |= {ln.account_code for ln in doc.lines if ln.account_code}
        else:
            codes["account_codes"] |= money.ledger_codes(doc)

    async def ask(**extra: set[Any]) -> rules.Resolution:
        try:
            return await resolve(lookup_from, tenant, company, **(codes | extra))
        except (httpx.HTTPError, ValidationError, AuthenticationRequiredError) as error:
            # Retryable for the job: rows stay STAGED and the next run asks again.
            raise ConflictError("master lookup owner is unavailable; retry") from error

    found = await ask() if any(codes.values()) else None
    outcomes: dict[uuid.UUID, dict[str, Any]] = {}
    resolved: list[tuple[uuid.UUID, Any, dict[str, Any], tuple[str, int]]] = []
    for row_id, doc, issues, (sheet, number) in docs:
        if doc is None or found is None:
            outcomes[row_id] = {"state": "INVALID", "errors": issues}
            continue
        # Money ledgers resolve once their open bills are known (second lookup below).
        masters, issues = rules.resolve(doc, found, sheet, number) if invoice_family else ({}, [])
        if doc.class_code is not None:
            klass = classes.get(doc.class_code.casefold())
            if klass is None:
                issues.append(
                    rules.Issue(
                        sheet,
                        number,
                        "voucher_class_code",
                        "unknown_master",
                        "class does not exist for this voucher type",
                        "L4",
                    )
                )
            elif masters is not None:
                masters["class_id"] = klass
        if masters is None or issues:
            outcomes[row_id] = {"state": "INVALID", "errors": issues}
            continue
        resolved.append((row_id, doc, masters, (sheet, number)))
    # Second lookup: open bills and original invoices, named through resolved ledgers.
    bills: set[tuple[uuid.UUID, str]] = set()
    originals: set[tuple[str, uuid.UUID, str]] = set()
    for _, doc, masters, _ in resolved:
        if not invoice_family:
            assert found is not None
            bills |= money.bill_requests(doc, found)
        elif doc.kind in rules.NOTE_KINDS:
            ledger = masters["ledger"].source_id
            number = doc.original_number.strip().casefold()
            originals.add((rules.ORIGINAL_KIND[doc.kind], ledger, number))
            bills.add((ledger, number))
    if bills or originals:
        second = await ask(bills=bills, invoices=originals)
        assert found is not None
        found = replace(found, bills=second.bills, invoices=second.invoices)
    pending = []
    versions: dict[uuid.UUID, int] = {}
    if originals and found is not None:
        with tenant_scope(tenant):
            async with factory() as db:
                versions = await master_versions(
                    db,
                    current,
                    {
                        line.account_id
                        for sources in found.invoices.values()
                        for source in sources
                        for line in source.lines
                    },
                )
    year = fiscal_year(current)
    budget = StepBudget(STEP)
    for row_id, doc, masters, (sheet, number) in resolved:
        if not budget.take():
            break
        assert found is not None
        if not invoice_family:
            klass = masters.get("class_id")
            masters, issues = money.resolve(doc, found, profile=voucher_type.profile)
            if masters is None:
                outcomes[row_id] = {"state": "INVALID", "errors": issues}
                continue
            body = money.content(
                doc,
                masters,
                job_id=job_id,
                type_revision_id=revision.id,
                class_id=klass,
                include=include,
            )
            probes = money.probes(doc, masters)
        else:
            bill = None
            if doc.kind in rules.NOTE_KINDS:
                source, issues = rules.original(doc, masters, found, sheet, number)
                if source is None:
                    outcomes[row_id] = {"state": "INVALID", "errors": issues}
                    continue
                if any(line.account_id not in versions for line in source["lines"].values()):
                    outcomes[row_id] = {
                        "state": "INVALID",
                        "errors": [
                            rules.Issue(
                                sheet,
                                number,
                                "original_line_no",
                                "master_unavailable",
                                "original line ledgers are not yet available here; retry later",
                                "L4",
                            )
                        ],
                    }
                    continue
                masters["original"] = source
                open_bills = found.bill(masters["ledger"].source_id, doc.original_number)
                if len(open_bills) != 1:
                    # The owner adjusts a note only against its original's party bill.
                    outcomes[row_id] = {
                        "state": "INVALID",
                        "errors": [
                            rules.Issue(
                                sheet,
                                number,
                                None,
                                "original_bill_missing",
                                "the original invoice has no open party bill to adjust",
                                "L4",
                            )
                        ],
                    }
                    continue
                bill = open_bills[0]
                masters["bill"] = bill
                # What unposted drafts already allocate on the bill is not offered again.
                with tenant_scope(tenant):
                    async with factory() as db:
                        taken = await consumed(
                            db, current, {"probe": "allocation", "item_id": str(bill.item_id)}
                        )
                bill = replace(bill, remaining=bill.remaining - taken)
            body = rules.content(
                doc,
                masters,
                job_id=job_id,
                type_revision_id=revision.id,
                class_id=masters.get("class_id"),
                payment_days=finance.default_payment_terms_days,
                include=include,
                versions=versions,
                bill=bill,
            )
            probes = invoice_probes(doc, masters, body, rule, year)
        try:
            native = VoucherInput.model_validate(body)
            with tenant_scope(tenant):
                async with factory() as db:
                    transaction = await db.begin()
                    try:
                        db.info["voucher_actor"] = current.actor.user_id
                        written = await documents.write(db, current, native)
                        stored = await documents.revision_for(db, current, written)
                        digest = stored.configuration_hash
                        native_policy, _ = await effective(
                            db,
                            current,
                            revision.id,
                            date=native.document_date,
                            posting_date=native.posting_date,
                            class_id=native.class_id,
                        )
                        probes, found_issues = await evaluate(
                            db, current, probes, sheet, number, exclude=written.id
                        )
                    finally:
                        # The dry run never keeps a voucher, audit row or outbox message.
                        await transaction.rollback()
        except (ValidationError, PlatformError) as error:
            outcomes[row_id] = {"state": "INVALID", "errors": [failure(error, sheet, number)]}
            continue
        errors = [issue for issue in found_issues if issue.severity == "error"]
        if errors:
            outcomes[row_id] = {"state": "INVALID", "errors": errors}
            continue
        warnings = [issue for issue in found_issues if issue.severity == "warning"]
        outcomes[row_id] = {
            "state": "WARNING" if warnings else "VALID",
            "errors": warnings,
            "prepared": body,
            "probes": probes,
            "configuration_hash": digest,
            "currency": doc.currency,
            "declared": None,
            "payable": None if invoice_family else doc.total,
            "tax_total": None,
            "difference": None,
        }
        if invoice_family:
            pending.append(
                (
                    row_id,
                    doc,
                    body,
                    native_policy.invoice or InvoicePolicy(),
                    digest,
                    (sheet, number),
                )
            )
    for row_id, doc, body, invoice_policy, configuration, (sheet, number) in pending:
        if not budget.alive():
            outcomes.pop(row_id, None)
            continue
        assert calculator is not None
        invoice = dict(body["invoice"])
        invoice.pop("supplier_declared_total", None)
        invoice.pop("supplier_difference_reason", None)
        try:
            calculation = await preview(
                calculator,
                InvoicePreviewCommand.model_validate(
                    {
                        "tenant_id": tenant,
                        "company_id": company,
                        "actor_user_id": current.actor.user_id,
                        "authority": current.authority,
                        "kind": doc.kind,
                        "profile": "STANDARD",
                        "currency": doc.currency,
                        "document_date": doc.document_date,
                        "posting_date": doc.posting_date,
                        "invoice": invoice,
                        "policy": invoice_policy,
                        "configuration_hash": configuration,
                        "company_configuration_hash": finance.configuration_hash,
                    }
                ),
            )
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status not in {403, 409, 422}:
                raise ConflictError("invoice calculation owner is unavailable; retry") from error
            outcomes[row_id] = {
                "state": "INVALID",
                "errors": [
                    rules.Issue(
                        sheet,
                        number,
                        None,
                        "permission_denied" if status == 403 else "calculation_refused",
                        "invoice calculation was refused; verify ledgers, tax and configuration",
                        "L5",
                    )
                ],
            }
            continue
        except httpx.RequestError as error:
            raise ConflictError("invoice calculation owner is unavailable; retry") from error
        outcome = outcomes[row_id]
        outcome |= {"payable": calculation.payable, "tax_total": calculation.tax_total}
        if doc.kind != "PURCHASE":
            continue
        assert doc.declared_total is not None
        state, difference, issue = rules.control(
            doc.declared_total,
            calculation.payable,
            invoice_policy.supplier_difference_limit,
            doc.difference_reason,
            sheet=sheet,
            row=number,
        )
        outcome |= {"declared": doc.declared_total, "difference": difference}
        if state == "INVALID":
            outcomes[row_id] = {"state": "INVALID", "errors": [issue]}
        elif state == "WARNING" or outcome["state"] == "WARNING":
            outcome["state"] = "WARNING"
    require(current, "import.manage", "create")
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            db.info["voucher_actor"] = current.actor.user_id
            job = await scoped_job(db, current, job_id, lock=True)
            actionable(job)
            if await definition_digest(db, current) != review_context:
                raise ConflictError("import field configuration changed during validation; retry")
            if job.state != "VALIDATING" or job.row_version != start_version:
                return
            locked = {row.id: row for row in await job_rows(db, current, job.id, lock=True)}
            for row_id, outcome in outcomes.items():
                row = locked[row_id]
                if row.state != "STAGED":
                    continue
                row.state = outcome["state"]
                row.errors = (
                    list(row.errors)
                    + [issue.as_dict() for issue in outcome.get("errors", [])][: rules.MAX_ERRORS]
                )
                if outcome["state"] in {"VALID", "WARNING"}:
                    row.prepared_input = {
                        "content": outcome["prepared"],
                        "probes": outcome["probes"],
                        "review_context": review_context,
                    }
                    row.configuration_hash = outcome["configuration_hash"]
                    row.currency = outcome["currency"]
                    row.declared_total = outcome["declared"]
                    row.computed_payable = outcome["payable"]
                    row.computed_tax_total = outcome["tax_total"]
                    row.supplier_difference = outcome["difference"]
                row.row_version += 1
            if not any(row.state == "STAGED" for row in locked.values()):
                finish_validation(job, list(locked.values()))
                job_audit(db, current, job, "validated")
            if job.state == "READY":
                await journal.checkpoint(db, current, job, list(locked.values()), finish=True)
            job.row_version += 1


def fiscal_year(current: Access) -> Callable[[dt.date], tuple[dt.date, dt.date]]:
    finance = current.context.finance
    assert finance is not None

    def bounds(day: dt.date) -> tuple[dt.date, dt.date]:
        start = fiscal_start(day, finance.fiscal_year_start_month, finance.fiscal_year_start_day)
        following = fiscal_start(
            start.replace(year=start.year + 1),
            finance.fiscal_year_start_month,
            finance.fiscal_year_start_day,
        )
        return start, following - dt.timedelta(days=1)

    return bounds


def finish_validation(job: im.VoucherImportJob, rows: list[im.VoucherImportRow]) -> None:
    """Collisions inside the job: a repeated identity or a balance consumed twice."""
    ordered = sorted(rows, key=lambda item: item.ordinal)
    selected = [row for row in ordered if row.state in {"VALID", "WARNING"}]
    collisions = checks.within(
        (row.import_key, (row.prepared_input or {}).get("probes", [])) for row in selected
    )
    for row in selected:
        for item, earlier in collisions.get(row.import_key, []):
            sheet, number = row.source_rows[0]
            code, text = checks.message(item)
            if earlier:
                text = f"repeats {earlier} in this file: {text}"
            issue = rules.Issue(
                sheet, number, checks.column(item), code, text, "L6", item["severity"]
            )
            row.errors = [*row.errors, issue.as_dict()]
            if item["severity"] == "error":
                row.state = "INVALID"
                row.prepared_input = None
            elif row.state == "VALID":
                row.state = "WARNING"
            row.row_version += 1
    count(job, rows)
    job.state = "READY"
    job.selection_digest = selection_digest(
        {
            "job": str(job.id),
            "type_revision_id": str(job.type_revision_id),
            "input_sha256": job.input_sha256,
            "duplicate_rule": job.duplicate_rule,
            "vouchers": [
                [
                    row.import_key,
                    row.state,
                    row.configuration_hash,
                    hashlib.sha256(canonical_json(row.prepared_input)).hexdigest()
                    if row.prepared_input is not None
                    else None,
                    money_text(row.computed_payable),
                ]
                for row in ordered
            ],
        }
    )


async def commit_step(
    factory: async_sessionmaker[AsyncSession], current: Access, job_id: uuid.UUID
) -> None:
    """Create the next bounded chunk of drafts, each in its own native transaction."""
    require(current, "import.commit", "create")
    tenant = current.actor.tenant_id
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            job = await scoped_job(db, current, job_id)
            actionable(job)
            if job.state != "COMMITTING":
                return
            on_error = job.on_error
            selected = [
                (
                    row.id,
                    row.import_key,
                    dict(row.prepared_input or {}),
                    row.configuration_hash,
                    row.source_rows[0],
                )
                for row in await job_rows(
                    db, current, job.id, states=("VALID", "WARNING"), limit=STEP
                )
            ]
    stop = False
    budget = StepBudget(STEP)
    for row_id, key, prepared, configuration, (sheet, number) in selected:
        if not budget.take():
            break
        error: rules.Issue | None = None
        try:
            await create_draft(
                factory, current, job_id, row_id, key, prepared, configuration, (sheet, number)
            )
        except IdempotencyConflictError as exc:
            error = rules.Issue(sheet, number, None, "conflict", exc.message, "L5")
        except DraftRefusedError as exc:
            error = exc.issue
        except ConflictError as exc:
            if exc.message.startswith(TRANSIENT):
                # Contention, not a verdict on the voucher: it stays selected for the next run.
                break
            error = failure(exc, sheet, number)
        except (ValidationError, PlatformError) as exc:
            error = failure(exc, sheet, number)
        if error is not None:
            await record_failure(factory, current, job_id, row_id, error)
            if on_error == "STOP":
                stop = True
                break
    with tenant_scope(tenant):
        async with factory() as db, db.begin():
            db.info["voucher_actor"] = current.actor.user_id
            job = await scoped_job(db, current, job_id, lock=True)
            rows = await job_rows(db, current, job.id, lock=True)
            if job.state != "COMMITTING":
                # Cancelled meanwhile: keep the counts true to the drafts this step created.
                if job.state == "CANCELLED":
                    count(job, rows)
                    job.row_version += 1
                return
            remaining = [row for row in rows if row.state in {"VALID", "WARNING"}]
            if stop:
                for row in remaining:
                    row.state = "BLOCKED"
                    row.row_version += 1
                remaining = []
            count(job, rows)
            if not remaining:
                if not job.failed_count and not any(row.state == "BLOCKED" for row in rows):
                    job.state = "SUCCEEDED"
                elif job.created_count:
                    job.state = "PARTIAL"
                else:
                    job.state = "FAILED"
                job_audit(db, current, job, "complete")
            await journal.checkpoint(db, current, job, rows, finish=not remaining)
            job.row_version += 1


class DraftRefusedError(ConflictError):
    """A commit-time duplicate or over-consumption; carries the row's safe issue."""

    def __init__(self, issue: rules.Issue) -> None:
        super().__init__(issue.message)
        self.issue = issue


async def create_draft(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    job_id: uuid.UUID,
    row_id: uuid.UUID,
    key: str,
    prepared: dict[str, Any],
    configuration: str | None,
    position: tuple[str, int] = ("vouchers", 1),
) -> None:
    """The native create command; its receipt, effect and row state commit together.

    Duplicate and consumption probes run again after the write, under the company voucher
    lock, so two jobs (or a user typing the same voucher) cannot both get through.
    """
    if not prepared.get("content"):
        raise ConflictError("import prepared data is unavailable; validate again")
    native = VoucherInput.model_validate(prepared["content"])
    probes: list[dict[str, Any]] = prepared.get("probes", [])

    async def mutate(db: AsyncSession) -> CommandReceipt:
        job = await scoped_job(db, current, job_id, lock=True)
        actionable(job)
        if job.state != "COMMITTING":
            raise ConflictError("import is no longer committing")
        if prepared.get("review_context") != await definition_digest(db, current):
            raise ConflictError(
                "import field configuration changed since validation; validate again"
            )
        row = await get(db, current, im.VoucherImportRow, row_id, lock=True)
        if row.job_id != job_id or row.state not in {"VALID", "WARNING"}:
            raise ConflictError("import voucher is no longer selected")
        voucher = await documents.write(db, current, native)
        await db.flush()
        revision = await documents.revision_for(db, current, voucher)
        if revision.configuration_hash != configuration:
            raise ConflictError("voucher configuration changed since validation; validate again")
        for item in probes:
            if item["severity"] != "error":
                continue
            code, text = checks.message(item)
            issue = rules.Issue(*position, checks.column(item), code, text, "L6")
            if item["probe"] in checks.CONSUMPTION:
                checked = dt.datetime.fromisoformat(item["checked_at"])
                if utcnow() - checked > BALANCE_TTL:
                    # The owner's balance may have moved since; posting rechecks, but a stale
                    # snapshot is no basis for a new draft.
                    raise DraftRefusedError(
                        rules.Issue(
                            *position,
                            checks.column(item),
                            "revalidate",
                            "the balance was checked over an hour ago; validate again",
                            "L6",
                        )
                    )
                # Includes this draft and the job's earlier drafts; posted use is the owner's.
                if await consumed(db, current, item) > Decimal(item["owner_remaining"]):
                    raise DraftRefusedError(issue)
            elif await found_identity(db, current, item, voucher.id):
                raise DraftRefusedError(issue)
        db.add(
            new(
                im.VoucherImportEffect,
                current,
                job_id=job_id,
                import_key=key,
                voucher_id=voucher.id,
                revision_id=revision.id,
            )
        )
        row.state = "CREATED"
        row.voucher_id = voucher.id
        row.row_version += 1
        await journal.checkpoint(db, current, job, [row])
        return CommandReceipt(201, {"id": str(voucher.id)})

    async def render(db: AsyncSession, refs: dict[str, Any]) -> dict[str, Any]:
        return refs

    await command(
        factory,
        current,
        "create",
        f"voucher-import:{job_id}:{key}",
        native,
        mutate,
        render,
    )


async def record_failure(
    factory: async_sessionmaker[AsyncSession],
    current: Access,
    job_id: uuid.UUID,
    row_id: uuid.UUID,
    issue: rules.Issue,
) -> None:
    with tenant_scope(current.actor.tenant_id):
        async with factory() as db, db.begin():
            db.info["voucher_actor"] = current.actor.user_id
            job = await scoped_job(db, current, job_id, lock=True)
            if job.state != "COMMITTING":
                return
            row = await get(db, current, im.VoucherImportRow, row_id, lock=True)
            if row.job_id == job_id and row.state in {"VALID", "WARNING"}:
                row.state = "FAILED"
                row.errors = [*row.errors, issue.as_dict()][-rules.MAX_ERRORS :]
                row.row_version += 1
                await journal.checkpoint(db, current, job, [row])


def money_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def job_view(job: im.VoucherImportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "revision": job.revision,
        "company_id": job.company_id,
        "row_version": job.row_version,
        "kind": job.kind,
        "type_id": job.type_id,
        "type_revision_id": job.type_revision_id,
        "source_format": job.source_format,
        "state": job.state,
        "on_error": job.on_error,
        "duplicate_rule": job.duplicate_rule,
        "input_sha256": job.input_sha256,
        "selection_digest": job.selection_digest,
        "voucher_count": job.voucher_count,
        "valid_count": job.valid_count,
        "warning_count": job.warning_count,
        "invalid_count": job.invalid_count,
        "created_count": job.created_count,
        "failed_count": job.failed_count,
        "created_at": job.created_at,
        "expires_at": job.expires_at,
    }


def masked(current: Access) -> bool:
    """A read-deny on invoice content hides amounts and cells here too (field policy §6)."""
    fields = set(CONTENT_FIELDS) | {
        str(policy.get("field_key", "")).removeprefix("custom_field:")
        for policy in current.context.policies
        if policy.get("entity_type") == "vouchers.voucher"
    }
    return bool(denied(current, "vouchers.voucher", fields, "read"))


def row_view(row: im.VoucherImportRow, *, detail: bool, owner: bool, hide: bool) -> dict[str, Any]:
    def amount(value: Decimal | None) -> str | None:
        return None if hide else money_text(value)

    result: dict[str, Any] = {
        "id": row.id,
        "import_key": row.import_key,
        "ordinal": row.ordinal,
        "state": row.state,
        "error_count": len(row.errors) if detail else row.error_count,
        "currency": None if hide else row.currency,
        "declared_total": amount(row.declared_total),
        "computed_payable": amount(row.computed_payable),
        "supplier_difference": amount(row.supplier_difference),
        "voucher_id": row.voucher_id,
        "row_version": row.row_version,
    }
    if detail:
        result |= {
            "errors": row.errors,
            "source_rows": row.source_rows,
            "computed_tax_total": amount(row.computed_tax_total),
        }
        if owner and not hide:
            result["source_input"] = row.source_input
    return result


async def readable_job(db: AsyncSession, current: Access, job_id: uuid.UUID) -> im.VoucherImportJob:
    """The uploader reads their job; other readers need durable-work inspection authority."""
    require(current, "import.read")
    job = await scoped_job(db, current, job_id, owner=False)
    if job.actor_user_id != current.actor.user_id:
        require(current, "operation.read")
    return job


async def job_detail(db: AsyncSession, current: Access, job_id: uuid.UUID) -> dict[str, Any]:
    job = await readable_job(db, current, job_id)
    return job_view(job) | {"own": job.actor_user_id == current.actor.user_id}


def cursor_codec(secret: bytes, current: Access, scope: str) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"vouchers.import.cursor.v1", "sha256"),
        context=f"voucher-import:{scope}:{fingerprint(current)}",
    )


def after(codec: CursorCodec, cursor: str | None) -> Any:
    if cursor is None:
        return None
    try:
        return codec.decode(cursor)["after"]
    except (KeyError, TypeError) as error:
        raise ValidationFailedError("invalid or expired cursor") from error


LIST_FIELDS = frozenset(
    {
        "id",
        "row_version",
        "kind",
        "source_format",
        "state",
        "voucher_count",
        "valid_count",
        "warning_count",
        "invalid_count",
        "created_count",
        "failed_count",
        "created_at",
    }
)


async def job_page(
    db: AsyncSession,
    current: Access,
    secret: bytes,
    *,
    limit: int,
    cursor: str | None,
    state: str | None,
    mine: bool,
) -> dict[str, Any]:
    require(current, "import.read")
    if not mine:
        require(current, "operation.read")
    codec = cursor_codec(secret, current, f"jobs:{state}:{mine}")
    statement = select(im.VoucherImportJob).where(
        im.VoucherImportJob.company_id == current.context.company_id
    )
    if mine:
        statement = statement.where(im.VoucherImportJob.actor_user_id == current.actor.user_id)
    if state is not None:
        statement = statement.where(im.VoucherImportJob.state == state)
    if (start := after(codec, cursor)) is not None:
        statement = statement.where(im.VoucherImportJob.id < uuid.UUID(str(start)))
    rows = list(
        await db.scalars(statement.order_by(im.VoucherImportJob.id.desc()).limit(limit + 1))
    )
    page = rows[:limit]
    return {
        "items": [
            {key: value for key, value in job_view(row).items() if key in LIST_FIELDS}
            | {"own": row.actor_user_id == current.actor.user_id}
            for row in page
        ],
        "next_cursor": codec.encode({"after": str(page[-1].id)}) if len(rows) > limit else None,
    }


async def row_page(
    db: AsyncSession,
    current: Access,
    secret: bytes,
    job_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None,
    state: str | None,
) -> dict[str, Any]:
    job = await readable_job(db, current, job_id)
    codec = cursor_codec(secret, current, f"rows:{job.id}:{state}")
    statement = (
        select(im.VoucherImportRow)
        .options(
            load_only(
                im.VoucherImportRow.id,
                im.VoucherImportRow.import_key,
                im.VoucherImportRow.ordinal,
                im.VoucherImportRow.state,
                im.VoucherImportRow.error_count,
                im.VoucherImportRow.currency,
                im.VoucherImportRow.declared_total,
                im.VoucherImportRow.computed_payable,
                im.VoucherImportRow.supplier_difference,
                im.VoucherImportRow.voucher_id,
                im.VoucherImportRow.row_version,
            )
        )
        .where(
            im.VoucherImportRow.company_id == current.context.company_id,
            im.VoucherImportRow.job_id == job.id,
        )
    )
    if state is not None:
        statement = statement.where(im.VoucherImportRow.state == state)
    if (start := after(codec, cursor)) is not None:
        statement = statement.where(im.VoucherImportRow.ordinal > int(start))
    rows = list(await db.scalars(statement.order_by(im.VoucherImportRow.ordinal).limit(limit + 1)))
    page, hide = rows[:limit], masked(current)
    return {
        "items": [row_view(row, detail=False, owner=False, hide=hide) for row in page],
        "next_cursor": codec.encode({"after": page[-1].ordinal}) if len(rows) > limit else None,
    }


async def row_detail(
    db: AsyncSession, current: Access, job_id: uuid.UUID, import_key: str
) -> dict[str, Any]:
    job = await readable_job(db, current, job_id)
    row = await db.scalar(
        select(im.VoucherImportRow).where(
            im.VoucherImportRow.company_id == current.context.company_id,
            im.VoucherImportRow.job_id == job.id,
            im.VoucherImportRow.import_key == import_key,
        )
    )
    if row is None:
        raise NotFoundError("import voucher not found")
    return row_view(
        row, detail=True, owner=job.actor_user_id == current.actor.user_id, hide=masked(current)
    )


def report_codec(secret: bytes, current: Access, job: im.VoucherImportJob) -> CursorCodec:
    return CursorCodec(
        hmac.digest(secret, b"vouchers.import.report.v1", "sha256"),
        context=f"voucher-import-report:{current.actor.tenant_id}:{current.context.company_id}:"
        f"{current.actor.user_id}:{job.id}",
        ttl_seconds=REPORT_TTL,
    )


REPORT_COLUMNS = [
    "import_key",
    "state",
    "sheet",
    "row",
    "column",
    "error_code",
    "message",
    "party",
    "document_reference",
    "currency",
    "declared_total",
    "computed_amount",
    "difference",
    "voucher_id",
]
PARTY_CELLS = ("supplier_code", "supplier_gstin", "customer_code", "customer_gstin")
REFERENCE_CELLS = (
    "supplier_invoice_number",
    "source_reference",
    "original_invoice_number",
    "original_bill_number",
    "return_reference",
)


async def report_rows(
    db: AsyncSession, current: Access, job: im.VoucherImportJob
) -> list[list[str]]:
    hide = masked(current)
    result: list[list[str]] = []
    for row in await job_rows(db, current, job.id):
        header = {} if hide else row.source_input.get("header", {})
        sheet, number = row.source_rows[0]
        common = [
            next((header[name] for name in PARTY_CELLS if header.get(name)), ""),
            next((header[name] for name in REFERENCE_CELLS if header.get(name)), ""),
            row.currency or header.get("currency", ""),
            ("" if hide else money_text(row.declared_total))
            or header.get("supplier_declared_total", ""),
            ("" if hide else money_text(row.computed_payable)) or "",
            ("" if hide else money_text(row.supplier_difference)) or "",
            str(row.voucher_id or ""),
        ]
        for error in row.errors or [{}]:
            result.append(
                [
                    row.import_key,
                    row.state,
                    str(error.get("sheet", sheet)),
                    str(error.get("row", number)),
                    str(error.get("column") or ""),
                    str(error.get("code", "")),
                    str(error.get("message", "")),
                    *common,
                ]
            )
    return result


async def expire(db: AsyncSession, current: Access) -> None:
    """Compatibility sweep; scheduled maintenance is available without a new upload."""
    from vouchers.tasks.import_cleanup import sweep

    await sweep(db, current.actor.tenant_id, current.context.company_id, limit=50, now=utcnow())


def actionable(job: im.VoucherImportJob) -> None:
    if job.expires_at <= utcnow() or job.state == "EXPIRED":
        raise ConflictError("import job has expired; upload the file again")


async def definition_digest(db: AsyncSession, current: Access) -> str:
    definitions = list(
        await db.execute(
            select(
                m.VoucherDefinitionProjection.entity_type,
                m.VoucherDefinitionProjection.field_key,
                m.VoucherDefinitionProjection.content_hash,
            )
            .where(m.VoucherDefinitionProjection.company_id == current.context.company_id)
            .order_by(
                m.VoucherDefinitionProjection.entity_type, m.VoucherDefinitionProjection.field_key
            )
        )
    )
    return selection_digest(
        {
            "definitions": [list(row) for row in definitions],
            "policies": list(current.context.policies),
            "layouts": list(current.context.layouts),
            "features": sorted(current.context.features),
            "currency": current.context.base_currency,
        }
    )
