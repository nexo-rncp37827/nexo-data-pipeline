-- Modèle physique des données (MPD) du référentiel clients — PostgreSQL 16.
-- Traduction du MLD de docs/MODELE_DONNEES.md. Exécuté à la création de la base (conteneur
-- referentiel-db, dossier /docker-entrypoint-initdb.d) et par la CI sur une base vide.
-- Colonnes marquées [DP] dans les commentaires : données personnelles (registre des traitements).

CREATE TABLE client (
    client_id               integer      PRIMARY KEY,           -- identifiant Nexo
    nom                     varchar(255) NOT NULL,
    type_client             varchar(30)  NOT NULL
        CHECK (type_client IN ('regie', 'entreprise', 'copropriete', 'collectivite', 'particulier')),
    statut                  varchar(30),
    siret                   char(14)     CHECK (siret ~ '^[0-9]{14}$'),
    siren                   char(9)      CHECK (siren ~ '^[0-9]{9}$'),
    verification_siret      varchar(20)  NOT NULL
        CHECK (verification_siret IN ('verifie', 'non_trouve', 'siret_invalide', 'non_verifie')),
    denomination_officielle varchar(255),
    similarite_nom          numeric(4,3) CHECK (similarite_nom BETWEEN 0 AND 1),
    etat_etablissement      varchar(10)  CHECK (etat_etablissement IN ('actif', 'ferme')),
    activite_principale     varchar(10),
    nature_juridique        varchar(10),
    adresse                 varchar(500),
    code_postal             char(5)      CHECK (code_postal ~ '^[0-9]{5}$'),
    ville                   varchar(100),
    date_creation           date,
    date_mise_a_jour        date,
    importe_le              timestamptz  NOT NULL DEFAULT now(),
    CHECK (siren IS NULL OR siren = left(siret, 9))
);

