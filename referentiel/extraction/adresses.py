"""Source 2a — API REST de géocodage de la Géoplateforme (IGN), service « Adresse ».

L'ancienne API api-adresse.data.gouv.fr a été transférée à l'IGN : l'adresse
https://data.geopf.fr/geocodage/search est le point d'accès actuel, au même format (GeoJSON).
Une requête par site ; la réponse donne l'adresse normalisée, le code commune INSEE, les
coordonnées et un score de confiance.
"""

import logging

import httpx
import pandas as pd

from referentiel.extraction import ErreurSource
from referentiel.extraction.http import Cadence, client_http, get_json, toutes_en_erreur

journal = logging.getLogger(__name__)

URL = "https://data.geopf.fr/geocodage/search"
REQUETES_PAR_SECONDE = 10


def requete_adresse(site: pd.Series) -> str:
    morceaux = [site.get("adresse"), site.get("code_postal"), site.get("ville")]
    return " ".join(str(m).strip() for m in morceaux if m is not None and str(m).strip())


def lire_reponse(corps: dict) -> dict:
    resultats = corps.get("features") or []
    if not resultats:
        return {"statut": "non_trouve"}
    p = resultats[0].get("properties", {})
    lon, lat = (resultats[0].get("geometry") or {}).get("coordinates", [None, None])
    return {
        "statut": "ok",
        "adresse_normalisee": p.get("label"),
        "numero": p.get("housenumber"),
        "voie": p.get("street") or p.get("name"),
        "code_postal": p.get("postcode"),
        "code_insee": p.get("citycode"),
        "commune": p.get("city"),
        "type_resultat": p.get("type"),
        "score": p.get("score"),
        "longitude": lon,
        "latitude": lat,
    }


def extraire(sites: pd.DataFrame, transport: httpx.BaseTransport | None = None) -> pd.DataFrame:
    cadence = Cadence(REQUETES_PAR_SECONDE)
    lignes = []
    with client_http(transport) as client:
        for _, site in sites.iterrows():
            q = requete_adresse(site)
            ligne = {"site_id": site["site_id"], "requete": q}
            if not q:
                ligne["statut"] = "adresse_vide"
            else:
                cadence.attendre()
                statut, corps = get_json(client, URL, {"q": q, "limit": 1, "index": "address"})
                ligne.update(lire_reponse(corps) if statut == "ok" else {"statut": statut})
            lignes.append(ligne)
    resultat = pd.DataFrame(lignes)
    if toutes_en_erreur(resultat["statut"], "adresse_vide"):
        raise ErreurSource("API de géocodage : aucune réponse exploitable (service indisponible ?)")
    journal.info("géocodage : %s", resultat["statut"].value_counts().to_dict())
    return resultat
