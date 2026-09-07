"""
clean_aggregate.py — C3 : Agrégation et nettoyage des données
Source : data/raw/*.csv (sorties des 4 scripts d'extraction)
Produit : data/clean/dataset_final.csv

Ce script est DISTINCT des scripts d'extraction (exigence C3).
Il ne fait aucune extraction — uniquement du nettoyage et de la normalisation.

Traitements appliqués :
  1. Chargement des 4 fichiers CSV bruts
  2. Suppression des doublons (sur adresse normalisée, email, référence, client/site)
  3. Homogénéisation des formats de dates (→ YYYY-MM-DD)
  4. Normalisation des numéros de téléphone (→ 0X XX XX XX XX)
  5. Normalisation de la casse (noms en Title Case)
  6. Normalisation des types de contrat (CDI/CDD/Interim)
  7. Suppression des entrées corrompues (champs obligatoires vides)
  8. Fusion des données en un jeu de données final

Choix de nettoyage documentés :
  - Téléphones : format français normalisé (10 chiffres, espaces)
  - Dates : ISO 8601 (YYYY-MM-DD) pour compatibilité PostgreSQL
  - Doublons : conserve la première occurrence (ordre d'import)
  - Corrompues : ligne supprimée si nom ET email manquants simultanément
"""

import pandas as pd
import re
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")
OUTPUT_FILE = CLEAN_DIR / "dataset_final.csv"


# ---------------------------------------------------------------------------
# FONCTIONS DE NETTOYAGE
# ---------------------------------------------------------------------------

def normaliser_telephone(tel: str) -> str:
    """
    Normalise un numéro de téléphone français au format : 0X XX XX XX XX
    Gère : indicatif +33, espaces/tirets, format compact
    """
    if pd.isna(tel) or str(tel).strip() == "":
        return ""

    tel = str(tel).strip()
    chiffres = re.sub(r"[^\d]", "", tel)

    if chiffres.startswith("33") and len(chiffres) == 11:
        chiffres = "0" + chiffres[2:]

    if len(chiffres) == 10:
        return f"{chiffres[0:2]} {chiffres[2:4]} {chiffres[4:6]} {chiffres[6:8]} {chiffres[8:10]}"

    logger.debug(f"Téléphone non normalisé conservé : {tel}")
    return tel


