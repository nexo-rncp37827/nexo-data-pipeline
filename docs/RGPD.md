# Données personnelles du référentiel clients (C4)

Responsable des traitements : Foxabrille Nettoyage, représentée par sa gérante. Contact pour l'exercice des droits : contact@foxabrille.com. Document à valider par la gérante ; revu chaque année (procédure P6).

## Registre des traitements (article 30 du RGPD)

Les fiches ci-dessous couvrent tous les traitements de données personnelles impliqués dans la base `referentiel` et dans la chaîne qui l'alimente.

### T1 — Gestion du référentiel des contacts clients

| Rubrique | Contenu |
|---|---|
| Finalité | Disposer de coordonnées professionnelles fiables des interlocuteurs des clients (régies, syndics, entreprises) pour l'exécution des contrats de prestation |
| Base légale | Exécution des contrats avec les clients ; intérêt légitime de l'entreprise à joindre ses interlocuteurs professionnels |
| Personnes concernées | Interlocuteurs professionnels des clients (gestionnaires de régie, comptables, gestionnaires de site) |
| Données | Nom, rôle, poste, e-mail professionnel, téléphones professionnels (table `contact`) ; sites suivis (`contact_site`) |
| Source | Base de Nexo (saisie par l'entreprise), compte en lecture seule limité aux tables clients, sites et contacts |
| Destinataires | Gérante et direction de Foxabrille ; applications internes via l'API (compte `referentiel_api`, lecture seule, accès authentifié) |
| Sous-traitant | OVH (hébergement du serveur, France) |
| Transferts hors UE | Aucun |
| Durée de conservation | Tant que le client est actif ; puis 3 ans après la fin de la relation (dernière mise à jour d'un client inactif), puis suppression (P2). Synchronisation avec Nexo à chaque import (P1) |
| Sécurité | Base non exposée sur Internet (port local uniquement), comptes de moindre privilège, mots de passe hors dépôt, contraintes de format, sauvegarde du serveur ; aucune donnée personnelle dans les journaux ni dans Git |

### T2 — Vérification et enrichissement des données clients et sites

| Rubrique | Contenu |
|---|---|
| Finalité | Vérifier l'identité légale des clients (SIRET), normaliser et localiser les adresses des sites, les rapprocher du registre national des copropriétés |
| Personnes concernées | Aucune donnée personnelle envoyée aux API : adresses d'immeubles et SIRET d'entreprises. Le registre des copropriétés peut contenir le nom d'un syndic bénévole (personne physique) |
| Données et minimisation | Du registre ne sont gardés que les copropriétés des codes postaux des sites et les colonnes utiles ; la colonne d'identification du représentant légal n'est jamais conservée, et son nom ne l'est que s'il a un SIRET (syndic professionnel) |
| Sources | API de géocodage de la Géoplateforme (IGN), API Recherche d'entreprises (DINUM), Registre national d'immatriculation des copropriétés (ANAH, Licence Ouverte 2.0) |
| Durée de conservation | Copropriétés : tant qu'un site leur correspond. Fichiers de travail : 30 jours (P3) |

### T3 — Journaux techniques de la chaîne

| Rubrique | Contenu |
|---|---|
| Finalité | Tracer les imports et diagnostiquer les erreurs |
| Données | Horodatages, comptages, statuts ; aucune donnée personnelle (le journal des requêtes HTTP est désactivé) |
| Durée de conservation | Journal des imports : 1 an (P4) ; journaux de la chaîne : 30 jours |

## Procédures de tri des données personnelles

| N° | Procédure | Type | Fréquence | Mise en œuvre |
|---|---|---|---|---|
| P1 | Synchronisation avec Nexo : un client, site ou contact supprimé dans Nexo est supprimé du référentiel | Automatisée | À chaque import (chaque semaine) | `referentiel/importer.py` (suppression des absents, dans la même transaction) |
| P2 | Fin de relation : les contacts d'un client qui n'est plus actif depuis plus de 3 ans ne sont plus conservés | Automatisée | À chaque import | `importer.contacts_conserves` |
| P3 | Fichiers de travail (extractions brutes, référentiels agrégés, plans, fichier du registre) supprimés après 30 jours, sauf la dernière extraction complète | Automatisée | Chaque semaine | `referentiel/purger.py` |
| P4 | Journal des imports : lignes de plus d'un an supprimées | Automatisée | Chaque semaine | `referentiel/purger.py` |
| P5 | Exercice des droits (accès, rectification, effacement, opposition) | Manuelle | À chaque demande, réponse sous un mois | Voir ci-dessous |
| P6 | Revue du registre, des durées de conservation et des comptes d'accès | Manuelle | Une fois par an, et à chaque nouvelle source ou finalité | Gérante, avec l'administratrice technique |

Les procédures automatisées s'exécutent chaque semaine par `scripts/chaine_hebdomadaire.sh` (extraction → agrégation → import → tri), planifié dans la crontab du serveur.

**P5 — exercice des droits, étape par étape.**
1. La demande arrive à contact@foxabrille.com ; elle est enregistrée (date, demandeur, droit exercé).
2. Vérifier l'identité du demandeur (adresse e-mail professionnelle connue ou justificatif).
3. Accès : extraire ses données avec `SELECT * FROM contact WHERE email = '…'` et les sites suivis (`contact_site`), et les transmettre.
4. Rectification ou effacement : corriger ou supprimer **dans Nexo** (source) ; l'import suivant applique le changement au référentiel (P1). En cas d'urgence, supprimer aussi directement le contact dans le référentiel (la suppression en cascade retire ses associations).
5. Répondre au demandeur sous un mois et noter la date de clôture.
