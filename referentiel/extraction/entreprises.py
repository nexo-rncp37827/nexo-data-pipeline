"""Source 2b — API REST « Recherche d'entreprises » (DINUM, données SIRENE).

Publique, sans clé ; limite annoncée : 7 requêtes par seconde. Une requête par SIRET de client.
"""

import logging
import re

import httpx
import pandas as pd

from referentiel.extraction import ErreurSource
from referentiel.extraction.http import Cadence, client_http, get_json, toutes_en_erreur

journal = logging.getLogger(__name__)

URL = "https://recherche-entreprises.api.gouv.fr/search"
REQUETES_PAR_SECONDE = 5


def siret_valide(brut) -> str | None:
    """14 chiffres après suppression des espaces et séparateurs, sinon None."""
    if brut is None or (isinstance(brut, float) and pd.isna(brut)):
        return None
    chiffres = re.sub(r"\D", "", str(brut))
    return chiffres if len(chiffres) == 14 else None


def lire_reponse(corps: dict, siret: str) -> dict:
    for unite in corps.get("results") or []:
        etablissements = list(unite.get("matching_etablissements") or [])
        if unite.get("siege"):
            etablissements.append(unite["siege"])
        for e in etablissements:
            if e.get("siret") == siret:
                return {
                    "statut": "ok",
                    "siren": unite.get("siren"),
                    "denomination": unite.get("nom_raison_sociale") or unite.get("nom_complet"),
                    "nature_juridique": unite.get("nature_juridique"),
                    "activite_principale": e.get("activite_principale")
                    or unite.get("activite_principale"),
                    "etat_unite_legale": unite.get("etat_administratif"),
                    "etat_etablissement": e.get("etat_administratif"),
                    "est_siege": bool(e.get("est_siege")),
                    "adresse_etablissement": e.get("adresse"),
                    "code_postal_etablissement": e.get("code_postal"),
                    "commune_etablissement": e.get("libelle_commune"),
                }
    return {"statut": "non_trouve"}


def extraire(clients: pd.DataFrame, transport: httpx.BaseTransport | None = None) -> pd.DataFrame:
    cadence = Cadence(REQUETES_PAR_SECONDE)
    lignes = []
    with client_http(transport) as client:
        for _, c in clients.iterrows():
            siret = siret_valide(c.get("siret"))
            ligne = {"client_id": c["client_id"], "siret": siret}
            if siret is None:
                ligne["statut"] = "siret_absent_ou_invalide"
            else:
                cadence.attendre()
                statut, corps = get_json(client, URL, {"q": siret, "page": 1, "per_page": 5})
                ligne.update(lire_reponse(corps, siret) if statut == "ok" else {"statut": statut})
            lignes.append(ligne)
    resultat = pd.DataFrame(lignes)
    if toutes_en_erreur(resultat["statut"], "siret_absent_ou_invalide"):
        raise ErreurSource("API Recherche d'entreprises : aucune réponse exploitable")
    journal.info("entreprises : %s", resultat["statut"].value_counts().to_dict())
    return resultat
