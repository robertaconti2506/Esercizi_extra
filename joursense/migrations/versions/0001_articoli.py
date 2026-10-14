"""Tabella articoli, con un primo articolo di benvenuto

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    articoli = op.create_table(
        "articoli",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titolo", sa.String(200), nullable=False),
        sa.Column("sommario", sa.String(400), nullable=False),
        sa.Column("contenuto", sa.Text(), nullable=False),
        sa.Column("autore", sa.String(100), nullable=False),
        sa.Column(
            "pubblicato_il",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_articoli_pubblicato_il", "articoli", ["pubblicato_il"])

    op.bulk_insert(articoli, [{
        "titolo": "Benvenuti su Joursense!",
        "sommario": "Nasce il giornalino aziendale: notizie, eventi e tutto quello che succede in ufficio.",
        "contenuto": (
            "Da oggi abbiamo un posto dove raccontare quello che succede in azienda: "
            "novità dai team, eventi in arrivo, nuovi arrivi e piccole curiosità.\n\n"
            "Chiunque può scrivere un articolo con il pulsante in alto a destra. "
            "Gli articoli più letti finiscono nella classifica in homepage.\n\n"
            "Questo sito gira su OpenShift: l'app è scritta in Python con FastAPI, "
            "gli articoli sono salvati su PostgreSQL e le letture vengono contate su Redis."
        ),
        "autore": "La redazione",
    }])


def downgrade():
    op.drop_index("ix_articoli_pubblicato_il", table_name="articoli")
    op.drop_table("articoli")
