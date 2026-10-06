"""Intégration de la base dédiée (C4) sur un vrai PostgreSQL 16 : création à partir du MPD,
comptes de moindre privilège, import, idempotence, synchronisation, annulation sur erreur.
Exécuté quand TEST_POSTGRES_ADMIN_URL est défini (CI) ; ignoré sinon."""

import os
import re
from pathlib import Path

import psycopg
import pytest

from referentiel import importer
from referentiel.agregation import agreger
from tests.test_agregation import sources_fictives

ADMIN = os.environ.get("TEST_POSTGRES_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN, reason="TEST_POSTGRES_ADMIN_URL non défini")
RACINE = Path(__file__).resolve().parents[1]
BASE = "referentiel"


def sql_des_roles() -> str:
    script = (RACINE / "sql/referentiel/02_roles.sh").read_text()
    sql = re.search(r"<<'SQL'\n(.*?)\nSQL", script, re.S).group(1)
    return sql.replace(":'mdp_import'", "'imp'").replace(":'mdp_api'", "'api'")


@pytest.fixture
def base():
    with psycopg.connect(ADMIN, autocommit=True) as cnx:
        cnx.execute(f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)")
        for role in ("referentiel_import", "referentiel_api"):
            cnx.execute(f"DROP ROLE IF EXISTS {role}")
        cnx.execute(f"CREATE DATABASE {BASE}")
    admin = psycopg.conninfo.make_conninfo(ADMIN, dbname=BASE)
    with psycopg.connect(admin, autocommit=True) as cnx:
        cnx.execute((RACINE / "sql/referentiel/01_schema.sql").read_text())
        cnx.execute(sql_des_roles())
    return {
        "admin": admin,
        "import": psycopg.conninfo.make_conninfo(
            ADMIN, dbname=BASE, user="referentiel_import", password="imp"
        ),
        "api": psycopg.conninfo.make_conninfo(
            ADMIN, dbname=BASE, user="referentiel_api", password="api"
        ),
    }


def ecrire_referentiel(dossier: Path, sources=None) -> Path:
    tables, _ = agreger(sources or sources_fictives())
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, df in tables.items():
        df.to_csv(dossier / f"{nom}.csv", index=False)
    return dossier


def contenu(url) -> dict:
    with psycopg.connect(url) as cnx:
        return {
            t: cnx.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
            for t in ("client", "site", "copropriete", "contact", "contact_site")
        }


def sans_horodatage(d: dict) -> dict:
    """Contenu des tables sans la colonne importe_le (dernière colonne)."""
    return {t: [r if t == "contact_site" else r[:-1] for r in v] for t, v in d.items()}


def test_mpd_cree_la_base_sans_erreur(base):
    with psycopg.connect(base["admin"]) as cnx:
        tables = {
            r[0]
            for r in cnx.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
    assert {
        "client",
        "site",
        "copropriete",
        "contact",
        "contact_site",
        "import",
        "v_site",
    } <= tables


def test_import_puis_idempotence(base, tmp_path):
    dossier = ecrire_referentiel(tmp_path / "20261006T102355Z")
    with psycopg.connect(base["import"]) as cnx:
        bilan = importer.importer(cnx, dossier)
    assert bilan["nb_clients"] == 3 and bilan["nb_sites"] == 2 and bilan["nb_coproprietes"] == 1
    avant = contenu(base["admin"])
    with psycopg.connect(base["import"]) as cnx:
        importer.importer(cnx, dossier)
    apres = contenu(base["admin"])
    assert sans_horodatage(avant) == sans_horodatage(apres)
    with psycopg.connect(base["api"]) as cnx:
        ligne = cnx.execute(
            "SELECT client_est_syndic, nombre_total_lots FROM v_site WHERE site_id = 10"
        ).fetchone()
        journal = cnx.execute("SELECT 1").fetchone()
    assert ligne == (True, 40) and journal == (1,)
    with psycopg.connect(base["admin"]) as cnx:
        statuts = [r[0] for r in cnx.execute("SELECT statut FROM import ORDER BY import_id")]
    assert statuts == ["ok", "ok"]


def test_synchronisation_supprime_les_absents(base, tmp_path):
    with psycopg.connect(base["import"]) as cnx:
        importer.importer(cnx, ecrire_referentiel(tmp_path / "a"))
    sources = sources_fictives()
    sources["nexo_clients"] = sources["nexo_clients"][sources["nexo_clients"]["client_id"] != "3"]
    with psycopg.connect(base["import"]) as cnx:
        bilan = importer.importer(cnx, ecrire_referentiel(tmp_path / "b", sources))
    assert bilan["nb_supprimes"] == 1
    with psycopg.connect(base["admin"]) as cnx:
        assert [r[0] for r in cnx.execute("SELECT client_id FROM client ORDER BY 1")] == [1, 2]


def test_erreur_rien_n_est_modifie(base, tmp_path):
    with psycopg.connect(base["import"]) as cnx:
        importer.importer(cnx, ecrire_referentiel(tmp_path / "a"))
    avant = contenu(base["admin"])
    dossier = ecrire_referentiel(tmp_path / "b")
    (dossier / "clients.csv").write_text(
        (dossier / "clients.csv").read_text().replace("12345678900015", "123")  # SIRET invalide
    )
    with psycopg.connect(base["import"]) as cnx, pytest.raises(psycopg.errors.CheckViolation):
        importer.importer(cnx, dossier)
    assert contenu(base["admin"]) == avant
    with psycopg.connect(base["admin"]) as cnx:
        assert cnx.execute("SELECT statut FROM import ORDER BY import_id DESC").fetchone() == (
            "echec",
        )


def test_comptes_de_moindre_privilege(base):
    with psycopg.connect(base["api"]) as cnx, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        cnx.execute("DELETE FROM contact")
    with psycopg.connect(base["api"]) as cnx, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cnx.execute("SELECT * FROM import")
    with (
        psycopg.connect(base["import"]) as cnx,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        cnx.execute("DROP TABLE contact")


def test_cli(base, tmp_path, monkeypatch):
    ecrire_referentiel(tmp_path / "propre" / "20261006T102355Z")
    monkeypatch.setenv("REFERENTIEL_DATABASE_URL", base["import"])
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path))
    assert importer.main([]) == 0
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path / "vide"))
    assert importer.main([]) == 2


