# Référentiel clients de Nexo

Chaîne de données de la **partie clientèle** de Nexo, l'ERP de Foxabrille Nettoyage : collecte depuis trois sources, nettoyage et fusion en un référentiel unique, base de données dédiée, API REST.

Projet de l'épreuve E1 du titre Développeur en intelligence artificielle (RNCP37827, compétences C1 à C5).

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

## Requêtes SQL (C2)

Requêtes versionnées dans `sql/`, documentées (choix de sélection, filtres, jointures, optimisations, mesures) dans [`docs/REQUETES_SQL.md`](docs/REQUETES_SQL.md).

Mesure des plans d'exécution sur le serveur :

```bash
docker compose -f docker-compose.yml -f docker-compose.serveur.yml --profile pipeline run --rm pipeline python -m referentiel.plans
```

## Agrégation (C3)

Nettoyage, homogénéisation des formats et fusion des trois sources en un référentiel unique (clients, sites, contacts), avec la liste des entrées écartées et leur motif : voir [`docs/AGREGATION.md`](docs/AGREGATION.md).

```bash
docker compose -f docker-compose.yml -f docker-compose.serveur.yml --profile pipeline run --rm pipeline python -m referentiel.agreger
```

## Base de données et import (C4)

Modèle Merise (MCD, MLD, MPD) et choix de la base : [`docs/MODELE_DONNEES.md`](docs/MODELE_DONNEES.md). Registre des traitements et procédures de tri : [`docs/RGPD.md`](docs/RGPD.md).

### Dépendances

Docker et Docker Compose (base PostgreSQL 16, image officielle) ; l'image du pipeline et de l'API contient Python 3.12 et les dépendances figées dans `uv.lock` (`pandas`, `psycopg`, `httpx`, `fastapi`, `uvicorn`, `pyjwt`).

### Installation de la base

1. Renseigner dans `.env` (voir `.env.example`) `REFERENTIEL_DB_PASSWORD`, `REFERENTIEL_IMPORT_PASSWORD`, `REFERENTIEL_API_PASSWORD` (`openssl rand -hex 24`) et `REFERENTIEL_DATABASE_URL` (compte `referentiel_import`).
2. Créer la base : `docker compose up -d referentiel-db`. Au premier démarrage (volume vide), PostgreSQL exécute `sql/referentiel/01_schema.sql` (MPD) puis `02_roles.sh` (comptes).
3. Vérifier : `docker compose exec referentiel-db psql -U referentiel -d referentiel -c "\dt"` (6 tables).

Pour recréer la base de zéro : `docker compose down -v` puis l'étape 2 (supprime le volume et donc les données du référentiel, qui seront réimportées).

### Script d'import

```bash
docker compose -f docker-compose.yml -f docker-compose.serveur.yml --profile pipeline run --rm pipeline python -m referentiel.importer [--propre data/propre/<horodatage>]
```

- **Entrée** : le dernier référentiel agrégé (`data/propre/<horodatage>/`).
- **Traitement**, dans une seule transaction : insertion ou mise à jour des copropriétés, clients, sites, contacts et associations ; suppression de ce qui n'existe plus dans la source (P1) ; contacts en fin de conservation écartés (P2) ; ligne de journal dans la table `import`.
- **Rejouable** : importer deux fois le même dossier ne change rien. En cas d'erreur (donnée refusée par une contrainte, base injoignable), rien n'est modifié et le journal garde un import « echec ».
- **Codes de sortie** : 0 réussi, 1 échec (base inchangée), 2 configuration ou dossier manquant.
- **Tests** : `tests/test_integration_referentiel.py` (création de la base, import, idempotence, synchronisation, annulation, droits des comptes), exécutés en CI.

### Tri et chaîne hebdomadaire

`python -m referentiel.purger` applique les procédures P3 et P4. La chaîne complète (extraction, agrégation, import, tri) est planifiée sur le serveur :

```bash
crontab -e
# ajouter la ligne :
10 4 * * 1 bash /home/ubuntu/nexo-data-pipeline/scripts/chaine_hebdomadaire.sh
```

## API REST (C5)

API en **lecture seule** qui met le référentiel à disposition des applications internes (FastAPI, standard **OpenAPI 3.1**). Spécification complète : [`docs/openapi.json`](docs/openapi.json) (régénérée par `python -m referentiel.api.exporter_openapi`, vérifiée par la CI) ; documentation interactive sur `/docs` une fois l'API lancée.

### Endpoints

