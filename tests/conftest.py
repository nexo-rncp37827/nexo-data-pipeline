import pytest

from referentiel.extraction import http


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    """Aucune vraie pause pendant les tests (nouvelles tentatives, cadence)."""
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
