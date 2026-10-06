"""Agrégation des trois sources en un référentiel clients unique (C3).

Entrée : les données brutes d'une extraction (`data/brut/<horodatage>/`).
Sortie : trois tables liées par leurs identifiants — clients, sites, contacts — au même format,
plus la liste des entrées écartées et le motif de chaque rejet.

Enchaînement : 1. nettoyage de chaque source ; 2. suppression des entrées corrompues ;
3. jointure des résultats d'API (SIRET, géocodage) ; 4. rapprochement de chaque site avec sa
copropriété dans le registre ; 5. contrôle de cohérence final.
"""

from collections import defaultdict

import pandas as pd

from referentiel import nettoyage as n

SCORE_GEOCODAGE_FIABLE = 0.7  # score de l'API (0 à 1) à partir duquel l'adresse est retenue
DISTANCE_CERTAINE_M = 15  # même point d'adresse à la précision du géocodage près
DISTANCE_CANDIDAT_M = 50  # au-delà, ce n'est plus le même immeuble
SIMILARITE_ADRESSE = 0.85

COLONNES_CLIENTS = [
    "client_id",
    "nom",
    "type_client",
    "statut",
    "siret",
    "siren",
    "verification_siret",
    "denomination_officielle",
    "similarite_nom",
    "etat_etablissement",
    "activite_principale",
    "nature_juridique",
    "adresse",
    "code_postal",
    "ville",
    "date_creation",
    "date_mise_a_jour",
]
COLONNES_SITES = [
    "site_id",
    "client_id",
    "nom",
    "adresse_saisie",
    "code_postal_saisi",
    "ville_saisie",
    "adresse_normalisee",
    "numero",
    "voie",
    "code_postal",
    "code_insee",
    "commune",
    "latitude",
    "longitude",
    "score_geocodage",
    "geocodage",
    "date_debut_contrat",
    "date_fin_contrat",
    "rapprochement_copropriete",
    "distance_copropriete_m",
    "numero_immatriculation",
    "nom_usage_copropriete",
    "nombre_total_lots",
    "nombre_lots_habitation",
    "type_syndic",
    "syndic_raison_sociale",
    "syndic_siret",
    "mandat_en_cours",
    "client_est_syndic",
    "immatriculations_candidates",
]
COLONNES_CONTACTS = [
    "contact_id",
    "client_id",
    "site_id",
    "nom",
    "role",
    "poste",
    "email",
    "telephone_fixe",
    "telephone_portable",
]


class Rejets:
    def __init__(self):
        self.lignes = []

    def ajouter(self, source: str, identifiant, motif: str) -> None:
        self.lignes.append({"source": source, "identifiant": identifiant, "motif": motif})

    def tableau(self) -> pd.DataFrame:
        return pd.DataFrame(self.lignes, columns=["source", "identifiant", "motif"])


def entier(valeur):
    return None if n.absent(valeur) else int(float(valeur))


# ── Clients ──────────────────────────────────────────────────────────────────


def clients(brut: pd.DataFrame, entreprises: pd.DataFrame, rejets: Rejets) -> pd.DataFrame:
    api = {entier(r["client_id"]): r for _, r in entreprises.iterrows()}
    lignes = []
    for _, c in brut.iterrows():
        cid, nom = entier(c.get("client_id")), n.texte(c.get("nom"))
        if cid is None or nom is None:
            rejets.ajouter("clients", cid, "identifiant ou nom absent")
            continue
        siret = n.siret(c.get("siret"))
        e = api.get(cid)
        statut_api = None if e is None else e.get("statut")
        if siret is None:
            verification = "siret_invalide"
        elif statut_api == "ok":
            verification = "verifie"
        elif statut_api == "non_trouve":
            verification = "non_trouve"
        else:
            verification = "non_verifie"
        ok = verification == "verifie"
        etat = e.get("etat_etablissement") if ok else None
        lignes.append(
            {
                "client_id": cid,
                "nom": nom,
                "type_client": (n.texte(c.get("type_client")) or "").lower() or None,
                "statut": (n.texte(c.get("statut")) or "").lower() or None,
                "siret": siret,
                "siren": siret[:9] if siret else None,
                "verification_siret": verification,
                "denomination_officielle": n.texte(e.get("denomination")) if ok else None,
                "similarite_nom": n.similarite(nom, e.get("denomination")) if ok else None,
                "etat_etablissement": {"A": "actif", "F": "ferme"}.get(etat),
                "activite_principale": n.texte(e.get("activite_principale")) if ok else None,
                "nature_juridique": n.texte(e.get("nature_juridique")) if ok else None,
                "adresse": n.texte(c.get("adresse")),
                "code_postal": n.code_postal(c.get("code_postal")),
                "ville": n.texte(c.get("ville")),
                "date_creation": n.date_iso(c.get("date_creation")),
                "date_mise_a_jour": n.date_iso(c.get("date_mise_a_jour")),
            }
        )
    df = pd.DataFrame(lignes, columns=COLONNES_CLIENTS)
    return df.drop_duplicates("client_id")


