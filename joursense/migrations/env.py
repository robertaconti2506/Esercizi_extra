"""Configurazione di Alembic: come collegarsi al database ed eseguire le migrazioni."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

from app.db import engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Numero arbitrario che identifica il "lucchetto" delle migrazioni
LOCK_ID = 424242


def run_migrations_online():
    with engine.connect() as connection:
        postgres = connection.dialect.name == "postgresql"

        # Con 2 repliche, due pod partono insieme e lanciano le migrazioni nello
        # stesso momento. Il lucchetto di PostgreSQL fa si' che uno aspetti l'altro:
        # il secondo, quando entra, trova tutto gia' fatto e non fa nulla.
        if postgres:
            connection.execute(text(f"SELECT pg_advisory_lock({LOCK_ID})"))
            connection.commit()

        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            if postgres:
                connection.execute(text(f"SELECT pg_advisory_unlock({LOCK_ID})"))
                connection.commit()


run_migrations_online()
