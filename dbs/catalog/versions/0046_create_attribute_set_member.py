"""Create attribute_set_member; one atomic DDL with its paired model."""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_CREATE = """
CREATE TABLE attribute_set_member (
    company_id BINARY(16) NOT NULL,
    revision_id BINARY(16) NOT NULL,
    definition_id BINARY(16) NOT NULL,
    position INTEGER NOT NULL,
    is_required BOOL NOT NULL,
    allow_variant_axis BOOL NOT NULL,
    id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    created_by BINARY(16) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by BINARY(16) NULL,
    CONSTRAINT ck_attribute_set_member_attribute_set_member_flags CHECK (is_required IN (0,1) AND
        allow_variant_axis IN (0,1)),
    CONSTRAINT ck_attribute_set_member_attribute_set_member_position CHECK (position >= 0 AND
        position < 128),
    CONSTRAINT fk_attribute_set_member_definition FOREIGN KEY(tenant_id, company_id, definition_id)
        REFERENCES attribute_definition (tenant_id, company_id, id),
    CONSTRAINT fk_attribute_set_member_revision FOREIGN KEY(tenant_id, company_id, revision_id)
        REFERENCES attribute_set_revision (tenant_id, company_id, id),
    CONSTRAINT pk_attribute_set_member PRIMARY KEY (id),
    CONSTRAINT uq_attribute_set_member_definition UNIQUE (tenant_id, company_id, revision_id,
        definition_id),
    CONSTRAINT uq_attribute_set_member_position UNIQUE (tenant_id, company_id, revision_id,
        position),
    KEY ix_attribute_set_member_definition (tenant_id, company_id, definition_id),
    KEY ix_attribute_set_member_tenant_id (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE attribute_set_member")