# ── Registre des copropriétés ────────────────────────────────────────────────


def coproprietes(brut: pd.DataFrame, rejets: Rejets) -> pd.DataFrame:
    df = brut.copy()
    df["numero_immatriculation"] = df["numero_immatriculation"].map(n.texte)
    sans_numero = df["numero_immatriculation"].isna()
    for _ in range(int(sans_numero.sum())):
        rejets.ajouter("registre_coproprietes", None, "numéro d'immatriculation absent")
    df = df[~sans_numero].copy()
    df["date_derniere_maj"] = df["date_derniere_maj"].map(n.date_iso)
    df = df.sort_values("date_derniere_maj", na_position="first")
    avant = len(df)
    df = df.drop_duplicates("numero_immatriculation", keep="last")
    for _ in range(avant - len(df)):
        rejets.ajouter("registre_coproprietes", None, "doublon (version la plus récente gardée)")
    df["code_postal_adresse"] = df["code_postal_adresse"].map(n.code_postal)
    df["latitude"] = df["latitude"].map(lambda v: n.coordonnee(v, 41.0, 51.5))
    df["longitude"] = df["longitude"].map(lambda v: n.coordonnee(v, -5.5, 10.0))
    df["siret_representant_legal"] = df["siret_representant_legal"].map(n.siret)
    for col in ("nombre_total_lots", "nombre_lots_habitation"):
        df[col] = df[col].map(n.nombre_entier)
    return df.reset_index(drop=True)


def cle_adresse_site(site: dict) -> str:
    return n.cle_texte(f"{site.get('numero') or ''} {site.get('voie') or ''}")


def score_adresse(site: dict, copro) -> float:
    cle_site = cle_adresse_site(site)
    cle_copro = n.cle_texte(copro.get("adresse_reference"))
    if cle_site and cle_site in cle_copro:
        return 1.0
    return n.similarite(cle_site, cle_copro)


