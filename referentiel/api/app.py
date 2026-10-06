"""API REST du référentiel clients (C5) — lecture seule.

Lancement : `uvicorn referentiel.api.app:app --host 0.0.0.0 --port 8000`.
Documentation interactive : `/docs` ; spécification OpenAPI : `/openapi.json`
(copie versionnée dans `docs/openapi.json`).
"""

from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from psycopg import sql
from psycopg.rows import dict_row

from referentiel.api import schemas
from referentiel.api.securite import PORTEES, authentifier, emettre_jeton, lecture
from referentiel.config import Reglages, reglages

DESCRIPTION = """
Référentiel clients de **Nexo** (ERP Foxabrille Nettoyage) : clients vérifiés, sites géocodés et
rapprochés du registre national des copropriétés, contacts dédoublonnés. Données mises à jour
chaque semaine par la chaîne d'import.

**Authentification** : `POST /auth/jeton` avec l'identifiant et le secret de l'application
(formulaire OAuth2, champs `username` et `password`) ; le jeton JWT renvoyé (30 min) se passe dans
l'en-tête `Authorization: Bearer <jeton>`.

**Autorisation** : portée `referentiel` pour les clients, sites et copropriétés ; portée
`contacts` en plus pour les contacts (données personnelles). L'API est en **lecture seule** :
elle se connecte à la base avec un compte PostgreSQL qui n'a que le droit `SELECT`.
"""

ERREURS_AUTH = {
    401: {"model": schemas.Erreur, "description": "Jeton absent, invalide ou expiré"},
    403: {"model": schemas.Erreur, "description": "Portée insuffisante"},
}
INTROUVABLE = {404: {"model": schemas.Erreur, "description": "Ressource introuvable"}}

app = FastAPI(
    title="API du référentiel clients — ERP Foxabrille",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=[
        {"name": "authentification", "description": "Obtention d'un jeton d'accès"},
        {"name": "clients", "description": "Clients vérifiés (SIRET, état administratif)"},
        {"name": "sites", "description": "Sites géocodés et rapprochés des copropriétés"},
        {"name": "coproprietes", "description": "Copropriétés du registre national (ANAH)"},
        {"name": "contacts", "description": "Contacts des clients — données personnelles"},
        {"name": "supervision", "description": "État du service"},
    ],
)

Limite = Annotated[int, Query(ge=1, le=500, description="Nombre maximal d'éléments")]
Decalage = Annotated[int, Query(ge=0, description="Nombre d'éléments à sauter")]


def connexion(r: Annotated[Reglages, Depends(reglages)]) -> Iterator[psycopg.Connection]:
    if not r.referentiel_api_database_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base non configurée")
    try:
        cnx = psycopg.connect(r.referentiel_api_database_url, connect_timeout=5)
    except psycopg.OperationalError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base injoignable") from None
    with cnx:
        cnx.row_factory = dict_row
        cnx.read_only = True
        yield cnx


Cnx = Annotated[psycopg.Connection, Depends(connexion)]

# Colonnes de chaque ressource, dans l'ordre des schémas de réponse
REQ_CONTACTS = """
    SELECT c.*, coalesce(array_agg(cs.site_id ORDER BY cs.site_id)
                         FILTER (WHERE cs.site_id IS NOT NULL), '{}') AS site_ids
    FROM contact c LEFT JOIN contact_site cs USING (contact_id)
"""


def page(cnx, source: str, filtres: dict, ordre: str, limite: int, decalage: int) -> dict:
    """Liste paginée ; les filtres (colonne → valeur) sont combinés par ET, valeurs paramétrées."""
    conditions = [
        sql.SQL("{} = {}").format(sql.Identifier(*col.split(".")), sql.Placeholder(col))
        for col, val in filtres.items()
        if val is not None
    ]
    valeurs = {col: val for col, val in filtres.items() if val is not None}
    where = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("")
    base = sql.SQL(source)
    total = cnx.execute(
        sql.SQL("SELECT count(*) AS n FROM ({} {}) t").format(base, where), valeurs
    ).fetchone()["n"]
    lignes = cnx.execute(
        sql.SQL("{} {} ORDER BY {} LIMIT {} OFFSET {}").format(
            base, where, sql.SQL(ordre), sql.Literal(limite), sql.Literal(decalage)
        ),
        valeurs,
    ).fetchall()
    return {"total": total, "limite": limite, "decalage": decalage, "elements": lignes}


