"""Règles de nettoyage et d'homogénéisation des formats (C3).

Fonctions pures, sans effet de bord : chacune prend une valeur brute et renvoie la valeur
normalisée, ou None si la valeur est absente ou invalide (jamais une valeur inventée).
"""

import math
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

ABREVIATIONS_VOIES = {
    "AV": "AVENUE",
    "AVE": "AVENUE",
    "BD": "BOULEVARD",
    "BLD": "BOULEVARD",
    "BLVD": "BOULEVARD",
    "R": "RUE",
    "PL": "PLACE",
    "CH": "CHEMIN",
    "CHE": "CHEMIN",
    "ALL": "ALLEE",
    "IMP": "IMPASSE",
    "QU": "QUAI",
    "RTE": "ROUTE",
    "CRS": "COURS",
    "SQ": "SQUARE",
    "PAS": "PASSAGE",
    "ST": "SAINT",
    "STE": "SAINTE",
    "FG": "FAUBOURG",
    "FBG": "FAUBOURG",
}
MOTIF_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


def absent(valeur) -> bool:
    if valeur is None:
        return True
    if isinstance(valeur, float) and math.isnan(valeur):
        return True
    return valeur is pd.NA or (isinstance(valeur, str) and not valeur.strip())


def texte(valeur) -> str | None:
    """Espaces de début et de fin retirés, espaces multiples réduits à un seul."""
    if absent(valeur):
        return None
    return re.sub(r"\s+", " ", str(valeur)).strip()


def sans_accents(valeur: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", valeur) if unicodedata.category(c) != "Mn"
    )


def cle_texte(valeur) -> str:
    """Clé de comparaison : majuscules, sans accents ni ponctuation, abréviations de voie
    développées. « 10 bd du 11-Novembre » et « 10 Boulevard du 11 Novembre » donnent la même clé."""
    t = texte(valeur)
    if t is None:
        return ""
    mots = re.sub(r"[^A-Z0-9]+", " ", sans_accents(t).upper()).split()
    return " ".join(ABREVIATIONS_VOIES.get(m, m) for m in mots)


def similarite(a, b) -> float:
    ka, kb = cle_texte(a), cle_texte(b)
    if not ka or not kb:
        return 0.0
    return round(SequenceMatcher(None, ka, kb).ratio(), 3)


def code_postal(valeur) -> str | None:
    """5 chiffres ; un code à 4 chiffres (zéro initial perdu par un tableur) est complété."""
    if absent(valeur):
        return None
    chiffres = re.sub(r"\D", "", str(valeur).split(".")[0])
    if len(chiffres) == 4:
        chiffres = "0" + chiffres
    return chiffres if len(chiffres) == 5 else None


def luhn(chiffres: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def siret(valeur) -> str | None:
    """14 chiffres et clé de Luhn valide (exception : établissements de La Poste, SIREN
    356000000, dont la somme des chiffres est un multiple de 5)."""
    if absent(valeur):
        return None
    chiffres = re.sub(r"\D", "", str(valeur))
    if len(chiffres) != 14:
        return None
    if chiffres.startswith("356000000"):
        return chiffres if sum(map(int, chiffres)) % 5 == 0 else None
    return chiffres if luhn(chiffres) else None


def telephone(valeur) -> str | None:
    """Format international E.164 (+33XXXXXXXXX) pour les numéros français à 10 chiffres."""
    if absent(valeur):
        return None
    chiffres = re.sub(r"\D", "", str(valeur))
    if chiffres.startswith("0033"):
        chiffres = "0" + chiffres[4:]
    elif chiffres.startswith("33") and len(chiffres) == 11:
        chiffres = "0" + chiffres[2:]
    if len(chiffres) == 10 and chiffres.startswith("0") and chiffres[1] != "0":
        return "+33" + chiffres[1:]
    return None


def email(valeur) -> str | None:
    t = texte(valeur)
    if t is None:
        return None
    t = t.lower()
    return t if MOTIF_EMAIL.match(t) else None


def date_iso(valeur) -> str | None:
    if absent(valeur):
        return None
    d = pd.to_datetime(str(valeur), errors="coerce", dayfirst=not re.match(r"^\d{4}-", str(valeur)))
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def nombre_entier(valeur) -> int | None:
    if absent(valeur):
        return None
    try:
        return int(float(str(valeur).replace(",", ".")))
    except ValueError:
        return None


def decimal(valeur, decimales: int = 3) -> float | None:
    """Nombre décimal (les fichiers bruts sont lus en texte : « 0.95 » ou « 0,95 »)."""
    if absent(valeur):
        return None
    try:
        return round(float(str(valeur).replace(",", ".")), decimales)
    except ValueError:
        return None


def coordonnee(valeur, minimum: float, maximum: float) -> float | None:
    if absent(valeur):
        return None
    try:
        x = float(str(valeur).replace(",", "."))
    except ValueError:
        return None
    return round(x, 6) if minimum <= x <= maximum else None


def distance_m(lat1, lon1, lat2, lon2) -> float | None:
    """Distance à vol d'oiseau en mètres (formule de haversine)."""
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (lat1, lon1, lat2, lon2)):
        return None
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)
