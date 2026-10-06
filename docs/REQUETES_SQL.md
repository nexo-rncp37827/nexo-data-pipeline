# Requêtes SQL d'extraction (C2)

Les trois requêtes qui extraient la partie clientèle de la base PostgreSQL 16 de Nexo sont versionnées dans `sql/` et exécutées telles quelles par `referentiel/extraction/nexo.py`, avec le compte `referentiel_lecture` (lecture seule, droits limités aux trois tables, `sql/role_lecture_nexo.sql`).

## Objectif de collecte

Constituer, pour chaque client, l'identité légale (SIRET, type), l'adresse de ses sites et ses contacts professionnels, afin de les vérifier auprès des API publiques et du registre des copropriétés. **Tout ce qui n'est pas nécessaire à cet objectif est exclu dès la requête** (minimisation RGPD, moins de données transférées).

## 1. Clients — `sql/extraction_nexo_clients.sql`

| Choix | Détail | Raison |
|---|---|---|
| Sélection | `id`, `nom`, `type_client`, `siret`, `adresse`, `code_postal`, `ville`, `statut`, dates de création et de mise à jour | Identité légale et adresse : clés de la vérification SIRET ; dates pour la fraîcheur de l'information |
| Exclusions | `notes` (texte libre), `email`, `score_geocodage` | Notes : risque de données personnelles non maîtrisées ; e-mail inutile à la collecte ; le score est recalculé par l'API |
| Filtre | Aucun | Tous les clients sont collectés, actifs ou non : le statut est conservé et traité au nettoyage (un client inactif reste utile pour l'historique des sites) |
| Conversions | `created_at::date`, `updated_at::date` | L'heure n'a pas d'usage ; format homogène dès la source |
| Tri | `ORDER BY c.id` | Résultat reproductible d'une exécution à l'autre |

## 2. Sites — `sql/extraction_nexo_sites.sql`

| Choix | Détail | Raison |
|---|---|---|
| Sélection | `id`, `client_id`, `nom`, `adresse`, `code_postal`, `ville`, dates de début et de fin de contrat, `type_client` | L'adresse est la clé du géocodage et du rapprochement avec le registre |
| Jointure | `JOIN clients AS c ON c.id = s.client_id` (interne) | Ajoute le type du client (régie, entreprise, copropriété) sans seconde requête ; `sites.client_id` est obligatoire (clé étrangère `NOT NULL`), une jointure interne ne perd donc aucun site |
| Exclusions | `code_acces`, `notes`, `prestations` | Code d'accès : information de sécurité, jamais extraite ; notes : texte libre |
| Tri | `ORDER BY s.id` | Reproductibilité |

## 3. Contacts — `sql/extraction_nexo_contacts.sql`

| Choix | Détail | Raison |
|---|---|---|
| Sélection | `id`, nom, rôle, poste, e-mail et téléphones professionnels, `site_id`, client calculé | Contacts professionnels des clients : données personnelles nécessaires à la relation contractuelle (registre des traitements) |
| Jointure | `LEFT JOIN sites AS s ON s.id = ct.site_id` | Un contact peut être rattaché à un site sans l'être au client : la jointure externe retrouve son client sans écarter les contacts rattachés directement au client |
| Calcul | `COALESCE(ct.client_id, s.client_id) AS client_id` | Un seul identifiant de client pour tous les contacts, quel que soit leur rattachement |
| Filtre | `WHERE ct.client_id IS NOT NULL OR ct.site_id IS NOT NULL` | Écarte un éventuel contact orphelin, sans client ni site |
| Tri | `ORDER BY ct.id` | Reproductibilité |

## Optimisations appliquées

1. **Projection explicite, jamais `SELECT *`** : seules les colonnes utiles sont lues et transférées (minimisation et volume) ; un test vérifie l'absence de `SELECT *`, `notes` et `code_acces` dans les requêtes.
2. **Jointures sur des colonnes indexées** : `sites.client_id` (index `ix_sites_client_id`, migration 019 de Nexo) et `contacts.site_id` (`idx_contacts_site_id`, migration 060) ; tris sur les clés primaires (index uniques).
3. **Pas de sous-requête corrélée** : le client d'un contact de site est obtenu par une jointure et un `COALESCE`, et non par une sous-requête exécutée pour chaque contact.
4. **Filtrage et conversions côté base** : le `WHERE` et les `::date` sont appliqués par PostgreSQL, avant le transfert, plutôt qu'en Python.
5. **Une connexion, une transaction en lecture seule** pour les trois requêtes : pas de reconnexion, aucune écriture possible.
6. **Mesure plutôt que supposition** : `python -m referentiel.plans` exécute `EXPLAIN (ANALYZE, BUFFERS)` sur chaque requête, puis une seconde fois avec les parcours séquentiels désactivés pour comparer au plan par index.

**Lecture des plans.** Sur des tables de quelques dizaines à quelques centaines de lignes (une ou deux pages de 8 Ko), PostgreSQL choisit un parcours séquentiel et une jointure par hachage : lire une page entière coûte moins que de passer par un index. C'est le comportement attendu, pas une absence d'optimisation. Les index sont en place et utilisables (plan de comparaison) ; ils deviennent avantageux quand les tables grossissent.

## Mesures sur la base de production

Exécution de `python -m referentiel.plans` sur le serveur de Nexo, le 06/10/2026 à 11h12 UTC, avec le compte `referentiel_lecture` (plans complets : `data/plans/20261006T111254Z.txt`, conservé sur le serveur).

| Requête | Lignes | Plan choisi par PostgreSQL | Durée | Plan par index (comparaison) | Durée |
|---|---|---|---|---|---|
| Clients | 35 | Parcours séquentiel, tri | 0,319 ms | Parcours de la clé primaire | 0,128 ms |
| Sites | 145 | Parcours séquentiels, jointure par hachage | 0,682 ms | Parcours d'index, boucle imbriquée | 0,526 ms |
| Contacts | 162 | Parcours séquentiels, jointure externe par hachage | 0,834 ms | Parcours d'index | 1,769 ms |

**Interprétation.**
- Les trois requêtes s'exécutent en moins d'une milliseconde chacune : le volume de la partie clientèle (35 clients, 145 sites, 162 contacts) ne pose aucun problème de performance, et l'extraction complète dure 0,07 s (manifeste du 06/10).
- Pour les contacts, le plan choisi par PostgreSQL est deux fois plus rapide que le plan forcé par index : sur une petite table, le parcours séquentiel et la jointure par hachage sont le bon choix, ce que confirme la mesure.
- Pour les clients et les sites, le plan par index paraît légèrement plus rapide, mais l'écart (0,2 ms) est dans la marge de mesure : chaque requête est d'abord exécutée avec le plan choisi, qui lit les pages depuis le disque, puis avec le plan par index, qui les trouve en mémoire. Cette mesure ne justifie donc pas de forcer un plan.
- Conclusion : aucune optimisation supplémentaire n'est utile à ce volume. Les index existants (`ix_sites_client_id`, `idx_contacts_site_id`) sont utilisables, comme le montre le plan de comparaison, et prendront le relais si les tables grossissent ; la mesure sera rejouée à chaque évolution des requêtes.

## Exécution et tests

- Extraction : `python -m referentiel.extraire` (voir README, section Extraction).
- Mesure des plans : `python -m referentiel.plans` → résumé à l'écran, plans complets dans `data/plans/<horodatage>.txt`.
- Tests d'intégration : `tests/test_integration_postgres.py` exécute les trois requêtes sur un PostgreSQL 16 au schéma réel des tables de Nexo (`tests/donnees/schema_nexo_clientele.sql`), avec des données fictives ; il vérifie aussi que le compte ne peut ni écrire ni lire une table hors périmètre. La CI les exécute à chaque pull request (service `postgres:16`) ; en local : `TEST_POSTGRES_ADMIN_URL=postgresql://... uv run pytest`.
