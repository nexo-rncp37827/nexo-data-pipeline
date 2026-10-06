#!/bin/bash
# Comptes de moindre privilège, créés à l'initialisation de la base (conteneur referentiel-db).
#  - referentiel_import : écrit le référentiel (script d'import) ;
#  - referentiel_api    : lecture seule (API REST).
set -euo pipefail
: "${REFERENTIEL_IMPORT_PASSWORD:?REFERENTIEL_IMPORT_PASSWORD manquant}"
: "${REFERENTIEL_API_PASSWORD:?REFERENTIEL_API_PASSWORD manquant}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v mdp_import="$REFERENTIEL_IMPORT_PASSWORD" -v mdp_api="$REFERENTIEL_API_PASSWORD" <<'SQL'
CREATE ROLE referentiel_import LOGIN PASSWORD :'mdp_import';
CREATE ROLE referentiel_api LOGIN PASSWORD :'mdp_api';
GRANT CONNECT ON DATABASE referentiel TO referentiel_import, referentiel_api;
GRANT USAGE ON SCHEMA public TO referentiel_import, referentiel_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON client, site, copropriete, contact, contact_site, import
  TO referentiel_import;
GRANT USAGE ON SEQUENCE import_import_id_seq TO referentiel_import;
GRANT SELECT ON client, site, copropriete, contact, contact_site, v_site TO referentiel_api;
ALTER ROLE referentiel_api SET default_transaction_read_only = on;
SQL
