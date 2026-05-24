-- Danışmanlık / görüşme saatleri (öğrenci panelinde danışmana gösterilir).
-- PostgreSQL OBS veritabanında bir kez çalıştırın.
ALTER TABLE obs_academic_profiles
    ADD COLUMN IF NOT EXISTS consulting_hours TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN obs_academic_profiles.consulting_hours IS
    'Akademisyenin öğrencilere yayınladığı danışmanlık / ofis görüşme saatleri metni';
