"""Le letture degli articoli passano da Redis a una colonna su PostgreSQL

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Gli articoli gia' esistenti partono da 0 letture: quelle contate su Redis
    # sono andate perse insieme a Redis.
    op.add_column(
        "articoli",
        sa.Column("letture", sa.Integer(), server_default="0", nullable=False),
    )
    # Indice per la classifica dei piu' letti
    op.create_index("ix_articoli_letture", "articoli", ["letture"])

    # L'articolo di benvenuto citava Redis: aggiorniamo la frase.
    # (La migrazione 0001 e' gia' stata applicata, quindi non si modifica:
    # le correzioni ai dati si fanno con una migrazione nuova, come questa.)
    op.execute(
        sa.text(
            "UPDATE articoli SET contenuto = replace(contenuto, :vecchio, :nuovo) "
            "WHERE titolo = 'Benvenuti su Joursense!' AND autore = 'La redazione'"
        ).bindparams(
            vecchio="gli articoli sono salvati su PostgreSQL e le letture vengono contate su Redis.",
            nuovo="articoli e letture sono salvati su PostgreSQL.",
        )
    )


def downgrade():
    op.drop_index("ix_articoli_letture", table_name="articoli")
    op.drop_column("articoli", "letture")
