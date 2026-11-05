"""Catalog-owned custom_field_value_index; one DDL, no source definitions."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE custom_field_value_index (
    company_id BINARY(16) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    entity_id BINARY(16) NOT NULL, 
    field_key VARCHAR(64) NOT NULL, 
    generation BIGINT NOT NULL, 
    value_text VARCHAR(512) COLLATE utf8mb4_bin NULL, 
    value_number NUMERIC(19,4) NULL, 
    value_date DATE NULL, 
    value_datetime_at DATETIME(6) NULL, 
    value_bool BOOL NULL, 
    currency VARCHAR(3) NULL, 
    id BINARY(16) NOT NULL, 
    tenant_id BINARY(16) NOT NULL, 
    CONSTRAINT pk_custom_field_value_index PRIMARY KEY (id), 
        CONSTRAINT uq_custom_field_index_owner UNIQUE (tenant_id, company_id, entity_type,
        entity_id, field_key, generation),
    CONSTRAINT ck_custom_field_value_index_custom_index_generation CHECK (generation >= 1), 
        CONSTRAINT ck_custom_field_value_index_custom_index_one_value CHECK ((value_text IS NOT
        NULL) + (value_number IS NOT NULL) + (value_date IS NOT NULL) + (value_datetime_at IS
        NOT NULL) + (value_bool IS NOT NULL) = 1),
        CONSTRAINT ck_custom_field_value_index_custom_index_currency CHECK (currency IS NULL OR
        value_number IS NOT NULL),
    KEY ix_custom_field_value_index_tenant_id (tenant_id),
        KEY ix_custom_index_bool (tenant_id, company_id, entity_type, field_key, generation,
        value_bool, entity_id),
        KEY ix_custom_index_date (tenant_id, company_id, entity_type, field_key, generation,
        value_date, entity_id),
        KEY ix_custom_index_number (tenant_id, company_id, entity_type, field_key, generation,
        value_number, entity_id),
        KEY ix_custom_index_text (tenant_id, company_id, entity_type, field_key, generation,
        value_text, entity_id),
        KEY ix_custom_index_time (tenant_id, company_id, entity_type, field_key, generation,
        value_datetime_at, entity_id)
)ROW_FORMAT=DYNAMIC CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE custom_field_value_index")
