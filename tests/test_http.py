import httpx

from referentiel.extraction import http


def client(gestionnaire):
    return http.client_http(httpx.MockTransport(gestionnaire))


def test_erreur_non_rejouee_400():
    appels = []

    def g(req):
        appels.append(req)
        return httpx.Response(400)

    with client(g) as c:
        assert http.get_json(c, "https://exemple.test/x", {}) == ("erreur_http_400", None)
    assert len(appels) == 1


def test_erreur_reseau_rejouee_puis_abandon():
    appels = []

    def g(req):
        appels.append(req)
        raise httpx.ConnectError("refus")

    with client(g) as c:
        assert http.get_json(c, "https://exemple.test/x", {}, tentatives=3) == (
            "erreur_reseau",
            None,
        )
    assert len(appels) == 3


def test_cadence(monkeypatch):
    pauses = []
    monkeypatch.setattr(http.time, "sleep", pauses.append)
    cad = http.Cadence(10)
    cad.attendre()
    cad.attendre()
    assert pauses and 0 < pauses[0] <= 0.1
