-- Schéma des tables clients, sites et contacts de Nexo (copie de pg_dump --schema-only, migrations
-- Alembic de Nexo-erp, 06/10/2026), utilisé par les tests d'intégration et la CI.
-- Les index ix_sites_client_id, idx_contacts_client_id, idx_contacts_site_id sont ceux des
-- migrations 019 et 060 de Nexo.
CREATE TABLE public.clients (
    id integer NOT NULL,
    nom character varying(255) NOT NULL,
    type_client character varying(50) NOT NULL,
    email character varying(255),
    adresse character varying(500),
    ville character varying(100),
    code_postal character varying(10),
    score_geocodage double precision,
    siret character varying(20),
    statut character varying(50) NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.clients_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.clients_id_seq OWNED BY public.clients.id;
CREATE TABLE public.contacts (
    id integer NOT NULL,
    client_id integer,
    site_id integer,
    nom character varying(200) NOT NULL,
    role character varying(30) NOT NULL,
    poste character varying(100),
    telephone_fixe character varying(20),
    telephone_portable character varying(20),
    email character varying(255),
    CONSTRAINT ck_contacts_client_xor_site CHECK ((((client_id IS NOT NULL) AND (site_id IS NULL)) OR ((client_id IS NULL) AND (site_id IS NOT NULL))))
);
CREATE SEQUENCE public.contacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.contacts_id_seq OWNED BY public.contacts.id;
CREATE TABLE public.sites (
    id integer NOT NULL,
    client_id integer NOT NULL,
    nom character varying(255) NOT NULL,
    adresse character varying(500) NOT NULL,
    ville character varying(100) NOT NULL,
    code_postal character varying(10) NOT NULL,
    prestations text,
    notes text,
    code_acces character varying(200),
    date_debut_contrat date,
    date_fin_contrat date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.sites_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.sites_id_seq OWNED BY public.sites.id;
ALTER TABLE ONLY public.clients ALTER COLUMN id SET DEFAULT nextval('public.clients_id_seq'::regclass);
ALTER TABLE ONLY public.contacts ALTER COLUMN id SET DEFAULT nextval('public.contacts_id_seq'::regclass);
ALTER TABLE ONLY public.sites ALTER COLUMN id SET DEFAULT nextval('public.sites_id_seq'::regclass);
ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT contacts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sites
    ADD CONSTRAINT sites_pkey PRIMARY KEY (id);
CREATE INDEX idx_contacts_client_id ON public.contacts USING btree (client_id);
CREATE INDEX idx_contacts_site_id ON public.contacts USING btree (site_id);
CREATE INDEX ix_sites_client_id ON public.sites USING btree (client_id);
ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT contacts_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT contacts_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.sites
    ADD CONSTRAINT sites_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id);
