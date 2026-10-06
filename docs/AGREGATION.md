# Agrégation et nettoyage du référentiel clients (C3)

`python -m referentiel.agreger` transforme les données brutes d'une extraction en **un seul jeu de données** : le référentiel clients, composé de trois tables liées par leurs identifiants (clients, sites, contacts), au même format, prêtes pour l'import en base (C4).

## Dépendances et commandes

- Python 3.12, `pandas` (lecture, écriture), bibliothèque standard (`difflib`, `unicodedata`, `math`) ; versions figées dans `uv.lock`.
- Sur le serveur :
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.serveur.yml --profile pipeline run --rm pipeline python -m referentiel.agreger
  ```
- En développement : `uv run python -m referentiel.agreger [--brut data/brut/<horodatage>]`.
- Tests : `uv run pytest tests/test_nettoyage.py tests/test_agregation.py`.

**Entrée** : par défaut, la dernière extraction **complète** de `data/brut/` (code de sortie 0 dans son manifeste) ; une extraction partielle n'est jamais agrégée. Les fichiers sont lus en texte, pour que les codes postaux, SIRET et numéros de téléphone gardent leurs zéros.

**Sortie** : `data/propre/<horodatage de l'extraction>/` — `clients.csv`, `sites.csv`, `contacts.csv`, `rejets.csv` (une ligne par entrée écartée, avec son motif) et `rapport.json` (comptages par étape). Codes de sortie : 0 référentiel produit, 1 fichier source manquant, 2 aucune extraction complète.

## Enchaînement

| Étape | Traitement | Code |
|---|---|---|
| 1 | Clients : nettoyage, contrôle du SIRET, jointure du résultat de l'API Recherche d'entreprises | `agregation.clients` |
| 2 | Registre des copropriétés : dédoublonnage, normalisation des codes postaux, coordonnées, SIRET du syndic, nombres de lots | `agregation.coproprietes` |
| 3 | Sites : nettoyage, jointure du géocodage, qualité de l'adresse, rapprochement avec la copropriété | `agregation.sites`, `agregation.rapprocher` |
| 4 | Contacts : nettoyage des coordonnées, rattachement au client, dédoublonnage | `agregation.contacts` |
| 5 | Contrôle de cohérence : tout site et tout contact pointe vers un client présent ; sinon arrêt | `agregation.agreger` |

## Homogénéisation des formats

| Donnée | Format retenu | Règle (`referentiel/nettoyage.py`) |
|---|---|---|
| Textes | Espaces superflus supprimés | `texte` |
| Code postal | 5 chiffres ; un code à 4 chiffres (zéro initial perdu par un tableur) est complété | `code_postal` |
| SIRET | 14 chiffres, clé de Luhn vérifiée (règle particulière de La Poste) ; SIREN = 9 premiers chiffres | `siret` |
| Téléphone | Format international E.164 (`+33…`) | `telephone` |
| E-mail | Minuscules, forme valide, sinon vide | `email` |
| Dates | ISO 8601 (`AAAA-MM-JJ`) | `date_iso` |
| Coordonnées | Degrés décimaux à 6 décimales (≈ 10 cm), bornées à la France métropolitaine | `coordonnee` |
| Nombres de lots, score | Entiers ; décimaux à 3 décimales | `nombre_entier`, `decimal` |
| Valeurs codées | Minuscules (`regie`, `actif`…) ; état de l'établissement `actif` / `ferme` | `agregation.clients` |
| Comparaison de textes | Majuscules, sans accents ni ponctuation, abréviations de voie développées (`BD` → `BOULEVARD`) | `cle_texte`, `similarite` |

## Entrées corrompues supprimées (`rejets.csv`)

| Source | Motif | Raison |
|---|---|---|
| Clients | identifiant ou nom absent | Inutilisable comme client |
| Sites | client inexistant ou écarté | Site orphelin : aucun rattachement possible |
| Sites | ni adresse ni code postal | Impossible à localiser ou à vérifier |
| Contacts | nom absent ; client inexistant | Inutilisable |
| Contacts | aucune coordonnée valide | Ni e-mail ni téléphone exploitable : rien à conserver (minimisation) |
| Contacts | doublon (même client, même nom, même coordonnée) | Premier gardé |
| Registre | numéro d'immatriculation absent | Copropriété non identifiable |
| Registre | doublon | Version la plus récente (`date_derniere_maj`) gardée |

Une donnée invalide qui n'empêche pas d'utiliser la ligne (SIRET à la clé fausse, e-mail mal formé) est vidée et signalée, mais la ligne est conservée : rien n'est jamais remplacé par une valeur inventée.

## Choix d'agrégation

**SIRET des clients.** `verification_siret` vaut `verifie` (trouvé par l'API), `non_trouve`, `siret_invalide` (format ou clé) ou `non_verifie` (API en échec). Pour un SIRET vérifié, le référentiel ajoute la dénomination officielle, l'activité (code NAF), la nature juridique et l'état de l'établissement (`ferme` = client à examiner), ainsi qu'un taux de `similarite_nom` entre le nom saisi dans Nexo et la dénomination officielle (de 0 à 1).

**Adresse des sites.** `geocodage` vaut `fiable` si l'API a trouvé le numéro exact avec un score d'au moins 0,7 : l'adresse normalisée, le code commune INSEE et les coordonnées remplacent alors la saisie (gardée dans `adresse_saisie`). Sinon `a_verifier` (rue seule ou score faible) ou `echec` : la saisie est conservée et le site signalé.

**Rapprochement avec le registre des copropriétés** (sites au géocodage fiable, candidates du même code postal) :

| Situation | Statut |
|---|---|
| Une copropriété à moins de 15 m, ou à moins de 50 m avec une adresse identique (similarité ≥ 0,85) | `correspondance` |
| Plusieurs dans ce cas (syndicat principal et secondaires d'une même résidence) | `correspondance` si une seule a pour syndic le client, sinon `ambigu` (numéros candidats listés) |
| Seulement des copropriétés à moins de 50 m avec une autre adresse | `a_verifier` (la plus proche, avec sa distance) |
| Aucune copropriété à moins de 50 m | `aucune` (site qui n'est pas en copropriété immatriculée, ou adresse à corriger) |
| Géocodage non fiable | `non_evalue` |

Seuils : 15 m correspond à la précision d'un même point d'adresse géocodé (le registre est géocodé sur la même Base Adresse Nationale) ; au-delà de 50 m, il ne s'agit plus du même immeuble.

Pour une correspondance, le référentiel ajoute le numéro d'immatriculation, le nom d'usage, le nombre de lots, le type de syndic, sa raison sociale et son SIRET (syndic professionnel uniquement), le mandat en cours et **`client_est_syndic`**. Cette dernière colonne est une information sur la relation contractuelle, **pas une anomalie** : un syndic peut contracter directement avec Foxabrille ou passer par une régie qui gère le contrat pour lui.

## Limites connues

- Seule l'adresse de référence d'une copropriété est utilisée (pas ses adresses complémentaires) : un site situé à une entrée secondaire peut ressortir `a_verifier` ou `aucune`.
- Les seuils sont fixés a priori ; ils seront ajustés au vu des résultats réels (rapport du serveur).
