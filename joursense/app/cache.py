"""Tutto quello che passa da Redis.

Le visualizzazioni degli articoli stanno in un "sorted set": una lista in cui
ogni elemento (l'id dell'articolo) ha un punteggio (le visite). Redis la tiene
gia' ordinata, quindi la classifica dei piu' letti costa una sola chiamata.

Se Redis non risponde, il sito continua a funzionare: semplicemente
non mostra i numeri delle visite.
"""
import logging
import os

import redis

log = logging.getLogger(__name__)

CLASSIFICA = "articoli:visite"

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD"),
    socket_timeout=2,
    decode_responses=True,
)


def registra_visita(articolo_id: int) -> int | None:
    """Aggiunge 1 alle visite dell'articolo e restituisce il nuovo totale."""
    try:
        return int(r.zincrby(CLASSIFICA, 1, articolo_id))
    except redis.RedisError as e:
        log.warning("Redis non disponibile: %s", e)
        return None


def visite(ids: list[int]) -> dict[int, int]:
    """Visite di piu' articoli in una sola chiamata."""
    if not ids:
        return {}
    try:
        punteggi = r.zmscore(CLASSIFICA, ids)
    except redis.RedisError as e:
        log.warning("Redis non disponibile: %s", e)
        return {}
    return {i: int(p or 0) for i, p in zip(ids, punteggi)}


def piu_letti(n: int = 5) -> list[tuple[int, int]]:
    """Gli n articoli piu' letti, come lista di (id, visite)."""
    try:
        risultato = r.zrevrange(CLASSIFICA, 0, n - 1, withscores=True)
    except redis.RedisError as e:
        log.warning("Redis non disponibile: %s", e)
        return []
    return [(int(i), int(p)) for i, p in risultato]


def ping() -> None:
    r.ping()
