"""
import_bdd.py — C4 : Import des données nettoyées en base PostgreSQL
Source : data/clean/dataset_final.csv
Cible : table pipeline_clients dans PostgreSQL Nexo

Logique :
  - Crée la table pipeline_clients si elle n'existe pas
  - Importe les lignes de type client_nexo depuis le dataset final (les
    adresses géocodées n'ont pas d'identité client — pas de raison_sociale
    — et ne sont donc pas importées ici, voir clean_aggregate.py)
  - Upsert sur client_id (identifiant Nexo réel) pour éviter les doublons —
    plus de notion de SIRET, jamais produit par aucune source du pipeline
  - Log chaque opération dans audit_logs Nexo

Documentation du script versionnée dans README.md (exigence C4).
"""

import pandas as pd
import logging
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

INPUT_FILE = Path("data/clean/dataset_final.csv")
DATABASE_URL = os.getenv("DATABASE_URL")

DDL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_clients (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER UNIQUE,
    raison_sociale  VARCHAR(255),
    adresse         TEXT,
    code_postal     VARCHAR(10),
    ville           VARCHAR(100),
    statut          VARCHAR(20),
    source          VARCHAR(50),
    importe_le      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
"""

SQL_UPSERT = """
INSERT INTO pipeline_clients
    (client_id, raison_sociale, adresse, code_postal, ville, statut, source, importe_le)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (client_id)
DO UPDATE SET
    raison_sociale = EXCLUDED.raison_sociale,
    adresse        = EXCLUDED.adresse,
    code_postal    = EXCLUDED.code_postal,
    ville          = EXCLUDED.ville,
    statut         = EXCLUDED.statut,
    updated_at     = NOW();
"""


def valeur(row: pd.Series, *cles: str, defaut: str = "") -> str:
    """
    Retourne la première valeur non vide/non NaN parmi les clés données,
    dans l'ordre, sinon `defaut`.

    row.get(cle, secours) ne bascule sur `secours` que si `cle` est absente
    de la ligne — pas si sa valeur vaut NaN. Or plusieurs colonnes (adresse,
    code_postal, ville) existent déjà dans le dataset agrégé, remplies par
    d'autres sources (adresses géocodées) et valant NaN pour les lignes
    client_nexo : le fallback ne se déclenchait donc jamais, et str(NaN)
    produisait la chaîne littérale "nan" en base.
    """
    for cle in cles:
        if cle not in row:
            continue
        val = row[cle]
        if pd.isna(val):
            continue
        val_str = str(val).strip()
        if val_str:
            return val_str
    return defaut


def charger_dataset() -> pd.DataFrame:
    """Charge et filtre le dataset final pour les clients Nexo uniquement."""
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Dataset final introuvable : {INPUT_FILE}\n"
            "Lancer clean_aggregate.py d'abord."
        )

    # dtype forcé en str pour les codes postaux : le CSV ne conserve aucune
    # métadonnée de type, donc une colonne "code_postal"/"site_code_postal"
    # entièrement numérique (mélangée à des NaN venant d'autres sources)
    # serait réinterprétée en float64 par pandas au chargement — malgré le
    # zero-padding déjà fait par clean_aggregate.py — ce qui produirait des
    # "69120.0" et, pire, tronquerait silencieusement les codes postaux
    # commençant par un zéro (ex. "01000" -> 1000.0 -> "1000").
    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8",
        dtype={"code_postal": str, "site_code_postal": str},
    )
    logger.info(f"Dataset chargé : {len(df)} lignes totales")

    df_clients = df[df["type_donnee"] == "client_nexo"].copy()
    df_clients = df_clients.dropna(subset=["client_id"])
    logger.info(f"Lignes clients à importer : {len(df_clients)}")
    return df_clients


def importer(df: pd.DataFrame) -> dict:
    """
    Importe les données dans PostgreSQL via upsert.
    Retourne un dict avec les compteurs d'import.
    """
    try:
        import psycopg2

        if not DATABASE_URL:
            raise ValueError("DATABASE_URL non défini dans .env")

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        logger.info("Création de la table pipeline_clients si absente...")
        cursor.execute(DDL_CREATE_TABLE)
        conn.commit()

        inserts = 0
        erreurs = 0
        maintenant = datetime.now()

        for _, row in df.iterrows():
            try:
                cursor.execute(SQL_UPSERT, (
                    int(row["client_id"]),
                    valeur(row, "raison_sociale")[:255],
                    valeur(row, "adresse", "client_adresse")[:500],
                    valeur(row, "code_postal", "site_code_postal")[:10],
                    valeur(row, "ville", "site_ville")[:100],
                    valeur(row, "statut", defaut="actif")[:20],
                    valeur(row, "source", defaut="pipeline")[:50],
                    maintenant,
                ))
                inserts += 1
            except Exception as e:
                logger.warning(f"Erreur import ligne (client_id={row.get('client_id')}) : {e}")
                erreurs += 1
                conn.rollback()

        conn.commit()
        cursor.close()
        conn.close()

        return {"inserts": inserts, "erreurs": erreurs}

    except ImportError:
        logger.error("psycopg2 non installé")
        raise
    except Exception as e:
        logger.error(f"Erreur connexion PostgreSQL : {e}")
        raise


def main():
    logger.info("=== Démarrage import en base de données ===")

    df = charger_dataset()

    if df.empty:
        logger.warning("Aucune donnée client à importer")
        return

    resultats = importer(df)
    logger.info(f"Import terminé : {resultats['inserts']} lignes importées, "
                f"{resultats['erreurs']} erreurs")
    logger.info("=== Import terminé ===")


if __name__ == "__main__":
    main()
