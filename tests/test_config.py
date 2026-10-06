from referentiel.config import Reglages


def test_variables_lues_depuis_l_environnement(monkeypatch):
    monkeypatch.setenv("NEXO_DATABASE_URL", "postgresql://lecture@nexo/nexo_db")
    monkeypatch.setenv("DOSSIER_DONNEES", "/tmp/donnees")
    r = Reglages(_env_file=None)
    assert r.nexo_database_url == "postgresql://lecture@nexo/nexo_db"
    assert str(r.dossier_donnees) == "/tmp/donnees"


def test_aucune_url_de_base_par_defaut(monkeypatch):
    monkeypatch.delenv("NEXO_DATABASE_URL", raising=False)
    monkeypatch.delenv("REFERENTIEL_DATABASE_URL", raising=False)
    r = Reglages(_env_file=None)
    assert r.nexo_database_url is None
    assert r.referentiel_database_url is None
