-- Migration 001 : ajout du token FCM pour les notifications push
ALTER TABLE device_registry
    ADD COLUMN IF NOT EXISTS fcm_token TEXT;

CREATE INDEX IF NOT EXISTS idx_device_fcm
    ON device_registry(patient_id, fcm_token)
    WHERE actif = TRUE AND fcm_token IS NOT NULL;
