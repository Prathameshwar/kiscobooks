"""Schema conventions, the migration contract, and the publisher's wiring.

These are the checks that keep the service inside the platform's rules rather than inside
its own: table names and column types (CLAUDE.md §4), the migration head the readiness
probe asserts, and a publisher whose key is minted from the declared event set.
"""

from __future__ import annotations

import pathlib
import uuid
from decimal import Decimal

import pytest
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from pydantic import SecretStr
from sqlalchemy import Numeric, String

from design.events.audit_contract import AUDIT_EVENTS
from design.metadata import MIGRATION_HEAD, TABLES, service_metadata
from design.models.template import (
    InvoiceRenderSnapshot,
    InvoiceTemplate,
    InvoiceTemplateAsset,
    InvoiceTemplateAssignment,
    InvoiceTemplateComponent,
    InvoiceTemplateVersion,
)
from design.tasks.assets import storage_path
from design.tasks.audit_publisher import AuditPublisherSettings, configuration

MODELS = (
    InvoiceTemplate,
    InvoiceTemplateVersion,
    InvoiceTemplateAssignment,
    InvoiceTemplateAsset,
    InvoiceTemplateComponent,
    InvoiceRenderSnapshot,
)


def test_table_names_are_singular_and_registered() -> None:
    for model in MODELS:
        name = table_of(model).name
        assert not name.endswith("s"), name
        assert name in TABLES, name
    assert "outbox" in TABLES


def test_metadata_covers_exactly_this_service() -> None:
    assert set(service_metadata().tables) == TABLES


def test_measurements_store_four_decimals() -> None:
    """Never narrowed per column: MySQL re-scales a smaller scale silently."""
    columns = table_of(InvoiceTemplate).columns
    for name in ("page_width_mm", "page_height_mm"):
        kind = columns[name].type
        assert isinstance(kind, Numeric)
        assert (kind.precision, kind.scale) == (19, 4)


def test_one_lifecycle_mechanism_per_entity() -> None:
    """Rule 4.12: ``status`` or ``is_active``, never both."""
    for model in MODELS:
        names = set(table_of(model).columns.keys())
        assert not ({"status", "is_active"} <= names), table_of(model).name
        assert "is_deleted" not in names, table_of(model).name
    assert "status" in table_of(InvoiceTemplate).columns
    assert "is_active" in table_of(InvoiceTemplateAssignment).columns
    # A version's liveness is a date, not a flag.
    assert "published_at" in table_of(InvoiceTemplateVersion).columns
    assert "is_locked" not in table_of(InvoiceTemplateVersion).columns


def test_status_vocabulary_matches_the_generated_column_and_the_domain() -> None:
    from design.models.template import TEMPLATE_STATUSES

    assert TEMPLATE_STATUSES == ("DRAFT", "PUBLISHED", "ARCHIVED")
    computed = table_of(InvoiceTemplate).columns["live_code"].computed
    assert computed is not None
    assert "ARCHIVED" in str(computed.sqltext)


def test_no_compiled_document_body_is_stored() -> None:
    columns = set(table_of(InvoiceTemplateVersion).columns.keys())
    assert "compiled_html_template" not in columns
    assert "compiled_css" not in columns


def test_assets_store_no_public_url() -> None:
    """Downloads are signed and expiring; a public URL column invites the opposite."""
    assert "public_url" not in table_of(InvoiceTemplateAsset).columns


def test_digest_columns_are_fixed_width() -> None:
    for model, column in (
        (InvoiceTemplateVersion, "layout_digest"),
        (InvoiceTemplateAsset, "content_digest"),
        (InvoiceRenderSnapshot, "checksum_sha256"),
    ):
        kind = table_of(model).columns[column].type
        assert isinstance(kind, String)
        assert kind.length == 64


def test_print_evidence_parents_are_restricted() -> None:
    """Invariant 12: a version a document printed from is never removable."""
    keys = {key.column.table.name: key for key in table_of(InvoiceRenderSnapshot).foreign_keys}
    assert keys["invoice_template"].ondelete == "RESTRICT"
    assert keys["invoice_template_version"].ondelete == "RESTRICT"


def test_migration_head_matches_the_revision_tree() -> None:
    versions = pathlib.Path(__file__).resolve().parents[3] / "dbs" / "design" / "versions"
    revisions = sorted(path.name.split("_", 1)[0] for path in versions.glob("[0-9]*.py"))
    assert revisions[-1] == MIGRATION_HEAD
    assert revisions == [f"{index:04d}" for index in range(1, len(revisions) + 1)]


def test_every_revision_has_a_downgrade() -> None:
    versions = pathlib.Path(__file__).resolve().parents[3] / "dbs" / "design" / "versions"
    for path in versions.glob("[0-9]*.py"):
        body = path.read_text(encoding="utf-8")
        assert "def downgrade() -> None:" in body, path.name
        assert "pass" not in body.split("def downgrade() -> None:")[1], path.name


def test_publisher_key_is_minted_from_the_declared_events() -> None:
    settings = AuditPublisherSettings(
        database_url="mysql+asyncmy://localhost/design",
        audit_broker_url=SecretStr("amqp://localhost"),
        audit_broker_user="design-publisher",
        audit_event_secret=SecretStr("x" * 32),
    )
    config = configuration(settings)
    assert config.key.operations == AUDIT_EVENTS
    assert (config.key.issuer, config.key.audience) == ("design", "audit")
    assert config.exchange == "platform.audit"
    assert all(event.startswith("design.") for event in config.key.operations)


def test_asset_paths_are_scoped_and_refuse_unknown_media() -> None:
    tenant, company, asset = uuid7(), uuid7(), uuid7()
    path = storage_path(
        prefix="design",
        tenant_id=tenant,
        company_id=company,
        asset_id=asset,
        mime_type="image/png",
    )
    assert path == f"design/assets/{tenant}/{company}/{asset}.png"
    with pytest.raises(Exception, match="unsupported asset media type"):
        storage_path(
            prefix="design",
            tenant_id=tenant,
            company_id=company,
            asset_id=asset,
            mime_type="application/x-msdownload",
        )


def test_layout_digest_is_pure_and_order_independent() -> None:
    from design.schemas.canvas import CANVAS
    from design.tasks.templates import layout_digest

    one = CANVAS.validate_python(
        {"schema_version": "1.0.0", "sections": [{"id": "a", "type": "HEADER"}]}
    )
    again = CANVAS.validate_python(
        {"sections": [{"type": "HEADER", "id": "a"}], "schema_version": "1.0.0"}
    )
    assert layout_digest(one) == layout_digest(again)
    assert len(layout_digest(one)) == 64


def test_measure_decimal_type_is_used_by_the_schema() -> None:
    from design.schemas.templates import TemplateCreate

    created = TemplateCreate.model_validate(
        {
            "name": "t",
            "code": "t",
            "paper_size": "CUSTOM",
            "page_width_mm": "80.5",
            "page_height_mm": "200",
        }
    )
    assert isinstance(created.page_width_mm, Decimal)


def test_scope_sentinel_is_refused_as_a_company() -> None:
    from billing_platform.errors import ValidationFailedError

    from design.api.authorization import company_scope

    with pytest.raises(ValidationFailedError):
        company_scope(uuid.UUID(int=0))
    subject = uuid7()
    assert company_scope(subject) == subject
