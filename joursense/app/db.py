"""Connessione a PostgreSQL tramite SQLAlchemy."""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker


def database_url():
    # DATABASE_URL serve solo per i test in locale; su OpenShift usiamo le variabili DB_*
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return URL.create(
        "postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )


# pool_pre_ping: prima di usare una connessione controlla che sia ancora viva
# (utile se il pod di Postgres e' stato riavviato)
engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
