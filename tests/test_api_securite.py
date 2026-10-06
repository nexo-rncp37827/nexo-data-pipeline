"""API (C5) : authentification, autorisation et documentation, sans base de données."""

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from referentiel.api import secret as outil_secret
from referentiel.api import securite
from referentiel.api.app import app
from referentiel.api.exporter_openapi import main as exporter
from referentiel.config import ClientApi, Reglages, reglages

SECRET_JWT = "s" * 64
SECRET_NEXO = "secret-de-test-nexo-0123456789"
SECRET_STATS = "secret-de-test-stats-0123456789"


def reglages_test(**autres) -> Reglages:
    valeurs = {
        "referentiel_api_database_url": None,
        "api_jwt_secret": SECRET_JWT,
        "api_clients": [
            ClientApi(
                id="nexo",
                empreinte=securite.empreinte(SECRET_NEXO),
                portees=["referentiel", "contacts"],
            ),
            ClientApi(
                id="statistiques",
                empreinte=securite.empreinte(SECRET_STATS),
                portees=["referentiel"],
            ),
        ],
    }
    return Reglages(_env_file=None, **(valeurs | autres))


@pytest.fixture
def client():
    r = reglages_test()
    app.dependency_overrides[reglages] = lambda: r
    yield TestClient(app)
    app.dependency_overrides.clear()


def jeton(client, identifiant="nexo", secret=SECRET_NEXO, **autres):
    return client.post("/auth/jeton", data={"username": identifiant, "password": secret} | autres)


def entete(valeur):
    return {"Authorization": f"Bearer {valeur}"}


def test_empreinte_verifiee_et_sans_dollar():
    e = securite.empreinte("abc")
    assert "$" not in e and e.startswith("scrypt:")
    assert securite.verifier_secret("abc", e)
    assert not securite.verifier_secret("abd", e)
    assert not securite.verifier_secret("abc", "md5:xx")
    assert not securite.verifier_secret("abc", "mal-forme")


def test_jeton_delivre_avec_les_portees_du_client(client):
    rep = jeton(client)
    assert rep.status_code == 200
    corps = rep.json()
    assert corps["token_type"] == "bearer" and corps["expires_in"] == 1800
    charge = jwt.decode(
        corps["access_token"], SECRET_JWT, algorithms=["HS256"], audience="referentiel-api"
    )
    assert charge["sub"] == "nexo" and charge["scope"] == "referentiel contacts"
    assert charge["exp"] - charge["iat"] == 1800


@pytest.mark.parametrize(
    ("identifiant", "secret"), [("nexo", "mauvais"), ("inconnu", SECRET_NEXO), ("", "")]
)
def test_identifiants_invalides_refuses(client, identifiant, secret):
    rep = jeton(client, identifiant, secret)
    assert rep.status_code in (401, 422)
    assert "access_token" not in rep.text


def test_portee_non_autorisee_refusee_a_l_emission(client):
    assert jeton(client, "statistiques", SECRET_STATS, scope="contacts").status_code == 401
    assert jeton(client, scope="administration").status_code == 401
    assert jeton(client, scope="referentiel").json()["scope"] == "referentiel"


ROUTES_PROTEGEES = [
    "/clients",
    "/clients/1",
    "/clients/1/sites",
    "/clients/1/contacts",
    "/sites",
    "/sites/1",
    "/sites/1/contacts",
    "/coproprietes",
    "/coproprietes/AA1234567",
    "/contacts",
    "/contacts/1",
]


@pytest.mark.parametrize("route", ROUTES_PROTEGEES)
def test_sans_jeton_401(client, route):
    rep = client.get(route)
    assert rep.status_code == 401
    assert rep.headers["www-authenticate"].startswith("Bearer")


