-- Extraction des clients de Nexo (source : base PostgreSQL de l'ERP, compte en lecture seule).
-- Sélection : identité légale et adresse du client ; ni notes libres ni e-mail (minimisation).
-- Filtre : aucun — tous les clients, actifs ou non (le statut est conservé pour le nettoyage).
SELECT
    c.id            AS client_id,
    c.nom,
    c.type_client,
    c.siret,
    c.adresse,
    c.code_postal,
    c.ville,
    c.statut,
    c.created_at::date AS date_creation,
    c.updated_at::date AS date_mise_a_jour
FROM clients AS c
ORDER BY c.id;
