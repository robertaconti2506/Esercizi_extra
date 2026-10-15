"""Account, password e sessioni di login.

Come funziona una sessione:
  1. al login generiamo un token casuale lungo (impossibile da indovinare)
  2. nel database salviamo il suo hash SHA-256, con la scadenza
  3. al browser mandiamo un cookie che contiene il token
  4. a ogni pagina ricalcoliamo l'hash del token del cookie e lo cerchiamo
     nella tabella "sessioni": se c'e' e non e' scaduto, sappiamo chi e' l'utente
"""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Sessione, TentativoLogin, Utente

COOKIE = "sessione"
DURATA_SESSIONE = timedelta(days=7)

# Blocco dei tentativi: dopo 5 password sbagliate in 15 minuti sulla stessa email
MAX_TENTATIVI = 5
FINESTRA_TENTATIVI = timedelta(minutes=15)

PASSWORD_MIN = 8

# Se impostata (es. "sourcesense.com"), solo le email di quel dominio possono registrarsi.
# Si imposta come variabile d'ambiente nel Deployment, senza toccare il codice.
DOMINIO_CONSENTITO = os.getenv("DOMINIO_EMAIL_CONSENTITO", "").strip().lower().lstrip("@")

# Email degli amministratori, separate da virgola (es. "a@x.com,b@x.com").
# Si imposta come variabile d'ambiente nel Deployment: cosi' nessuno puo'
# diventare admin dal sito, serve accesso al progetto su OpenShift.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}


def is_admin(utente) -> bool:
    return utente is not None and utente.email in ADMIN_EMAILS


def puo_eliminare(utente, articolo) -> bool:
    """L'autore puo' eliminare i suoi articoli; un admin puo' eliminare tutto."""
    if utente is None:
        return False
    return articolo.autore_id == utente.id or is_admin(utente)


_hasher = PasswordHasher()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Hash di una password a caso: serve a rendere il login con un'email inesistente
# lento quanto quello con un'email esistente (vedi verifica_credenziali).
_HASH_FINTO = _hasher.hash(secrets.token_urlsafe(16))


def _adesso():
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalizza_email(email: str) -> str:
    return email.strip().lower()


# ---------- Registrazione ----------

def valida_registrazione(db: Session, nome: str, email: str, password: str, conferma: str) -> list[str]:
    errori = []
    if not nome:
        errori.append("Inserisci il tuo nome.")
    elif len(nome) > 100:
        errori.append("Il nome puo' avere al massimo 100 caratteri.")

    if not _EMAIL_RE.match(email) or len(email) > 254:
        errori.append("L'indirizzo email non sembra valido.")
    elif DOMINIO_CONSENTITO and not email.endswith("@" + DOMINIO_CONSENTITO):
        errori.append(f"Puoi registrarti solo con un indirizzo @{DOMINIO_CONSENTITO}.")
    elif db.scalar(select(Utente.id).where(Utente.email == email)) is not None:
        errori.append("Esiste gia' un account con questa email.")

    if len(password) < PASSWORD_MIN:
        errori.append(f"La password deve avere almeno {PASSWORD_MIN} caratteri.")
    elif password != conferma:
        errori.append("Le due password non coincidono.")
    return errori


def crea_utente(db: Session, nome: str, email: str, password: str) -> Utente:
    utente = Utente(nome=nome, email=email, password_hash=_hasher.hash(password))
    db.add(utente)
    db.flush()  # assegna l'id
    return utente


# ---------- Login ----------

def troppi_tentativi(db: Session, email: str) -> bool:
    limite = _adesso() - FINESTRA_TENTATIVI
    n = db.scalar(
        select(func.count())
        .select_from(TentativoLogin)
        .where(TentativoLogin.email == email, TentativoLogin.avvenuto_il > limite)
    )
    return n >= MAX_TENTATIVI


def registra_tentativo_fallito(db: Session, email: str) -> None:
    db.add(TentativoLogin(email=email))


def verifica_credenziali(db: Session, email: str, password: str) -> Utente | None:
    utente = db.scalar(select(Utente).where(Utente.email == email))
    if utente is None:
        # Verifichiamo comunque una password: cosi' la risposta impiega lo stesso
        # tempo e non si puo' capire dai tempi quali email sono registrate.
        try:
            _hasher.verify(_HASH_FINTO, password)
        except VerificationError:
            pass
        return None
    try:
        _hasher.verify(utente.password_hash, password)
    except (VerificationError, InvalidHashError):
        return None

    # Se in futuro cambiamo i parametri di Argon2, aggiorna l'hash al login
    if _hasher.check_needs_rehash(utente.password_hash):
        utente.password_hash = _hasher.hash(password)
    return utente


# ---------- Sessioni ----------

def crea_sessione(db: Session, utente: Utente) -> str:
    """Crea la sessione e restituisce il token da mettere nel cookie."""
    adesso = _adesso()
    # Pulizia: via le sessioni scadute e i tentativi falliti vecchi
    db.execute(delete(Sessione).where(Sessione.scade_il < adesso))
    db.execute(delete(TentativoLogin).where(TentativoLogin.avvenuto_il < adesso - timedelta(days=1)))
    # Login riuscito: azzera i tentativi falliti per questa email
    db.execute(delete(TentativoLogin).where(TentativoLogin.email == utente.email))

    token = secrets.token_urlsafe(32)
    db.add(Sessione(
        token_hash=_hash_token(token),
        utente_id=utente.id,
        scade_il=adesso + DURATA_SESSIONE,
    ))
    return token


def utente_da_token(db: Session, token: str | None) -> Utente | None:
    if not token:
        return None
    return db.scalar(
        select(Utente)
        .join(Sessione, Sessione.utente_id == Utente.id)
        .where(Sessione.token_hash == _hash_token(token), Sessione.scade_il > _adesso())
    )


def elimina_sessione(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(Sessione).where(Sessione.token_hash == _hash_token(token)))
