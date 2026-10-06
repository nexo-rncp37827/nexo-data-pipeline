"""Outil d'administration : prépare les valeurs d'API à copier dans `.env`.

    python -m referentiel.api.secret jwt                      # secret de signature des jetons
    python -m referentiel.api.secret client nexo referentiel contacts
        # demande le secret du client (non affiché) et imprime la valeur API_CLIENTS

Le secret du client n'est jamais écrit sur disque : seule son empreinte va dans `.env`.
"""

import argparse
import getpass
import json
import secrets
import sys

from referentiel.api.securite import PORTEES, empreinte


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    sous.add_parser("jwt", help="générer API_JWT_SECRET")
    cli = sous.add_parser("client", help="générer l'entrée API_CLIENTS d'une application")
    cli.add_argument("identifiant")
    cli.add_argument("portees", nargs="+", choices=sorted(PORTEES))
    args = parser.parse_args(argv)

    if args.commande == "jwt":
        print(f"API_JWT_SECRET={secrets.token_hex(32)}")
        return 0
    secret = getpass.getpass("Secret du client (openssl rand -hex 24) : ")
    if len(secret) < 24:
        print("Secret trop court (24 caractères au moins).", file=sys.stderr)
        return 2
    entree = {"id": args.identifiant, "empreinte": empreinte(secret), "portees": args.portees}
    print(f"API_CLIENTS='{json.dumps([entree])}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