def test_jeton_expire_falsifie_ou_d_une_autre_audience(client):
    maintenant = datetime.now(UTC)
    base = {"iss": "referentiel-clients", "aud": "referentiel-api", "sub": "nexo"}
    base |= {"scope": "referentiel", "iat": maintenant}
    expire = jwt.encode(base | {"exp": maintenant - timedelta(seconds=1)}, SECRET_JWT)
    falsifie = jwt.encode(base | {"exp": maintenant + timedelta(minutes=5)}, "x" * 64)
    autre_aud = jwt.encode(
        base | {"aud": "autre", "exp": maintenant + timedelta(minutes=5)}, SECRET_JWT
    )
    sans_signature = jwt.encode(
        base | {"exp": maintenant + timedelta(minutes=5)}, None, algorithm="none"
    )
    assert client.get("/clients", headers=entete(expire)).json()["detail"] == "Jeton expiré"
    for valeur in (falsifie, autre_aud, sans_signature, "abc"):
        assert client.get("/clients", headers=entete(valeur)).status_code == 401


def test_contacts_exigent_la_portee_contacts(client):
    valeur = jeton(client, "statistiques", SECRET_STATS).json()["access_token"]
    for route in ("/contacts", "/contacts/1", "/clients/1/contacts", "/sites/1/contacts"):
        rep = client.get(route, headers=entete(valeur))
        assert rep.status_code == 403, route
        assert rep.json()["detail"] == "Portée insuffisante"


def test_jeton_valide_sans_base_503(client):
    valeur = jeton(client).json()["access_token"]
    rep = client.get("/clients", headers=entete(valeur))
    assert rep.status_code == 503


def test_secret_jwt_obligatoire_et_assez_long():
    for valeur in (None, "court"):
        with pytest.raises(RuntimeError):
            securite.secret_jwt(reglages_test(api_jwt_secret=valeur))


def test_sante_sans_authentification_ni_donnee(client):
    assert client.get("/sante").json() == {"statut": "degrade", "base": "non_configuree"}


def test_api_en_lecture_seule(client):
    valeur = jeton(client).json()["access_token"]
    for methode in ("post", "put", "patch", "delete"):
        rep = getattr(client, methode)("/clients", headers=entete(valeur))
        assert rep.status_code == 405


def test_specification_openapi_complete():
    spec = app.openapi()
    assert spec["openapi"].startswith("3.")
    assert spec["components"]["securitySchemes"]["OAuth2PasswordBearer"]["type"] == "oauth2"
    for chemin, operations in spec["paths"].items():
        for methode, op in operations.items():
            assert op.get("summary"), f"{methode} {chemin} sans résumé"
            protegee = chemin not in ("/auth/jeton", "/sante")
            assert bool(op.get("security")) == protegee, chemin
            if protegee:
                assert {"401", "403"} <= set(op["responses"]), chemin


def test_copie_versionnee_de_la_specification_a_jour():
    assert exporter(["--verifier"]) == 0


def test_outil_secret(monkeypatch, capsys):
    assert outil_secret.main(["jwt"]) == 0
    assert len(capsys.readouterr().out.strip().split("=", 1)[1]) == 64
    monkeypatch.setattr(outil_secret.getpass, "getpass", lambda _: "x" * 30)
    assert outil_secret.main(["client", "nexo", "referentiel", "contacts"]) == 0
    sortie = capsys.readouterr().out.strip()
    assert sortie.startswith("API_CLIENTS='") and "x" * 30 not in sortie
    entree = json.loads(sortie.split("=", 1)[1].strip("'"))[0]
    assert securite.verifier_secret("x" * 30, entree["empreinte"])
    assert entree["portees"] == ["referentiel", "contacts"]
    monkeypatch.setattr(outil_secret.getpass, "getpass", lambda _: "court")
    assert outil_secret.main(["client", "nexo", "referentiel"]) == 2


def test_clients_api_lus_depuis_l_environnement(monkeypatch):
    entree = [{"id": "nexo", "empreinte": securite.empreinte("y" * 30), "portees": ["referentiel"]}]
    monkeypatch.setenv("API_CLIENTS", json.dumps(entree))
    r = Reglages(_env_file=None)
    assert r.api_clients[0].id == "nexo" and r.api_jwt_minutes == 30
