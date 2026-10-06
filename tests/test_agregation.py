"""Tests de l'agrégation (C3) sur des données fictives, au format des fichiers bruts (texte)."""

import json

import pandas as pd
import pytest

from referentiel import agregation as a
from referentiel import agreger

SIRET_REGIE = "12345678900015"  # SIREN 123456789
SIRET_AUTRE = "98765432100015"
SIRET_SYNDIC_TIERS = "55555555500013"
LAT, LON = 45.760000, 4.850000


def df(lignes):
    return pd.DataFrame(lignes).astype(object).where(pd.DataFrame(lignes).notna(), None)


def copro(numero, lat=LAT, lon=LON, siret=SIRET_REGIE, adresse="10 Rue de l'Exemple", **k):
    return {
        "numero_immatriculation": numero,
        "date_immatriculation": "2017-01-01",
        "date_derniere_maj": k.get("maj", "2026-01-01"),
        "type_syndic": "professionnel",
        "raison_sociale_representant_legal": "SYNDIC",
        "siret_representant_legal": siret,
        "code_ape": "6832A",
        "mandat_en_cours": "Oui",
        "nom_usage_copropriete": "RESIDENCE",
        "adresse_reference": adresse,
        "numero_voie_adresse": "10",
        "code_postal_adresse": "69003",
        "commune_adresse": "Lyon",
        "commune": "69383",
        "longitude": str(lon),
        "latitude": str(lat),
        "nombre_total_lots": "40",
        "nombre_lots_habitation": "30",
    }


def geo(site_id, lat=LAT, lon=LON, score="0.95", statut="ok", type_="housenumber"):
    return {
        "site_id": str(site_id),
        "statut": statut,
        "adresse_normalisee": "10 Rue de l'Exemple 69003 Lyon",
        "numero": "10",
        "voie": "Rue de l'Exemple",
        "code_postal": "69003",
        "code_insee": "69383",
        "commune": "Lyon",
        "type_resultat": type_,
        "score": score,
        "longitude": str(lon),
        "latitude": str(lat),
    }


@pytest.fixture
def sources():
    return sources_fictives()


def sources_fictives():
    return {
        "nexo_clients": df(
            [
                {
                    "client_id": "1",
                    "nom": " Régie  Exemple ",
                    "type_client": "regie",
                    "siret": SIRET_REGIE,
                    "adresse": "1 rue A",
                    "code_postal": "69003",
                    "ville": "Lyon",
                    "statut": "Actif",
                    "date_creation": "2026-08-10",
                    "date_mise_a_jour": "2026-08-10",
                },
                {
                    "client_id": "2",
                    "nom": "Entreprise B",
                    "type_client": "entreprise",
                    "siret": "123",
                    "adresse": None,
                    "code_postal": None,
                    "ville": None,
                    "statut": "actif",
                    "date_creation": None,
                    "date_mise_a_jour": None,
                },
                {
                    "client_id": "3",
                    "nom": "Régie fermée",
                    "type_client": "regie",
                    "siret": SIRET_AUTRE,
                    "adresse": None,
                    "code_postal": None,
                    "ville": None,
                    "statut": "actif",
                    "date_creation": None,
                    "date_mise_a_jour": None,
                },
                {
                    "client_id": "4",
                    "nom": "  ",
                    "type_client": "regie",
                    "siret": None,
                    "adresse": None,
                    "code_postal": None,
                    "ville": None,
                    "statut": "actif",
                    "date_creation": None,
                    "date_mise_a_jour": None,
                },
            ]
        ),
        "api_entreprises_clients": df(
            [
                {
                    "client_id": "1",
                    "statut": "ok",
                    "denomination": "REGIE EXEMPLE",
                    "etat_etablissement": "A",
                    "activite_principale": "68.32A",
                    "nature_juridique": "5710",
                },
                {"client_id": "2", "statut": "siret_absent_ou_invalide"},
                {
                    "client_id": "3",
                    "statut": "ok",
                    "denomination": "REGIE FERMEE",
                    "etat_etablissement": "F",
                    "activite_principale": "68.32A",
                    "nature_juridique": "5710",
                },
            ]
        ),
        "nexo_sites": df(
            [
                {
                    "site_id": "10",
                    "client_id": "1",
                    "nom": "Résidence",
                    "adresse": "10 rue de l'exemple",
                    "code_postal": "69003",
                    "ville": "lyon",
                    "date_debut_contrat": "01/04/2024",
                    "date_fin_contrat": None,
                },
                {
                    "site_id": "11",
                    "client_id": "1",
                    "nom": "Introuvable",
                    "adresse": "rue inconnue",
                    "code_postal": "69003",
                    "ville": "Lyon",
                    "date_debut_contrat": None,
                    "date_fin_contrat": None,
                },
                {
                    "site_id": "12",
                    "client_id": "99",
                    "nom": "Orphelin",
                    "adresse": "x",
                    "code_postal": "69003",
                    "ville": "Lyon",
                    "date_debut_contrat": None,
                    "date_fin_contrat": None,
                },
                {
                    "site_id": "13",
                    "client_id": "1",
                    "nom": "Vide",
                    "adresse": " ",
                    "code_postal": None,
                    "ville": None,
                    "date_debut_contrat": None,
                    "date_fin_contrat": None,
                },
            ]
        ),
        "api_geocodage_sites": df([geo(10), {"site_id": "11", "statut": "non_trouve"}]),
        "nexo_contacts": df(
            [
                {
                    "contact_id": "1",
                    "client_id": "1",
                    "site_id": None,
                    "nom": "Contact Fictif",
                    "role": "Client",
                    "poste": None,
                    "email": "Contact@Exemple.fr",
                    "telephone_fixe": "04 78 00 00 00",
                    "telephone_portable": None,
                },
                {
                    "contact_id": "2",
                    "client_id": "1",
                    "site_id": None,
                    "nom": "contact  fictif",
                    "role": "client",
                    "poste": None,
                    "email": "contact@exemple.fr",
                    "telephone_fixe": None,
                    "telephone_portable": None,
                },
                {
                    "contact_id": "3",
                    "client_id": "1",
                    "site_id": "10",
                    "nom": "Gardien",
                    "role": "gestionnaire_site",
                    "poste": None,
                    "email": "faux",
                    "telephone_fixe": None,
                    "telephone_portable": "123",
                },
                {
                    "contact_id": "4",
                    "client_id": "99",
                    "site_id": None,
                    "nom": "Orphelin",
                    "role": "client",
                    "poste": None,
                    "email": "o@exemple.fr",
                    "telephone_fixe": None,
                    "telephone_portable": None,
                },
                {
                    "contact_id": "5",
                    "client_id": "1",
                    "site_id": None,
                    "nom": None,
                    "role": "client",
                    "poste": None,
                    "email": "n@exemple.fr",
                    "telephone_fixe": None,
                    "telephone_portable": None,
                },
            ]
        ),
        "fichier_coproprietes": df(
            [
                copro("AA1", maj="2025-01-01"),
                copro("AA1", maj="2026-01-01"),  # doublon : la version la plus récente est gardée
                copro("BB2", lat=LAT + 0.01, siret=SIRET_SYNDIC_TIERS),  # à plus d'un km
                {**copro("CC3"), "numero_immatriculation": None},
            ]
        ),
    }


