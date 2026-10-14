"""Tabelle del database, descritte come classi Python."""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Articolo(Base):
    __tablename__ = "articoli"

    id: Mapped[int] = mapped_column(primary_key=True)
    titolo: Mapped[str] = mapped_column(String(200))
    sommario: Mapped[str] = mapped_column(String(400))
    contenuto: Mapped[str] = mapped_column(Text)
    autore: Mapped[str] = mapped_column(String(100))
    pubblicato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
