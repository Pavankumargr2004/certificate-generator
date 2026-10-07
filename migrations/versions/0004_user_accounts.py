"""Add dynamic user accounts and ownership for batches and templates."""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_accounts"
down_revision = "0003_certificate_font"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("owner_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_generation_jobs_owner_user_id", "users", ["owner_user_id"], ["id"])
        batch.create_index("ix_generation_jobs_owner_user_id", ["owner_user_id"])
    with op.batch_alter_table("certificate_templates") as batch:
        batch.add_column(sa.Column("owner_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_certificate_templates_owner_user_id", "users", ["owner_user_id"], ["id"])
        batch.create_index("ix_certificate_templates_owner_user_id", ["owner_user_id"])


def downgrade():
    with op.batch_alter_table("certificate_templates") as batch:
        batch.drop_index("ix_certificate_templates_owner_user_id")
        batch.drop_constraint("fk_certificate_templates_owner_user_id", type_="foreignkey")
        batch.drop_column("owner_user_id")
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_index("ix_generation_jobs_owner_user_id")
        batch.drop_constraint("fk_generation_jobs_owner_user_id", type_="foreignkey")
        batch.drop_column("owner_user_id")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
