"""Procédures de tri automatisées (C4, RGPD) : `python -m referentiel.purger`.

P3 — fichiers de travail (`data/brut`, `data/propre`, `data/plans`, `data/sources`) de plus de
     30 jours supprimés ; la dernière extraction complète et son référentiel sont toujours gardés.
P4 — journal des imports : lignes de plus d'un an supprimées.
Exécuté chaque semaine par `scripts/chaine_hebdomadaire.sh` (voir docs/RGPD.md).
Codes de sortie : 0 = tri effectué ; 1 = erreur ; 2 = configuration incomplète.
"""

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

import psycopg

from referentiel.agreger import derniere_extraction_complete
from referentiel.config import Reglages

journal = logging.getLogger("referentiel.purger")
DUREE_FICHIERS_JOURS = 30
DUREE_JOURNAL_IMPORTS = "1 year"


def fichiers_a_supprimer(dossier: Path, maintenant: float | None = None) -> list[Path]:
    maintenant = maintenant or time.time()
    limite = maintenant - DUREE_FICHIERS_JOURS * 86400
    proteges = set()
    derniere = derniere_extraction_complete(dossier / "brut")
    if derniere is not None:
        proteges = {derniere, dossier / "propre" / derniere.name}
    candidats = []
    for sous_dossier in ("brut", "propre", "plans", "sources"):
        for chemin in sorted((dossier / sous_dossier).glob("*")):
            if chemin not in proteges and chemin.stat().st_mtime < limite:
                candidats.append(chemin)
    return candidats


def purger_fichiers(dossier: Path, maintenant: float | None = None) -> int:
    supprimes = fichiers_a_supprimer(dossier, maintenant)
    for chemin in supprimes:
        shutil.rmtree(chemin) if chemin.is_dir() else chemin.unlink()
    return len(supprimes)


def purger_journal(connexion) -> int:
    with connexion.cursor() as cur:
        cur.execute(
            "DELETE FROM import WHERE debut < now() - %s::interval", (DUREE_JOURNAL_IMPORTS,)
        )
        return cur.rowcount


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Procédures de tri RGPD automatisées").parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    reglages = Reglages()
    if not reglages.referentiel_database_url:
        journal.error("REFERENTIEL_DATABASE_URL manquant")
        return 2
    try:
        bilan = {"fichiers": purger_fichiers(reglages.dossier_donnees)}
        with psycopg.connect(reglages.referentiel_database_url, connect_timeout=10) as cnx:
            bilan["journal_imports"] = purger_journal(cnx)
    except (OSError, psycopg.Error) as exc:
        journal.error("tri en échec : %s", exc)
        return 1
    journal.info("tri effectué : %s", json.dumps(bilan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
