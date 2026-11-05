"""Retain the exact purpose assignment selected during planning."""
from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE notification_delivery
        ADD COLUMN use_case_binding_id BINARY(16) NULL,
        ADD CONSTRAINT fk_notification_delivery_assignment FOREIGN KEY (use_case_binding_id)
            REFERENCES notification_use_case_binding (id),
        ADD CONSTRAINT fk_notification_delivery_use_case_binding_id_space
            FOREIGN KEY (use_case_binding_id, tenant_id, space_id)
            REFERENCES notification_use_case_binding (id, tenant_id, space_id)
    """)


def downgrade() -> None:
    op.execute("""ALTER TABLE notification_delivery
        DROP FOREIGN KEY fk_notification_delivery_use_case_binding_id_space,
        DROP FOREIGN KEY fk_notification_delivery_assignment,
        DROP COLUMN use_case_binding_id
    """)
