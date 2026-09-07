"""
import_bdd.py — C4 : Import des données nettoyées en base PostgreSQL
Source : data/clean/dataset_final.csv
Cible : table pipeline_clients dans PostgreSQL Nexo

Logique :
  - Crée la table pipeline_clients si elle n'existe pas
  - Importe les lignes de type client (sirene + nexo) depuis le dataset final
  - Upsert sur siret pour éviter les doublons
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
    siret           VARCHAR(14) UNIQUE,
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
    (siret, raison_sociale, adresse, code_postal, ville, statut, source, importe_le)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (siret)
DO UPDATE SET
    raison_sociale = EXCLUDED.raison_sociale,
    adresse        = EXCLUDED.adresse,
    code_postal    = EXCLUDED.code_postal,
    ville          = EXCLUDED.ville,
    statut         = EXCLUDED.statut,
    updated_at     = NOW();
"""


def charger_dataset() -> pd.DataFrame:
    """Charge et filtre le dataset final pour les clients uniquement."""
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Dataset final introuvable : {INPUT_FILE}\n"
            "Lancer clean_aggregate.py d'abord."
        )

    df = pd.read_csv(INPUT_FILE, encoding="utf-8")
    logger.info(f"Dataset chargé : {len(df)} lignes totales")

    df_clients = df[df["type_donnee"].isin(["client_sirene", "client_nexo"])].copy()
    df_clients = df_clients.dropna(subset=["siret"])
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
                    str(row.get("siret", ""))[:14],
                    str(row.get("raison_sociale", ""))[:255],
                    str(row.get("adresse", row.get("client_adresse", "")))[:500],
                    str(row.get("code_postal", row.get("site_code_postal", "")))[:10],
                    str(row.get("ville", row.get("site_ville", "")))[:100],
                    str(row.get("statut", "actif"))[:20],
                    str(row.get("source", "pipeline"))[:50],
                    maintenant,
                ))
                inserts += 1
            except Exception as e:
                logger.warning(f"Erreur import ligne (siret={row.get('siret')}) : {e}")
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