def test_referentiel_complet(sources):
    tables, rapport = a.agreger(sources)
    clients = tables["clients"].set_index("client_id")
    assert list(clients.index) == [1, 2, 3]
    assert clients.loc[1, "nom"] == "Régie Exemple" and clients.loc[1, "statut"] == "actif"
    assert (
        clients.loc[1, "verification_siret"] == "verifie" and clients.loc[1, "siren"] == "123456789"
    )
    assert clients.loc[1, "similarite_nom"] == 1.0
    assert clients.loc[2, "verification_siret"] == "siret_invalide"
    assert clients.loc[3, "etat_etablissement"] == "ferme"

    sites = tables["sites"].set_index("site_id")
    assert list(sites.index) == [10, 11]
    s10 = sites.loc[10]
    assert s10["geocodage"] == "fiable" and s10["rapprochement_copropriete"] == "correspondance"
    assert s10["numero_immatriculation"] == "AA1" and s10["nombre_total_lots"] == 40
    assert bool(s10["client_est_syndic"]) is True and s10["date_debut_contrat"] == "2024-04-01"
    assert sites.loc[11, "geocodage"] == "echec"
    assert sites.loc[11, "rapprochement_copropriete"] == "non_evalue"
    assert s10["adresse_copropriete"] == "10 Rue de l'Exemple"
    assert sites.loc[11, "adresse_saisie"] == "rue inconnue"

    contacts = tables["contacts"].set_index("contact_id")
    assert list(contacts.index) == [1]
    assert contacts.loc[1, "email"] == "contact@exemple.fr"
    assert contacts.loc[1, "telephone_fixe"] == "+33478000000"

    motifs = set(zip(tables["rejets"]["source"], tables["rejets"]["motif"], strict=True))
    assert ("clients", "identifiant ou nom absent") in motifs
    assert ("sites", "client inexistant ou écarté") in motifs
    assert ("sites", "ni adresse ni code postal") in motifs
    assert ("contacts", "doublon (même client, même personne, même site)") in motifs
    assert ("contacts", "aucune coordonnée valide") in motifs
    assert ("contacts", "nom absent") in motifs
    assert ("registre_coproprietes", "numéro d'immatriculation absent") in motifs
    assert ("registre_coproprietes", "doublon (version la plus récente gardée)") in motifs
    assert rapport["sorties"] == {"clients": 3, "sites": 2, "contacts": 1, "contacts_sites": 0}
    json.dumps(rapport)  # sérialisable


