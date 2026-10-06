import json

import pandas as pd

from referentiel import extraire
from referentiel.config import Reglages
from referentiel.extraction import ErreurSource


def reglages(tmp_path, url="postgresql://x"):
    return Reglages(_env_file=None, nexo_database_url=url, dossier_donnees=tmp_path)


def nexo_factice(url):
    return {
        "nexo_clients": pd.DataFrame([{"client_id": 1, "siret": "00000000000017"}]),
        "nexo_sites": pd.DataFrame([{"site_id": 10, "client_id": 1, "code_postal": "69003"}]),
        "nexo_contacts": pd.DataFrame(columns=["contact_id"]),
    }


def brancher(monkeypatch, nexo=nexo_factice, geo=None, ent=None, copro=None):
    monkeypatch.setattr(extraire.nexo, "extraire", nexo)
    monkeypatch.setattr(
        extraire.adresses,
        "extraire",
        geo or (lambda s: pd.DataFrame([{"site_id": 10, "statut": "ok", "code_postal": "69003"}])),
    )
    monkeypatch.setattr(
        extraire.entreprises,
        "extraire",
        ent or (lambda c: pd.DataFrame([{"client_id": 1, "statut": "ok"}])),
    )
    monkeypatch.setattr(
        extraire.coproprietes,
        "extraire",
        copro
        or (
            lambda f, cps: (pd.DataFrame([{"numero_immatriculation": "AA1"}]), {"cps": sorted(cps)})
        ),
    )
    monkeypatch.setattr(extraire.coproprietes, "empreinte", lambda f: "0" * 64)


def test_extraction_complete(tmp_path, monkeypatch):
    brancher(monkeypatch)
    fichier = tmp_path / "rnic.csv"
    fichier.write_text("x")
    code = extraire.lancer(reglages(tmp_path), fichier, tmp_path / "sortie")
    assert code == 0
    m = json.loads((tmp_path / "sortie" / "manifeste.json").read_text())
    assert {s["statut"] for s in m["sources"].values()} == {"ok"}
    assert m["fichiers"]["nexo_clients"]["lignes"] == 1
    assert m["sources"]["fichier_coproprietes"]["cps"] == ["69003"]
    for nom in (
        "nexo_sites",
        "api_geocodage_sites",
        "api_entreprises_clients",
        "fichier_coproprietes",
    ):
        assert (tmp_path / "sortie" / f"{nom}.csv").exists()


def test_configuration_incomplete(tmp_path):
    assert extraire.lancer(reglages(tmp_path, url=None), None, None) == 2


def test_base_nexo_en_echec_arrete_tout(tmp_path, monkeypatch):
    def echec(url):
        raise ErreurSource("base Nexo inaccessible")

    brancher(monkeypatch, nexo=echec)
    code = extraire.lancer(reglages(tmp_path), None, tmp_path / "s")
    m = json.loads((tmp_path / "s" / "manifeste.json").read_text())
    assert code == 1 and m["sources"]["base_nexo"]["statut"] == "echec"
    assert "api_geocodage" not in m["sources"]


def test_une_api_en_echec_les_autres_continuent(tmp_path, monkeypatch):
    def echec(s):
        raise ErreurSource("API de géocodage : aucune réponse exploitable")

    brancher(monkeypatch, geo=echec)
    fichier = tmp_path / "rnic.csv"
    fichier.write_text("x")
    code = extraire.lancer(reglages(tmp_path), fichier, tmp_path / "s")
    m = json.loads((tmp_path / "s" / "manifeste.json").read_text())
    assert code == 1
    assert m["sources"]["api_geocodage"]["statut"] == "echec"
    assert m["sources"]["fichier_coproprietes"]["statut"] == "ok"


def test_main_lit_les_arguments(tmp_path, monkeypatch):
    vus = {}
    monkeypatch.setattr(extraire, "lancer", lambda r, f, s: vus.update(f=f, s=s) or 0)
    assert extraire.main(["--rnic-fichier", "a.csv", "--sortie", "b"]) == 0
    assert str(vus["f"]) == "a.csv" and str(vus["s"]) == "b"


def test_lignes_api_en_erreur_extraction_partielle(tmp_path, monkeypatch):
    brancher(
        monkeypatch,
        ent=lambda c: pd.DataFrame(
            [{"client_id": 1, "statut": "ok"}, {"client_id": 2, "statut": "erreur_http_503"}]
        ),
    )
    fichier = tmp_path / "rnic.csv"
    fichier.write_text("x")
    code = extraire.lancer(reglages(tmp_path), fichier, tmp_path / "s")
    m = json.loads((tmp_path / "s" / "manifeste.json").read_text())
    assert code == 1
    assert m["sources"]["api_entreprises"]["statut"] == "partiel"
    assert m["sources"]["api_entreprises"]["lignes_en_erreur"] == 1
