import pandas as pd
import psycopg
import pytest

from referentiel.extraction import ErreurSource, nexo


class Colonne:
    def __init__(self, nom):
        self.name = nom


class CurseurFactice:
    def __init__(self, journal, tables):
        self.journal, self.tables = journal, tables

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, requete):
        self.journal.append(requete)
        self.nom = next(n for n in self.tables if f"FROM {n} " in requete)
        cols, self.lignes = self.tables[self.nom]
        self.description = [Colonne(c) for c in cols]

    def fetchall(self):
        return self.lignes


class ConnexionFactice:
    def __init__(self, tables):
        self.journal, self.tables, self.read_only = [], tables, False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        assert self.read_only, "la transaction doit être en lecture seule"
        return CurseurFactice(self.journal, self.tables)


TABLES = {
    "clients": (["client_id", "nom"], [(1, "Régie A"), (2, "Régie B")]),
    "sites": (["site_id", "client_id"], [(10, 1)]),
    "contacts": (["contact_id", "nom"], []),
}


def test_trois_requetes_versionnees_executees_en_lecture_seule():
    cnx = ConnexionFactice(TABLES)
    res = nexo.extraire("postgresql://x", connecter=lambda url, **kw: cnx)
    assert set(res) == {"nexo_clients", "nexo_sites", "nexo_contacts"}
    assert len(res["nexo_clients"]) == 2 and isinstance(res["nexo_sites"], pd.DataFrame)
    assert cnx.journal == [nexo.lire_requete(f) for f in nexo.REQUETES.values()]


def test_requetes_sans_donnees_inutiles():
    sql = " ".join(
        ligne
        for f in nexo.REQUETES.values()
        for ligne in nexo.lire_requete(f).splitlines()
        if not ligne.strip().startswith("--")
    )
    for colonne in ("notes", "code_acces", "SELECT *"):
        assert colonne not in sql


def test_base_inaccessible_leve_une_erreur_de_source():
    def refus(url, **kw):
        raise psycopg.OperationalError("connexion refusée")

    with pytest.raises(ErreurSource, match="base Nexo inaccessible"):
        nexo.extraire("postgresql://x", connecter=refus)


def test_aucun_client_est_une_erreur():
    vide = dict(TABLES, clients=(["client_id", "nom"], []))
    with pytest.raises(ErreurSource, match="aucun client"):
        nexo.extraire("postgresql://x", connecter=lambda url, **kw: ConnexionFactice(vide))
