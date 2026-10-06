"""Tests d'intégration sur un vrai PostgreSQL (schéma réel de Nexo, données fictives).

Exécutés quand TEST_POSTGRES_ADMIN_URL est défini (CI : service postgres:16) ; ignorés sinon.
Vérifient les requêtes SQL (C2), le compte en lecture seule et la mesure des plans.
"""

import os
from pathlib import Path

import psycopg
import pytest

from referentiel import plans
from referentiel.extraction import nexo

ADMIN = os.environ.get("TEST_POSTGRES_ADMIN_URL")
pytestmark = pytest.mark.skipif(not ADMIN, reason="TEST_POSTGRES_ADMIN_URL non défini")
RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def url_lecture():
    base = "nexo_test_referentiel"
    with psycopg.connect(ADMIN, autocommit=True) as cnx:
        cnx.execute(f"DROP DATABASE IF EXISTS {base}")
        cnx.execute("DROP ROLE IF EXISTS referentiel_lecture")
        cnx.execute(f"CREATE DATABASE {base}")
    admin_base = psycopg.conninfo.make_conninfo(ADMIN, dbname=base)
    with psycopg.connect(admin_base, autocommit=True) as cnx:
        cnx.execute((RACINE / "tests/donnees/schema_nexo_clientele.sql").read_text())
        cnx.execute((RACINE / "tests/donnees/jeu_nexo_fictif.sql").read_text())
        # Table hors périmètre : le compte du pipeline ne doit pas pouvoir la lire
        cnx.execute("CREATE TABLE users (id int, email text)")
        role = (RACINE / "sql/role_lecture_nexo.sql").read_text()
        role = role.replace(":'mdp'", "'test'").replace("nexo_db", base)
        cnx.execute(role)
    return psycopg.conninfo.make_conninfo(
        ADMIN, dbname=base, user="referentiel_lecture", password="test"
    )


def test_requetes_reelles(url_lecture):
    res = nexo.extraire(url_lecture)
    assert len(res["nexo_clients"]) == 2
    assert len(res["nexo_sites"]) == 3
    assert list(res["nexo_sites"]["type_client"]) == ["regie", "regie", "entreprise"]
    contacts = res["nexo_contacts"].set_index("nom")
    # Contact de site : son client est retrouvé par la jointure sur sites
    assert contacts.loc["Gardien Fictif", "client_id"] == 2
    assert "notes" not in res["nexo_clients"] and "code_acces" not in res["nexo_sites"]


def test_compte_lecture_seule(url_lecture):
    with psycopg.connect(url_lecture) as cnx:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            cnx.execute("DELETE FROM clients")
    with psycopg.connect(url_lecture) as cnx:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cnx.execute("SELECT email FROM users")


def test_mesure_des_plans(url_lecture, tmp_path, monkeypatch):
    monkeypatch.setenv("NEXO_DATABASE_URL", url_lecture)
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path))
    assert plans.main() == 0
    texte = next((tmp_path / "plans").glob("*.txt")).read_text()
    assert "ix_sites_client_id" in texte and "Execution Time" in texte
