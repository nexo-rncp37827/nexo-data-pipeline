import pytest

from referentiel import plans
from referentiel.extraction import nexo

PLAN = [
    "Sort  (cost=11.49..11.49 rows=2 width=1422) (actual time=0.018..0.020 rows=145 loops=1)",
    "  ->  Hash Join  (cost=1.04..11.48 rows=2) (actual time=0.012..0.014 rows=2 loops=1)",
    "        ->  Seq Scan on clients c  (cost=0.00..10.30 rows=30 width=122)",
    "        ->  Index Scan using sites_pkey on sites s  (cost=0.14..8.16 rows=1 width=4)",
    "Planning Time: 0.1 ms",
    "Execution Time: 0.042 ms",
]


def test_commentaires_et_point_virgule_retires():
    sql = plans.requete_sans_commentaires(nexo.lire_requete("extraction_nexo_sites.sql"))
    assert not sql.startswith("--") and not sql.endswith(";") and "JOIN clients" in sql


def test_resume_du_plan():
    r = plans.resumer(PLAN)
    assert r == {
        "execution_ms": 0.042,
        "lignes": 145,
        "parcours": ["Index Scan", "Seq Scan"],
        "jointures": ["Hash Join"],
    }


class Curseur:
    def __init__(self):
        self.executees = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executees.append(sql)
        self.derniere = sql

    def fetchall(self):
        if "pg_indexes" in self.derniere:
            return [("sites", "ix_sites_client_id", "CREATE INDEX ...")]
        return [(ligne,) for ligne in PLAN]


class Connexion:
    def __init__(self):
        self.c = Curseur()

    def cursor(self):
        return self.c


def test_chaque_requete_mesuree_dans_les_deux_modes():
    cnx = Connexion()
    rapport, resumes = plans.mesurer(cnx)
    assert len(resumes) == 2 * len(nexo.REQUETES)
    assert {r["mode"] for r in resumes} == {"plan choisi", "parcours sequentiels desactives"}
    assert "SET LOCAL enable_seqscan = off" in cnx.c.executees
    assert all(not s.startswith("EXPLAIN") or "ANALYZE, BUFFERS" in s for s in cnx.c.executees)
    assert rapport[0] == "== Index existants ==" and "ix_sites_client_id" in rapport[1]


def test_configuration_incomplete(monkeypatch):
    monkeypatch.delenv("NEXO_DATABASE_URL", raising=False)
    origine = plans.Reglages
    monkeypatch.setattr(plans, "Reglages", lambda: origine(_env_file=None))
    assert plans.main() == 2


@pytest.mark.parametrize("plan", [[], ["Seq Scan on x"]])
def test_resume_plan_incomplet(plan):
    assert plans.resumer(plan)["execution_ms"] is None


def test_toutes_les_formes_de_jointure_reconnues():
    plan = ["Merge Left Join  (cost=1..2)", "  ->  Hash Left Join", "  ->  Nested Loop Left Join"]
    assert plans.resumer(plan)["jointures"] == ["Hash Left Join", "Merge Left Join", "Nested Loop"]
