import os
import socket
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, text, update
from urllib.parse import quote

from app import auth
from app.db import SessionLocal
from app.models import Articolo, Utente

BASE = Path(__file__).parent

app = FastAPI(title="Joursense")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# Nome del pod che risponde, mostrato nel pie' di pagina
templates.env.globals["pod"] = socket.gethostname()


NOMI_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
             "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _formatta_data(d):
    return f"{d.day} {NOMI_MESI[d.month - 1]} {d.year}" if d else ""


templates.env.filters["data"] = _formatta_data

# Citta' mostrata di default nella pagina meteo (configurabile dal Deployment)
CITTA_METEO = os.getenv("CITTA_METEO", "Roma")

# Il dipendente del mese e' sempre lui. Cambia solo la motivazione.
MOTIVAZIONI_CAGE = [
    "Ha recuperato il badge smarrito di un collega con la stessa determinazione con cui altri recuperano la Dichiarazione d'Indipendenza.",
    "Ha consegnato il report trimestrale in 60 secondi netti.",
    "Ha preso in carico il ticket più vecchio del backlog senza battere ciglio, e senza cambiare faccia.",
    "Ha sostituito il toner della stampante del terzo piano. Nessuno sa come ci sia arrivato.",
    "Ha guidato il team attraverso un deploy del venerdì pomeriggio. Ne sono usciti tutti vivi.",
    "Ha portato i cornetti a tutto l'open space, compresi i colleghi in smart working.",
    "Ha ottenuto un 'sì' in riunione da tre stakeholder contemporaneamente. Faccia a faccia.",
    "Ha messo in sicurezza il server di staging come se custodisse un tesoro nazionale.",
    "Ha risposto a tutte le email arretrate in una sola notte. Nessuno l'ha visto dormire.",
    "Ha difeso la macchinetta del caffè da un guasto con coraggio esemplare.",
    "Ha chiuso più pull request di chiunque altro, guardandole intensamente.",
    "Ha organizzato la cena aziendale e ha scelto il ristorante con un solo sguardo.",
]


def pagina(request: Request, nome: str, contesto: dict | None = None, status_code: int = 200):
    """Mostra un template, passando sempre anche l'utente loggato (se c'e')."""
    contesto = dict(contesto or {})
    contesto.setdefault("utente", getattr(request.state, "utente", None))
    return templates.TemplateResponse(request, nome, contesto, status_code=status_code)


# ---------- Protezione delle pagine ----------

class NonAutenticato(Exception):
    pass


def utente_loggato(request: Request) -> Utente:
    """Da aggiungere alle pagine riservate: se non c'e' un login valido, porta al login."""
    with SessionLocal() as db:
        utente = auth.utente_da_token(db, request.cookies.get(auth.COOKIE))
    if utente is None:
        raise NonAutenticato()
    request.state.utente = utente
    return utente


@app.exception_handler(NonAutenticato)
def vai_al_login(request: Request, exc: NonAutenticato):
    # Ricordiamo dove voleva andare, per riportarlo li' dopo il login
    destinazione = request.url.path
    url = "/login" if destinazione == "/" else f"/login?next={quote(destinazione)}"
    risposta = RedirectResponse(url=url, status_code=303)
    risposta.delete_cookie(auth.COOKIE)
    return risposta


def _destinazione_sicura(next_url: str) -> str:
    """Accetta solo indirizzi interni al sito (evita redirect verso siti esterni)."""
    if next_url.startswith("/") and not next_url.startswith(("//", "/\\")):
        return next_url
    return "/"


def _accedi(request: Request, db, utente: Utente, destinazione: str) -> RedirectResponse:
    token = auth.crea_sessione(db, utente)
    db.commit()
    risposta = RedirectResponse(url=destinazione, status_code=303)
    risposta.set_cookie(
        auth.COOKIE,
        token,
        max_age=int(auth.DURATA_SESSIONE.total_seconds()),
        httponly=True,                              # JavaScript non puo' leggerlo
        secure=request.url.scheme == "https",       # viaggia solo in https
        samesite="lax",                             # non viene inviato dai moduli di altri siti
    )
    return risposta


