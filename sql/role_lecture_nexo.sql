-- Compte PostgreSQL dédié au pipeline, en lecture seule, limité aux trois tables de la partie
-- clientèle. À exécuter une seule fois sur la base de Nexo par l'administratrice ; le mot de
-- passe est passé en variable psql (-v mdp=...), jamais écrit dans un fichier versionné :
--   docker exec -i nexo-db psql -U nexo -d nexo_db -v mdp="$MDP" < sql/role_lecture_nexo.sql
CREATE ROLE referentiel_lecture LOGIN PASSWORD :'mdp';
ALTER ROLE referentiel_lecture SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE nexo_db TO referentiel_lecture;
GRANT USAGE ON SCHEMA public TO referentiel_lecture;
GRANT SELECT ON clients, sites, contacts TO referentiel_lecture;
