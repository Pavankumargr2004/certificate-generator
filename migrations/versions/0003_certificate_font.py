"""Persist certificate font selection for each generation job."""
from alembic import op
import sqlalchemy as sa

revision = "0003_certificate_font"
down_revision = "0002_templates_editor"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generation_jobs", sa.Column("font_family", sa.String(16), nullable=False,
                                                  server_default="serif"))
    with op.batch_alter_table("generation_jobs") as batch:
        batch.alter_column("font_family", server_default=None)


def downgrade():
    op.drop_column("generation_jobs", "font_family")
