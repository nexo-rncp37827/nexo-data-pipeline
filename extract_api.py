"""
extract_api.py — C1 : Extraction depuis API REST
Source : API Adresse du gouvernement (api-adresse.data.gouv.fr) — géocodage
Produit : data/raw/adresses_geocodees.csv

Logique :
- Entrée : liste d'adresses de sites clients Nexo, codées en dur (ADRESSES_CLIENTS)
- Interroge l'API Adresse (Base Adresse Nationale, publique, sans clé) pour
  chaque adresse
- Sauvegarde les résultats géocodés (adresse normalisée, coordonnées GPS,
  score de géocodage)
- Gère les erreurs : timeout, adresse non trouvée, API indisponible

Note : ce script ne fait aucune validation SIRET/SIRENE — c'est du géocodage
d'adresses uniquement (voir Option C, décision du 07/09/2026 : le critère C1
est couvert par ailleurs via extract_bdd.py et generate_excel_template.py).
"""

import requests
import pandas as pd
import time
import logging
from pathlib import Path
from faker import Faker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

fake = Faker("fr_FR")

OUTPUT_DIR = Path("data/raw")
OUTPUT_FILE = OUTPUT_DIR / "adresses_geocodees.csv"

# API Adresse (adresse.data.gouv.fr) — publique, sans clé, sans authentification
# Documentation : https://adresse.data.gouv.fr/api-doc/adresse
API_BASE_URL = "https://api-adresse.data.gouv.fr/search/"
TIMEOUT = 10
DELAY_BETWEEN_REQUESTS = 0.3

# Adresses de sites clients Nexo (entreprises de nettoyage interviennent
# sur des bureaux, hôpitaux, écoles, entrepôts)
ADRESSES_CLIENTS = [
    {"query": "20 avenue de la République Paris", "type_site": "bureau"},
    {"query": "15 rue du Commerce Lyon", "type_site": "commerce"},
    {"query": "3 boulevard Gambetta Marseille", "type_site": "bureau"},
    {"query": "10 rue des Fleurs Bordeaux", "type_site": "entrepot"},
    {"query": "25 avenue Jean Jaurès Toulouse", "type_site": "bureau"},
    {"query": "8 place de la Mairie Nantes", "type_site": "commerce"},
    {"query": "12 rue Victor Hugo Lille", "type_site": "bureau"},
    {"query": "5 allée des Roses Strasbourg", "type_site": "entrepot"},
    {"query": "30 rue de la Paix Nice", "type_site": "bureau"},
    {"query": "18 boulevard du Général de Gaulle Rennes", "type_site": "commerce"},
]


def fetch_adresse(query: str, type_site: str, session: requests.Session) -> dict:
    """
    Interroge l'API Adresse pour géocoder et valider une adresse client.
    Retourne un dict avec les données normalisées ou un dict d'erreur.

    API Adresse — adresse.data.gouv.fr :
    - Publique, sans authentification
    - Géocodage d'adresses françaises (données BAN — Base Adresse Nationale)
    - Retourne : adresse normalisée, code postal, ville, coordonnées GPS
    """
    params = {
        "q": query,
        "limit": 1,
        "type": "housenumber",
    }

    try:
        response = session.get(API_BASE_URL, params=params, timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()
        features = data.get("features", [])

        if features:
            props = features[0]["properties"]
            coords = features[0]["geometry"]["coordinates"]

            return {
                "query_originale": query,
                "adresse_normalisee": props.get("label", ""),
                "numero": props.get("housenumber", ""),
                "rue": props.get("street", ""),
                "code_postal": props.get("postcode", ""),
                "ville": props.get("city", ""),
                "departement": props.get("context", "").split(",")[0].strip(),
                "longitude": coords[0],
                "latitude": coords[1],
                "score_geocodage": round(props.get("score", 0), 3),
                "type_site": type_site,
                "source": "api_adresse_gouv",
                "erreur": None,
            }
        else:
            logger.warning(f"Aucun résultat pour : {query}")
            return {
                "query_originale": query,
                "adresse_normalisee": None,
                "numero": None,
                "rue": None,
                "code_postal": None,
                "ville": None,
                "departement": None,
                "longitude": None,
                "latitude": None,
                "score_geocodage": 0,
                "type_site": type_site,
                "source": "api_adresse_gouv",
                "erreur": "Aucun résultat",
            }

    except requests.exceptions.Timeout:
        logger.error(f"Timeout pour : {query}")
        return {
            "query_originale": query,
            "adresse_normalisee": None,
            "numero": None, "rue": None, "code_postal": None,
            "ville": None, "departement": None,
            "longitude": None, "latitude": None,
            "score_geocodage": 0, "type_site": type_site,
            "source": "api_adresse_gouv", "erreur": "Timeout",
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur requête pour {query} : {e}")
        return {
            "query_originale": query,
            "adresse_normalisee": None,
            "numero": None, "rue": None, "code_postal": None,
            "ville": None, "departement": None,
            "longitude": None, "latitude": None,
            "score_geocodage": 0, "type_site": type_site,
            "source": "api_adresse_gouv", "erreur": str(e),
        }


def main():
    logger.info("=== Démarrage extraction API Adresse (adresse.data.gouv.fr) ===")
    logger.info("API publique — géocodage adresses clients Nexo (sans authentification)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    resultats = []

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "NexoPipeline/1.0 (certification RNCP37827)"
        })

        for i, item in enumerate(ADRESSES_CLIENTS, 1):
            logger.info(
                f"[{i}/{len(ADRESSES_CLIENTS)}] Géocodage : {item['query']}"
            )
            resultat = fetch_adresse(item["query"], item["type_site"], session)
            resultats.append(resultat)

            if i < len(ADRESSES_CLIENTS):
                time.sleep(DELAY_BETWEEN_REQUESTS)

    df = pd.DataFrame(resultats)

    succes = df["erreur"].isna().sum()
    echecs = len(df) - succes
    score_moyen = df["score_geocodage"].mean()

    logger.info(f"Résultats : {succes}/{len(df)} adresses géocodées, {echecs} erreurs")
    logger.info(f"Score de géocodage moyen : {score_moyen:.3f}")

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    logger.info(f"Fichier sauvegardé : {OUTPUT_FILE}")
    logger.info("=== Extraction API Adresse terminée ===")


if __name__ == "__main__":
    main()
