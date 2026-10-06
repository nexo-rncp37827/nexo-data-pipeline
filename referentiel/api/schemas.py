"""Schémas des réponses (documentés dans la spécification OpenAPI)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TypeClient = Literal["regie", "entreprise", "copropriete", "collectivite", "particulier"]
Verification = Literal["verifie", "non_trouve", "siret_invalide", "non_verifie"]
Geocodage = Literal["fiable", "a_verifier", "echec"]
Rapprochement = Literal["correspondance", "a_verifier", "ambigu", "aucune", "non_evalue"]


class Page[T](BaseModel):
    total: int = Field(description="Nombre total d'éléments correspondant aux filtres")
    limite: int
    decalage: int
    elements: list[T]


class Client(BaseModel):
    client_id: int = Field(description="Identifiant du client dans Nexo")
    nom: str
    type_client: TypeClient
    statut: str | None = Field(description="Statut commercial dans Nexo (actif, inactif…)")
    siret: str | None
    siren: str | None
    verification_siret: Verification = Field(
        description="Résultat de la vérification par l'API Recherche d'entreprises"
    )
    denomination_officielle: str | None
    similarite_nom: Decimal | None = Field(
        description="Similarité (0 à 1) entre le nom saisi et la dénomination officielle"
    )
    etat_etablissement: Literal["actif", "ferme"] | None
    activite_principale: str | None = Field(description="Code APE / NAF")
    nature_juridique: str | None
    adresse: str | None
    code_postal: str | None
    ville: str | None
    date_creation: date | None
    date_mise_a_jour: date | None
    importe_le: datetime


class Copropriete(BaseModel):
    numero_immatriculation: str = Field(description="Numéro au registre national (ANAH)")
    adresse: str | None
    nom_usage: str | None
    nombre_total_lots: int | None
    nombre_lots_habitation: int | None
    type_syndic: str | None
    syndic_raison_sociale: str | None = Field(description="Uniquement un syndic professionnel")
    syndic_siret: str | None
    mandat_en_cours: str | None
    importe_le: datetime


class Site(BaseModel):
    site_id: int = Field(description="Identifiant du site dans Nexo")
    client_id: int
    client_nom: str
    nom: str | None
    adresse_saisie: str | None = Field(description="Adresse telle que saisie dans Nexo")
    code_postal_saisi: str | None
    ville_saisie: str | None
    adresse_normalisee: str | None = Field(description="Adresse renvoyée par le géocodage IGN")
    numero: str | None
    voie: str | None
    code_postal: str | None
    code_insee: str | None
    commune: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    score_geocodage: Decimal | None
    geocodage: Geocodage
    date_debut_contrat: date | None
    date_fin_contrat: date | None
    rapprochement_copropriete: Rapprochement
    distance_copropriete_m: Decimal | None
    immatriculations_candidates: str | None = Field(
        description="Copropriétés candidates quand le rapprochement est ambigu"
    )
    numero_immatriculation: str | None
    nom_usage: str | None = Field(description="Nom d'usage de la copropriété rapprochée")
    nombre_total_lots: int | None
    nombre_lots_habitation: int | None
    type_syndic: str | None
    syndic_raison_sociale: str | None
    syndic_siret: str | None
    mandat_en_cours: str | None
    client_est_syndic: bool | None = Field(
        description="Le client est-il le syndic de la copropriété ? Calculé, null si inconnu"
    )
    importe_le: datetime


class Contact(BaseModel):
    contact_id: int
    client_id: int
    nom: str
    role: str | None
    poste: str | None
    email: str | None
    telephone_fixe: str | None = Field(description="Format E.164 (+33…)")
    telephone_portable: str | None = Field(description="Format E.164 (+33…)")
    site_ids: list[int] = Field(description="Sites suivis par ce contact")
    importe_le: datetime


class Jeton(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Durée de validité en secondes")
    scope: str = Field(description="Portées accordées, séparées par des espaces")


class Sante(BaseModel):
    statut: Literal["ok", "degrade"]
    base: Literal["ok", "injoignable", "non_configuree"]


class Erreur(BaseModel):
    detail: str