def rapprocher(site: dict, candidats: list, siren_client: str | None) -> dict:
    """Associe un site à sa copropriété. Renvoie le statut, la distance et la copropriété."""
    if site["geocodage"] != "fiable":
        return {"rapprochement_copropriete": "non_evalue"}
    notes = []
    for copro in candidats:
        d = n.distance_m(site["latitude"], site["longitude"], copro["latitude"], copro["longitude"])
        if d is None or d > DISTANCE_CANDIDAT_M:
            continue
        sim = score_adresse(site, copro)
        certain = d <= DISTANCE_CERTAINE_M or sim >= SIMILARITE_ADRESSE
        notes.append((certain, d, sim, copro))
    if not notes:
        return {"rapprochement_copropriete": "aucune"}
    certains = [x for x in notes if x[0]]
    if len(certains) > 1 and siren_client:
        # Plusieurs copropriétés au même point (syndicat principal et secondaires) :
        # on garde celle dont le syndic est le client, s'il y en a exactement une.
        meme_syndic = [
            x for x in certains if (x[3]["siret_representant_legal"] or "")[:9] == siren_client
        ]
        if len(meme_syndic) == 1:
            certains = meme_syndic
    if len(certains) == 1:
        statut, (_, d, _, copro) = "correspondance", certains[0]
    elif len(certains) > 1:
        numeros = sorted(x[3]["numero_immatriculation"] for x in certains)
        return {
            "rapprochement_copropriete": "ambigu",
            "immatriculations_candidates": ";".join(numeros),
        }
    else:
        statut, (_, d, _, copro) = "a_verifier", min(notes, key=lambda x: x[1])
    syndic = copro["siret_representant_legal"]
    return {
        "rapprochement_copropriete": statut,
        "distance_copropriete_m": d,
        "numero_immatriculation": copro["numero_immatriculation"],
        "nom_usage_copropriete": n.texte(copro.get("nom_usage_copropriete")),
        "nombre_total_lots": copro["nombre_total_lots"],
        "nombre_lots_habitation": copro["nombre_lots_habitation"],
        "type_syndic": n.texte(copro.get("type_syndic")),
        "syndic_raison_sociale": n.texte(copro.get("raison_sociale_representant_legal")),
        "syndic_siret": syndic,
        "mandat_en_cours": n.texte(copro.get("mandat_en_cours")),
        "client_est_syndic": (syndic[:9] == siren_client) if syndic and siren_client else None,
    }


# ── Sites ────────────────────────────────────────────────────────────────────


def qualite_geocodage(g) -> str:
    if g is None or g.get("statut") != "ok":
        return "echec"
    score = n.decimal(g.get("score"))
    if (
        g.get("type_resultat") == "housenumber"
        and score is not None
        and score >= SCORE_GEOCODAGE_FIABLE
    ):
        return "fiable"
    return "a_verifier"


def sites(
    brut: pd.DataFrame,
    geocodage: pd.DataFrame,
    copros: pd.DataFrame,
    table_clients: pd.DataFrame,
    rejets: Rejets,
) -> pd.DataFrame:
    geo = {entier(r["site_id"]): r for _, r in geocodage.iterrows()}
    siren = dict(zip(table_clients["client_id"], table_clients["siren"], strict=True))
    par_cp = defaultdict(list)
    for _, c in copros.iterrows():
        if c["code_postal_adresse"]:
            par_cp[c["code_postal_adresse"]].append(c)
    lignes = []
    for _, s in brut.iterrows():
        sid, cid = entier(s.get("site_id")), entier(s.get("client_id"))
        adresse, cp = n.texte(s.get("adresse")), n.code_postal(s.get("code_postal"))
        if sid is None:
            rejets.ajouter("sites", None, "identifiant absent")
            continue
        if cid not in siren:
            rejets.ajouter("sites", sid, "client inexistant ou écarté")
            continue
        if adresse is None and cp is None:
            rejets.ajouter("sites", sid, "ni adresse ni code postal")
            continue
        g = geo.get(sid)
        qualite = qualite_geocodage(g)
        ligne = {
            "site_id": sid,
            "client_id": cid,
            "nom": n.texte(s.get("nom")),
            "adresse_saisie": adresse,
            "code_postal_saisi": cp,
            "ville_saisie": n.texte(s.get("ville")),
            "geocodage": qualite,
            "date_debut_contrat": n.date_iso(s.get("date_debut_contrat")),
            "date_fin_contrat": n.date_iso(s.get("date_fin_contrat")),
        }
        if qualite != "echec":
            ligne.update(
                {
                    "adresse_normalisee": n.texte(g.get("adresse_normalisee")),
                    "numero": n.texte(g.get("numero")),
                    "voie": n.texte(g.get("voie")),
                    "code_postal": n.code_postal(g.get("code_postal")),
                    "code_insee": n.texte(g.get("code_insee")),
                    "commune": n.texte(g.get("commune")),
                    "latitude": n.coordonnee(g.get("latitude"), 41.0, 51.5),
                    "longitude": n.coordonnee(g.get("longitude"), -5.5, 10.0),
                    "score_geocodage": n.decimal(g.get("score")),
                }
            )
        else:
            # Adresse non retrouvée : on garde la saisie, signalée pour vérification.
            ligne.update(
                {"adresse_normalisee": None, "code_postal": cp, "commune": ligne["ville_saisie"]}
            )
        candidats = par_cp.get(ligne["code_postal"] or "", [])
        ligne.update(rapprocher(ligne, candidats, siren.get(cid)))
        lignes.append(ligne)
    return pd.DataFrame(lignes, columns=COLONNES_SITES)


