# nexo-data-pipeline

Pipeline de collecte, nettoyage et import de données pour le projet Nexo (ERP Foxabrille Nettoyage).  
Produit dans le cadre de la certification RNCP37827 — Développeur en Intelligence Artificielle.

---

## Compétences couvertes

| Script | Compétence |
|---|---|
| `extract_api.py` | C1 — Extraction API REST (API Adresse gouv.fr — géocodage) |
| `generate_excel_template.py` | C1 — Génération template Excel import Nexo (Clients + Salariés) |
| `extract_scraping.py` | C1 — Extraction scraping (tarifs fournitures) |
| `extract_bdd.py` | C1 + C2 — Extraction PostgreSQL Nexo + requêtes SQL |
| `clean_aggregate.py` | C3 — Agrégation et nettoyage dédié |
| `import_bdd.py` | C4 — Import des données nettoyées en base |
| `purge_audit_logs.py` | C4 — Procédure de tri RGPD (purge logs > 1 an) |

---

## Prérequis

- Python 3.12+ avec `uv`
- PostgreSQL 16 (instance Nexo locale)
- Accès internet pour API Adresse et scraping

---

## Installation

```powershell
# Cloner le repo
git clone https://github.com/<votre-compte>/nexo-data-pipeline.git
cd nexo-data-pipeline

# Installer les dépendances
uv add requests pandas openpyxl beautifulsoup4 psycopg2-binary python-dotenv

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env : renseigner DATABASE_URL
```

---

## Configuration — .env

```env
DATABASE_URL=postgresql://user:password@localhost:5432/nexo
```

---

## Exécution des scripts

### 1. Extraction des données (C1)

```powershell
# API Adresse — géocodage des adresses de sites clients
uv run python extract_api.py

# Template Excel — générer le fichier à remplir par Foxabrille
uv run python generate_excel_template.py

# Scraping — tarifs fournitures nettoyage
uv run python extract_scraping.py

# Base de données PostgreSQL Nexo
uv run python extract_bdd.py
```

Chaque script produit un fichier CSV dans `data/raw/`.

### 2. Nettoyage et agrégation (C3)

```powershell
uv run python clean_aggregate.py
```

Produit `data/clean/dataset_final.csv` — jeu de données nettoyé et normalisé.

### 3. Import en base (C4)

```powershell
uv run python import_bdd.py
```

Insère les données nettoyées dans la table `pipeline_clients` de PostgreSQL Nexo.

### 4. Purge RGPD des logs d'audit (C4)

```powershell
uv run python purge_audit_logs.py
```

Supprime les entrées `audit_logs` dont `created_at < NOW() - 1 an`.  
À exécuter mensuellement (procédure de tri RGPD — voir registre des traitements).

---

## Structure des dossiers

```
nexo-data-pipeline/
├── data/
│   ├── raw/              ← données brutes extraites
│   │   ├── adresses_geocodees.csv
│   │   ├── salaries_legacy.csv
│   │   ├── tarifs_scraping.csv
│   │   └── nexo_export.csv
│   └── clean/            ← données nettoyées
│       └── dataset_final.csv
├── extract_api.py
├── generate_excel_template.py
├── extract_scraping.py
├── extract_bdd.py
├── clean_aggregate.py
├── import_bdd.py
├── purge_audit_logs.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Requêtes SQL documentées (C2)

Les requêtes d'extraction depuis PostgreSQL Nexo sont dans `extract_bdd.py`.  
Chaque requête est commentée avec : objectif, colonnes sélectionnées, jointures, filtres, optimisations.

---

## Choix techniques

- **API Adresse** (api-adresse.data.gouv.fr) : gratuite, sans clé, données officielles (Base Adresse Nationale) — géocodage des adresses de sites clients
- **openpyxl / pandas** : génération du template Excel import Nexo (deux onglets, lignes d'exemple)
- **pandas** : nettoyage et normalisation des données (dédoublonnage, formats dates/téléphones)
- **psycopg2-binary** : connexion PostgreSQL directe pour extraction et import
- **BeautifulSoup4** : parsing HTML pour le scraping des tarifs

---

*Dernière mise à jour : 23 juin 2026*
