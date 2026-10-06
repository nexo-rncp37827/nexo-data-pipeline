"""Écrit la spécification OpenAPI de l'API dans `docs/openapi.json` (copie versionnée).

    python -m referentiel.api.exporter_openapi [--verifier]

`--verifier` (utilisé par la CI) échoue si la copie versionnée n'est plus à jour.
"""

import argparse
import json
from pathlib import Path

from referentiel.api.app import app

FICHIER = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def specification() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verifier", action="store_true", help="vérifier sans écrire")
    args = parser.parse_args(argv)
    if args.verifier:
        a_jour = FICHIER.exists() and FICHIER.read_text() == specification()
        print("docs/openapi.json à jour" if a_jour else "docs/openapi.json à régénérer")
        return 0 if a_jour else 1
    FICHIER.write_text(specification())
    print(f"Spécification écrite : {FICHIER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