# ── Contacts ─────────────────────────────────────────────────────────────────


def contacts(brut: pd.DataFrame, table_clients: pd.DataFrame, rejets: Rejets) -> pd.DataFrame:
    connus = set(table_clients["client_id"])
    lignes, vus = [], set()
    for _, c in brut.iterrows():
        ctid, cid, nom = (
            entier(c.get("contact_id")),
            entier(c.get("client_id")),
            n.texte(c.get("nom")),
        )
        if nom is None:
            rejets.ajouter("contacts", ctid, "nom absent")
            continue
        if cid not in connus:
            rejets.ajouter("contacts", ctid, "client inexistant ou écarté")
            continue
        mail = n.email(c.get("email"))
        fixe, portable = (
            n.telephone(c.get("telephone_fixe")),
            n.telephone(c.get("telephone_portable")),
        )
        if not (mail or fixe or portable):
            rejets.ajouter("contacts", ctid, "aucune coordonnée valide")
            continue
        cle = (cid, n.cle_texte(nom), mail or fixe or portable)
        if cle in vus:
            rejets.ajouter("contacts", ctid, "doublon (même client, même nom, même coordonnée)")
            continue
        vus.add(cle)
        lignes.append(
            {
                "contact_id": ctid,
                "client_id": cid,
                "site_id": entier(c.get("site_id")),
                "nom": nom,
                "role": (n.texte(c.get("role")) or "").lower() or None,
                "poste": n.texte(c.get("poste")),
                "email": mail,
                "telephone_fixe": fixe,
                "telephone_portable": portable,
            }
        )
    return pd.DataFrame(lignes, columns=COLONNES_CONTACTS)


# ── Assemblage ───────────────────────────────────────────────────────────────


def agreger(sources: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict]:
    rejets = Rejets()
    t_clients = clients(sources["nexo_clients"], sources["api_entreprises_clients"], rejets)
    t_copros = coproprietes(sources["fichier_coproprietes"], rejets)
    t_sites = sites(
        sources["nexo_sites"], sources["api_geocodage_sites"], t_copros, t_clients, rejets
    )
    t_contacts = contacts(sources["nexo_contacts"], t_clients, rejets)
    # Contrôle final : toute référence pointe vers une ligne existante.
    if not set(t_sites["client_id"]) <= set(t_clients["client_id"]) or not set(
        t_contacts["client_id"]
    ) <= set(t_clients["client_id"]):
        raise ValueError("référentiel incohérent : référence vers un client absent")
    t_rejets = rejets.tableau()
    rapport = {
        "entrees": {k: len(v) for k, v in sources.items()},
        "sorties": {"clients": len(t_clients), "sites": len(t_sites), "contacts": len(t_contacts)},
        "rejets": t_rejets.groupby(["source", "motif"])
        .size()
        .reset_index(name="n")
        .to_dict("records"),
        "clients_verification_siret": t_clients["verification_siret"].value_counts().to_dict(),
        "clients_etablissement": t_clients["etat_etablissement"]
        .value_counts(dropna=False)
        .to_dict(),
        "sites_geocodage": t_sites["geocodage"].value_counts().to_dict(),
        "sites_rapprochement": t_sites["rapprochement_copropriete"].value_counts().to_dict(),
        "sites_client_est_syndic": t_sites["client_est_syndic"]
        .value_counts(dropna=False)
        .to_dict(),
    }
    rapport = {
        k: ({str(a): b for a, b in v.items()} if isinstance(v, dict) else v)
        for k, v in rapport.items()
    }
    return {
        "clients": t_clients,
        "sites": t_sites,
        "contacts": t_contacts,
        "rejets": t_rejets,
    }, rapport
