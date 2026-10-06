-- Extraction des contacts professionnels rattachés à un client ou à un site.
-- Données personnelles : nom, fonction, coordonnées professionnelles (finalité : gestion de la
-- relation contractuelle, voir le registre des traitements).
-- Filtre : contacts rattachés à au moins un client ou un site (LEFT JOIN pour retrouver le client
-- d'un contact de site).
SELECT
    ct.id                              AS contact_id,
    COALESCE(ct.client_id, s.client_id) AS client_id,
    ct.site_id,
    ct.nom,
    ct.role,
    ct.poste,
    ct.email,
    ct.telephone_fixe,
    ct.telephone_portable
FROM contacts AS ct
LEFT JOIN sites AS s ON s.id = ct.site_id
WHERE ct.client_id IS NOT NULL OR ct.site_id IS NOT NULL
ORDER BY ct.id;
