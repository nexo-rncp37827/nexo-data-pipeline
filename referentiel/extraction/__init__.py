"""Extraction des trois sources du référentiel clients (compétence C1)."""


class ErreurSource(Exception):
    """Une source n'a pas pu être extraite : le lancement s'arrête avec un code d'erreur."""
