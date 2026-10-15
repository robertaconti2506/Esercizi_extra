"""Utenti, sessioni di login e tentativi falliti

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "utenti",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("creato_il", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sessioni",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "utente_id",
            sa.Integer(),
            sa.ForeignKey("utenti.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scade_il", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessioni_scade_il", "sessioni", ["scade_il"])

    op.create_table(
        "tentativi_login",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("avvenuto_il", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tentativi_login_email_data", "tentativi_login", ["email", "avvenuto_il"])

    # Gli articoli nuovi saranno collegati a chi li ha scritti.
    # Quelli esistenti restano senza collegamento (NULL), con la loro firma testuale.
    op.add_column(
        "articoli",
        sa.Column(
            "autore_id",
            sa.Integer(),
            sa.ForeignKey("utenti.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("articoli", "autore_id")
    op.drop_index("ix_tentativi_login_email_data", table_name="tentativi_login")
    op.drop_table("tentativi_login")
    op.drop_index("ix_sessioni_scade_il", table_name="sessioni")
    op.drop_table("sessioni")
    op.drop_table("utenti")
