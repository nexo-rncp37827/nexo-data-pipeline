"""
extract_bdd.py — C1 + C2 : Extraction depuis base de données PostgreSQL
Source : Base PostgreSQL Nexo (locale)
Produit : data/raw/nexo_export.csv

Requêtes SQL documentées (C2) :
  - Sélection clients avec leurs sites actifs (jointure clients + sites)
  - Filtrage sur clients actifs uniquement
  - Agrégation du nombre d'interventions par client
  - Optimisation : index sur interventions.site_id (migration 019 Nexo)

Gestion des erreurs :
  - Toute erreur d'extraction (connexion refusée, base inaccessible, requête
    invalide, colonne/table absente...) est fatale : log ERROR détaillé puis
    l'exception remonte. Pas de fallback silencieux — une extraction ratée
    doit être visible, pas masquée par des données simulées.
"""

import pandas as pd
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/raw")
OUTPUT_FILE = OUTPUT_DIR / "nexo_export.csv"
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------------------------------
# REQUÊTES SQL DOCUMENTÉES (C2)
# ---------------------------------------------------------------------------

SQL_CLIENTS_AVEC_SITES = """
-- Requête C2 — Extraction clients avec leurs sites
-- Objectif : récupérer l'ensemble des clients actifs et leurs sites d'intervention
-- Jointure : clients (1) → sites (n) via sites.client_id
-- Filtre : aucun filtre sur is_active (colonne absente sur clients dans ce schéma)
-- Colonnes sélectionnées : identité client, coordonnées, données site
-- Optimisation : index implicite sur sites.client_id (FK PostgreSQL)
-- Colonnes volontairement absentes (schéma actuel) :
--   - c.telephone : supprimé de `clients` par la migration 060, déplacé vers
--     le modèle Contact (rôle "client") — hors scope de cette extraction.
--   - s.type_site : n'a jamais existé dans le schéma Nexo, aucun équivalent.

SELECT
    c.id            AS client_id,
    c.nom           AS raison_sociale,
    c.email         AS client_email,
    c.adresse       AS client_adresse,
    s.id            AS site_id,
    s.nom           AS site_nom,
    s.adresse       AS site_adresse,
    s.ville         AS site_ville,
    s.code_postal   AS site_code_postal,
    c.created_at    AS client_created_at
FROM clients c
LEFT JOIN sites s ON s.client_id = c.id
ORDER BY c.id, s.id;
"""

SQL_INTERVENTIONS_PAR_CLIENT = """
-- Requête C2 — Agrégation interventions par client
-- Objectif : compter les interventions passées par client pour scoring
-- Jointure : clients → sites → interventions (chaîne de 3 tables)
-- Filtre : interventions passées uniquement (date_debut < NOW())
-- Agrégation : COUNT avec GROUP BY pour éviter les doublons
-- Optimisation : index sur interventions.site_id (migration 019 Nexo)
--               + index sur interventions.date_debut pour le filtre temporel

SELECT
    c.id                            AS client_id,
    c.nom                           AS raison_sociale,
    COUNT(i.id)                     AS nb_interventions_total,
    COUNT(CASE WHEN i.statut = 'termine' THEN 1 END)
                                    AS nb_interventions_terminees,
    MAX(i.date_debut)               AS derniere_intervention
FROM clients c
LEFT JOIN sites s ON s.client_id = c.id
LEFT JOIN interventions i ON i.site_id = s.id
    AND i.date_debut < NOW()
GROUP BY c.id, c.nom
ORDER BY nb_interventions_total DESC;
"""

SQL_EMPLOYES_ACTIFS = """
-- Requête C2 — Extraction employés actifs
-- Objectif : récupérer les salariés pour croisement avec données legacy CSV
-- Filtre : is_active = true (exclut les comptes désactivés)
-- Colonnes : identité uniquement — pas de données sensibles (mot de passe, titre séjour)
-- Optimisation : pas d'index spécifique nécessaire (table petite)

SELECT
    e.id,
    e.nom,
    e.prenom,
    e.email,
    e.poste,
    e.tournee,
    e.type_contrat,
    e.date_embauche,
    e.created_at
FROM employes e
JOIN users u ON u.id = e.user_id
WHERE u.is_active = true
ORDER BY e.nom, e.prenom;
"""


def extract_from_postgres() -> pd.DataFrame:
    """
    Extrait les données depuis PostgreSQL Nexo.
    Lève une exception si l'extraction échoue — aucun fallback silencieux.
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL non défini dans .env")

    try:
        import psycopg2
        import psycopg2.extras

        logger.info(f"Connexion à PostgreSQL : {DATABASE_URL[:30]}...")
        conn = psycopg2.connect(DATABASE_URL)

        logger.info("Exécution requête : clients avec sites")
        df_clients = pd.read_sql(SQL_CLIENTS_AVEC_SITES, conn)
        logger.info(f"  → {len(df_clients)} lignes clients/sites")

        logger.info("Exécution requête : interventions par client")
        df_interventions = pd.read_sql(SQL_INTERVENTIONS_PAR_CLIENT, conn)
        logger.info(f"  → {len(df_interventions)} lignes agrégées")

        # Jointure des deux DataFrames sur client_id
        # Optimisation : merge sur index pour éviter scan complet
        df_final = df_clients.merge(
            df_interventions[["client_id", "nb_interventions_total", "derniere_intervention"]],
            on="client_id",
            how="left"
        )

        conn.close()
        logger.info("Connexion PostgreSQL fermée proprement")
        return df_final

    except Exception:
        logger.error("Extraction PostgreSQL échouée", exc_info=True)
        raise


def main():
    logger.info("=== Démarrage extraction base de données Nexo ===")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = extract_from_postgres()
    df["source"] = "postgresql_nexo"

    logger.info(f"Lignes extraites : {len(df)}")
    logger.info(f"Colonnes : {list(df.columns)}")

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    logger.info(f"Fichier sauvegardé : {OUTPUT_FILE}")
    logger.info("=== Extraction BDD terminée ===")


if __name__ == "__main__":
    main()
