from pathlib import Path

import httpx
import pandas as pd
import pytest

from referentiel.extraction import ErreurSource, coproprietes

DONNEES = Path(__file__).parent / "donnees"


@pytest.mark.parametrize("fichier", ["rnic_point_virgule.csv", "rnic_virgule.csv"])
def test_filtre_par_code_postal_quel_que_soit_le_separateur(fichier):
    df, stats = coproprietes.extraire(DONNEES / fichier, {"69003"})
    assert stats["lignes_lues"] == 3 and stats["lignes_gardees"] == 2
    assert set(df["numero_immatriculation"]) == {"AA1111111", "AA2222222"}


def test_minimisation_syndic_benevole_et_identification():
    df, _ = coproprietes.extraire(DONNEES / "rnic_point_virgule.csv", {"69003"})
    assert "identification_representant_legal" not in df.columns
    pro = df.set_index("numero_immatriculation").loc["AA1111111"]
    benevole = df.set_index("numero_immatriculation").loc["AA2222222"]
    assert pro["raison_sociale_representant_legal"] == "REGIE FICTIVE"
    assert pd.isna(benevole["raison_sociale_representant_legal"])


def test_colonne_absente_format_change(tmp_path):
    f = tmp_path / "rnic.csv"
    f.write_text('"numero_immatriculation";"code_postal_adresse"\n"X";"69003"\n', encoding="utf-8")
    with pytest.raises(ErreurSource, match="colonnes absentes"):
        coproprietes.extraire(f, {"69003"})


def test_fichier_absent(tmp_path):
    with pytest.raises(ErreurSource, match="introuvable"):
        coproprietes.extraire(tmp_path / "absent.csv", {"69003"})


def test_telechargement_complet_puis_renomme(tmp_path):
    contenu = (DONNEES / "rnic_virgule.csv").read_bytes()
    t = httpx.MockTransport(
        lambda r: httpx.Response(200, content=contenu, headers={"content-type": "text/csv"})
    )
    chemin = coproprietes.telecharger(tmp_path / "rnic.csv", t)
    assert chemin.read_bytes() == contenu
    assert not (tmp_path / "rnic.partiel").exists()
    assert len(coproprietes.empreinte(chemin)) == 64


def test_telechargement_page_html_refusee(tmp_path):
    t = httpx.MockTransport(
        lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(ErreurSource, match="HTML"):
        coproprietes.telecharger(tmp_path / "rnic.csv", t)
    assert not (tmp_path / "rnic.csv").exists()


def test_telechargement_erreur_http(tmp_path):
    t = httpx.MockTransport(lambda r: httpx.Response(404))
    with pytest.raises(ErreurSource, match="téléchargement"):
        coproprietes.telecharger(tmp_path / "rnic.csv", t)
    assert not list(tmp_path.iterdir())
