"""Persist template selection and certificate editor options."""
from alembic import op
import sqlalchemy as sa

revision = "0002_templates_editor"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "certificate_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("background_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("generation_jobs", sa.Column("design", sa.String(32), nullable=False,
                                                 server_default="classic"))
    op.add_column("generation_jobs", sa.Column("template_id", sa.String(36), nullable=True))
    with op.batch_alter_table("generation_jobs") as batch:
        batch.create_foreign_key("fk_generation_jobs_template_id", "certificate_templates",
                                 ["template_id"], ["id"])
    op.add_column("generation_jobs", sa.Column("title_text", sa.String(120), nullable=False,
                                                 server_default="CERTIFICATE OF COMPLETION"))
    op.add_column("generation_jobs", sa.Column("accent_color", sa.String(7), nullable=False,
                                                 server_default="#B28B3D"))
    op.add_column("generation_jobs", sa.Column("signatory", sa.String(120), nullable=False,
                                                 server_default=""))
    with op.batch_alter_table("generation_jobs") as batch:
        batch.alter_column("design", server_default=None)
        batch.alter_column("title_text", server_default=None)
        batch.alter_column("accent_color", server_default=None)
        batch.alter_column("signatory", server_default=None)


def downgrade():
    op.drop_column("generation_jobs", "signatory")
    op.drop_column("generation_jobs", "accent_color")
    op.drop_column("generation_jobs", "title_text")
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_constraint("fk_generation_jobs_template_id", type_="foreignkey")
    op.drop_column("generation_jobs", "template_id")
    op.drop_column("generation_jobs", "design")
    op.drop_table("certificate_templates")