# ---------- Login, registrazione, logout ----------

@app.get("/login")
def login_form(request: Request, next: str = "/"):
    with SessionLocal() as db:
        if auth.utente_da_token(db, request.cookies.get(auth.COOKIE)):
            return RedirectResponse(url=_destinazione_sicura(next), status_code=303)
    return pagina(request, "login.html", {"errori": [], "email": "", "next": next})


@app.post("/login")
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    email = auth.normalizza_email(email)
    contesto = {"email": email, "next": next}

    with SessionLocal() as db:
        if auth.troppi_tentativi(db, email):
            contesto["errori"] = [
                "Troppi tentativi sbagliati per questa email. Riprova tra qualche minuto."
            ]
            return pagina(request, "login.html", contesto, status_code=429)

        utente = auth.verifica_credenziali(db, email, password)
        if utente is None:
            auth.registra_tentativo_fallito(db, email)
            db.commit()
            # Messaggio generico: non diciamo se e' sbagliata l'email o la password
            contesto["errori"] = ["Email o password non corretti."]
            return pagina(request, "login.html", contesto, status_code=400)

        return _accedi(request, db, utente, _destinazione_sicura(next))


@app.get("/registrati")
def registrati_form(request: Request):
    return pagina(request, "registrati.html", {
        "errori": [], "valori": {}, "dominio": auth.DOMINIO_CONSENTITO,
    })


@app.post("/registrati")
def registrati(
    request: Request,
    nome: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    conferma: str = Form(""),
):
    nome = " ".join(nome.split())
    email = auth.normalizza_email(email)

    with SessionLocal() as db:
        errori = auth.valida_registrazione(db, nome, email, password, conferma)
        if errori:
            return pagina(request, "registrati.html", {
                "errori": errori,
                "valori": {"nome": nome, "email": email},
                "dominio": auth.DOMINIO_CONSENTITO,
            }, status_code=400)

        utente = auth.crea_utente(db, nome, email, password)
        # Appena registrato e' gia' dentro, senza dover rifare il login
        return _accedi(request, db, utente, "/")


@app.post("/logout")
def logout(request: Request):
    with SessionLocal() as db:
        auth.elimina_sessione(db, request.cookies.get(auth.COOKIE))
        db.commit()
    risposta = RedirectResponse(url="/login", status_code=303)
    risposta.delete_cookie(auth.COOKIE)
    return risposta


# ---------- Pagine del giornalino (tutte riservate) ----------

@app.get("/")
def home(request: Request, utente: Utente = Depends(utente_loggato)):
    with SessionLocal() as db:
        articoli = db.scalars(
            select(Articolo).order_by(Articolo.pubblicato_il.desc(), Articolo.id.desc()).limit(20)
        ).all()

        # Classifica: i 5 articoli con piu' letture (almeno una)
        piu_letti = db.scalars(
            select(Articolo)
            .where(Articolo.letture > 0)
            .order_by(Articolo.letture.desc(), Articolo.id.desc())
            .limit(5)
        ).all()

    return pagina(request, "home.html", {"articoli": articoli, "piu_letti": piu_letti})


@app.get("/articoli/{articolo_id}")
def dettaglio(request: Request, articolo_id: int, utente: Utente = Depends(utente_loggato)):
    with SessionLocal() as db:
        # Aggiunge 1 alle letture e restituisce il nuovo totale in un'unica istruzione.
        # Fatto dal database ("letture = letture + 1"), non da Python: cosi' due letture
        # nello stesso istante, magari su due pod diversi, vengono contate entrambe.
        visite = db.execute(
            update(Articolo)
            .where(Articolo.id == articolo_id)
            .values(letture=Articolo.letture + 1)
            .returning(Articolo.letture)
        ).scalar_one_or_none()
        db.commit()
        articolo = db.get(Articolo, articolo_id) if visite is not None else None

    if articolo is None:
        raise HTTPException(status_code=404, detail="Articolo non trovato")

    paragrafi = [p.strip() for p in articolo.contenuto.split("\n\n") if p.strip()]

    return pagina(request, "articolo.html", {
        "articolo": articolo,
        "paragrafi": paragrafi,
        "visite": visite,
    })


