-- ---------------------------------------------------------------------------
-- Katalog (obs_courses + obs_departments) — seçilen dönemde ŞUBESİ OLMAYANLARA tek şube
-- ---------------------------------------------------------------------------
-- Senin sıralamanla uyumlu: bolum, sinif, yarıyıl, kod, ders...
--
-- 1) Aşağıdaki `<<<BURAYA_OBS_TERM_UUID>>>` ifadesinin İÇİNE `obs_terms.id` yapıştır.
--    (Tüm CTE blokları otomatik aynı parametreyi kullanır.)
-- 2) A) ile önce kaç satır ekleneceğine bak.
-- 3) B) blok yorumunu kaldırıp INSERT'i çalıştır — tercihan BEGIN / COMMIT arasında.
--
-- Notlar:
--   - Varsayılan: instructor_id=NULL, classroom_id=NULL. Tabloda NOT NULL ise INSERT
--     hata verir; o zaman yorum satırlarındaki alt sorguları kullan veya akademisyen ata.
--   - Pazartesi 09:00–10:30 ve kapasite 50 yer tutucu; sonra gerçek programla güncellenmeli.
-- ---------------------------------------------------------------------------

WITH params AS (
    SELECT CAST('<<<BURAYA_OBS_TERM_UUID>>>' AS uuid) AS term_id
)

-- ========== A) Ön izleme: bu term için şubesiz kalacak ders satırları ==========
SELECT
    dep.name AS bolum,
    c.class_year AS sinif,
    c.semester_no AS yariyil,
    c.code,
    c.name AS ders,
    c.akts,
    c.credits,
    c.type AS tur,
    c.is_mandatory AS zorunlu,
    params.term_id::text AS hedef_term_id
FROM obs_courses c
JOIN obs_departments dep ON dep.id = c.department_id
CROSS JOIN params
WHERE NOT EXISTS (
        SELECT 1
        FROM obs_course_sections cs
        WHERE cs.course_id = c.id
          AND cs.term_id = params.term_id
    )
ORDER BY
    dep.name,
    c.class_year,
    c.semester_no,
    c.is_mandatory DESC NULLS LAST,
    c.name;

/*
-- ========== B) Ekleme: section_no = 1, yalnızca bu term için yoksa ==========
BEGIN;

WITH params AS (
    SELECT CAST('<<<BURAYA_OBS_TERM_UUID>>>' AS uuid) AS term_id
)
INSERT INTO obs_course_sections (
    id,
    course_id,
    term_id,
    instructor_id,
    section_no,
    classroom_id,
    day_of_week,
    start_time,
    end_time,
    capacity,
    created_at
)
SELECT
    gen_random_uuid (),
    c.id,
    params.term_id,
    NULL::uuid,
    -- (SELECT ap.id FROM obs_academic_profiles ap LIMIT 1),
    1,
    NULL::uuid,
    -- (SELECT cl.id FROM obs_classrooms cl LIMIT 1),
    'Pazartesi',
    TIME '09:00',
    TIME '10:30',
    50,
    NOW ()
FROM
    obs_courses c
    JOIN obs_departments dep ON dep.id = c.department_id
    CROSS JOIN params
WHERE
    NOT EXISTS (
        SELECT 1
        FROM obs_course_sections cs
        WHERE cs.course_id = c.id
          AND cs.term_id = params.term_id
    )
    -- İsteğe bağlı süzgeçler (aç/kapa):
    -- AND dep.name = 'İşletme'
    -- AND c.class_year = 2 AND c.semester_no IN (2, 4)
;

COMMIT;
*/