def unique(cnx, requete: str, valeur) -> dict:
    ligne = cnx.execute(requete, (valeur,)).fetchone()
    if ligne is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ressource introuvable")
    return ligne


def existe(cnx, table: str, cle: str, valeur) -> None:
    unique(cnx, f"SELECT 1 FROM {table} WHERE {cle} = %s", valeur)


# --- Authentification --------------------------------------------------------------------


@app.post(
    "/auth/jeton",
    response_model=schemas.Jeton,
    tags=["authentification"],
    summary="Obtenir un jeton d'accès",
    responses={401: {"model": schemas.Erreur, "description": "Identifiants invalides"}},
)
def jeton(
    formulaire: Annotated[OAuth2PasswordRequestForm, Depends()],
    r: Annotated[Reglages, Depends(reglages)],
):
    """Échange l'identifiant (`username`) et le secret (`password`) d'une application contre un
    jeton JWT. Champ `scope` facultatif : sans lui, toutes les portées de l'application sont
    accordées ; une portée demandée mais non autorisée est refusée."""
    client = authentifier(r, formulaire.username, formulaire.password)
    if client is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )
    demandees = formulaire.scopes or client.portees
    if not set(demandees) <= set(client.portees) or not set(demandees) <= set(PORTEES):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portée non autorisée")
    valeur, duree = emettre_jeton(r, client, demandees)
    return {"access_token": valeur, "expires_in": duree, "scope": " ".join(demandees)}


# --- Clients -----------------------------------------------------------------------------


@app.get(
    "/clients",
    response_model=schemas.Page[schemas.Client],
    tags=["clients"],
    summary="Lister les clients",
    responses=ERREURS_AUTH,
    dependencies=[lecture("referentiel")],
)
def lister_clients(
    cnx: Cnx,
    limite: Limite = 100,
    decalage: Decalage = 0,
    type_client: schemas.TypeClient | None = None,
    verification_siret: schemas.Verification | None = None,
    etat_etablissement: Annotated[str | None, Query(pattern="^(actif|ferme)$")] = None,
):
    filtres = {
        "type_client": type_client,
        "verification_siret": verification_siret,
        "etat_etablissement": etat_etablissement,
    }
    return page(cnx, "SELECT * FROM client", filtres, "client_id", limite, decalage)


@app.get(
    "/clients/{client_id}",
    response_model=schemas.Client,
    tags=["clients"],
    summary="Lire un client",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel")],
)
def lire_client(cnx: Cnx, client_id: Annotated[int, Path(ge=1)]):
    return unique(cnx, "SELECT * FROM client WHERE client_id = %s", client_id)


@app.get(
    "/clients/{client_id}/sites",
    response_model=schemas.Page[schemas.Site],
    tags=["clients"],
    summary="Lister les sites d'un client",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel")],
)
def sites_du_client(
    cnx: Cnx, client_id: Annotated[int, Path(ge=1)], limite: Limite = 100, decalage: Decalage = 0
):
    existe(cnx, "client", "client_id", client_id)
    filtres = {"client_id": client_id}
    return page(cnx, "SELECT * FROM v_site", filtres, "site_id", limite, decalage)


@app.get(
    "/clients/{client_id}/contacts",
    response_model=schemas.Page[schemas.Contact],
    tags=["clients", "contacts"],
    summary="Lister les contacts d'un client",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel", "contacts")],
)
def contacts_du_client(
    cnx: Cnx, client_id: Annotated[int, Path(ge=1)], limite: Limite = 100, decalage: Decalage = 0
):
    existe(cnx, "client", "client_id", client_id)
    source = f"SELECT * FROM ({REQ_CONTACTS} GROUP BY c.contact_id) c"
    return page(cnx, source, {"client_id": client_id}, "contact_id", limite, decalage)


# --- Sites -------------------------------------------------------------------------------