CREATE TABLE copropriete (
    numero_immatriculation  varchar(20)  PRIMARY KEY,           -- registre national (ANAH)
    adresse                 varchar(500),
    nom_usage               varchar(255),
    nombre_total_lots       integer      CHECK (nombre_total_lots >= 0),
    nombre_lots_habitation  integer      CHECK (nombre_lots_habitation >= 0),
    type_syndic             varchar(30),
    syndic_raison_sociale   varchar(255),                       -- jamais un syndic bénévole
    syndic_siret            char(14)     CHECK (syndic_siret ~ '^[0-9]{14}$'),
    mandat_en_cours         varchar(30),
    importe_le              timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE site (
    site_id                     integer      PRIMARY KEY,       -- identifiant Nexo
    client_id                   integer      NOT NULL REFERENCES client (client_id),
    numero_immatriculation      varchar(20)  REFERENCES copropriete (numero_immatriculation),
    nom                         varchar(255),
    adresse_saisie              varchar(500),
    code_postal_saisi           char(5)      CHECK (code_postal_saisi ~ '^[0-9]{5}$'),
    ville_saisie                varchar(100),
    adresse_normalisee          varchar(500),
    numero                      varchar(20),
    voie                        varchar(255),
    code_postal                 char(5)      CHECK (code_postal ~ '^[0-9]{5}$'),
    code_insee                  char(5),
    commune                     varchar(100),
    latitude                    numeric(9,6) CHECK (latitude BETWEEN 41 AND 51.5),
    longitude                   numeric(9,6) CHECK (longitude BETWEEN -5.5 AND 10),
    score_geocodage             numeric(4,3) CHECK (score_geocodage BETWEEN 0 AND 1),
    geocodage                   varchar(20)  NOT NULL CHECK (geocodage IN ('fiable', 'a_verifier', 'echec')),
    date_debut_contrat          date,
    date_fin_contrat            date,
    rapprochement_copropriete   varchar(20)  NOT NULL
        CHECK (rapprochement_copropriete IN ('correspondance', 'a_verifier', 'ambigu', 'aucune', 'non_evalue')),
    distance_copropriete_m      numeric(6,1) CHECK (distance_copropriete_m >= 0),
    immatriculations_candidates varchar(500),
    importe_le                  timestamptz  NOT NULL DEFAULT now(),
    CHECK (date_fin_contrat IS NULL OR date_debut_contrat IS NULL OR date_fin_contrat >= date_debut_contrat),
    CHECK ((numero_immatriculation IS NULL) = (rapprochement_copropriete NOT IN ('correspondance', 'a_verifier')))
);

CREATE TABLE contact (
    contact_id          integer      PRIMARY KEY,               -- identifiant Nexo
    client_id           integer      NOT NULL REFERENCES client (client_id) ON DELETE CASCADE,
    nom                 varchar(200) NOT NULL,                  -- [DP]
    role                varchar(30),
    poste               varchar(100),                           -- [DP]
    email               varchar(255) CHECK (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[a-z]{2,}$'), -- [DP]
    telephone_fixe      varchar(16)  CHECK (telephone_fixe ~ '^\+33[1-9][0-9]{8}$'),     -- [DP]
    telephone_portable  varchar(16)  CHECK (telephone_portable ~ '^\+33[1-9][0-9]{8}$'), -- [DP]
    importe_le          timestamptz  NOT NULL DEFAULT now(),
    CHECK (email IS NOT NULL OR telephone_fixe IS NOT NULL OR telephone_portable IS NOT NULL)
);

-- Association SUIVRE (n:n) : une personne suit plusieurs sites, un site a plusieurs contacts.
CREATE TABLE contact_site (
    contact_id  integer NOT NULL REFERENCES contact (contact_id) ON DELETE CASCADE,
    site_id     integer NOT NULL REFERENCES site (site_id) ON DELETE CASCADE,
    PRIMARY KEY (contact_id, site_id)
);

-- Journal des imports (traçabilité, durée de conservation : 1 an).
CREATE TABLE import (
    import_id      serial       PRIMARY KEY,
    extraction     varchar(20)  NOT NULL,                       -- horodatage de l'extraction source
    debut          timestamptz  NOT NULL DEFAULT now(),
    fin            timestamptz,
    nb_clients     integer,
    nb_sites       integer,
    nb_coproprietes integer,
    nb_contacts    integer,
    nb_contacts_sites integer,
    nb_supprimes   integer,
    statut         varchar(10)  NOT NULL DEFAULT 'en_cours' CHECK (statut IN ('en_cours', 'ok', 'echec'))
);

-- Index : clés étrangères (jointures de l'API, suppressions en cascade) et filtres usuels.
CREATE INDEX ix_site_client_id ON site (client_id);
CREATE INDEX ix_site_numero_immatriculation ON site (numero_immatriculation);
CREATE INDEX ix_site_code_postal ON site (code_postal);
CREATE INDEX ix_contact_client_id ON contact (client_id);
CREATE INDEX ix_contact_site_site_id ON contact_site (site_id);

-- Information dérivée, calculée et non stockée : le client est-il le syndic de la copropriété ?
CREATE VIEW v_site AS
SELECT s.*,
       c.nom  AS client_nom,
       c.siren AS client_siren,
       co.nom_usage, co.nombre_total_lots, co.nombre_lots_habitation, co.type_syndic,
       co.syndic_raison_sociale, co.syndic_siret, co.mandat_en_cours,
       CASE WHEN co.syndic_siret IS NULL OR c.siren IS NULL THEN NULL
            ELSE left(co.syndic_siret, 9) = c.siren END AS client_est_syndic
FROM site s
JOIN client c ON c.client_id = s.client_id
LEFT JOIN copropriete co ON co.numero_immatriculation = s.numero_immatriculation;

COMMENT ON TABLE contact IS 'Contacts professionnels des clients — données personnelles (registre : traitement T1)';
COMMENT ON COLUMN contact.nom IS '[DP] nom du contact';
COMMENT ON COLUMN contact.email IS '[DP] e-mail professionnel';
COMMENT ON COLUMN contact.telephone_fixe IS '[DP] téléphone professionnel, format E.164';
COMMENT ON COLUMN contact.telephone_portable IS '[DP] téléphone professionnel, format E.164';
