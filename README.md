# Référentiel clients de Nexo

Chaîne de données de la **partie clientèle** de Nexo, l'ERP de Foxabrille Nettoyage : collecte depuis trois sources, nettoyage et fusion en un référentiel unique, base de données dédiée, API REST.

Projet de l'épreuve E1 du titre Développeur en intelligence artificielle (RNCP37827, compétences C1 à C5).

> Dépôt en reconstruction (octobre 2026). Ce README est complété à chaque étape : les sections « Requêtes SQL », « Agrégation », « Base de données et import » et « API » arrivent avec les lots correspondants.

## Sources

| Source | Type | Contenu |
|---|---|---|
| Base PostgreSQL de Nexo | Base de données | Clients, sites, contacts (compte en lecture seule) |
| Géocodage de la Géoplateforme (IGN, ex-API Adresse) et API Recherche d'entreprises | API REST | Adresses normalisées et géocodées ; données légales des clients avec SIRET |
| Registre national d'immatriculation des copropriétés (ANAH) | Fichier de données (CSV, open data) | Caractéristiques des copropriétés |

## Extraction (C1)

Un seul point de lancement enchaîne les trois sources :

```bash
python -m referentiel.extraire [--rnic-fichier CHEMIN] [--sortie DOSSIER]
```

| Étape | Source | Module | Règles |
|---|---|---|---|
| 1 | Base PostgreSQL de Nexo | `referentiel/extraction/nexo.py` | Compte `referentiel_lecture` limité à `clients`, `sites`, `contacts` ; transaction en lecture seule ; requêtes versionnées dans `sql/extraction_nexo_*.sql` |
| 2 | Géocodage des sites — `https://data.geopf.fr/geocodage/search` | `referentiel/extraction/adresses.py` | Une requête par site (adresse + code postal + ville), 10 requêtes/s au plus |
| 3 | Recherche d'entreprises — `https://recherche-entreprises.api.gouv.fr/search` | `referentiel/extraction/entreprises.py` | Une requête par SIRET valide (14 chiffres), 5 requêtes/s au plus (limite annoncée : 7) |
| 4 | Registre national d'immatriculation des copropriétés (CSV ≈ 390 Mo) | `referentiel/extraction/coproprietes.py` | Téléchargé par son lien permanent data.gouv.fr (ou fichier fourni), lu en flux ; seules les copropriétés des codes postaux des sites sont gardées |

**Initialisation.** Configuration lue dans les variables d'environnement (`referentiel/config.py`) ; sans `NEXO_DATABASE_URL`, arrêt immédiat (code 2). Connexions : PostgreSQL (`psycopg`, délai 10 s), HTTP (`httpx`, délai 10 s, en-tête `User-Agent` identifiant le projet).

**Erreurs et exceptions.** Les erreurs 429 et 5xx, délais dépassés et erreurs réseau sont rejoués trois fois (attente doublée, ou durée `Retry-After`) ; une ligne qui échoue malgré tout garde son statut (`erreur_http_503`, `timeout`…) et rend l'extraction « partielle ». Une source entièrement inaccessible (base injoignable, API qui ne répond à aucun appel, fichier absent, téléchargement interrompu, page HTML reçue au lieu du CSV, colonne manquante) est signalée « échec ». **Aucune donnée n'est jamais remplacée par des valeurs simulées.** Sans la base Nexo, les autres sources n'ont pas d'objet : arrêt.

**Fin de traitement et sauvegarde.** Les données brutes sont écrites dans `data/brut/<horodatage UTC>/` (un CSV par source) avec un `manifeste.json` : statut, durée et nombre de lignes par source, répartition des statuts des appels d'API, empreinte SHA-256 du fichier du registre. Code de sortie : `0` toutes les données récupérées, `1` source en échec ou extraction partielle, `2` configuration incomplète.

**Minimisation.** Ni notes libres, ni codes d'accès, ni e-mail du client ne sont extraits de Nexo. Dans le registre des copropriétés, la colonne `identification_representant_legal` n'est jamais conservée, et le nom du représentant légal n'est gardé que s'il a un SIRET (syndic professionnel) : un syndic bénévole est une personne physique.

### Mise en place sur le serveur de Nexo

1. Créer le compte en lecture seule (une fois) :
   ```bash
   read -s MDP && docker exec -i nexo-db psql -U nexo -d nexo_db -v mdp="$MDP" < sql/role_lecture_nexo.sql
   ```
2. Créer `.env` (voir `.env.example`) avec `NEXO_DATABASE_URL=postgresql://referentiel_lecture:<mot de passe>@nexo-db:5432/nexo_db`.
3. Lancer l'extraction (le pipeline rejoint le réseau interne de Nexo) :
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.serveur.yml --profile pipeline run --rm pipeline python -m referentiel.extraire
   ```

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
