import json
import os
import time

import pandas as pd

from referentiel import importer, purger


def vieillir(chemin, jours):
    t = time.time() - jours * 86400
    os.utime(chemin, (t, t))


def test_fichiers_de_plus_de_30_jours_sauf_la_derniere_extraction(tmp_path):
    for nom, code, age in (
        ("20260801T000000Z", 0, 60),
        ("20260802T000000Z", 0, 59),
        ("20260803T000000Z", 1, 58),
    ):
        d = tmp_path / "brut" / nom
        d.mkdir(parents=True)
        (d / "manifeste.json").write_text(json.dumps({"code_sortie": code}))
        (tmp_path / "propre" / nom).mkdir(parents=True)
        vieillir(d, age)
        vieillir(tmp_path / "propre" / nom, age)
    recent = tmp_path / "plans" / "recent.txt"
    recent.parent.mkdir()
    recent.write_text("x")
    supprimes = purger.purger_fichiers(tmp_path)
    restants = sorted(p.name for p in (tmp_path / "brut").iterdir())
    # La dernière extraction complète (02/08) est protégée, même ancienne ; la partielle part.
    assert restants == ["20260802T000000Z"]
    assert (tmp_path / "propre" / "20260802T000000Z").exists() and recent.exists()
    assert supprimes == 4


def test_contacts_conserves_fin_de_relation():
    clients = pd.DataFrame(
        {
            "client_id": ["1", "2", "3"],
            "statut": ["actif", "inactif", "inactif"],
            "date_mise_a_jour": ["2020-01-01", "2022-01-01", "2026-01-01"],
        }
    )
    contacts = pd.DataFrame({"contact_id": ["10", "20", "30"], "client_id": ["1", "2", "3"]})
    gardes, ecartes = importer.contacts_conserves(clients, contacts, "2026-10-06")
    assert list(gardes["contact_id"]) == ["10", "30"] and ecartes == 1


def test_configuration_incomplete(monkeypatch):
    monkeypatch.delenv("REFERENTIEL_DATABASE_URL", raising=False)
    monkeypatch.chdir("/")
    assert purger.main([]) == 2