def test_purge_du_journal_des_imports(base, tmp_path, monkeypatch):
    from referentiel import purger

    with psycopg.connect(base["admin"]) as cnx:
        cnx.execute(
            "INSERT INTO import (extraction, debut, statut) VALUES "
            "('ancien', now() - interval '400 days', 'ok'), ('recent', now(), 'ok')"
        )
    monkeypatch.setenv("REFERENTIEL_DATABASE_URL", base["import"])
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path))
    assert purger.main([]) == 0
    with psycopg.connect(base["admin"]) as cnx:
        assert [r[0] for r in cnx.execute("SELECT extraction FROM import")] == ["recent"]


def test_textes_longs_du_registre_acceptes(base, tmp_path):
    """Régression (06/10, données réelles) : texte du registre de plus de 30 caractères."""
    sources = sources_fictives()
    long = "Mandat en cours (valeur longue du registre national)"
    sources["fichier_coproprietes"]["mandat_en_cours"] = long
    with psycopg.connect(base["import"]) as cnx:
        importer.importer(cnx, ecrire_referentiel(tmp_path / "a", sources))
    with psycopg.connect(base["admin"]) as cnx:
        assert cnx.execute("SELECT mandat_en_cours FROM copropriete").fetchone() == (long,)


def test_message_d_erreur_nomme_la_table(base, tmp_path, monkeypatch, caplog):
    dossier = ecrire_referentiel(tmp_path / "propre" / "x")
    (dossier / "clients.csv").write_text(
        (dossier / "clients.csv").read_text().replace("12345678900015", "123")
    )
    monkeypatch.setenv("REFERENTIEL_DATABASE_URL", base["import"])
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path))
    assert importer.main([]) == 1
    assert "table client" in caplog.text
