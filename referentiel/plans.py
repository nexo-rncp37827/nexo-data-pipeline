"""Mesure des requêtes d'extraction (C2) : `python -m referentiel.plans`.

Pour chaque requête de `sql/`, exécute `EXPLAIN (ANALYZE, BUFFERS)` avec le compte en lecture
seule et enregistre le plan dans `data/plans/<horodatage>.txt`. Une seconde mesure, avec les
parcours séquentiels désactivés (`enable_seqscan = off`), montre le plan par index que
PostgreSQL utiliserait sur une table plus volumineuse et permet de comparer les coûts estimés.
Seul un résumé (durées, nombre de lignes, type de parcours) est affiché à l'écran.
"""

import re
import sys
from datetime import UTC, datetime

import psycopg

from referentiel.config import Reglages
from referentiel.extraction import nexo

TABLES = ("clients", "sites", "contacts")
PARCOURS = r"(Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan)"
JOINTURES = r"(Hash Join|Merge Join|Nested Loop|Hash Right Join|Hash Left Join)"


def requete_sans_commentaires(sql: str) -> str:
    lignes = [ligne for ligne in sql.splitlines() if not ligne.strip().startswith("--")]
    return "\n".join(lignes).strip().rstrip(";")


def expliquer(curseur, sql: str) -> list[str]:
    curseur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {requete_sans_commentaires(sql)}")
    return [ligne[0] for ligne in curseur.fetchall()]


def resumer(plan: list[str]) -> dict:
    texte = "\n".join(plan)
    duree = re.search(r"Execution Time: ([\d.]+) ms", texte)
    lignes = re.search(r"actual time=[\d.]+\.\.[\d.]+ rows=(\d+)", plan[0]) if plan else None
    return {
        "execution_ms": float(duree.group(1)) if duree else None,
        "lignes": int(lignes.group(1)) if lignes else None,
        "parcours": sorted(
            set(re.findall(r"(Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan)", texte))
        ),
        "jointures": sorted(
            set(
                re.findall(
                    r"(Hash Join|Merge Join|Nested Loop|Hash Right Join|Hash Left Join)", texte
                )
            )
        ),
    }


def mesurer(connexion) -> tuple[list[str], list[dict]]:
    rapport, resumes = [], []
    with connexion.cursor() as cur:
        cur.execute(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = ANY(%s) ORDER BY 1, 2",
            (list(TABLES),),
        )
        rapport.append("== Index existants ==")
        rapport += [f"{t} | {i} | {d}" for t, i, d in cur.fetchall()]
        for nom, fichier in nexo.REQUETES.items():
            sql = nexo.lire_requete(fichier)
            for mode in ("plan choisi", "parcours sequentiels desactives"):
                cur.execute(
                    "SET LOCAL enable_seqscan = %s" % ("on" if mode == "plan choisi" else "off")
                )
                plan = expliquer(cur, sql)
                r = {"requete": nom, "mode": mode, **resumer(plan)}
                resumes.append(r)
                rapport += ["", f"== {nom} ({fichier}) - {mode} ==", *plan]
    return rapport, resumes


def main() -> int:
    reglages = Reglages()
    if not reglages.nexo_database_url:
        print("NEXO_DATABASE_URL manquant", file=sys.stderr)
        return 2
    with psycopg.connect(reglages.nexo_database_url, connect_timeout=10) as cnx:
        cnx.read_only = True
        rapport, resumes = mesurer(cnx)
    dossier = reglages.dossier_donnees / "plans"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.txt"
    chemin.write_text("\n".join(rapport) + "\n", encoding="utf-8")
    for r in resumes:
        print(
            f"{r['requete']:14} | {r['mode']:31} | {r['lignes']} lignes | "
            f"{r['execution_ms']} ms | {', '.join(r['parcours'])} | {', '.join(r['jointures'])}"
        )
    print(f"Plans complets : {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