def normaliser_date(date_str: str) -> str:
    """
    Normalise une date vers le format ISO 8601 (YYYY-MM-DD).
    Gère : DD/MM/YYYY, YYYY-MM-DD, DD-MM-YY, DD-MM-YYYY
    """
    if pd.isna(date_str) or str(date_str).strip() == "":
        return ""

    date_str = str(date_str).strip()

    formats_entree = [
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    for fmt in formats_entree:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning(f"Format de date non reconnu : {date_str}")
    return date_str


def normaliser_contrat(contrat: str) -> str:
    """
    Normalise les types de contrat vers CDI / CDD / Interim / Stage.
    Gère les variantes : C.D.I, cdi, contrat durée indéterminée, etc.
    """
    if pd.isna(contrat) or str(contrat).strip() == "":
        return "Inconnu"

    contrat_clean = str(contrat).strip().lower().replace(".", "").replace("-", "")

    mapping = {
        "cdi": "CDI",
        "contrat duree indeterminee": "CDI",
        "contrat a duree indeterminee": "CDI",
        "contrat durée indéterminée": "CDI",
        "contrat à durée indéterminée": "CDI",
        "cdd": "CDD",
        "contrat duree determinee": "CDD",
        "interim": "Interim",
        "intérim": "Interim",
        "stage": "Stage",
        "alternance": "Alternance",
    }

    for cle, valeur in mapping.items():
        if cle in contrat_clean:
            return valeur

    logger.warning(f"Type de contrat non reconnu : {contrat}")
    return contrat.strip()


def supprimer_corrompues(df: pd.DataFrame, champs_obligatoires: list) -> pd.DataFrame:
    """
    Supprime les lignes où tous les champs obligatoires sont vides simultanément.
    Choix : suppression seulement si TOUS les champs critiques sont manquants.
    Une ligne avec email mais sans nom est conservée (cas valide).
    """
    avant = len(df)
    masque_corrompu = df[champs_obligatoires].isnull().all(axis=1)
    df_clean = df[~masque_corrompu].copy()
    apres = len(df_clean)

    if avant - apres > 0:
        logger.info(f"Lignes corrompues supprimées : {avant - apres}")

    return df_clean


# ---------------------------------------------------------------------------
# CHARGEMENT ET NETTOYAGE PAR SOURCE
# ---------------------------------------------------------------------------

def nettoyer_adresses(fichier: Path) -> pd.DataFrame:
    """Nettoyage des données API Adresse (adresse.data.gouv.fr).
    Colonnes : query_originale, adresse_normalisee, rue, code_postal, ville,
               departement, longitude, latitude, score_geocodage, type_site, erreur
    """
    if not fichier.exists():
        logger.warning(f"Fichier absent : {fichier}")
        return pd.DataFrame()

    # dtype forcé en str pour code_postal : sans ça, une ligne en erreur de
    # géocodage (code_postal=NaN) suffit à faire réinterpréter toute la
    # colonne en float64 par pandas — "69120" devient alors "69120.0" avant
    # même que le zfill ci-dessous ne s'exécute (voir même correctif dans
    # nettoyer_nexo_export ci-dessous et import_bdd.py, où le bug a été
    # repéré en base).
    df = pd.read_csv(fichier, encoding="utf-8", dtype={"code_postal": str})
    logger.info(f"API Adresse : {len(df)} lignes chargées")

    # Suppression des doublons sur l'adresse normalisée
    df = df.drop_duplicates(subset=["adresse_normalisee"])

    # Normalisation casse
    df["ville"] = df["ville"].str.strip().str.upper()
    df["rue"] = df["rue"].str.strip().str.title()

    # Normalisation code postal (5 chiffres)
    df["code_postal"] = df["code_postal"].astype(str).str.zfill(5)

    # Suppression des lignes en erreur
    df = df[df["erreur"].isna()].copy()

    # Filtre qualité : score de géocodage > 0.5
    df = df[df["score_geocodage"] > 0.5]

    df["type_donnee"] = "adresse_client"

    logger.info(f"API Adresse après nettoyage : {len(df)} lignes")
    return df


def nettoyer_salaries_legacy(fichier: Path) -> pd.DataFrame:
    """Nettoyage des données salariés legacy CSV."""
    if not fichier.exists():
        logger.warning(f"Fichier absent : {fichier}")
        return pd.DataFrame()

    df = pd.read_csv(fichier, encoding="utf-8")
    logger.info(f"Salariés legacy : {len(df)} lignes chargées")

    df = df.drop_duplicates(subset=["Email"])
    df["NOM"] = df["NOM"].str.strip().str.title()
    df["prenom"] = df["prenom"].str.strip().str.title()
    df["TELEPHONE"] = df["TELEPHONE"].apply(normaliser_telephone)
    df["date_embauche"] = df["date_embauche"].apply(normaliser_date)
    df["type_contrat"] = df["type_contrat"].apply(normaliser_contrat)
    df["tournee"] = df["tournee"].str.strip().str.title()
    df["tournee"] = df["tournee"].replace("", "Non assignée")

    df = df.rename(columns={"NOM": "nom", "Email": "email", "TELEPHONE": "telephone"})
    df = supprimer_corrompues(df, ["nom", "email"])
    df["type_donnee"] = "salarie_legacy"

    logger.info(f"Salariés legacy après nettoyage : {len(df)} lignes")
    return df


def nettoyer_tarifs_scraping(fichier: Path) -> pd.DataFrame:
    """Nettoyage des données scraping tarifs."""
    if not fichier.exists():
        logger.warning(f"Fichier absent : {fichier}")
        return pd.DataFrame()

    df = pd.read_csv(fichier, encoding="utf-8")
    logger.info(f"Tarifs scraping : {len(df)} lignes chargées")

    df = df.drop_duplicates(subset=["reference"])
    df["designation"] = df["designation"].str.strip().str.title()
    df["prix_achat_ht"] = pd.to_numeric(df["prix_achat_ht"], errors="coerce").round(2)
    df["prix_vente_ht"] = pd.to_numeric(df["prix_vente_ht"], errors="coerce").round(2)
    df = df[df["prix_vente_ht"] > 0]
    df["taux_tva"] = df["taux_tva"].fillna(20.0)
    df["type_donnee"] = "catalogue_produit"

    logger.info(f"Tarifs scraping après nettoyage : {len(df)} lignes")
    return df


def nettoyer_nexo_export(fichier: Path) -> pd.DataFrame:
    """Nettoyage des données export PostgreSQL Nexo."""
    if not fichier.exists():
        logger.warning(f"Fichier absent : {fichier}")
        return pd.DataFrame()

    # dtype forcé en str pour site_code_postal : les clients sans site (LEFT
    # JOIN -> NaN dans extract_bdd.py) suffisent à faire réinterpréter toute
    # la colonne en float64 au chargement du CSV — "69120" devient "69120.0"
    # avant même le zfill ci-dessous. C'est ce mécanisme précis qui a produit
    # le "nan"/"69120.0" trouvé en base (voir import_bdd.py).
    df = pd.read_csv(fichier, encoding="utf-8", dtype={"site_code_postal": str})
    logger.info(f"Export Nexo : {len(df)} lignes chargées")

    df = df.drop_duplicates(subset=["client_id", "site_id"])
    df["raison_sociale"] = df["raison_sociale"].str.strip().str.title()
    df["site_ville"] = df["site_ville"].str.strip().str.title()
    df["site_code_postal"] = df["site_code_postal"].astype(str).str.zfill(5)
    # client_telephone retiré de extract_bdd.py (colonne absente du schéma
    # actuel, cf. commentaire SQL_CLIENTS_AVEC_SITES) — plus de colonne à normaliser ici.
    df["nb_interventions_total"] = df["nb_interventions_total"].fillna(0).astype(int)
    df["type_donnee"] = "client_nexo"

    logger.info(f"Export Nexo après nettoyage : {len(df)} lignes")
    return df


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    logger.info("=== Démarrage nettoyage et agrégation ===")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    df_adresses = nettoyer_adresses(RAW_DIR / "adresses_geocodees.csv")
    df_salaries = nettoyer_salaries_legacy(RAW_DIR / "salaries_legacy.csv")
    df_tarifs = nettoyer_tarifs_scraping(RAW_DIR / "tarifs_scraping.csv")
    df_nexo = nettoyer_nexo_export(RAW_DIR / "nexo_export.csv")

    datasets = {
        "adresses": df_adresses,
        "salaries": df_salaries,
        "tarifs": df_tarifs,
        "nexo": df_nexo,
    }

    logger.info("=== Rapport de nettoyage ===")
    for nom, df in datasets.items():
        if not df.empty:
            logger.info(f"  {nom:12s} : {len(df):4d} lignes | "
                        f"valeurs manquantes : {df.isnull().sum().sum()}")

    df_final = pd.concat(
        [df for df in datasets.values() if not df.empty],
        ignore_index=True,
        sort=False
    )

    df_final["date_traitement"] = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Dataset final : {len(df_final)} lignes, {len(df_final.columns)} colonnes")

    df_final.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    logger.info(f"Fichier sauvegardé : {OUTPUT_FILE}")
    logger.info("=== Nettoyage et agrégation terminés ===")


if __name__ == "__main__":
    main()
