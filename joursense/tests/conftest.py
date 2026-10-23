"""Configurazione comune ai test.

app/db.py crea il collegamento al database appena viene importato e, senza
DATABASE_URL, cerca le variabili DB_USER, DB_PASSWORD, DB_NAME (che nei test
non ci sono). Impostiamo quindi DATABASE_URL su un database SQLite in memoria
PRIMA di importare l'app. /healthz non tocca il database, quindi basta questo:
nessun PostgreSQL necessario per eseguire i test.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    """Client HTTP che chiama l'app direttamente, senza avviare uvicorn."""
    with TestClient(app) as c:
        yield c