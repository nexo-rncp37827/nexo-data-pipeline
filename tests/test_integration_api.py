"""API (C5) sur un vrai PostgreSQL 16 : base créée par le MPD, référentiel importé, API connectée
avec le compte referentiel_api (lecture seule). Exécuté quand TEST_POSTGRES_ADMIN_URL est défini."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from referentiel import importer
from referentiel.api.app import app
from referentiel.config import reglages
from tests.test_api_securite import SECRET_NEXO, entete, jeton, reglages_test
from tests.test_integration_referentiel import (  # noqa: F401
    ADMIN,
    base,
    contenu,
    ecrire_referentiel,
)

pytestmark = pytest.mark.skipif(not ADMIN, reason="TEST_POSTGRES_ADMIN_URL non défini")


@pytest.fixture
def api(base, tmp_path):  # noqa: F811
    with psycopg.connect(base["import"]) as cnx:
        importer.importer(cnx, ecrire_referentiel(tmp_path / "propre"))
    r = reglages_test(referentiel_api_database_url=base["api"])
    app.dependency_overrides[reglages] = lambda: r
    client = TestClient(app)
    client.headers.update(entete(jeton(client, "nexo", SECRET_NEXO).json()["access_token"]))
    yield client, base
    app.dependency_overrides.clear()


def tout(client, route) -> list[dict]:
    """Parcourt toutes les pages d'une liste."""
    elements, decalage = [], 0
    while True:
        page = client.get(route, params={"limite": 2, "decalage": decalage}).json()
        elements += page["elements"]
        decalage += 2
        if decalage >= page["total"]:
            return elements


def test_l_api_restitue_l_ensemble_du_referentiel(api):
    client, bases = api
    attendu = contenu(bases["admin"])
    assert len(tout(client, "/clients")) == len(attendu["client"])
    assert len(tout(client, "/sites")) == len(attendu["site"])
    assert len(tout(client, "/contacts")) == len(attendu["contact"])
    assert len(tout(client, "/coproprietes")) == len(attendu["copropriete"])
    liens = sum(len(c["site_ids"]) for c in tout(client, "/contacts"))
    assert liens == len(attendu["contact_site"])


def test_detail_et_sous_ressources(api):
    client, _ = api
    premier = client.get("/clients").json()["elements"][0]
    cid = premier["client_id"]
    assert client.get(f"/clients/{cid}").json() == premier
    sites = client.get(f"/clients/{cid}/sites").json()["elements"]
    assert sites and all(s["client_id"] == cid for s in sites)
    site = client.get(f"/sites/{sites[0]['site_id']}").json()
    assert site["client_nom"] == premier["nom"] and "client_est_syndic" in site
    for c in client.get(f"/clients/{cid}/contacts").json()["elements"]:
        assert c["client_id"] == cid
        assert client.get(f"/contacts/{c['contact_id']}").json() == c
        for sid in c["site_ids"]:
            ids = [x["contact_id"] for x in client.get(f"/sites/{sid}/contacts").json()]
            assert c["contact_id"] in ids
    copro = client.get("/coproprietes").json()["elements"]
    if copro:
        num = copro[0]["numero_immatriculation"]
        assert client.get(f"/coproprietes/{num}").json() == copro[0]


def test_filtres(api):
    client, _ = api
    for statut in ("correspondance", "aucune"):
        sites = client.get("/sites", params={"rapprochement_copropriete": statut}).json()
        assert all(s["rapprochement_copropriete"] == statut for s in sites["elements"])
    regies = client.get("/clients", params={"type_client": "regie"}).json()["elements"]
    assert all(c["type_client"] == "regie" for c in regies)
    assert client.get("/clients", params={"type_client": "inconnu"}).status_code == 422
    assert client.get("/sites", params={"code_postal": "69'--"}).status_code == 422
    assert client.get("/clients", params={"limite": 501}).status_code == 422


def test_introuvable_404(api):
    client, _ = api
    for route in (
        "/clients/999999",
        "/clients/999999/sites",
        "/sites/999999",
        "/sites/999999/contacts",
        "/contacts/999999",
        "/coproprietes/ZZ0000000",
    ):
        assert client.get(route).status_code == 404, route


def test_sante(api):
    client, _ = api
    assert client.get("/sante").json() == {"statut": "ok", "base": "ok"}


def test_compte_de_l_api_ne_peut_pas_ecrire(api):
    _, bases = api
    with psycopg.connect(bases["api"]) as cnx, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        cnx.execute("DELETE FROM contact")
