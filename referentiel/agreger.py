"""Point de lancement de l'agrégation (C3) : `python -m referentiel.agreger`.

Lit la dernière extraction complète (`data/brut/<horodatage>/`, code de sortie 0 dans son
manifeste) et écrit le référentiel dans `data/propre/<même horodatage>/` : clients.csv,
sites.csv, contacts.csv, rejets.csv et rapport.json.
Codes de sortie : 0 = référentiel produit ; 1 = fichier source manquant ; 2 = aucune extraction
complète disponible.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from referentiel.agregation import agreger
from referentiel.config import Reglages

journal = logging.getLogger("referentiel.agreger")
SOURCES = [
    "nexo_clients",
    "nexo_sites",
    "nexo_contacts",
    "api_geocodage_sites",
    "api_entreprises_clients",
    "fichier_coproprietes",
]


def derniere_extraction_complete(dossier_brut: Path) -> Path | None:
    for dossier in sorted(dossier_brut.glob("*"), reverse=True):
        manifeste = dossier / "manifeste.json"
        if manifeste.exists() and json.loads(manifeste.read_text())["code_sortie"] == 0:
            return dossier
    return None


def lancer(entree: Path, sortie: Path) -> int:
    sources = {}
    for nom in SOURCES:
        fichier = entree / f"{nom}.csv"
        if not fichier.exists():
            journal.error("fichier source manquant : %s", fichier)
            return 1
        # Lecture en texte : les codes postaux, SIRET et téléphones gardent leurs zéros.
        sources[nom] = pd.read_csv(fichier, dtype=str, keep_default_na=False, na_values=[""])
    tables, rapport = agreger(sources)
    sortie.mkdir(parents=True, exist_ok=True)
    for nom, df in tables.items():
        df.to_csv(sortie / f"{nom}.csv", index=False, encoding="utf-8")
    rapport["extraction"] = entree.name
    (sortie / "rapport.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    journal.info("référentiel : %s ; rejets : %d", rapport["sorties"], len(tables["rejets"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agrégation du référentiel clients")
    parser.add_argument(
        "--brut", type=Path, help="dossier d'extraction (défaut : la dernière complète)"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    reglages = Reglages()
    entree = args.brut or derniere_extraction_complete(reglages.dossier_donnees / "brut")
    if entree is None:
        journal.error(
            "aucune extraction complète (code 0) dans %s", reglages.dossier_donnees / "brut"
        )
        return 2
    return lancer(entree, reglages.dossier_donnees / "propre" / entree.name)


if __name__ == "__main__":
    sys.exit(main())
