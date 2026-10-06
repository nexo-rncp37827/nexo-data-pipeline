"""Authentification et autorisation de l'API.

- Authentification : une application (client de l'API) échange son identifiant et son secret
  contre un jeton JWT signé (HS256), valable 30 minutes par défaut (`API_JWT_MINUTES`).
- Les secrets ne sont jamais stockés en clair : seule leur empreinte scrypt (sel aléatoire)
  figure dans la configuration (`API_CLIENTS`).
- Autorisation par portées : `referentiel` (clients, sites, copropriétés) et `contacts`
  (données personnelles, traitement T1 du registre). Un jeton sans la portée requise reçoit 403.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from referentiel.config import ClientApi, Reglages, reglages

PORTEES = {
    "referentiel": "Lecture des clients, sites et copropriétés",
    "contacts": "Lecture des contacts des clients (données personnelles)",
}
EMETTEUR = "referentiel-clients"
AUDIENCE = "referentiel-api"
ALGORITHME = "HS256"
LONGUEUR_MIN_SECRET_JWT = 32
# Paramètres scrypt (RFC 7914) : n = 2^14, r = 8, p = 1
SCRYPT = {"n": 2**14, "r": 8, "p": 1}

schema_oauth2 = OAuth2PasswordBearer(tokenUrl="auth/jeton", scopes=PORTEES)


def empreinte(secret: str, sel: bytes | None = None) -> str:
    """Empreinte d'un secret, au format `scrypt:<sel hex>:<empreinte hex>` (sans caractère $)."""
    sel = sel or secrets.token_bytes(16)
    calcul = hashlib.scrypt(secret.encode(), salt=sel, **SCRYPT)
    return f"scrypt:{sel.hex()}:{calcul.hex()}"


def verifier_secret(secret: str, empreinte_stockee: str) -> bool:
    try:
        algo, sel, attendu = empreinte_stockee.split(":")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    calcul = hashlib.scrypt(secret.encode(), salt=bytes.fromhex(sel), **SCRYPT)
    return hmac.compare_digest(calcul.hex(), attendu)


# Empreinte factice : le temps de réponse ne révèle pas si l'identifiant existe.
_EMPREINTE_LEURRE = empreinte(secrets.token_hex(16))


def secret_jwt(r: Reglages) -> str:
    if not r.api_jwt_secret or len(r.api_jwt_secret) < LONGUEUR_MIN_SECRET_JWT:
        raise RuntimeError(f"API_JWT_SECRET absent ou trop court (≥ {LONGUEUR_MIN_SECRET_JWT})")
    return r.api_jwt_secret


def authentifier(r: Reglages, identifiant: str, secret: str) -> ClientApi | None:
    client = next((c for c in r.api_clients if c.id == identifiant), None)
    valide = verifier_secret(secret, client.empreinte if client else _EMPREINTE_LEURRE)
    return client if client and valide else None


def emettre_jeton(r: Reglages, client: ClientApi, portees: list[str]) -> tuple[str, int]:
    duree = timedelta(minutes=r.api_jwt_minutes)
    maintenant = datetime.now(UTC)
    charge = {
        "iss": EMETTEUR,
        "aud": AUDIENCE,
        "sub": client.id,
        "scope": " ".join(portees),
        "iat": maintenant,
        "exp": maintenant + duree,
    }
    return jwt.encode(charge, secret_jwt(r), algorithm=ALGORITHME), int(duree.total_seconds())


def _refus(detail: str, portees: SecurityScopes, code=status.HTTP_401_UNAUTHORIZED):
    entete = "Bearer"
    if portees.scopes:
        entete += f' scope="{portees.scope_str}"'
    return HTTPException(status_code=code, detail=detail, headers={"WWW-Authenticate": entete})


def client_autorise(
    portees: SecurityScopes,
    jeton: Annotated[str, Depends(schema_oauth2)],
    r: Annotated[Reglages, Depends(reglages)],
) -> str:
    """Dépendance de chaque route protégée : jeton valide et portées suffisantes."""
    try:
        charge = jwt.decode(
            jeton,
            secret_jwt(r),
            algorithms=[ALGORITHME],
            audience=AUDIENCE,
            issuer=EMETTEUR,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise _refus("Jeton expiré", portees) from None
    except jwt.InvalidTokenError:
        raise _refus("Jeton invalide", portees) from None
    accordees = set(charge.get("scope", "").split())
    if not set(portees.scopes) <= accordees:
        raise _refus("Portée insuffisante", portees, status.HTTP_403_FORBIDDEN)
    return charge["sub"]


def lecture(*requises: str):
    return Security(client_autorise, scopes=list(requises))
