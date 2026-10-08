"""Add optional certificate email delivery state."""
from alembic import op
import sqlalchemy as sa

revision = "0005_email_delivery"
down_revision = "0004_user_accounts"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("send_email", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.alter_column("send_email", server_default=None)
    with op.batch_alter_table("certificates") as batch:
        batch.add_column(sa.Column("email_status", sa.String(16), nullable=False,
                                   server_default="not_requested"))
        batch.add_column(sa.Column("email_error", sa.Text(), nullable=True))
        batch.alter_column("email_status", server_default=None)


def downgrade():
    with op.batch_alter_table("certificates") as batch:
        batch.drop_column("email_error")
        batch.drop_column("email_status")
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_column("send_email")
