"""Appels HTTP communs aux deux API REST : délai, nouvelles tentatives bornées, cadence."""

import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import pandas as pd

journal = logging.getLogger(__name__)

USER_AGENT = "nexo-referentiel-clients/0.1 (Foxabrille Nettoyage)"
STATUTS_A_REJOUER = {429, 500, 502, 503, 504}


def client_http(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=10.0, headers={"User-Agent": USER_AGENT}, transport=transport, follow_redirects=True
    )


def get_json(
    client: httpx.Client, url: str, params: dict, tentatives: int = 3, attente: float = 1.0
) -> tuple[str, dict | None]:
    """Renvoie (statut, corps JSON). Statuts : ok, erreur_http_<code>, timeout, erreur_reseau.

    Les erreurs 429 et 5xx sont rejouées (attente doublée à chaque fois, ou `Retry-After`) ;
    les autres erreurs ne le sont pas. Aucune exception ne remonte : l'appelant enregistre le
    statut sur la ligne concernée.
    """
    statut = "erreur_reseau"
    for essai in range(1, tentatives + 1):
        try:
            reponse = client.get(url, params=params)
        except httpx.TimeoutException:
            statut = "timeout"
        except httpx.HTTPError:
            statut = "erreur_reseau"
        else:
            if reponse.status_code == 200:
                return "ok", reponse.json()
            statut = f"erreur_http_{reponse.status_code}"
            if reponse.status_code not in STATUTS_A_REJOUER:
                return statut, None
            retry_after = reponse.headers.get("Retry-After", "")
            if retry_after.isdigit():
                attente = max(attente, float(retry_after))
        if essai < tentatives:
            time.sleep(attente)
            attente *= 2
    journal.warning("%s : abandon après %d tentatives (%s)", url, tentatives, statut)
    return statut, None


class Cadence:
    """Respecte un nombre maximal de requêtes par seconde."""

    def __init__(self, par_seconde: float):
        self.intervalle = 1.0 / par_seconde
        self.dernier = 0.0

    def attendre(self) -> None:
        reste = self.dernier + self.intervalle - time.monotonic()
        if reste > 0:
            time.sleep(reste)
        self.dernier = time.monotonic()


def en_erreur(statuts) -> "pd.Series":
    """Lignes dont l'appel a échoué (après les nouvelles tentatives)."""
    return statuts.astype(str).str.startswith(("erreur", "timeout"))


def toutes_en_erreur(statuts, sans_appel: str) -> bool:
    """Vrai si tous les appels effectivement faits ont échoué (lignes sans appel exclues)."""
    appeles = statuts[statuts != sans_appel]
    return len(appeles) > 0 and bool(en_erreur(appeles).all())
