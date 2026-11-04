-- Utilisateur de réplication
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'stopmnt_replicator_2024';

-- Table patients
CREATE TABLE IF NOT EXISTS patients (
    id                  SERIAL PRIMARY KEY,
    patient_id          VARCHAR(20) UNIQUE NOT NULL,
    email               VARCHAR(255) UNIQUE NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    nom                 VARCHAR(100),
    prenom              VARCHAR(100),
    date_naissance      DATE,
    departement         VARCHAR(50) NOT NULL,
    telephone           VARCHAR(20),
    date_inscription    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    actif               BOOLEAN DEFAULT TRUE,
    seuils_custom       JSONB DEFAULT '{}'
);

-- Table utilisateurs (médecins, admins)
CREATE TABLE IF NOT EXISTS utilisateurs (
    id                  SERIAL PRIMARY KEY,
    email               VARCHAR(255) UNIQUE NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    nom                 VARCHAR(100) NOT NULL,
    prenom              VARCHAR(100) NOT NULL,
    role                VARCHAR(20) NOT NULL CHECK (role IN ('medecin','admin','epidemio')),
    departement         VARCHAR(50),
    actif               BOOLEAN DEFAULT TRUE,
    date_creation       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    derniere_connexion  TIMESTAMP WITH TIME ZONE
);

-- Table device_registry
CREATE TABLE IF NOT EXISTS device_registry (
    id                  SERIAL PRIMARY KEY,
    device_id           VARCHAR(100) UNIQUE NOT NULL,
    patient_id          VARCHAR(20) REFERENCES patients(patient_id),
    cert_fingerprint    VARCHAR(255) NOT NULL,
    cert_cn             VARCHAR(255) NOT NULL,
    date_enrolement     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    date_expiration     TIMESTAMP WITH TIME ZONE NOT NULL,
    actif               BOOLEAN DEFAULT TRUE,
    dernier_acces       TIMESTAMP WITH TIME ZONE
);

-- Table mesures_discretes
CREATE TABLE IF NOT EXISTS mesures_discretes (
    id                  SERIAL PRIMARY KEY,
    patient_id          VARCHAR(20) REFERENCES patients(patient_id),
    departement         VARCHAR(50) NOT NULL,
    capteur             VARCHAR(50) NOT NULL,
    timestamp_data      TIMESTAMP WITH TIME ZONE NOT NULL,
    timestamp_store     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    mesures             JSONB NOT NULL,
    anomalie            BOOLEAN DEFAULT FALSE,
    deferred            BOOLEAN DEFAULT FALSE,
    retry_count         INTEGER DEFAULT 0
);

-- Table alertes
CREATE TABLE IF NOT EXISTS alertes (
    id                      SERIAL PRIMARY KEY,
    patient_id              VARCHAR(20) REFERENCES patients(patient_id),
    departement             VARCHAR(50) NOT NULL,
    capteur                 VARCHAR(50) NOT NULL,
    niveau                  VARCHAR(20) NOT NULL CHECK (niveau IN ('alerte','critique')),
    message                 TEXT NOT NULL,
    timestamp               TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acquittee               BOOLEAN DEFAULT FALSE,
    acquittee_par           INTEGER REFERENCES utilisateurs(id),
    timestamp_acquittement  TIMESTAMP WITH TIME ZONE
);

-- Table audit_logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    utilisateur_id  INTEGER REFERENCES utilisateurs(id),
    patient_id      VARCHAR(20),
    action          VARCHAR(100) NOT NULL,
    details         JSONB,
    ip_address      INET
);

-- Table sessions
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    utilisateur_id  INTEGER REFERENCES utilisateurs(id),
    token_hash      VARCHAR(255) UNIQUE NOT NULL,
    date_creation   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    date_expiration TIMESTAMP WITH TIME ZONE NOT NULL,
    ip_address      INET,
    actif           BOOLEAN DEFAULT TRUE
);

-- Index
CREATE INDEX idx_mesures_patient  ON mesures_discretes(patient_id, timestamp_data DESC);
CREATE INDEX idx_mesures_dept     ON mesures_discretes(departement, timestamp_data DESC);
CREATE INDEX idx_alertes_patient  ON alertes(patient_id, acquittee, timestamp DESC);
CREATE INDEX idx_alertes_dept     ON alertes(departement, acquittee, timestamp DESC);
CREATE INDEX idx_device_patient   ON device_registry(patient_id, actif);
CREATE INDEX idx_audit_timestamp  ON audit_logs(timestamp DESC);

-- Admin par défaut
INSERT INTO utilisateurs (email, password_hash, nom, prenom, role)
VALUES (
    'admin@stopmnt.bj',
    'changeme_after_first_login',
    'Admin', 'STOPMNT', 'admin'
) ON CONFLICT DO NOTHING;
