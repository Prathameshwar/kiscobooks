"""Keep shared import state storage compatible; one reversible ALTER."""

import sqlalchemy as sa
from alembic import op

revision = "0233"
down_revision = "0232"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE import_job DROP CHECK ck_import_job_import_job_state, "
        "ADD CONSTRAINT ck_import_job_import_job_state CHECK (state IN ("
        "'STAGED','READY','INVALID','SUCCEEDED',"
        "'PARTIAL','FAILED','CANCELLED','EXPIRED','VALIDATING','IMPORTING'))"
    )


def downgrade() -> None:
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM import_job WHERE state IN ('VALIDATING','IMPORTING')")
    ):
        raise RuntimeError(
            "Import continuation rollback requires online validation and no pending work"
        )
    op.execute(
        "ALTER TABLE import_job DROP CHECK ck_import_job_import_job_state, "
        "ADD CONSTRAINT ck_import_job_import_job_state CHECK (state IN ("
        "'STAGED','READY','INVALID','SUCCEEDED',"
        "'PARTIAL','FAILED','CANCELLED','EXPIRED'))"
    )
