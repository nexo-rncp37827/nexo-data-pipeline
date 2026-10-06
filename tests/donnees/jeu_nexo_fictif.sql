-- Jeu de données fictif (aucune donnée réelle) pour les tests d'intégration.
INSERT INTO clients (nom, type_client, siret, adresse, code_postal, ville, statut, notes) VALUES
 ('Régie Fictive A', 'regie', '00000000000017', '1 rue A', '69003', 'Lyon', 'actif', 'note interne'),
 ('Entreprise Fictive B', 'entreprise', '123', '2 rue B', '69100', 'Villeurbanne', 'actif', NULL);
INSERT INTO sites (client_id, nom, adresse, code_postal, ville, code_acces) VALUES
 (1, 'Résidence Test', '10 rue de l''Exemple', '69003', 'Lyon', '1234A'),
 (1, 'Résidence Test 2', '12 rue de l''Exemple', '69003', 'Lyon', NULL),
 (2, 'Bureaux B', '2 rue B', '69100', 'Villeurbanne', NULL);
INSERT INTO contacts (client_id, site_id, nom, role, email) VALUES
 (1, NULL, 'Contact Fictif', 'client', 'contact@exemple.test'),
 (NULL, 3, 'Gardien Fictif', 'gestionnaire_site', NULL);