@app.get("/nuovo")
def nuovo_form(request: Request, utente: Utente = Depends(utente_loggato)):
    return pagina(request, "nuovo.html", {"errori": [], "valori": {}})


@app.post("/nuovo")
def nuovo_salva(
    request: Request,
    titolo: str = Form(""),
    sommario: str = Form(""),
    contenuto: str = Form(""),
    utente: Utente = Depends(utente_loggato),
):
    valori = {
        "titolo": titolo.strip(),
        "sommario": sommario.strip(),
        "contenuto": contenuto.strip(),
    }

    errori = []
    if not valori["titolo"]:
        errori.append("Il titolo e' obbligatorio.")
    elif len(valori["titolo"]) > 200:
        errori.append("Il titolo puo' avere al massimo 200 caratteri.")
    if not valori["contenuto"]:
        errori.append("Il testo dell'articolo e' obbligatorio.")
    if len(valori["sommario"]) > 400:
        errori.append("Il sommario puo' avere al massimo 400 caratteri.")

    if errori:
        return pagina(request, "nuovo.html", {"errori": errori, "valori": valori}, status_code=400)

    # Se il sommario e' vuoto, usiamo l'inizio del testo
    if not valori["sommario"]:
        testo = " ".join(valori["contenuto"].split())
        valori["sommario"] = testo if len(testo) <= 200 else testo[:197].rsplit(" ", 1)[0] + "..."

    with SessionLocal() as db:
        # La firma e' il nome di chi ha fatto login
        articolo = Articolo(**valori, autore=utente.nome, autore_id=utente.id)
        db.add(articolo)
        db.commit()
        nuovo_id = articolo.id

    # Redirect dopo il POST: se l'utente ricarica la pagina non ripubblica l'articolo
    return RedirectResponse(url=f"/articoli/{nuovo_id}", status_code=303)


@app.post("/articoli/{articolo_id}/elimina")
def elimina_articolo(articolo_id: int, utente: Utente = Depends(utente_loggato)):
    with SessionLocal() as db:
        articolo = db.get(Articolo, articolo_id)
        if articolo is None:
            raise HTTPException(status_code=404, detail="Articolo non trovato")
        # Il controllo vero e' qui, sul server: nascondere il pulsante non basta,
        # perche' chiunque potrebbe mandare questa richiesta a mano.
        if articolo.autore_id != utente.id:
            raise HTTPException(status_code=403, detail="Puoi eliminare solo i tuoi articoli")
        db.execute(delete(Articolo).where(Articolo.id == articolo_id))
        db.commit()
    return RedirectResponse(url="/", status_code=303)


# ---------- Sezioni extra ----------

@app.get("/giochi")
def giochi(request: Request, utente: Utente = Depends(utente_loggato)):
    return pagina(request, "giochi.html")


@app.get("/meteo")
def meteo(request: Request, utente: Utente = Depends(utente_loggato)):
    return pagina(request, "meteo.html", {"citta_predefinita": CITTA_METEO})


@app.get("/dipendente-del-mese")
def dipendente_del_mese(request: Request, utente: Utente = Depends(utente_loggato)):
    oggi = date.today()
    mesi = []
    anno, mese = oggi.year, oggi.month
    for i in range(12):
        mesi.append({
            "mese": f"{NOMI_MESI[mese - 1].capitalize()} {anno}",
            # Stessa motivazione per lo stesso mese, a ogni caricamento
            "motivazione": MOTIVAZIONI_CAGE[(anno * 12 + mese) % len(MOTIVAZIONI_CAGE)],
        })
        mese -= 1
        if mese == 0:
            anno, mese = anno - 1, 12
    return pagina(request, "dipendente.html", {"attuale": mesi[0], "archivio": mesi[1:]})


# ---------- Probe (non richiedono login: le chiama OpenShift) ----------

@app.get("/healthz")
def healthz():
    """Liveness: il processo Python risponde. Non controlla le dipendenze."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: l'app e' pronta solo se raggiunge PostgreSQL."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not ready", "postgres": str(e)})
    return {"status": "ready", "postgres": "ok"}
