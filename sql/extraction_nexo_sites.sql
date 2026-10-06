-- Extraction des sites d'intervention, avec le type du client pour le rapprochement avec le
-- registre des copropriétés.
-- Jointure : sites (n) → clients (1) sur sites.client_id (index ix_sites_client_id, migration 019).
-- Sélection : adresse et dates de contrat ; ni code d'accès ni notes (minimisation).
SELECT
    s.id                  AS site_id,
    s.client_id,
    c.type_client,
    s.nom,
    s.adresse,
    s.code_postal,
    s.ville,
    s.date_debut_contrat,
    s.date_fin_contrat
FROM sites AS s
JOIN clients AS c ON c.id = s.client_id
ORDER BY s.id;