| Méthode | Chemin | Rôle | Portées requises |
|---|---|---|---|
| POST | `/auth/jeton` | Obtenir un jeton d'accès | — (identifiant + secret) |
| GET | `/clients` | Lister les clients (filtres : `type_client`, `verification_siret`, `etat_etablissement`) | `referentiel` |
| GET | `/clients/{client_id}` | Lire un client | `referentiel` |
| GET | `/clients/{client_id}/sites` | Sites d'un client | `referentiel` |
| GET | `/clients/{client_id}/contacts` | Contacts d'un client | `referentiel` + `contacts` |
| GET | `/sites` | Lister les sites (filtres : `client_id`, `code_postal`, `geocodage`, `rapprochement_copropriete`, `client_est_syndic`) | `referentiel` |
| GET | `/sites/{site_id}` | Lire un site (avec `client_est_syndic`, calculé par la vue `v_site`) | `referentiel` |
| GET | `/sites/{site_id}/contacts` | Contacts qui suivent un site | `referentiel` + `contacts` |
| GET | `/coproprietes` | Lister les copropriétés rapprochées | `referentiel` |
| GET | `/coproprietes/{numero_immatriculation}` | Lire une copropriété | `referentiel` |
| GET | `/contacts` | Lister les contacts (filtre : `client_id`) | `referentiel` + `contacts` |
| GET | `/contacts/{contact_id}` | Lire un contact (avec les sites suivis) | `referentiel` + `contacts` |
| GET | `/sante` | État du service, sans donnée | aucune |

Listes paginées : paramètres `limite` (1 à 500, 100 par défaut) et `decalage` ; réponse `{total, limite, decalage, elements}`.

### Authentification et autorisation

- **Qui peut appeler l'API** : uniquement les applications déclarées dans `API_CLIENTS` (identifiant, **empreinte scrypt** du secret, portées). Le secret n'est jamais stocké en clair.
- **Jeton** : `POST /auth/jeton` (formulaire OAuth2 : `username` = identifiant, `password` = secret, `scope` facultatif) renvoie un **JWT signé HS256**, valable **30 minutes** (`API_JWT_MINUTES`, 60 au plus), avec émetteur, audience et portées. Il se passe dans l'en-tête `Authorization: Bearer <jeton>`.
- **Portées** : `referentiel` (clients, sites, copropriétés) ; `contacts` en plus pour les données personnelles des contacts (traitement T1 du registre). Une application n'obtient que les portées qui lui sont accordées.
- **Réponses** : 401 sans jeton, jeton invalide, falsifié ou expiré ; 403 portée insuffisante ; 404 ressource introuvable ; 503 base injoignable. Toute méthode d'écriture renvoie 405.
- **Lecture seule à deux niveaux** : l'API n'expose que des `GET`, et se connecte avec le compte PostgreSQL `referentiel_api`, qui n'a que le droit `SELECT` (transactions en lecture seule par défaut).
- **Exposition** : port publié sur `127.0.0.1` uniquement ; la base n'est jamais exposée.

### Installation de l'API

1. La base est installée (section précédente) et alimentée par un import.
2. Compléter `.env` (les commandes écrivent directement dans le fichier ; aucun secret ne s'affiche) :
   ```bash
   # adresse de la base pour le compte en lecture seule de l'API
   echo "REFERENTIEL_API_DATABASE_URL=postgresql://referentiel_api:$(grep '^REFERENTIEL_API_PASSWORD=' .env | cut -d= -f2)@referentiel-db:5432/referentiel" >> .env
   # secret de signature des jetons
   docker compose --profile api run --rm -T api python -m referentiel.api.secret jwt >> .env
   # secret de l'application cliente : le noter dans un gestionnaire de mots de passe et le lui transmettre
   openssl rand -hex 24
   read -s SECRET                # coller le secret, puis Entrée (rien ne s'affiche)
   # empreinte du secret (jamais le secret lui-même), une seule ligne API_CLIENTS
   sed -i '/^API_CLIENTS=/d' .env
   printf '%s\n' "$SECRET" | docker compose --profile api run --rm -T api python -m referentiel.api.secret client nexo referentiel contacts >> .env
   chmod 600 .env
   ```
   Contrôle : `grep -c '^API_CLIENTS=' .env` doit afficher `1`. Sans application déclarée, l'API refuse toute demande de jeton (401 « Identifiants invalides »). Après toute modification de `.env`, recréer le conteneur : `docker compose --profile api up -d --force-recreate api`.
3. Lancer : `docker compose --profile api up -d --build api`.
4. Vérifier : `curl -s http://127.0.0.1:8010/sante` doit renvoyer `{"statut":"ok","base":"ok"}`.
5. Appel authentifié (`SECRET` saisi à l'étape 2) :
   ```bash
   JETON=$(curl -s -X POST http://127.0.0.1:8010/auth/jeton -d "username=nexo&password=$SECRET" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
   curl -s -H "Authorization: Bearer $JETON" "http://127.0.0.1:8010/clients?limite=2"
   ```

Tests : `tests/test_api_securite.py` (authentification, portées, jetons expirés ou falsifiés, lecture seule, spécification complète) et `tests/test_integration_api.py` (API branchée sur une vraie base créée par le MPD, avec le compte `referentiel_api`).

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
docker compose --profile api up -d --build api
```

## Tests

```bash
docker compose --profile pipeline run --rm pipeline python -c "import referentiel"
uv run pytest                 # si uv est installé localement
```

L'intégration continue (`.github/workflows/ci.yml`) exécute le lint, les tests avec couverture et la construction de l'image à chaque pull request vers `main`.
