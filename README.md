# Référentiel clients de Nexo

Chaîne de données de la **partie clientèle** de Nexo, l'ERP de Foxabrille Nettoyage : collecte depuis trois sources, nettoyage et fusion en un référentiel unique, base de données dédiée, API REST.

Projet de l'épreuve E1 du titre Développeur en intelligence artificielle (RNCP37827, compétences C1 à C5).

> Dépôt en reconstruction (octobre 2026). Ce README est complété à chaque étape : les sections « Extraction », « Requêtes SQL », « Agrégation », « Base de données et import » et « API » arrivent avec les lots correspondants.

## Sources

| Source | Type | Contenu |
|---|---|---|
| Base PostgreSQL de Nexo | Base de données | Clients, sites, contacts (compte en lecture seule) |
| API Adresse et API Recherche d'entreprises | API REST | Adresses normalisées et géocodées ; données légales des clients avec SIRET |
| Registre national d'immatriculation des copropriétés (ANAH) | Fichier de données (CSV, open data) | Caractéristiques des copropriétés |

## Données et confidentialité

Aucune donnée n'est versionnée : le dossier `data/` est exclu de Git. Les données réelles sont traitées sur le serveur de Nexo ; le développement et la démonstration utilisent des données fictives.

## Installation (développement)

Prérequis : Docker et Docker Compose, Git.

```bash
git clone https://github.com/nexo-rncp37827/nexo-data-pipeline.git
cd nexo-data-pipeline
cp .env.example .env          # puis compléter les mots de passe
docker compose up -d referentiel-db
docker compose --profile pipeline build pipeline
```

## Tests

```bash
docker compose --profile pipeline run --rm pipeline python -c "import referentiel"
uv run pytest                 # si uv est installé localement
```

L'intégration continue (`.github/workflows/ci.yml`) exécute le lint, les tests avec couverture et la construction de l'image à chaque pull request vers `main`.
