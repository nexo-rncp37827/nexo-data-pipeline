"""Source 3 — fichier de données : Registre national d'immatriculation des copropriétés (ANAH).

CSV national (≈ 390 Mo, Licence Ouverte 2.0, actualisé chaque jour), lu en flux ligne à ligne :
seules les copropriétés situées dans les codes postaux des sites de Nexo sont conservées.

Minimisation : la colonne `identification_representant_legal` n'est jamais conservée, et le nom
du représentant légal n'est gardé que s'il a un SIRET (syndic professionnel) — un syndic
bénévole est une personne physique.
"""

import csv
import hashlib
import logging
from pathlib import Path

import httpx
import pandas as pd

from referentiel.extraction import ErreurSource

journal = logging.getLogger(__name__)

# Lien permanent data.gouv.fr vers la dernière version quotidienne du fichier.
URL_RNIC = "https://www.data.gouv.fr/api/1/datasets/r/3ea8e2c3-0038-464a-b17e-cd5c91f65ce2"

COLONNES = [
    "numero_immatriculation",
    "date_immatriculation",
    "date_derniere_maj",
    "type_syndic",
    "raison_sociale_representant_legal",
    "siret_representant_legal",
    "code_ape",
    "mandat_en_cours",
    "nom_usage_copropriete",
    "adresse_reference",
    "numero_voie_adresse",
    "code_postal_adresse",
    "commune_adresse",
    "commune",
    "longitude",
    "latitude",
    "nombre_total_lots",
    "nombre_lots_habitation",
]


def telecharger(destination: Path, transport: httpx.BaseTransport | None = None) -> Path:
    """Télécharge le fichier en flux (sans le charger en mémoire) dans un fichier temporaire,
    renommé seulement si le téléchargement est complet."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partiel = destination.with_suffix(".partiel")
    try:
        with httpx.Client(transport=transport, follow_redirects=True, timeout=60.0) as client:
            with client.stream("GET", URL_RNIC) as reponse:
                reponse.raise_for_status()
                if "html" in reponse.headers.get("content-type", ""):
                    raise ErreurSource("registre des copropriétés : page HTML reçue au lieu du CSV")
                with partiel.open("wb") as f:
                    for bloc in reponse.iter_bytes(1 << 20):
                        f.write(bloc)
    except httpx.HTTPError as exc:
        partiel.unlink(missing_ok=True)
        raise ErreurSource(f"registre des copropriétés : téléchargement en échec ({exc})") from exc
    partiel.replace(destination)
    return destination


def empreinte(fichier: Path) -> str:
    h = hashlib.sha256()
    with fichier.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def extraire(fichier: Path, codes_postaux: set[str]) -> tuple[pd.DataFrame, dict]:
    if not fichier.exists():
        raise ErreurSource(f"registre des copropriétés : fichier introuvable ({fichier})")
    with fichier.open(encoding="utf-8", newline="") as f:
        separateur = csv.Sniffer().sniff(f.readline(), delimiters=";,").delimiter
        f.seek(0)
        lecteur = csv.DictReader(f, delimiter=separateur)
        manquantes = [c for c in COLONNES if c not in (lecteur.fieldnames or [])]
        if manquantes:
            raise ErreurSource(f"registre des copropriétés : colonnes absentes {manquantes}")
        lues, gardees = 0, []
        for ligne in lecteur:
            lues += 1
            if (ligne.get("code_postal_adresse") or "").strip() not in codes_postaux:
                continue
            copro = {c: (ligne.get(c) or "").strip() or None for c in COLONNES}
            if not copro["siret_representant_legal"]:
                copro["raison_sociale_representant_legal"] = None
            gardees.append(copro)
    resultat = pd.DataFrame(gardees, columns=COLONNES)
    stats = {"lignes_lues": lues, "lignes_gardees": len(resultat), "separateur": separateur}
    journal.info("registre des copropriétés : %d lues, %d gardées", lues, len(resultat))
    return resultat, stats