def site_fiable(**k):
    return {
        "geocodage": "fiable",
        "latitude": LAT,
        "longitude": LON,
        "numero": "10",
        "voie": "Rue de l'Exemple",
        **k,
    }


def candidats(*copros):
    t = a.coproprietes(df(list(copros)), a.Rejets())
    return [r for _, r in t.iterrows()]


def test_plusieurs_coproprietes_au_meme_point_ambigu():
    r = a.rapprocher(
        site_fiable(),
        candidats(copro("AA1", siret=SIRET_SYNDIC_TIERS), copro("BB2", siret=SIRET_AUTRE)),
        "123456789",
    )
    assert r["rapprochement_copropriete"] == "ambigu"
    assert r["immatriculations_candidates"] == "AA1;BB2"


def test_plusieurs_au_meme_point_departagees_par_le_syndic_client():
    r = a.rapprocher(
        site_fiable(),
        candidats(copro("AA1", siret=SIRET_SYNDIC_TIERS), copro("BB2", siret=SIRET_REGIE)),
        "123456789",
    )
    assert (
        r["rapprochement_copropriete"] == "correspondance" and r["numero_immatriculation"] == "BB2"
    )


def test_syndic_different_du_client_est_une_information():
    r = a.rapprocher(site_fiable(), candidats(copro("AA1", siret=SIRET_SYNDIC_TIERS)), "123456789")
    assert r["rapprochement_copropriete"] == "correspondance" and r["client_est_syndic"] is False


def test_candidat_proche_mais_adresse_differente_a_verifier():
    proche = copro("AA1", lat=LAT + 0.0003, adresse="2 Place Imaginaire")  # ≈ 33 m
    r = a.rapprocher(site_fiable(), candidats(proche), "123456789")
    assert r["rapprochement_copropriete"] == "a_verifier" and 25 < r["distance_copropriete_m"] < 45


def test_meme_adresse_un_peu_plus_loin_correspondance():
    decale = copro("AA1", lat=LAT + 0.0003)  # ≈ 33 m mais même adresse
    r = a.rapprocher(site_fiable(), candidats(decale), "123456789")
    assert r["rapprochement_copropriete"] == "correspondance"


def test_aucune_copropriete_a_proximite():
    loin = copro("AA1", lat=LAT + 0.01)
    assert a.rapprocher(site_fiable(), candidats(loin), None) == {
        "rapprochement_copropriete": "aucune"
    }


def test_qualite_geocodage():
    assert a.qualite_geocodage(None) == "echec"
    assert (
        a.qualite_geocodage({"statut": "ok", "type_resultat": "street", "score": 0.9})
        == "a_verifier"
    )
    assert (
        a.qualite_geocodage({"statut": "ok", "type_resultat": "housenumber", "score": 0.5})
        == "a_verifier"
    )


def test_incoherence_detectee(sources, monkeypatch):
    monkeypatch.setattr(
        a,
        "contacts",
        lambda b, c, s, r: (
            pd.DataFrame({"client_id": [999], "contact_id": [1]}),
            pd.DataFrame({"contact_id": [], "site_id": []}),
        ),
    )
    with pytest.raises(ValueError, match="incohérent"):
        a.agreger(sources)


# ── Point de lancement ───────────────────────────────────────────────────────


def ecrire_extraction(dossier, sources, code=0):
    dossier.mkdir(parents=True)
    for nom, d in sources.items():
        d.to_csv(dossier / f"{nom}.csv", index=False)
    (dossier / "manifeste.json").write_text(json.dumps({"code_sortie": code}))


def test_cli_derniere_extraction_complete(tmp_path, sources, monkeypatch):
    ecrire_extraction(tmp_path / "brut" / "20261006T100000Z", sources)
    ecrire_extraction(tmp_path / "brut" / "20261006T110000Z", sources, code=1)  # partielle
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path))
    assert agreger.main([]) == 0
    sortie = tmp_path / "propre" / "20261006T100000Z"
    rapport = json.loads((sortie / "rapport.json").read_text())
    assert rapport["extraction"] == "20261006T100000Z" and rapport["sorties"]["sites"] == 2
    sites = pd.read_csv(sortie / "sites.csv", dtype=str)
    assert sites.loc[0, "code_postal"] == "69003"


def test_cli_sans_extraction(tmp_path, monkeypatch):
    monkeypatch.setenv("DOSSIER_DONNEES", str(tmp_path))
    assert agreger.main([]) == 2


