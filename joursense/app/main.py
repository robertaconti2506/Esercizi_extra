import html
import os
import socket

import psycopg
import redis
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# Configurazione letta dalle variabili d'ambiente (impostate nel Deployment)
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ["REDIS_PASSWORD"]

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    socket_timeout=2,
    decode_responses=True,
)

app = FastAPI(title="Giornalino")


def db_connect():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=3,
    )


@app.get("/", response_class=HTMLResponse)
def home():
    # Contatore visite su Redis
    visite = r.incr("visite:home")

    # Versione di PostgreSQL, per verificare la connessione al database
    with db_connect() as conn:
        versione_db = conn.execute("SELECT version()").fetchone()[0]

    # Nome del pod che ha risposto: con 2 repliche, ricaricando la pagina cambia
    pod = socket.gethostname()

    return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Giornalino</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 3rem auto; padding: 0 1rem; color: #222; }}
    h1 {{ margin-bottom: .2rem; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 1rem 1.2rem; margin: 1rem 0; }}
    .label {{ color: #777; font-size: .85rem; }}
    .value {{ font-size: 1.1rem; margin-top: .2rem; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>Hello giornalino!</h1>
  <p>Se vedi questa pagina, app, PostgreSQL e Redis si parlano.</p>
  <div class="card"><div class="label">Visite (contatore su Redis)</div><div class="value">{visite}</div></div>
  <div class="card"><div class="label">Database</div><div class="value">{html.escape(versione_db)}</div></div>
  <div class="card"><div class="label">Pod che ha risposto</div><div class="value">{html.escape(pod)}</div></div>
</body>
</html>"""


@app.get("/healthz")
def healthz():
    """Liveness: il processo Python risponde. Non controlla le dipendenze."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: l'app e' pronta solo se raggiunge sia PostgreSQL sia Redis."""
    errori = {}
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        errori["postgres"] = str(e)
    try:
        r.ping()
    except Exception as e:
        errori["redis"] = str(e)

    if errori:
        return JSONResponse(status_code=503, content={"status": "not ready", "errori": errori})
    return {"status": "ready"}

