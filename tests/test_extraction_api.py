import httpx
import pandas as pd
import pytest

from referentiel.extraction import ErreurSource, adresses, entreprises

GEO_OK = {
    "features": [
        {
            "geometry": {"coordinates": [4.85, 45.76]},
            "properties": {
                "label": "10 Rue de l'Exemple 69003 Lyon",
                "housenumber": "10",
                "street": "Rue de l'Exemple",
                "postcode": "69003",
                "citycode": "69383",
                "city": "Lyon",
                "type": "housenumber",
                "score": 0.93,
            },
        }
    ]
}


def transport(gestionnaire):
    return httpx.MockTransport(gestionnaire)


def sites(*adresses_):
    return pd.DataFrame(
        [
            {"site_id": i, "adresse": a, "code_postal": "69003", "ville": "Lyon"}
            for i, a in enumerate(adresses_, 1)
        ]
    )


def test_geocodage_nominal():
    vus = []

    def g(req):
        vus.append(req.url)
        return httpx.Response(200, json=GEO_OK)

    res = adresses.extraire(sites("10 rue de l'exemple"), transport(g))
    ligne = res.iloc[0]
    assert ligne["statut"] == "ok" and ligne["code_insee"] == "69383" and ligne["score"] == 0.93
    assert vus[0].host == "data.geopf.fr" and vus[0].params["q"] == "10 rue de l'exemple 69003 Lyon"


def test_geocodage_adresse_inconnue_et_adresse_vide():
    vide = pd.DataFrame([{"site_id": 2, "adresse": " ", "code_postal": None, "ville": ""}])
    res = adresses.extraire(
        pd.concat([sites("rue qui n'existe pas"), vide]),
        transport(lambda r: httpx.Response(200, json={"features": []})),
    )
    assert list(res["statut"]) == ["non_trouve", "adresse_vide"]


def test_geocodage_429_puis_succes():
    reponses = iter(
        [httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(200, json=GEO_OK)]
    )
    res = adresses.extraire(sites("10 rue"), transport(lambda r: next(reponses)))
    assert res.iloc[0]["statut"] == "ok"


def test_geocodage_erreur_isolee_enregistree_sur_la_ligne():
    reponses = iter([httpx.Response(200, json=GEO_OK)] + [httpx.Response(503)] * 3)
    res = adresses.extraire(sites("10 rue", "12 rue"), transport(lambda r: next(reponses)))
    assert list(res["statut"]) == ["ok", "erreur_http_503"]


def test_geocodage_service_indisponible_est_un_echec_de_source():
    with pytest.raises(ErreurSource, match="géocodage"):
        adresses.extraire(sites("10 rue", "12 rue"), transport(lambda r: httpx.Response(500)))


def test_geocodage_timeout():
    def lent(req):
        raise httpx.ReadTimeout("trop long")

    with pytest.raises(ErreurSource):
        adresses.extraire(sites("10 rue"), transport(lent))


SIRET = "00000000000017"
ENT_OK = {
    "results": [
        {
            "siren": "000000000",
            "nom_raison_sociale": "REGIE FICTIVE",
            "nature_juridique": "5710",
            "activite_principale": "68.32A",
            "etat_administratif": "A",
            "siege": {
                "siret": SIRET,
                "est_siege": True,
                "etat_administratif": "A",
                "activite_principale": "68.32A",
                "adresse": "1 RUE FICTIVE 69003 LYON",
                "code_postal": "69003",
                "libelle_commune": "LYON",
            },
            "matching_etablissements": [],
        }
    ]
}


def clients(*sirets):
    return pd.DataFrame([{"client_id": i, "siret": s} for i, s in enumerate(sirets, 1)])


def test_siret_normalise_ou_rejete():
    assert entreprises.siret_valide("000 000 000 00017") == SIRET
    assert entreprises.siret_valide("123") is None
    assert entreprises.siret_valide(None) is None
    assert entreprises.siret_valide(float("nan")) is None


def test_entreprise_trouvee():
    res = entreprises.extraire(
        clients(SIRET), transport(lambda r: httpx.Response(200, json=ENT_OK))
    )
    ligne = res.iloc[0]
    assert ligne["statut"] == "ok" and ligne["etat_etablissement"] == "A"
    assert ligne["activite_principale"] == "68.32A" and ligne["est_siege"]


def test_entreprise_non_trouvee_et_siret_invalide_sans_appel():
    appels = []

    def g(req):
        appels.append(req)
        return httpx.Response(200, json={"results": []})

    res = entreprises.extraire(clients(SIRET, "12"), transport(g))
    assert list(res["statut"]) == ["non_trouve", "siret_absent_ou_invalide"]
    assert len(appels) == 1


def test_api_entreprises_indisponible():
    with pytest.raises(ErreurSource, match="Recherche d'entreprises"):
        entreprises.extraire(clients(SIRET), transport(lambda r: httpx.Response(502)))


def test_entreprises_echec_des_appels_meme_avec_un_siret_invalide():
    with pytest.raises(ErreurSource):
        entreprises.extraire(clients(SIRET, "12"), transport(lambda r: httpx.Response(503)))
