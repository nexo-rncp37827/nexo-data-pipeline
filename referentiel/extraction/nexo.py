"""Source 1 — base de données PostgreSQL de Nexo (clients, sites, contacts).

Connexion avec un compte en lecture seule ; chaque requête est lue dans un fichier SQL versionné
(dossier `sql/`), documenté et exécuté tel quel.
"""

import logging
from pathlib import Path

import pandas as pd
import psycopg

from referentiel.extraction import ErreurSource

journal = logging.getLogger(__name__)

DOSSIER_SQL = Path(__file__).resolve().parents[2] / "sql"
REQUETES = {
    "nexo_clients": "extraction_nexo_clients.sql",
    "nexo_sites": "extraction_nexo_sites.sql",
    "nexo_contacts": "extraction_nexo_contacts.sql",
}


def lire_requete(fichier: str) -> str:
    return (DOSSIER_SQL / fichier).read_text(encoding="utf-8")


def executer(connexion, requete: str) -> pd.DataFrame:
    with connexion.cursor() as curseur:
        curseur.execute(requete)
        colonnes = [c.name for c in curseur.description]
        df = pd.DataFrame(curseur.fetchall(), columns=colonnes)
    # Identifiants en entiers « nullables » (sinon un identifiant absent transforme la colonne
    # en nombres décimaux : 2 devient 2.0).
    for col in df.columns:
        if col.endswith("_id"):
            df[col] = df[col].astype("Int64")
    return df


def extraire(url: str, connecter=psycopg.connect) -> dict[str, pd.DataFrame]:
    """Exécute les trois requêtes dans une transaction en lecture seule."""
    try:
        with connecter(url, connect_timeout=10) as connexion:
            connexion.read_only = True
            resultats = {}
            for nom, fichier in REQUETES.items():
                resultats[nom] = executer(connexion, lire_requete(fichier))
                journal.info("%s : %d lignes", nom, len(resultats[nom]))
    except psycopg.Error as exc:
        # Le message de psycopg ne contient pas le mot de passe ; on n'affiche pas l'URL.
        raise ErreurSource(f"base Nexo inaccessible ou requête en échec : {exc}") from exc
    if resultats["nexo_clients"].empty:
        raise ErreurSource("base Nexo : aucun client extrait")
    return resultats
