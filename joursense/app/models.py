"""Tabelle del database, descritte come classi Python."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Utente(Base):
    __tablename__ = "utenti"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    nome: Mapped[str] = mapped_column(String(100))
    # Mai la password in chiaro: solo la sua "impronta" calcolata con Argon2
    password_hash: Mapped[str] = mapped_column(String(255))
    creato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Sessione(Base):
    __tablename__ = "sessioni"

    # Nel database salviamo l'hash del token, non il token: chi leggesse
    # la tabella non potrebbe usare i valori per entrare al posto di qualcuno.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    utente_id: Mapped[int] = mapped_column(ForeignKey("utenti.id", ondelete="CASCADE"))
    scade_il: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TentativoLogin(Base):
    """Login falliti, per bloccare chi prova tante password di fila."""
    __tablename__ = "tentativi_login"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    avvenuto_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Articolo(Base):
    __tablename__ = "articoli"

    id: Mapped[int] = mapped_column(primary_key=True)
    titolo: Mapped[str] = mapped_column(String(200))
    sommario: Mapped[str] = mapped_column(String(400))
    contenuto: Mapped[str] = mapped_column(Text)
    # Nome mostrato come firma. Per gli articoli nuovi e' il nome dell'utente;
    # quelli scritti prima del login hanno la firma inserita a mano.
    autore: Mapped[str] = mapped_column(String(100))
    autore_id: Mapped[int | None] = mapped_column(
        ForeignKey("utenti.id", ondelete="SET NULL"), nullable=True
    )
    pubblicato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    letture: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