@app.get(
    "/sites",
    response_model=schemas.Page[schemas.Site],
    tags=["sites"],
    summary="Lister les sites",
    responses=ERREURS_AUTH,
    dependencies=[lecture("referentiel")],
)
def lister_sites(
    cnx: Cnx,
    limite: Limite = 100,
    decalage: Decalage = 0,
    client_id: Annotated[int | None, Query(ge=1)] = None,
    code_postal: Annotated[str | None, Query(pattern=r"^\d{5}$")] = None,
    geocodage: schemas.Geocodage | None = None,
    rapprochement_copropriete: schemas.Rapprochement | None = None,
    client_est_syndic: bool | None = None,
):
    filtres = {
        "client_id": client_id,
        "code_postal": code_postal,
        "geocodage": geocodage,
        "rapprochement_copropriete": rapprochement_copropriete,
        "client_est_syndic": client_est_syndic,
    }
    return page(cnx, "SELECT * FROM v_site", filtres, "site_id", limite, decalage)


@app.get(
    "/sites/{site_id}",
    response_model=schemas.Site,
    tags=["sites"],
    summary="Lire un site",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel")],
)
def lire_site(cnx: Cnx, site_id: Annotated[int, Path(ge=1)]):
    return unique(cnx, "SELECT * FROM v_site WHERE site_id = %s", site_id)


@app.get(
    "/sites/{site_id}/contacts",
    response_model=list[schemas.Contact],
    tags=["sites", "contacts"],
    summary="Lister les contacts qui suivent un site",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel", "contacts")],
)
def contacts_du_site(cnx: Cnx, site_id: Annotated[int, Path(ge=1)]):
    existe(cnx, "site", "site_id", site_id)
    return cnx.execute(
        f"""SELECT * FROM ({REQ_CONTACTS} GROUP BY c.contact_id) c
            WHERE %s = ANY(site_ids) ORDER BY contact_id""",
        (site_id,),
    ).fetchall()


# --- Copropriétés ------------------------------------------------------------------------


@app.get(
    "/coproprietes",
    response_model=schemas.Page[schemas.Copropriete],
    tags=["coproprietes"],
    summary="Lister les copropriétés rapprochées d'un site",
    responses=ERREURS_AUTH,
    dependencies=[lecture("referentiel")],
)
def lister_coproprietes(cnx: Cnx, limite: Limite = 100, decalage: Decalage = 0):
    return page(cnx, "SELECT * FROM copropriete", {}, "numero_immatriculation", limite, decalage)


@app.get(
    "/coproprietes/{numero_immatriculation}",
    response_model=schemas.Copropriete,
    tags=["coproprietes"],
    summary="Lire une copropriété",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel")],
)
def lire_copropriete(
    cnx: Cnx, numero_immatriculation: Annotated[str, Path(pattern=r"^[A-Z0-9]{1,20}$")]
):
    return unique(
        cnx,
        "SELECT * FROM copropriete WHERE numero_immatriculation = %s",
        numero_immatriculation,
    )


# --- Contacts ----------------------------------------------------------------------------


@app.get(
    "/contacts",
    response_model=schemas.Page[schemas.Contact],
    tags=["contacts"],
    summary="Lister les contacts",
    responses=ERREURS_AUTH,
    dependencies=[lecture("referentiel", "contacts")],
)
def lister_contacts(
    cnx: Cnx,
    limite: Limite = 100,
    decalage: Decalage = 0,
    client_id: Annotated[int | None, Query(ge=1)] = None,
):
    source = f"SELECT * FROM ({REQ_CONTACTS} GROUP BY c.contact_id) c"
    return page(cnx, source, {"client_id": client_id}, "contact_id", limite, decalage)


@app.get(
    "/contacts/{contact_id}",
    response_model=schemas.Contact,
    tags=["contacts"],
    summary="Lire un contact",
    responses=ERREURS_AUTH | INTROUVABLE,
    dependencies=[lecture("referentiel", "contacts")],
)
def lire_contact(cnx: Cnx, contact_id: Annotated[int, Path(ge=1)]):
    return unique(cnx, f"{REQ_CONTACTS} WHERE c.contact_id = %s GROUP BY c.contact_id", contact_id)


# --- Supervision -------------------------------------------------------------------------


@app.get(
    "/sante",
    response_model=schemas.Sante,
    tags=["supervision"],
    summary="État du service (sans authentification, aucune donnée)",
)
def sante(r: Annotated[Reglages, Depends(reglages)]):
    if not r.referentiel_api_database_url:
        return {"statut": "degrade", "base": "non_configuree"}
    try:
        with psycopg.connect(r.referentiel_api_database_url, connect_timeout=3) as cnx:
            cnx.execute("SELECT 1")
        return {"statut": "ok", "base": "ok"}
    except psycopg.Error:
        return {"statut": "degrade", "base": "injoignable"}
