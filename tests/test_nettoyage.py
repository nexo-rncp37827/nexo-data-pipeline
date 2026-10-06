import math

import pytest

from referentiel import nettoyage as n


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("04 78 00 00 00", "+33478000000"),
        ("+33 6 12 34 56 78", "+33612345678"),
        ("0033612345678", "+33612345678"),
        ("06.12.34.56.78", "+33612345678"),
        ("612345678", None),
        ("0012345678", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_telephone_e164(brut, attendu):
    assert n.telephone(brut) == attendu


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        (" Contact@Exemple.FR ", "contact@exemple.fr"),
        ("pas-un-mail", None),
        ("a@b", None),
        ("", None),
    ],
)
def test_email(brut, attendu):
    assert n.email(brut) == attendu


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [("69003", "69003"), ("1000", "01000"), ("69003.0", "69003"), ("690", None), (None, None)],
)
def test_code_postal(brut, attendu):
    assert n.code_postal(brut) == attendu


def test_siret_cle_de_luhn():
    assert n.siret("123 456 789 00015") == "12345678900015"
    assert n.siret("12345678900016") is None  # clé fausse
    assert n.siret("123") is None
    assert n.siret("35600000000056") == "35600000000056"  # La Poste : somme multiple de 5


def test_cle_texte_abreviations_accents_ponctuation():
    assert n.cle_texte("10 bd du 11-Novembre") == n.cle_texte("10, Boulevard du 11 novembre")
    assert n.cle_texte("Rue de l'Église") == "RUE DE L EGLISE"
    assert n.cle_texte(None) == ""


def test_similarite():
    assert n.similarite("Régie Exemple", "REGIE EXEMPLE") == 1.0
    assert n.similarite("Régie Exemple", None) == 0.0
    assert 0 < n.similarite("Régie Exemple", "Régie Exemplaire") < 1


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("2026-10-06", "2026-10-06"),
        ("06/10/2026", "2026-10-06"),
        ("pas une date", None),
        (None, None),
    ],
)
def test_date_iso(brut, attendu):
    assert n.date_iso(brut) == attendu


def test_nombres_et_coordonnees():
    assert n.nombre_entier("40") == 40 and n.nombre_entier("40.0") == 40
    assert n.nombre_entier("x") is None and n.nombre_entier(None) is None
    assert n.coordonnee("45,76", 41, 51.5) == 45.76
    assert n.coordonnee("0", 41, 51.5) is None and n.coordonnee("abc", 41, 51.5) is None


def test_distance():
    # Place Bellecour → place des Terreaux, Lyon : environ 1,5 km
    d = n.distance_m(45.7578, 4.8320, 45.7675, 4.8336)
    assert 1000 < d < 1200
    assert n.distance_m(45.0, 4.0, 45.0, 4.0) == 0
    assert n.distance_m(None, 4.0, 45.0, 4.0) is None
    assert n.distance_m(math.nan, 4.0, 45.0, 4.0) is None


def test_texte():
    assert n.texte("  Régie   A  ") == "Régie A"
    assert n.texte("   ") is None


def test_decimal():
    assert n.decimal("0,953") == 0.953 and n.decimal("0.95") == 0.95
    assert n.decimal("x") is None and n.decimal(None) is None
