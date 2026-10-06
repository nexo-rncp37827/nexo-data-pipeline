"""Import du référentiel agrégé dans la base dédiée (C4) : `python -m referentiel.importer`.

Lit le dernier dossier de `data/propre/` (ou celui passé en argument) et synchronise la base
`referentiel` dans **une seule transaction** :
1. copropriétés, clients, sites, contacts, associations : insertion ou mise à jour (`ON CONFLICT`) ;
2. suppression des lignes qui ne figurent plus dans le référentiel (client retiré de Nexo,
   contact supprimé…) : la base reflète exactement la dernière agrégation (procédure de tri P1) ;
3. ligne de journal dans `import`.
Rejouer l'import du même dossier ne change rien (idempotent). En cas d'erreur, rien n'est écrit
(annulation de la transaction) et le journal garde un import « echec ».
Codes de sortie : 0 = import réussi ; 1 = échec (rien n'a été modifié) ; 2 = configuration ou
dossier manquant.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import psycopg

from referentiel import nettoyage as n
from referentiel.config import Reglages

journal = logging.getLogger("referentiel.importer")

COLONNES = {
    "copropriete": [
        "numero_immatriculation",
        "adresse",
        "nom_usage",
        "nombre_total_lots",
        "nombre_lots_habitation",
        "type_syndic",
        "syndic_raison_sociale",
        "syndic_siret",
        "mandat_en_cours",
    ],
    "client": [
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
    ],
    "site": [
        "site_id",
        "client_id",
        "numero_immatriculation",
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
        "immatriculations_candidates",
    ],
    "contact": [
        "contact_id",
        "client_id",
        "nom",
        "role",
        "poste",
        "email",
        "telephone_fixe",
        "telephone_portable",
    ],
}
CLES = {
    "copropriete": ["numero_immatriculation"],
    "client": ["client_id"],
    "site": ["site_id"],
    "contact": ["contact_id"],
}


def lire(dossier: Path) -> dict[str, pd.DataFrame]:
    fichiers = {
        "clients": "clients.csv",
        "sites": "sites.csv",
        "contacts": "contacts.csv",
        "contacts_sites": "contacts_sites.csv",
    }
    manquants = [f for f in fichiers.values() if not (dossier / f).exists()]
    if manquants:
        raise FileNotFoundError(f"fichiers absents dans {dossier} : {manquants}")
    return {
        k: pd.read_csv(dossier / f, dtype=str, keep_default_na=False, na_values=[""])
        for k, f in fichiers.items()
    }


def coproprietes(sites: pd.DataFrame) -> pd.DataFrame:
    """Une copropriété par numéro, à partir des sites qui lui ont été rapprochés."""
    colonnes = {"adresse_copropriete": "adresse", "nom_usage_copropriete": "nom_usage"}
    df = sites[sites["numero_immatriculation"].notna()].rename(columns=colonnes)
    return df[COLONNES["copropriete"]].drop_duplicates("numero_immatriculation")


DUREE_CONSERVATION_CONTACTS_JOURS = 3 * 365  # 3 ans après la fin de la relation (procédure P2)


def contacts_conserves(clients: pd.DataFrame, contacts: pd.DataFrame, aujourd_hui=None):
    """Procédure P2 : les contacts d'un client qui n'est plus actif depuis plus de 3 ans
    (dernière mise à jour de sa fiche) ne sont pas conservés. Renvoie (gardés, écartés)."""
    aujourd_hui = pd.Timestamp(aujourd_hui or pd.Timestamp.today().normalize())
    limite = aujourd_hui - pd.Timedelta(days=DUREE_CONSERVATION_CONTACTS_JOURS)
    maj = pd.to_datetime(clients["date_mise_a_jour"], errors="coerce")
    expires = clients[(clients["statut"] != "actif") & (maj < limite)]["client_id"]
    masque = contacts["client_id"].isin(set(expires))
    return contacts[~masque], int(masque.sum())


def lignes(df: pd.DataFrame, colonnes: list[str]) -> list[tuple]:
    """Valeurs prêtes pour PostgreSQL : NaN → NULL, textes « True/False » → booléens."""
    return [
        tuple(None if n.absent(v) else v for v in ligne)
        for ligne in df[colonnes].itertuples(index=False)
    ]


def upsert(cur, table: str, df: pd.DataFrame) -> int:
    cols, cles = COLONNES[table], CLES[table]
    maj = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in cles)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT ({', '.join(cles)}) DO UPDATE SET {maj}, importe_le = now()"
    )
    valeurs = lignes(df, cols)
    if valeurs:
        cur.executemany(sql, valeurs)
    return len(valeurs)


def supprimer_absents(cur, table: str, cle: str, presents: list) -> int:
    cur.execute(f"DELETE FROM {table} WHERE NOT ({cle} = ANY(%s))", (presents,))
    return cur.rowcount


def importer(connexion, dossier: Path) -> dict:
    t = lire(dossier)
    copros = coproprietes(t["sites"])
    t["contacts"], ecartes = contacts_conserves(t["clients"], t["contacts"])
    gardes = set(t["contacts"]["contact_id"])
    t["contacts_sites"] = t["contacts_sites"][t["contacts_sites"]["contact_id"].isin(gardes)]
    with connexion.cursor() as cur:
        cur.execute(
            "INSERT INTO import (extraction) VALUES (%s) RETURNING import_id", (dossier.name,)
        )
        import_id = cur.fetchone()[0]
    connexion.commit()  # le journal garde la tentative, même si l'import échoue ensuite
    try:
        with connexion.transaction(), connexion.cursor() as cur:
            bilan = {
                "nb_coproprietes": upsert(cur, "copropriete", copros),
                "nb_clients": upsert(cur, "client", t["clients"]),
                "nb_sites": upsert(cur, "site", t["sites"]),
                "nb_contacts": upsert(cur, "contact", t["contacts"]),
            }
            # Associations : remplacées en bloc (table sans attribut propre).
            cur.execute("DELETE FROM contact_site")
            liens = lignes(t["contacts_sites"], ["contact_id", "site_id"])
            if liens:
                cur.executemany(
                    "INSERT INTO contact_site (contact_id, site_id) VALUES (%s, %s)", liens
                )
            bilan["nb_contacts_sites"] = len(liens)
            ids = {
                k: [int(v) for v in t[k][c]]
                for k, c in (
                    ("contacts", "contact_id"),
                    ("sites", "site_id"),
                    ("clients", "client_id"),
                )
            }
            supprimes = supprimer_absents(cur, "contact", "contact_id", ids["contacts"])
            supprimes += supprimer_absents(cur, "site", "site_id", ids["sites"])
            supprimes += supprimer_absents(cur, "client", "client_id", ids["clients"])
            supprimes += supprimer_absents(
                cur, "copropriete", "numero_immatriculation", list(copros["numero_immatriculation"])
            )
            bilan["nb_supprimes"] = supprimes
            bilan["nb_contacts_fin_conservation"] = ecartes
            cur.execute(
                "UPDATE import SET fin = now(), statut = 'ok', nb_clients = %s, nb_sites = %s, "
                "nb_coproprietes = %s, nb_contacts = %s, nb_contacts_sites = %s, nb_supprimes = %s "
                "WHERE import_id = %s",
                (
                    bilan["nb_clients"],
                    bilan["nb_sites"],
                    bilan["nb_coproprietes"],
                    bilan["nb_contacts"],
                    bilan["nb_contacts_sites"],
                    supprimes,
                    import_id,
                ),
            )
    except Exception:
        with connexion.cursor() as cur:
            cur.execute(
                "UPDATE import SET fin = now(), statut = 'echec' WHERE import_id = %s", (import_id,)
            )
        connexion.commit()
        raise
    return {"import_id": import_id, **bilan}


def dernier_dossier(dossier_propre: Path) -> Path | None:
    dossiers = sorted(d for d in dossier_propre.glob("*") if (d / "clients.csv").exists())
    return dossiers[-1] if dossiers else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import du référentiel dans la base dédiée")
    parser.add_argument("--propre", type=Path, help="dossier agrégé (défaut : le plus récent)")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    reglages = Reglages()
    if not reglages.referentiel_database_url:
        journal.error("REFERENTIEL_DATABASE_URL manquant")
        return 2
    dossier = args.propre or dernier_dossier(reglages.dossier_donnees / "propre")
    if dossier is None:
        journal.error("aucun référentiel agrégé dans %s", reglages.dossier_donnees / "propre")
        return 2
    try:
        with psycopg.connect(reglages.referentiel_database_url, connect_timeout=10) as cnx:
            bilan = importer(cnx, dossier)
    except (psycopg.Error, FileNotFoundError, ValueError) as exc:
        journal.error("import annulé, base inchangée : %s", exc)
        return 1
    journal.info("import réussi depuis %s : %s", dossier.name, bilan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
