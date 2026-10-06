"""Configuration lue dans les variables d'environnement (fichier .env en local).

Aucun secret n'a de valeur par défaut : une variable obligatoire absente arrête le programme
avec un message explicite, plutôt que de continuer avec une valeur inventée.
"""

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientApi(BaseModel):
    """Application autorisée à appeler l'API (secret stocké sous forme d'empreinte scrypt)."""

    id: str
    empreinte: str
    portees: list[str]


class Reglages(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de Nexo (source, lecture seule) — obligatoire pour l'extraction
    nexo_database_url: str | None = Field(default=None)
    # Base dédiée au référentiel clients (cible de l'import, lue par l'API)
    referentiel_database_url: str | None = Field(default=None)
    # API REST (C5) : compte referentiel_api en lecture seule, jetons signés, clients autorisés
    referentiel_api_database_url: str | None = Field(default=None)
    api_jwt_secret: str | None = Field(default=None)
    api_jwt_minutes: int = Field(default=30, ge=1, le=60)
    api_clients: list[ClientApi] = Field(default_factory=list)
    # Dossier des données (brutes, nettoyées, rejets) — hors dépôt Git
    dossier_donnees: Path = Path("data")


def reglages() -> Reglages:
    return Reglages()
