ALTER TABLE mesures_discretes ADD COLUMN IF NOT EXISTS mesure_uuid VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesure_uuid ON mesures_discretes (patient_id, mesure_uuid) WHERE mesure_uuid IS NOT NULL;