def test_cli_fichier_manquant(tmp_path, sources):
    ecrire_extraction(tmp_path / "x", {"nexo_clients": sources["nexo_clients"]})
    assert agreger.lancer(tmp_path / "x", tmp_path / "sortie") == 1


def test_syndic_sans_siret_benevole():
    """Régression (06/10, données réelles) : SIRET du syndic absent (NaN avec pandas 3)."""
    benevole = {**copro("AA1"), "siret_representant_legal": None, "type_syndic": "bénévole"}
    autre = copro("BB2", siret=SIRET_SYNDIC_TIERS)
    r = a.rapprocher(site_fiable(), candidats(benevole, autre), "123456789")
    assert r["rapprochement_copropriete"] == "ambigu"
    r = a.rapprocher(site_fiable(), candidats(benevole), "123456789")
    assert r["rapprochement_copropriete"] == "correspondance"
    assert r["syndic_siret"] is None and r["client_est_syndic"] is None


def test_entiers_sans_decimale_dans_les_csv(tmp_path, sources):
    tables, _ = a.agreger(sources)
    tables["sites"].to_csv(tmp_path / "s.csv", index=False)
    texte = (tmp_path / "s.csv").read_text()
    assert ",40," in texte and "40.0" not in texte


def test_une_personne_suivant_plusieurs_sites_devient_un_contact_et_des_liens():
    clients_ = pd.DataFrame({"client_id": [1], "siren": ["123456789"]})
    sites_ = pd.DataFrame({"site_id": [10, 11]})
    brut = df(
        [
            {
                "contact_id": "5",
                "client_id": "1",
                "site_id": "11",
                "nom": "Gestionnaire Fictif",
                "role": "gestionnaire_site",
                "poste": None,
                "email": "g@exemple.fr",
                "telephone_fixe": None,
                "telephone_portable": None,
            },
            {
                "contact_id": "3",
                "client_id": "1",
                "site_id": "10",
                "nom": "gestionnaire fictif",
                "role": "gestionnaire_site",
                "poste": None,
                "email": "G@exemple.fr",
                "telephone_fixe": None,
                "telephone_portable": None,
            },
            {
                "contact_id": "7",
                "client_id": "1",
                "site_id": "10",
                "nom": "Gestionnaire Fictif",
                "role": "gestionnaire_site",
                "poste": None,
                "email": "g@exemple.fr",
                "telephone_fixe": None,
                "telephone_portable": None,
            },
            {
                "contact_id": "8",
                "client_id": "1",
                "site_id": "99",
                "nom": "Autre Fictif",
                "role": "client",
                "poste": None,
                "email": "autre@exemple.fr",
                "telephone_fixe": None,
                "telephone_portable": None,
            },
        ]
    )
    rejets = a.Rejets()
    personnes, liens = a.contacts(brut, clients_, sites_, rejets)
    assert list(personnes["contact_id"]) == [5, 8]
    assert sorted(map(tuple, liens.values.tolist())) == [(5, 10), (5, 11)]
    motifs = {(r["identifiant"], r["motif"]) for r in rejets.lignes}
    assert (7, "doublon (même client, même personne, même site)") in motifs
    assert (8, "site inexistant ou écarté") in motifs


def test_plusieurs_au_meme_point_departagees_par_l_adresse():
    voisine = {
        **copro("BB2", siret=SIRET_SYNDIC_TIERS, adresse="12 Rue de l'Exemple"),
        "numero_voie_adresse": "12",
    }
    r = a.rapprocher(site_fiable(), candidats(copro("AA1", siret=SIRET_SYNDIC_TIERS), voisine), "1")
    assert (
        r["rapprochement_copropriete"] == "correspondance" and r["numero_immatriculation"] == "AA1"
    )


def test_geocodage_incertain_rapprochement_a_verifier():
    r = a.rapprocher(site_fiable(geocodage="a_verifier"), candidats(copro("AA1")), "123456789")
    assert r["rapprochement_copropriete"] == "a_verifier" and r["numero_immatriculation"] == "AA1"


def test_score_adresse_numeros_differents_et_frontiere_de_mot():
    site = site_fiable()
    assert a.score_adresse(site, {"adresse_reference": "10 Rue de l'Exemple 69003 Lyon"}) == 1.0
    assert a.score_adresse(site, {"adresse_reference": "12 Rue de l'Exemple"}) == 0.0
    assert a.score_adresse(site, {"adresse_reference": "110 Rue de l'Exemple"}) == 0.0
    assert (
        a.score_adresse({**site, "numero": None}, {"adresse_reference": "Rue de l'Exemple"}) == 1.0
    )
    assert a.numero_principal("10 bis") == "10" and a.numero_principal(None) is None
