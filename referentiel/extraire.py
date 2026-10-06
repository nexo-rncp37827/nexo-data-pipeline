"""Point de lancement de l'extraction (C1) : `python -m referentiel.extraire`.

Enchaîne les trois sources, enregistre les données brutes et un manifeste dans
`data/brut/<horodatage>/`, et renvoie un code de sortie :
0 = toutes les sources extraites ; 1 = une source en échec ; 2 = configuration incomplète.
"""

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from referentiel.config import Reglages
from referentiel.extraction import ErreurSource, adresses, coproprietes, entreprises, nexo
from referentiel.extraction.http import en_erreur

journal = logging.getLogger("referentiel.extraire")


def configurer_journal() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )


def codes_postaux(sites: pd.DataFrame, geocodage: pd.DataFrame) -> set[str]:
    codes = set(sites["code_postal"].dropna().astype(str).str.strip())
    if "code_postal" in geocodage:
        codes |= set(geocodage["code_postal"].dropna().astype(str).str.strip())
    return {c for c in codes if c}


def lancer(reglages: Reglages, rnic_fichier: Path | None, sortie: Path | None) -> int:
    if not reglages.nexo_database_url:
        journal.error("NEXO_DATABASE_URL manquant : extraction impossible")
        return 2
    horodatage = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dossier = sortie or reglages.dossier_donnees / "brut" / horodatage
    dossier.mkdir(parents=True, exist_ok=True)
    manifeste = {"debut": horodatage, "sources": {}, "fichiers": {}}
    code = 0

    def etape(nom, fonction):
        nonlocal code
        debut = time.monotonic()
        try:
            resultat = fonction()
            manifeste["sources"][nom] = {"statut": "ok"}
            return resultat
        except ErreurSource as exc:
            journal.error("%s : %s", nom, exc)
            manifeste["sources"][nom] = {"statut": "echec", "erreur": str(exc)}
            code = 1
            return None
        finally:
            manifeste["sources"].setdefault(nom, {})["duree_s"] = round(time.monotonic() - debut, 2)

    def enregistrer(nom: str, df: pd.DataFrame) -> None:
        chemin = dossier / f"{nom}.csv"
        df.to_csv(chemin, index=False, encoding="utf-8")
        manifeste["fichiers"][nom] = {"lignes": len(df)}

    def bilan_api(nom: str, df: pd.DataFrame) -> None:
        """Lignes en erreur après nouvelles tentatives : extraction partielle, code 1."""
        nonlocal code
        source = manifeste["sources"][nom]
        source["statuts"] = df["statut"].value_counts().to_dict()
        lignes_en_erreur = int(en_erreur(df["statut"]).sum())
        if lignes_en_erreur:
            source["statut"] = "partiel"
            source["lignes_en_erreur"] = lignes_en_erreur
            journal.error(
                "%s : %d ligne(s) en erreur, relancer l'extraction", nom, lignes_en_erreur
            )
            code = 1

    donnees_nexo = etape("base_nexo", lambda: nexo.extraire(reglages.nexo_database_url))
    if donnees_nexo is None:
        journal.error("sans la base Nexo, les autres sources n'ont pas d'objet : arrêt")
    else:
        for nom, df in donnees_nexo.items():
            enregistrer(nom, df)
        geo = etape("api_geocodage", lambda: adresses.extraire(donnees_nexo["nexo_sites"]))
        if geo is not None:
            enregistrer("api_geocodage_sites", geo)
            bilan_api("api_geocodage", geo)
        ent = etape("api_entreprises", lambda: entreprises.extraire(donnees_nexo["nexo_clients"]))
        if ent is not None:
            enregistrer("api_entreprises_clients", ent)
            bilan_api("api_entreprises", ent)

        def fichier_rnic():
            chemin = rnic_fichier or coproprietes.telecharger(
                reglages.dossier_donnees / "sources" / f"rnic-{horodatage[:8]}.csv"
            )
            cps = codes_postaux(
                donnees_nexo["nexo_sites"], geo if geo is not None else pd.DataFrame()
            )
            df, stats = coproprietes.extraire(chemin, cps)
            stats.update({"fichier": chemin.name, "sha256": coproprietes.empreinte(chemin)})
            return df, stats

        rnic = etape("fichier_coproprietes", fichier_rnic)
        if rnic is not None:
            enregistrer("fichier_coproprietes", rnic[0])
            manifeste["sources"]["fichier_coproprietes"].update(rnic[1])

    manifeste["fin"] = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    manifeste["code_sortie"] = code
    (dossier / "manifeste.json").write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    journal.info("extraction terminée (code %d) : %s", code, dossier)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction des sources du référentiel clients")
    parser.add_argument("--rnic-fichier", type=Path, help="CSV du registre déjà téléchargé")
    parser.add_argument("--sortie", type=Path, help="dossier de sortie (défaut : data/brut/<date>)")
    args = parser.parse_args(argv)
    configurer_journal()
    return lancer(Reglages(), args.rnic_fichier, args.sortie)


if __name__ == "__main__":
    sys.exit(main())
