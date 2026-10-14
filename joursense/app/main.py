import socket
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text

from app import cache
from app.db import SessionLocal
from app.models import Articolo

BASE = Path(__file__).parent

app = FastAPI(title="Joursense")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# Nome del pod che risponde, mostrato nel pie' di pagina
templates.env.globals["pod"] = socket.gethostname()


def _formatta_data(d):
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
            "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"{d.day} {mesi[d.month - 1]} {d.year}" if d else ""


templates.env.filters["data"] = _formatta_data


# ---------- Pagine ----------

@app.get("/")
def home(request: Request):
    with SessionLocal() as db:
        articoli = db.scalars(
            select(Articolo).order_by(Articolo.pubblicato_il.desc(), Articolo.id.desc()).limit(20)
        ).all()

        classifica = cache.piu_letti(5)
        per_id = {a.id: a for a in articoli}
        mancanti = [i for i, _ in classifica if i not in per_id]
        if mancanti:
            for a in db.scalars(select(Articolo).where(Articolo.id.in_(mancanti))):
                per_id[a.id] = a

    piu_letti = [(per_id[i], v) for i, v in classifica if i in per_id]
    conteggi = cache.visite([a.id for a in articoli])

    return templates.TemplateResponse(request, "home.html", {
        "articoli": articoli,
        "visite": conteggi,
        "piu_letti": piu_letti,
    })


@app.get("/articoli/{articolo_id}")
def dettaglio(request: Request, articolo_id: int):
    with SessionLocal() as db:
        articolo = db.get(Articolo, articolo_id)
    if articolo is None:
        raise HTTPException(status_code=404, detail="Articolo non trovato")

    visite = cache.registra_visita(articolo_id)
    paragrafi = [p.strip() for p in articolo.contenuto.split("\n\n") if p.strip()]

    return templates.TemplateResponse(request, "articolo.html", {
        "articolo": articolo,
        "paragrafi": paragrafi,
        "visite": visite,
    })


@app.get("/nuovo")
def nuovo_form(request: Request):
    return templates.TemplateResponse(request, "nuovo.html", {"errori": [], "valori": {}})


@app.post("/nuovo")
def nuovo_salva(
    request: Request,
    titolo: str = Form(""),
    sommario: str = Form(""),
    contenuto: str = Form(""),
    autore: str = Form(""),
):
    valori = {
        "titolo": titolo.strip(),
        "sommario": sommario.strip(),
        "contenuto": contenuto.strip(),
        "autore": autore.strip(),
    }

    errori = []
    if not valori["titolo"]:
        errori.append("Il titolo e' obbligatorio.")
    elif len(valori["titolo"]) > 200:
        errori.append("Il titolo puo' avere al massimo 200 caratteri.")
    if not valori["contenuto"]:
        errori.append("Il testo dell'articolo e' obbligatorio.")
    if not valori["autore"]:
        errori.append("Indica chi firma l'articolo.")
    elif len(valori["autore"]) > 100:
        errori.append("Il nome dell'autore puo' avere al massimo 100 caratteri.")
    if len(valori["sommario"]) > 400:
        errori.append("Il sommario puo' avere al massimo 400 caratteri.")

    if errori:
        return templates.TemplateResponse(
            request, "nuovo.html", {"errori": errori, "valori": valori}, status_code=400
        )

    # Se il sommario e' vuoto, usiamo l'inizio del testo
    if not valori["sommario"]:
        testo = " ".join(valori["contenuto"].split())
        valori["sommario"] = testo if len(testo) <= 200 else testo[:197].rsplit(" ", 1)[0] + "..."

    with SessionLocal() as db:
        articolo = Articolo(**valori)
        db.add(articolo)
        db.commit()
        nuovo_id = articolo.id

    # Redirect dopo il POST: se l'utente ricarica la pagina non ripubblica l'articolo
    return RedirectResponse(url=f"/articoli/{nuovo_id}", status_code=303)


# ---------- Probe ----------

@app.get("/healthz")
def healthz():
    """Liveness: il processo Python risponde. Non controlla le dipendenze."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: l'app e' pronta se raggiunge PostgreSQL.

    Redis viene solo segnalato: senza Redis il sito funziona lo stesso
    (mancano solo i conteggi delle letture), quindi non ha senso togliere
    il pod dal traffico.
    """
    stato = {"postgres": "ok", "redis": "ok"}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as e:
        stato["postgres"] = str(e)
    try:
        cache.ping()
    except Exception as e:
        stato["redis"] = str(e)

    if stato["postgres"] != "ok":
        return JSONResponse(status_code=503, content={"status": "not ready", **stato})
    return {"status": "ready", **stato}
