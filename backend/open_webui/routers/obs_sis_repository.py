"""Mevcut PostgreSQL obs_* şeması için SIS sorguları (UUID FK'lar, user_id varchar)."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional

from collections import defaultdict

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

USER_TBL = '"user"'


def _str_id(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)


def _fmt_date(d: Any) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def _normalize_attendance_status(raw: Any) -> str:
    """UI ve DB uyumu: absent/present/excused (küçük harf İngilizce)."""
    s = str(raw or "").strip().lower()
    if s in ("absent", "yok", "a"):
        return "absent"
    if s in ("excused", "mazeret", "x"):
        return "excused"
    if s in ("present", "var", "p", ""):
        return "present"
    return "present"


# Yoklama haftası geçerli bir tamsayı olmalı; UI 1..14 (telafili dönemde 30'a kadar) gönderir.
# Üst sınırı liberal tutuyoruz; alt sınırın altını / negatifi / yazıyı kesin reddediyoruz.
ATTENDANCE_MAX_WEEK_NO = 30


def validate_attendance_week_no(week_no: Any) -> int:
    """`week_no` tamsayı ve 1..ATTENDANCE_MAX_WEEK_NO aralığında olmalı.

    `record_attendance` bunu çağırır; geçersizse `ValueError` fırlatır ve API katmanı
    bunu HTTP 400'e çevirir. Tanımlı değilse `NameError` ile HTTP 500 oluşur.
    """
    try:
        n = int(week_no)
    except (TypeError, ValueError) as ex:
        raise ValueError("Hafta numarası tamsayı olmalı.") from ex
    if n < 1 or n > ATTENDANCE_MAX_WEEK_NO:
        raise ValueError(
            f"Hafta numarası 1 ile {ATTENDANCE_MAX_WEEK_NO} arasında olmalı."
        )
    return n


# --- Duyurular (obs_announcements): UUID / CHECK / opsiyonel student kolonu ---

ANNOUNCEMENT_VARCHAR_MAX = 255

_obs_ann_student_col_cache: dict[int, Optional[str]] = {}


def obs_announcements_target_student_column(db: Session) -> Optional[str]:
    """PostgreSQL/SQLite şemasında varsa `student_number` veya `student_no` kolon adı."""
    bind = db.get_bind()
    bid = id(bind)
    if bid in _obs_ann_student_col_cache:
        return _obs_ann_student_col_cache[bid]
    names: set[str] = set()
    try:
        if bind.dialect.name == "sqlite":
            rows = db.execute(text("PRAGMA table_info(obs_announcements)")).fetchall()
            names = {str(r[1]) for r in rows}
        else:
            rows = db.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = ANY (current_schemas(false))
                      AND table_name = 'obs_announcements'
                      AND column_name IN ('student_number', 'student_no')
                    """
                )
            ).fetchall()
            names = {str(r[0]) for r in rows}
            # information_schema bazı kurulumlarda boş dönebilir; pg_catalog yedeği.
            if not names and bind.dialect.name == "postgresql":
                rows2 = db.execute(
                    text(
                        """
                        SELECT a.attname::text
                        FROM pg_attribute a
                        JOIN pg_class c ON c.oid = a.attrelid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relname = 'obs_announcements'
                          AND n.nspname = ANY (current_schemas(true))
                          AND a.attnum > 0
                          AND NOT a.attisdropped
                          AND a.attname IN ('student_number', 'student_no')
                        """
                    )
                ).fetchall()
                names = {str(r[0]) for r in rows2}
    except Exception:
        # Geçici hata veya izin: None önbelleğe yazma; sonraki istekte yeniden dene.
        return None
    if "student_number" in names:
        col = "student_number"
    elif "student_no" in names:
        col = "student_no"
    else:
        col = None
    _obs_ann_student_col_cache[bid] = col
    return col


def clamp_announcement_varchar(s: str, max_len: int = ANNOUNCEMENT_VARCHAR_MAX) -> str:
    t = (s or "").strip()
    return t[:max_len] if max_len > 0 else t


def optional_uuid_param(val: Any, field_label: str) -> Optional[str]:
    """Boş veya None -> None; doluysa geçerli UUID string döner."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        uuid.UUID(s)
    except ValueError as ex:
        raise ValueError(f"{field_label} geçerli bir UUID olmalıdır.") from ex
    return s


def academic_department_id_for_user(db: Session, webui_user_id: str) -> Optional[str]:
    row = (
        db.execute(
            text(
                "SELECT department_id FROM obs_academic_profiles WHERE user_id = :u LIMIT 1"
            ),
            {"u": webui_user_id},
        )
        .mappings()
        .first()
    )
    if not row or row.get("department_id") is None:
        return None
    return str(row["department_id"])


def resolve_academic_announcement_targets(
    db: Session,
    creator_user_id: str,
    audience_type: str,
    department_id: Optional[str],
    course_section_id: Optional[str],
    student_no: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    (department_id, course_section_id, student_number_value)
    CHECK kısıtları ve FK'lar için akademisyen tarafında normalize edilmiş hedefler.
    """
    at = (audience_type or "section").strip().lower()
    if at not in ("section", "advisees", "student", "all"):
        raise ValueError("Geçersiz hedef kitle (audience_type).")

    dept_body = optional_uuid_param(department_id, "Bölüm kimliği")
    csid = optional_uuid_param(course_section_id, "Şube kimliği")
    sn = (student_no or "").strip() or None

    if at == "all":
        return None, None, None
    if at == "section":
        if not csid:
            raise ValueError("Şube seçmelisiniz.")
        return None, csid, None
    if at in ("advisees", "student"):
        ensure_academic_profile_for_user(db, creator_user_id)
        did = dept_body or academic_department_id_for_user(db, creator_user_id)
        if not did:
            raise ValueError(
                "Akademik profilinizde bölüm tanımlı değil; danışmanlık veya öğrenci hedefli duyuru oluşturulamıyor."
            )
        if at == "advisees":
            return did, None, None
        if not sn:
            raise ValueError("Öğrenci numarası zorunludur.")
        if not obs_announcements_target_student_column(db):
            raise ValueError(
                "Bu veritabanı şeması öğrenci hedefli duyuruyu desteklemiyor (student_number / student_no sütunu yok)."
            )
        return did, None, sn
    raise ValueError("Geçersiz hedef kitle.")


def _fmt_time(t: Any) -> str:
    if t is None:
        return ""
    if isinstance(t, time):
        return t.strftime("%H:%M")
    return str(t)[:5]


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _obs_section_weight_pct(raw: Any, default: float) -> float:
    """obs_course_sections ağırlık kolonları (NUMERIC/DECIMAL); None ise varsayılan."""
    if raw is None:
        return default
    try:
        if isinstance(raw, Decimal):
            return float(raw)
        return float(raw)
    except (TypeError, ValueError):
        return default


def _mapping_weight_pct(row: Any, column_name: str, default: float) -> float:
    """SQLAlchemy RowMapping / dict — anahtar adı sürücüye göre değişirse case-insensitive yedek."""
    if row is None:
        return default
    raw = row.get(column_name) if hasattr(row, "get") else None
    if raw is None and hasattr(row, "keys"):
        want = column_name.lower()
        for k in row.keys():
            if str(k).lower() == want:
                raw = row[k]
                break
    return _obs_section_weight_pct(raw, default)


# RG 24/8/2021-31578 (100 üzerinden yüzde → harf). Eski 4'lük harfler geri uyumluluk için saklanır.
LETTER_POINTS: dict[str, float] = {
    # Yeni ölçek (öğretim elemanı girişi / otomatik hesap)
    "A+": 4.0,
    "A": 3.75,
    "B+": 3.5,
    "B": 3.0,
    "C+": 2.5,
    "C": 2.0,
    "D+": 1.5,
    "D": 1.0,
    "F": 0.0,
    # Özel (ortalamaya katılmaz / manuel)
    "M": 0.0,
    "S": 0.0,
    "DZ": 0.0,
    "G": 0.0,
    "K": 0.0,
    "TKR": 0.0,
    # Eski 4'lük (mevcut kayıtlar)
    "AA": 4.0,
    "BA": 3.5,
    "BB": 3.0,
    "CB": 2.5,
    "CC": 2.0,
    "DC": 1.5,
    "DD": 1.0,
    "FD": 0.5,
    "FF": 0.0,
}

# Danışman tüm liste kesinleştirmesi — obs_approval_requests.note ile döneme bağlanır
BATCH_TERM_NOTE_PREFIX = "BATCH_TERM:"
BATCH_ADDDROP_TERM_NOTE_PREFIX = "BATCH_ADDDROP_TERM:"

# Ders ekle-bırak (add_drop): zorunlu AKTS tabanı ve GNO ile üst sınır (çakışma kontrolü bu modda yok).
ADD_DROP_AKTS_MIN_NORMAL = 30
ADD_DROP_GPA_EXTRA_AKTS_THRESHOLD = 2.5
ADD_DROP_AKTS_MAX_BELOW_THRESHOLD = 30
ADD_DROP_AKTS_MAX_FROM_THRESHOLD = 35

# Öğrenci arayüzü gün filtreleri Türkçe (Pazartesi, …). DB İngilizce veya sayı olabilir.
_EN_WEEKDAY_TO_TR: dict[str, str] = {
    "monday": "Pazartesi",
    "mon": "Pazartesi",
    "tuesday": "Salı",
    "tue": "Salı",
    "wednesday": "Çarşamba",
    "wed": "Çarşamba",
    "thursday": "Perşembe",
    "thu": "Perşembe",
    "friday": "Cuma",
    "fri": "Cuma",
    "saturday": "Cumartesi",
    "sat": "Cumartesi",
    "sunday": "Pazar",
    "sun": "Pazar",
}
_TR_WEEKDAY_BY_ASCII: dict[str, str] = {
    "pazartesi": "Pazartesi",
    "sali": "Salı",
    "carsamba": "Çarşamba",
    "persembe": "Perşembe",
    "cuma": "Cuma",
    "cumartesi": "Cumartesi",
    "pazar": "Pazar",
}


def normalize_weekday_tr(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    if isinstance(raw, int):
        iso = {
            1: "Pazartesi",
            2: "Salı",
            3: "Çarşamba",
            4: "Perşembe",
            5: "Cuma",
            6: "Cumartesi",
            7: "Pazar",
        }
        return iso.get(raw, "")
    s = str(raw).strip()
    if not s:
        return ""
    low = s.lower()
    if low in _EN_WEEKDAY_TO_TR:
        return _EN_WEEKDAY_TO_TR[low]
    folded = (
        low.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    if folded in _TR_WEEKDAY_BY_ASCII:
        return _TR_WEEKDAY_BY_ASCII[folded]
    if s.isdigit():
        n = int(s)
        iso2 = {
            1: "Pazartesi",
            2: "Salı",
            3: "Çarşamba",
            4: "Perşembe",
            5: "Cuma",
            6: "Cumartesi",
            7: "Pazar",
        }
        if n in iso2:
            return iso2[n]
    return s


def letter_to_point(lg: Optional[str]) -> Optional[float]:
    if not lg:
        return None
    return LETTER_POINTS.get(lg.upper().strip())


# --- Yönetmelik: yarıyıl, bırakma, çakışma, kayıt önceliği (Madde 23–25, 24/2) ---

_FAIL_REPEAT_GRADES = frozenset(
    {"FF", "FD", "FA", "FZ", "K", "DZ", "F", "NA", "YZ"}
)


def student_program_semester_number(db: Session, student_profile_id: str) -> int:
    row = db.execute(
        text(
            "SELECT program_semester_number FROM obs_student_profiles WHERE id = :id"
        ),
        {"id": student_profile_id},
    ).scalar()
    try:
        n = int(row) if row is not None else 1
    except (TypeError, ValueError):
        n = 1
    return max(1, n)


def _course_semester_index(class_year: Any, curriculum_semester: Any) -> Optional[int]:
    if curriculum_semester is not None:
        try:
            return int(curriculum_semester)
        except (TypeError, ValueError):
            pass
    try:
        cy = int(class_year or 0)
    except (TypeError, ValueError):
        cy = 0
    if cy > 0:
        return (cy - 1) * 2 + 1
    return None


def _is_first_two_curriculum_semesters(class_year: Any, curriculum_semester: Any) -> bool:
    if curriculum_semester is not None:
        try:
            return int(curriculum_semester) <= 2
        except (TypeError, ValueError):
            pass
    try:
        cy = int(class_year or 0)
    except (TypeError, ValueError):
        cy = 0
    return cy <= 1


def _normalized_letter(lg: Optional[Any]) -> str:
    if lg is None:
        return ""
    return str(lg).strip().upper()


def has_passing_grade_for_course(
    db: Session, student_profile_id: str, course_id: str
) -> bool:
    rows = (
        db.execute(
            text("""
            SELECT g.letter_grade
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
            WHERE ce.student_id = :spid AND cs.course_id = :cid
              AND ce.status IN ('active', 'dropped', 'pending_drop', 'pending')
            """),
            {"spid": student_profile_id, "cid": course_id},
        )
        .fetchall()
    )
    for (lg,) in rows:
        pt = letter_to_point(str(lg) if lg is not None else None)
        if pt is not None and pt >= 2.0:
            return True
    return False


def has_fail_repeat_grade_for_course(
    db: Session, student_profile_id: str, course_id: str
) -> bool:
    rows = (
        db.execute(
            text("""
            SELECT g.letter_grade
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
            WHERE ce.student_id = :spid AND cs.course_id = :cid
              AND ce.status IN ('active', 'dropped', 'pending_drop', 'pending')
            """),
            {"spid": student_profile_id, "cid": course_id},
        )
        .fetchall()
    )
    for (lg,) in rows:
        if _normalized_letter(lg) in _FAIL_REPEAT_GRADES:
            return True
    return False


def _prior_enrollment_count_same_course(
    db: Session,
    student_profile_id: str,
    course_id: str,
    exclude_enrollment_id: str,
) -> int:
    row = db.execute(
        text("""
        SELECT COUNT(*) FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        WHERE ce.student_id = :spid AND cs.course_id = :cid AND ce.id != :ex
          AND ce.status IN ('active', 'dropped', 'pending_drop', 'pending')
        """),
        {"spid": student_profile_id, "cid": course_id, "ex": exclude_enrollment_id},
    ).scalar()
    return int(row or 0)


def has_prior_dz_for_course(
    db: Session,
    student_profile_id: str,
    course_id: str,
    exclude_enrollment_id: str,
) -> bool:
    row = db.execute(
        text("""
        SELECT 1 FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_grade_entries g ON g.enrollment_id = ce.id
        WHERE ce.student_id = :spid AND cs.course_id = :cid AND ce.id != :ex
          AND ce.status IN ('active', 'dropped', 'pending_drop', 'pending')
          AND UPPER(TRIM(BOTH FROM g.letter_grade)) = 'DZ'
        LIMIT 1
        """),
        {"spid": student_profile_id, "cid": course_id, "ex": exclude_enrollment_id},
    ).first()
    return row is not None


def enrollment_drop_allowed(
    db: Session, student_profile_id: str, enrollment_id: str
) -> tuple[bool, str]:
    row = (
        db.execute(
            text("""
            SELECT c.id AS course_id, c.class_year, c.curriculum_semester
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.id = :eid AND ce.student_id = :spid
            """),
            {"eid": enrollment_id, "spid": student_profile_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return False, "Kayıt bulunamadı."
    cid = _str_id(row["course_id"])
    if not cid:
        return False, "Ders bilgisi eksik."
    cy, csem_raw = row.get("class_year"), row.get("curriculum_semester")
    if _is_first_two_curriculum_semesters(cy, csem_raw):
        return False, "İlk iki yarıyıl dersleri bırakılamaz."
    stud_sem = student_program_semester_number(db, student_profile_id)
    csem = _course_semester_index(cy, csem_raw)
    prior_n = _prior_enrollment_count_same_course(
        db, student_profile_id, cid, enrollment_id
    )
    if csem is not None and csem < stud_sem and prior_n == 0:
        return (
            False,
            "Daha önce hiç alınmamış alt yarıyıl dersi bırakılamaz.",
        )
    if has_prior_dz_for_course(db, student_profile_id, cid, enrollment_id):
        return False, "Devamsızlık (DZ) notu bulunan ders için bırakma yapılamaz."
    return True, ""


def registration_priority_tier(
    db: Session, student_profile_id: str, course_id: str
) -> tuple[int, str]:
    stud_sem = student_program_semester_number(db, student_profile_id)
    crow = (
        db.execute(
            text(
                "SELECT class_year, curriculum_semester FROM obs_courses WHERE id = :id"
            ),
            {"id": course_id},
        )
        .mappings()
        .first()
    )
    cy = crow.get("class_year") if crow else None
    ccur = crow.get("curriculum_semester") if crow else None
    csem = _course_semester_index(cy, ccur)

    if has_fail_repeat_grade_for_course(db, student_profile_id, course_id):
        return 1, "Tekrar / başarısız (F, DZ, …)"

    passed = has_passing_grade_for_course(db, student_profile_id, course_id)
    if csem is not None:
        if csem < stud_sem and not passed:
            return 2, "Hiç geçirilmemiş alt yarıyıl dersi"
        if csem == stud_sem:
            return 3, "Kendi yarıyılı dersi"
        return 4, "Üst yarıyıl dersi"
    try:
        cy_i = int(cy or 0)
        st_year = max(1, (stud_sem + 1) // 2)
    except (TypeError, ValueError):
        cy_i, st_year = 0, 1
    if cy_i > 0 and cy_i < st_year and not passed:
        return 2, "Hiç geçirilmemiş alt sınıf dersi"
    if cy_i == st_year:
        return 3, "Kendi sınıf yılı dersi"
    if cy_i > st_year:
        return 4, "Üst sınıf dersi"
    return 3, "Kendi yarıyılı dersi"


def _parse_schedule_time(v: Any) -> Optional[time]:
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    s = str(v).strip()
    if len(s) >= 5 and s[2] == ":":
        try:
            h, m = int(s[0:2]), int(s[3:5])
            return time(h, m)
        except ValueError:
            return None
    return None


def section_schedule_slot(
    db: Session, section_id: str
) -> Optional[dict[str, Any]]:
    row = (
        db.execute(
            text("""
            SELECT cs.id, cs.day_of_week, cs.start_time, cs.end_time
            FROM obs_course_sections cs WHERE cs.id = :sid
            """),
            {"sid": section_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return {
        "id": _str_id(row["id"]),
        "day": normalize_weekday_tr(row.get("day_of_week")),
        "start": _parse_schedule_time(row.get("start_time")),
        "end": _parse_schedule_time(row.get("end_time")),
    }


def _slots_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a.get("day") or not b.get("day"):
        return False
    if a["day"] != b["day"]:
        return False
    sa, ea, sb, eb = a.get("start"), a.get("end"), b.get("start"), b.get("end")
    if sa is None or ea is None or sb is None or eb is None:
        return False
    return sa < eb and ea > sb


def schedule_conflict_message_for_section(
    db: Session,
    student_profile_id: str,
    term_id: str,
    new_section_id: str,
    extra_section_ids: Optional[list[str]] = None,
) -> Optional[str]:
    """Öğrencinin aynı dönemdeki programı + eklenen şubeler ile yeni şube çakışıyorsa mesaj."""
    new_sid = _str_id(new_section_id)
    if not new_sid:
        return None
    new_slot = section_schedule_slot(db, new_sid)
    if not new_slot or not new_slot.get("start") or not new_slot.get("end"):
        return None
    occupant_rows = (
        db.execute(
            text("""
            SELECT cs.id FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')
            """),
            {"spid": student_profile_id, "tid": term_id},
        )
        .fetchall()
    )
    check_ids: set[str] = {
        _str_id(r[0]) for r in occupant_rows if r and r[0] is not None
    }
    for x in extra_section_ids or []:
        sx = _str_id(x)
        if sx:
            check_ids.add(sx)
    check_ids.discard(new_sid)
    for oid in check_ids:
        if not oid:
            continue
        other = section_schedule_slot(db, oid)
        if other and _slots_overlap(new_slot, other):
            return "Bu şube mevcut program ile saat çakışması oluşturuyor."
    return None


# AGNO/GNO: transkript, özet ve kayıt limiti aynı satır kümesini kullanır.
_OBS_AGNO_ELIGIBLE_FROM = """
    FROM obs_course_enrollments ce
    JOIN obs_course_sections cs ON ce.course_section_id = cs.id
    JOIN obs_courses c ON cs.course_id = c.id
    LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
    WHERE ce.student_id = :spid
      AND ce.status IN ('active', 'pending_drop', 'dropped')
      AND (
            g.is_finalized = true
            OR (g.letter_grade IS NOT NULL AND LENGTH(TRIM(BOTH FROM g.letter_grade)) > 0)
      )
"""


def _fetch_obs_agno_rows(
    db: Session, student_profile_id: str, term_id: Optional[str] = None
) -> list[Any]:
    q = f"""
        SELECT cs.term_id, ce.id AS enrollment_id, c.code AS course_code, c.name AS course_name,
               COALESCE(c.akts, 0) AS akts, COALESCE(c.credits, 0) AS credits,
               g.letter_grade, g.is_finalized
        {_OBS_AGNO_ELIGIBLE_FROM}
    """
    params: dict[str, Any] = {"spid": student_profile_id}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    return list(db.execute(text(q), params).mappings().all())


def _accumulate_weighted_agno(
    rows: list[Any],
) -> tuple[float, int]:
    weighted = 0.0
    akts_sum = 0
    for r in rows:
        akts_i = int(r["akts"] or 0)
        if akts_i <= 0:
            continue
        lg_raw = r.get("letter_grade")
        lg = (str(lg_raw).strip() if lg_raw is not None else "") or ""
        pt: Optional[float] = letter_to_point(lg) if lg else None
        if pt is None:
            if lg:
                pt = 0.0
            else:
                continue
        weighted += float(pt) * akts_i
        akts_sum += akts_i
    return weighted, akts_sum


def compute_weighted_agno_totals(
    db: Session, student_profile_id: str
) -> tuple[Optional[float], int]:
    """AGNO / GNO: Σ (harf→4\'lük puan × AKTS) / Σ AKTS.
    Dönem notu kesinleşmiş veya harf notu girilmiş kayıtlar (transkript ile uyumlu)."""
    rows = _fetch_obs_agno_rows(db, student_profile_id, None)
    weighted, akts_sum = _accumulate_weighted_agno(rows)
    if akts_sum <= 0:
        return None, 0
    return round(weighted / akts_sum, 2), akts_sum


def resolve_student_profile_id(db: Session, webui_user_id: str) -> Optional[str]:
    """Aynı user_id için birden fazla kart varsa güncel olanı seç (panel ile tutarlılık)."""
    row = db.execute(
        text(
            """
            SELECT id FROM obs_student_profiles
            WHERE user_id = :u
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"u": webui_user_id},
    ).first()
    return _str_id(row[0]) if row else None


def resolve_academic_profile_id(db: Session, webui_user_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT id FROM obs_academic_profiles WHERE user_id = :u LIMIT 1"),
        {"u": webui_user_id},
    ).first()
    return _str_id(row[0]) if row else None


def ensure_academic_profile_for_user(db: Session, webui_user_id: str) -> str:
    """
    Danışman / şube hocası ataması için obs_academic_profiles yoksa tek satır oluşturur.
    Bölüm olarak obs_departments içindeki ilk kayıt kullanılır (stub).
    """
    existing = resolve_academic_profile_id(db, webui_user_id)
    if existing:
        return existing
    row = db.execute(
        text("SELECT id FROM obs_departments ORDER BY code NULLS LAST LIMIT 1")
    ).first()
    if not row:
        raise ValueError("no_department_for_stub_profile")
    did = _str_id(row[0])
    aid = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO obs_academic_profiles (
                id, user_id, staff_number, title, department_id, office, phone, created_at
            ) VALUES (
                :id, :uid, '', '', :did, '', '', CURRENT_TIMESTAMP
            )
            """
        ),
        {"id": aid, "uid": webui_user_id, "did": did},
    )
    db.commit()
    return aid


def _allocate_auto_student_number(db: Session, hint: str) -> str:
    """obs_student_profiles.student_number benzersiz AUTO-* üretir."""
    cleaned = "".join(c for c in str(hint) if c.isalnum())[:14]
    base = f"AUTO-{cleaned}" if cleaned else "AUTO"
    base = base[:40]
    cand = base
    for _ in range(40):
        n = int(
            db.execute(
                text(
                    "SELECT COUNT(*) FROM obs_student_profiles WHERE student_number = :sn"
                ),
                {"sn": cand},
            ).scalar()
            or 0
        )
        if n == 0:
            return cand
        cand = f"AUTO-{uuid.uuid4().hex[:12]}"
    return f"AUTO-{uuid.uuid4().hex}"


def get_student_profile_api(
    db: Session, webui_user_id: str
) -> Optional[dict[str, Any]]:
    row = (
        db.execute(
            text(f"""
        SELECT sp.id, sp.user_id, sp.student_number, sp.department_id,
               d.name AS department_name, d.faculty_name, d.code AS department_code,
               sp.program, sp.class_year, sp.gpa, sp.completed_akts, sp.total_akts_required,
               sp.status, sp.enrollment_date, sp.is_financially_eligible,
               sp.phone, sp.address, sp.emergency_contact, sp.emergency_phone,
               sp.program_semester_number,
               u.name AS full_name, u.email AS email
        FROM obs_student_profiles sp
        LEFT JOIN obs_departments d ON sp.department_id = d.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        WHERE sp.user_id = :uid
        """),
            {"uid": webui_user_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    r = dict(row)
    dept_id = _str_id(r.get("department_id"))
    return {
        "user_id": r["user_id"],
        "email": r.get("email") or "",
        "full_name": r.get("full_name") or "",
        "student_no": r.get("student_number") or "",
        "department_id": dept_id or "",
        "department_name": r.get("department_name") or "",
        "faculty_name": r.get("faculty_name") or "",
        "program": r.get("program") or "",
        "class_level": int(r.get("class_year") or 0),
        "program_semester_number": int(r.get("program_semester_number") or 1),
        "gpa": _num(r.get("gpa")),
        "status": r.get("status") or "",
        "enrollment_date": _fmt_date(r.get("enrollment_date")),
        "is_financially_eligible": bool(r.get("is_financially_eligible")),
        "phone": r.get("phone") or "",
        "address": r.get("address") or "",
        "emergency_contact": r.get("emergency_contact") or "",
        "emergency_phone": r.get("emergency_phone") or "",
        "completed_akts": r.get("completed_akts"),
        "total_akts_required": r.get("total_akts_required"),
        "dno": None,
    }


def student_is_prep(db: Session, spid: str) -> bool:
    row = (
        db.execute(
            text("SELECT program, class_year FROM obs_student_profiles WHERE id = :id"),
            {"id": spid},
        )
        .mappings()
        .first()
    )
    if not row:
        return False
    p = (row.get("program") or "").lower()
    return "hazırlık" in p or "hazirlik" in p or row.get("class_year") == 0


def get_advisor_api(db: Session, webui_user_id: str) -> dict[str, Any]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return {
            "student_user_id": webui_user_id,
            "advisor": None,
            "valid_from": None,
            "valid_to": None,
        }
    row = (
        db.execute(
            text(f"""
        SELECT sa.valid_from, sa.valid_to, ap.user_id AS academic_user_id,
               u.name AS advisor_name, u.email AS advisor_email, ap.title,
               ap.department_id, d.name AS department_name, ap.office, ap.phone
        FROM obs_student_advisors sa
        JOIN obs_academic_profiles ap ON sa.advisor_id = ap.id
        LEFT JOIN {USER_TBL} u ON u.id = ap.user_id
        LEFT JOIN obs_departments d ON ap.department_id = d.id
        WHERE sa.student_id = :sid
          AND (sa.valid_to IS NULL OR sa.valid_to >= CURRENT_DATE)
        ORDER BY sa.valid_from DESC
        LIMIT 1
        """),
            {"sid": spid},
        )
        .mappings()
        .first()
    )
    if not row:
        return {
            "student_user_id": webui_user_id,
            "advisor": None,
            "valid_from": None,
            "valid_to": None,
        }
    adv = {
        "academic_user_id": row["academic_user_id"],
        "name": row.get("advisor_name") or "",
        "title": row.get("title") or "",
        "email": row.get("advisor_email") or "",
        "department_id": _str_id(row.get("department_id")) or "",
        "department_name": row.get("department_name") or "",
        "office": row.get("office") or "",
        "phone": row.get("phone") or "",
    }
    return {
        "student_user_id": webui_user_id,
        "advisor": adv,
        "valid_from": _fmt_date(row.get("valid_from")),
        "valid_to": _fmt_date(row.get("valid_to")),
    }


def list_terms(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT id, name, start_date, end_date, is_active,
               registration_open, registration_start, registration_end,
               add_drop_open, add_drop_start, add_drop_end
        FROM obs_terms
        ORDER BY start_date NULLS LAST, name
        """)).mappings().all()
    out = []
    for r in rows:
        name = r.get("name") or ""
        parts = name.replace("–", "-").split("-")
        ay = parts[0].strip() if parts else ""
        season = "fall"
        if "bahar" in name.lower():
            season = "spring"
        elif "yaz" in name.lower():
            season = "summer"
        out.append(
            {
                "id": _str_id(r["id"]),
                "name": name,
                "academic_year": ay or "",
                "season": season,
                "starts_at": _fmt_date(r.get("start_date")) or "",
                "ends_at": _fmt_date(r.get("end_date")) or "",
                "is_active": bool(r.get("is_active")),
                "registration_open": (
                    None
                    if r.get("registration_open") is None
                    else bool(r.get("registration_open"))
                ),
                "registration_start": _fmt_date(r.get("registration_start")) or "",
                "registration_end": _fmt_date(r.get("registration_end")) or "",
                "add_drop_open": (
                    None
                    if r.get("add_drop_open") is None
                    else bool(r.get("add_drop_open"))
                ),
                "add_drop_start": _fmt_date(r.get("add_drop_start")) or "",
                "add_drop_end": _fmt_date(r.get("add_drop_end")) or "",
            }
        )
    return out


def list_departments(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.execute(text("SELECT id, code, name FROM obs_departments ORDER BY name"))
        .mappings()
        .all()
    )
    return [
        {
            "id": _str_id(r["id"]),
            "code": r.get("code") or "",
            "name": r.get("name") or "",
        }
        for r in rows
    ]


def term_calendar(db: Session, term_id: str) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text("""
        SELECT id, term_id, event_type, title, start_date, end_date
        FROM obs_calendar_events WHERE term_id = :tid ORDER BY start_date
        """),
            {"tid": term_id},
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": _str_id(r["id"]),
            "term_id": _str_id(r["term_id"]),
            "event_type": r.get("event_type") or "",
            "title": r.get("title") or "",
            "start_date": _fmt_date(r.get("start_date")) or "",
            "end_date": _fmt_date(r.get("end_date")) or "",
        }
        for r in rows
    ]


def list_student_feed_announcements(
    db: Session, student_user_id: str
) -> list[dict[str, Any]]:
    """Öğrenci paneli: `all`, bölüm duyurusu, kayıtlı şube (`section`), danışmanlık (`advisees`),
    numaraya özel (`student` — tabloda hedef kolonu varsa)."""
    spid = resolve_student_profile_id(db, student_user_id)
    if not spid:
        return []
    pr = (
        db.execute(
            text(
                "SELECT department_id FROM obs_student_profiles WHERE id = :id LIMIT 1"
            ),
            {"id": spid},
        )
        .mappings()
        .first()
    )
    did = _str_id(pr.get("department_id")) if pr and pr.get("department_id") else None

    sn_col = obs_announcements_target_student_column(db)
    student_clause = ""
    if sn_col:
        student_clause = f"""
            OR (
                a.audience_type = 'student'
                AND a.{sn_col} IS NOT NULL
                AND trim(cast(a.{sn_col} AS text)) <> ''
                AND EXISTS (
                    SELECT 1 FROM obs_student_profiles sp
                    WHERE sp.id = :spid
                      AND trim(cast(sp.student_number AS text)) = trim(cast(a.{sn_col} AS text))
                )
            )
        """

    dept_clause = ""
    advisees_clause = ""
    if did:
        dept_clause = """
            OR (
                a.audience_type = 'department'
                AND cast(a.department_id AS text) = cast(:did AS text)
            )
        """
        advisees_clause = """
            OR (
                a.audience_type = 'advisees'
                AND cast(a.department_id AS text) = cast(:did AS text)
                AND EXISTS (
                    SELECT 1 FROM obs_student_advisors sa
                    JOIN obs_academic_profiles ap ON sa.advisor_id = ap.id
                    WHERE sa.student_id = :spid
                      AND ap.user_id = a.created_by_user_id
                )
            )
        """
    else:
        # Profilde bölüm yoksa bile danışmanı tarafından yayınlanan advisees duyuruları gösterilir.
        advisees_clause = """
            OR (
                a.audience_type = 'advisees'
                AND EXISTS (
                    SELECT 1 FROM obs_student_advisors sa
                    JOIN obs_academic_profiles ap ON sa.advisor_id = ap.id
                    WHERE sa.student_id = :spid
                      AND ap.user_id = a.created_by_user_id
                )
            )
        """

    section_clause = """
            OR (
                a.audience_type = 'section'
                AND EXISTS (
                    SELECT 1 FROM obs_course_enrollments ce
                    WHERE ce.course_section_id = a.course_section_id
                      AND ce.student_id = :spid
                      AND ce.status = 'active'
                )
            )
    """

    q = f"""
            SELECT a.id, a.title, a.content, a.audience_type, a.department_id, a.is_active, a.published_at,
                   a.created_by_user_id, u.name AS creator_name
            FROM obs_announcements a
            LEFT JOIN {USER_TBL} u ON u.id = a.created_by_user_id
            WHERE a.is_active = true
              AND (
                a.audience_type = 'all'
                {dept_clause}
                {advisees_clause}
                {section_clause}
                {student_clause}
              )
            ORDER BY a.published_at DESC NULLS LAST
            """
    params: dict[str, Any] = {"spid": spid}
    if did:
        params["did"] = did
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "title": r.get("title") or "",
            "content": r.get("content") or "",
            "audience_type": r.get("audience_type") or "",
            "department_id": _str_id(r.get("department_id")),
            "is_active": bool(r.get("is_active")),
            "published_at": (
                r.get("published_at").isoformat() if r.get("published_at") else None
            ),
            "created_by": r.get("created_by_user_id"),
            "created_by_name": r.get("creator_name") or "",
        }
        for r in rows
    ]


def list_announcements_filtered(
    db: Session, audience_type: Optional[str], department_id: Optional[str]
) -> list[dict[str, Any]]:
    q = f"""
        SELECT a.id, a.title, a.content, a.audience_type, a.department_id, a.is_active, a.published_at,
               a.created_by_user_id, u.name AS creator_name
        FROM obs_announcements a
        LEFT JOIN {USER_TBL} u ON u.id = a.created_by_user_id
        WHERE a.is_active = true
        """
    params: dict[str, Any] = {}
    if audience_type:
        q += " AND (a.audience_type = :at OR a.audience_type = 'all')"
        params["at"] = audience_type
    if department_id:
        q += " AND (a.department_id::text = :did OR a.department_id IS NULL)"
        params["did"] = department_id
    q += " ORDER BY a.published_at DESC NULLS LAST"
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "title": r.get("title") or "",
            "content": r.get("content") or "",
            "audience_type": r.get("audience_type") or "",
            "department_id": _str_id(r.get("department_id")),
            "is_active": bool(r.get("is_active")),
            "published_at": (
                r.get("published_at").isoformat() if r.get("published_at") else None
            ),
            "created_by": r.get("created_by_user_id"),
            "created_by_name": r.get("creator_name") or "",
        }
        for r in rows
    ]


def messages_inbox(
    db: Session, user_id: str, sender_type: Optional[str]
) -> list[dict[str, Any]]:
    q = """
        SELECT m.id, m.sender_user_id, m.receiver_user_id, m.subject, m.body,
               m.is_read, m.status, m.sent_at,
               su.name AS sender_name, ru.name AS receiver_name
        FROM obs_messages m
        LEFT JOIN "user" su ON su.id = m.sender_user_id
        LEFT JOIN "user" ru ON ru.id = m.receiver_user_id
        WHERE m.receiver_user_id = :uid AND m.status <> 'deleted'
        """
    params: dict[str, Any] = {"uid": user_id}
    _ = sender_type
    q += " ORDER BY m.sent_at DESC"
    rows = db.execute(text(q), params).mappings().all()
    return [_message_row(r) for r in rows]


def messages_sent(
    db: Session, user_id: str, receiver_type: Optional[str]
) -> list[dict[str, Any]]:
    q = """
        SELECT m.id, m.sender_user_id, m.receiver_user_id, m.subject, m.body,
               m.is_read, m.status, m.sent_at,
               su.name AS sender_name, ru.name AS receiver_name
        FROM obs_messages m
        LEFT JOIN "user" su ON su.id = m.sender_user_id
        LEFT JOIN "user" ru ON ru.id = m.receiver_user_id
        WHERE m.sender_user_id = :uid AND m.status <> 'deleted'
        """
    params: dict[str, Any] = {"uid": user_id}
    _ = receiver_type
    q += " ORDER BY m.sent_at DESC"
    rows = db.execute(text(q), params).mappings().all()
    return [_message_row(r) for r in rows]


def _message_row(r: Any) -> dict[str, Any]:
    return {
        "id": _str_id(r["id"]),
        "sender_user_id": r.get("sender_user_id"),
        "sender_name": r.get("sender_name"),
        "receiver_user_id": r.get("receiver_user_id"),
        "receiver_name": r.get("receiver_name"),
        "subject": r.get("subject") or "",
        "body": r.get("body") or "",
        "is_read": bool(r.get("is_read")),
        "status": r.get("status") or "",
        "sent_at": r["sent_at"].isoformat() if r.get("sent_at") else "",
    }


def insert_message(
    db: Session,
    sender_user_id: str,
    receiver_user_id: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    mid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_messages (id, sender_user_id, receiver_user_id, subject, body, is_read, status, sent_at)
        VALUES (:id, :su, :ru, :sub, :body, false, 'active', NOW())
        """),
        {
            "id": mid,
            "su": sender_user_id,
            "ru": receiver_user_id,
            "sub": subject,
            "body": body,
        },
    )
    db.commit()
    row = (
        db.execute(
            text("""
        SELECT m.id, m.sender_user_id, m.receiver_user_id, m.subject, m.body,
               m.is_read, m.status, m.sent_at,
               su.name AS sender_name, ru.name AS receiver_name
        FROM obs_messages m
        LEFT JOIN "user" su ON su.id = m.sender_user_id
        LEFT JOIN "user" ru ON ru.id = m.receiver_user_id
        WHERE m.id = :mid
        """),
            {"mid": mid},
        )
        .mappings()
        .first()
    )
    return _message_row(row) if row else {"id": mid, "subject": subject, "body": body}


def mark_message_read(db: Session, message_id: str, reader_user_id: str) -> bool:
    res = db.execute(
        text("""
        UPDATE obs_messages SET is_read = true, read_at = NOW(), status = 'read'
        WHERE id = :mid AND receiver_user_id = :uid
        """),
        {"mid": message_id, "uid": reader_user_id},
    )
    db.commit()
    return res.rowcount > 0


def soft_delete_message(db: Session, message_id: str, user_id: str) -> bool:
    res = db.execute(
        text("""
        UPDATE obs_messages SET status = 'deleted'
        WHERE id = :mid AND (sender_user_id = :uid OR receiver_user_id = :uid)
        """),
        {"mid": message_id, "uid": user_id},
    )
    db.commit()
    return res.rowcount > 0


def list_enrollments(
    db: Session,
    webui_user_id: str,
    term_id: Optional[str],
    statuses: Optional[tuple[str, ...]] = ("active",),
) -> tuple[Optional[str], list[dict[str, Any]]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, []
    allowed = {"draft", "pending", "pending_drop", "active", "dropped", "rejected"}
    st = tuple(s for s in (statuses or ("active",)) if s in allowed)
    if not st:
        st = ("active",)
    in_clause = ", ".join(f"'{x}'" for x in st)
    q = f"""
        SELECT ce.id AS enrollment_id, ce.status, COALESCE(ce.enrollment_reason, '') AS enrollment_reason,
               c.id AS course_id, c.code AS course_code, c.name AS course_name, c.credits, c.akts,
               c.theory_hours, c.language, c.class_year, c.type,
               cs.id AS section_id, cs.term_id, cs.section_no, cs.day_of_week,
               cs.start_time, cs.end_time, cs.capacity,
               cr.code AS classroom_code, cr.name AS classroom_name,
               ins_u.name AS instructor_name
        FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" ins_u ON ins_u.id = ap.user_id
        WHERE ce.student_id = :spid AND ce.status IN ({in_clause})
        """
    params: dict[str, Any] = {"spid": spid}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    rows = db.execute(text(q), params).mappings().all()
    out = []
    for r in rows:
        room = r.get("classroom_code") or r.get("classroom_name") or ""
        cid_en = _str_id(r.get("course_id"))
        ptier, plab = (
            registration_priority_tier(db, spid, cid_en) if cid_en else (3, "")
        )
        out.append(
            {
                "id": _str_id(r["enrollment_id"]),
                "student_id": webui_user_id,
                "course_id": cid_en or "",
                "section_id": _str_id(r["section_id"]),
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "instructor_name": r.get("instructor_name") or "",
                "credits": int(r.get("credits") or 0),
                "akts": int(r.get("akts") or 0),
                "term_id": _str_id(r["term_id"]),
                "classroom": room,
                "day_of_week": normalize_weekday_tr(r.get("day_of_week")),
                "start_time": _fmt_time(r.get("start_time")),
                "end_time": _fmt_time(r.get("end_time")),
                "section_no": int(r.get("section_no") or 0),
                "theory_hours": r.get("theory_hours") or "",
                "language": r.get("language") or "",
                "class_year": int(r.get("class_year") or 0),
                "type": r.get("type") or "",
                "status": r.get("status") or "",
                "enrollment_reason": r.get("enrollment_reason") or "",
                "registration_priority_tier": ptier,
                "registration_priority_label": plab,
            }
        )
    total_akts = sum(x["akts"] for x in out if x["status"] == "active")
    for x in out:
        x["_total_akts_computed"] = total_akts
    return spid, out


def schedule_from_enrollments(
    rows: list[dict[str, Any]], term_id: str
) -> list[dict[str, Any]]:
    sched = []
    for r in rows:
        if r.get("term_id") != term_id and term_id:
            continue
        sched.append(
            {
                "day": normalize_weekday_tr(r.get("day_of_week")),
                "start": r.get("start_time") or "",
                "end": r.get("end_time") or "",
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "classroom": r.get("classroom") or "",
                "instructor": r.get("instructor_name") or "",
            }
        )
    return sched


def list_student_exams(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> list[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return []
    q = """
        SELECT ex.id, c.code AS course_code, c.name AS course_name,
               ex.exam_type, ex.exam_date, ex.exam_time, ex.weight_percent,
               cr.code AS classroom_code
        FROM obs_exams ex
        JOIN obs_course_sections cs ON ex.course_section_id = cs.id
        JOIN obs_course_enrollments ce ON ce.course_section_id = cs.id AND ce.student_id = :spid
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON ex.classroom_id = cr.id
        WHERE ce.status IN ('active', 'pending_drop')
        """
    params: dict[str, Any] = {"spid": spid}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "course_code": r.get("course_code") or "",
            "course_name": r.get("course_name") or "",
            "exam_type": r.get("exam_type") or "",
            "exam_date": _fmt_date(r.get("exam_date")) or "",
            "exam_time": _fmt_time(r.get("exam_time")),
            "classroom": r.get("classroom_code") or "",
            "weight_percent": float(r.get("weight_percent") or 0),
        }
        for r in rows
    ]


def list_student_grades(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> list[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return []
    q = """
        SELECT ce.id AS enrollment_id, c.code AS course_code, c.name AS course_name,
               cs.term_id, g.midterm, g.final, g.letter_grade, g.is_published, g.is_finalized
        FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
        WHERE ce.student_id = :spid AND ce.status IN ('active', 'pending_drop')
        """
    params: dict[str, Any] = {"spid": spid}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "enrollment_id": _str_id(r["enrollment_id"]),
            "course_code": r.get("course_code") or "",
            "course_name": r.get("course_name") or "",
            "term_id": _str_id(r["term_id"]),
            "midterm": _num(r.get("midterm")),
            "final": _num(r.get("final")),
            "letter_grade": r.get("letter_grade"),
            "is_published": bool(r.get("is_published")),
            "is_finalized": bool(r.get("is_finalized")),
        }
        for r in rows
    ]


def gpa_summary(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> dict[str, Any]:
    prof = get_student_profile_api(db, webui_user_id) or {}
    spid = resolve_student_profile_id(db, webui_user_id)
    cum_gpa = (
        compute_weighted_agno_totals(db, spid)[0] if spid else None
    )
    rows = _fetch_obs_agno_rows(db, spid, term_id) if spid else []
    terms_gpa: dict[str, dict[str, Any]] = {}
    for r in rows:
        ak = int(r["akts"] or 0)
        if ak <= 0:
            continue
        lg_raw = r.get("letter_grade")
        lg = (str(lg_raw).strip() if lg_raw is not None else "") or ""
        pt: Optional[float] = letter_to_point(lg) if lg else None
        if pt is None:
            if lg:
                pt = 0.0
            else:
                continue
        tid = _str_id(r["term_id"]) or ""
        if tid not in terms_gpa:
            terms_gpa[tid] = {"pts": 0.0, "akts": 0, "name": tid}
        terms_gpa[tid]["pts"] += float(pt) * ak
        terms_gpa[tid]["akts"] += ak
    term_list = []
    for tid, v in terms_gpa.items():
        tg = round(v["pts"] / v["akts"], 2) if v["akts"] else None
        tname = db.execute(
            text("SELECT name FROM obs_terms WHERE id = :id"), {"id": tid}
        ).scalar()
        term_list.append(
            {
                "term_id": tid,
                "term_name": tname or tid,
                "term_gpa": tg,
                "akts_completed": v["akts"],
                "akts_passed": v["akts"],
            }
        )
    return {
        "student_user_id": webui_user_id,
        "cumulative_gpa": cum_gpa,
        "total_akts_completed": int(prof.get("completed_akts") or 0),
        "class_level": int(prof.get("class_level") or 0),
        "terms": term_list,
    }


def transcript(db: Session, webui_user_id: str) -> dict[str, Any]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return {
            "student_user_id": webui_user_id,
            "cumulative_gpa": 0.0,
            "total_akts": 0,
            "transcript": [],
        }
    rows = _fetch_obs_agno_rows(db, spid, None)
    by_term: dict[str, list[Any]] = {}
    for r in rows:
        tid = _str_id(r["term_id"]) or ""
        by_term.setdefault(tid, []).append(r)
    transcript_terms = []
    total_akts = 0
    for tid, trows in by_term.items():
        tname = (
            db.execute(
                text("SELECT name FROM obs_terms WHERE id = :id"), {"id": tid}
            ).scalar()
            or tid
        )
        courses = []
        term_akts = 0
        term_pts = 0.0
        for r in trows:
            akts = int(r["akts"] or 0)
            credits = int(r["credits"] or 0)
            lg_raw = r.get("letter_grade")
            lg = (str(lg_raw).strip() if lg_raw is not None else "") or ""
            pt: Optional[float] = letter_to_point(lg) if lg else None
            if pt is None:
                if lg:
                    pt = 0.0
                else:
                    pt = None
            gp_for_display = float(pt) if pt is not None else 0.0
            courses.append(
                {
                    "code": r["course_code"],
                    "name": r["course_name"],
                    "credits": credits,
                    "akts": akts,
                    "letter": lg,
                    "grade_point": gp_for_display,
                }
            )
            total_akts += akts
            if pt is not None and akts > 0:
                term_akts += akts
                term_pts += float(pt) * akts
        term_gpa = round(term_pts / term_akts, 2) if term_akts else 0.0
        transcript_terms.append(
            {
                "term_name": tname,
                "courses": courses,
                "term_gpa": term_gpa,
                "term_akts": term_akts,
            }
        )
    cgpa_val, _ = compute_weighted_agno_totals(db, spid)
    cgpa = float(cgpa_val) if cgpa_val is not None else 0.0
    return {
        "student_user_id": webui_user_id,
        "cumulative_gpa": cgpa,
        "total_akts": total_akts,
        "transcript": transcript_terms,
    }


_CURRICULUM_CAT_ORDER = [
    "Zorunlu Dersler",
    "Teknik Seçmeli",
    "Sosyal Seçmeli",
    "Program Dersleri",
    "Diğer",
]


def student_curriculum_status(db: Session, webui_user_id: str) -> dict[str, Any]:
    """Müfredat görünümü: obs kayıtları + notlar; ayrı müfredat tablosu yok."""
    prof = get_student_profile_api(db, webui_user_id) or {}
    spid = resolve_student_profile_id(db, webui_user_id)
    base = {
        "student_user_id": webui_user_id,
        "program": prof.get("program") or "",
        "catalog_year": "",
        "overall_progress_pct": 0.0,
        "categories": [],
    }
    if not spid:
        return base

    q = """
        SELECT c.code AS course_code, c.name AS course_name, c.akts, c.type,
               ce.status AS enr_status,
               g.letter_grade, g.is_finalized, g.is_published,
               t.start_date AS term_start
        FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        JOIN obs_terms t ON cs.term_id = t.id
        LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
        WHERE ce.student_id = :spid AND ce.status = 'active'
        ORDER BY t.start_date DESC NULLS LAST, ce.id DESC
        """
    rows = db.execute(text(q), {"spid": spid}).mappings().all()

    type_to_cat: dict[str, str] = {
        "zorunlu": "Zorunlu Dersler",
        "required": "Zorunlu Dersler",
        "teknik_secmeli": "Teknik Seçmeli",
        "technical_elective": "Teknik Seçmeli",
        "sosyal_secmeli": "Sosyal Seçmeli",
        "social_elective": "Sosyal Seçmeli",
    }

    seen_codes: set[str] = set()
    cats: dict[str, list[dict[str, Any]]] = {name: [] for name in _CURRICULUM_CAT_ORDER}

    for r in rows:
        code = (r.get("course_code") or "").strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)

        raw_type = (r.get("type") or "").strip().lower().replace(" ", "_")
        cat_name = type_to_cat.get(raw_type) or (
            "Diğer" if raw_type else "Program Dersleri"
        )
        if cat_name not in cats:
            cats[cat_name] = []

        lg = r.get("letter_grade")
        if isinstance(lg, str):
            lg = lg.strip() or None
        finalized = bool(r.get("is_finalized"))
        published = bool(r.get("is_published"))
        enr_st = (r.get("enr_status") or "").lower()
        akts_i = int(r.get("akts") or 0)

        if lg and (finalized or published):
            st = "tamamlandi"
        elif lg:
            st = "tamamlandi"
        elif enr_st == "active":
            st = "devam_ediyor"
        else:
            st = "alinmadi"

        cats[cat_name].append(
            {
                "code": code,
                "name": r.get("course_name") or "",
                "akts": akts_i,
                "status": st,
                "grade": lg,
            }
        )

    categories_out: list[dict[str, Any]] = []
    for name in _CURRICULUM_CAT_ORDER:
        if cats.get(name):
            categories_out.append({"name": name, "courses": cats[name]})
    for name, courses in cats.items():
        if name not in _CURRICULUM_CAT_ORDER and courses:
            categories_out.append({"name": name, "courses": courses})

    flat = [c for cat in categories_out for c in cat["courses"]]
    n = len(flat)
    done = sum(1 for c in flat if c.get("status") == "tamamlandi")

    # Yalnızca bu endpointte listelenen (obs_course_enrollments) derslere göre —
    # profildeki completed_akts/total_akts_required seed değerleri çubukta yanıltıcı olur.
    pct = round(100.0 * done / n, 1) if n else 0.0

    base["overall_progress_pct"] = pct
    base["categories"] = categories_out
    return base


def clear_student_enrollments_and_related(
    db: Session, webui_user_id: str
) -> dict[str, Any]:
    """Öğrencinin tüm şube kayıtlarını, not ve yoklama satırlarını siler (demo / test temizliği)."""
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return {"ok": False, "detail": "Öğrenci profili yok", "deleted_enrollments": 0}

    rows = db.execute(
        text("SELECT id FROM obs_course_enrollments WHERE student_id = :spid"),
        {"spid": spid},
    ).fetchall()
    eids = [r[0] for r in rows]
    if not eids:
        return {"ok": True, "deleted_enrollments": 0, "detail": "Silinecek kayıt yok"}

    for eid in eids:
        db.execute(
            text("DELETE FROM obs_grade_entries WHERE enrollment_id = :eid"),
            {"eid": eid},
        )
        db.execute(
            text(
                "DELETE FROM obs_approval_requests WHERE related_enrollment_id = :eid"
            ),
            {"eid": eid},
        )
    db.execute(
        text("DELETE FROM obs_attendance_records WHERE student_id = :spid"),
        {"spid": spid},
    )
    res = db.execute(
        text("DELETE FROM obs_course_enrollments WHERE student_id = :spid"),
        {"spid": spid},
    )
    deleted = int(res.rowcount or 0)
    db.commit()
    return {"ok": True, "deleted_enrollments": deleted, "detail": "Kayıtlar silindi"}


def attendance_summary(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> list[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return []
    q = """
        SELECT c.code AS course_code, c.name AS course_name,
               COUNT(*) FILTER (WHERE ar.status IN ('absent', 'Absent', 'yok')) AS absent_count,
               MAX(ar.week_no) AS max_week
        FROM obs_attendance_records ar
        JOIN obs_course_sections cs ON ar.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        WHERE ar.student_id = :spid
        """
    params: dict[str, Any] = {"spid": spid}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    q += " GROUP BY c.code, c.name"
    rows = db.execute(text(q), params).mappings().all()
    out = []
    for r in rows:
        tw = int(r.get("max_week") or 14)
        ab = int(r.get("absent_count") or 0)
        pct = round(100.0 * (tw - ab) / tw, 1) if tw else 100.0
        st = "ok"
        if pct < 70:
            st = "fail"
        elif pct < 85:
            st = "warning"
        out.append(
            {
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "total_weeks": tw,
                "absent_count": ab,
                "attendance_pct": pct,
                "status": st,
            }
        )
    return out


def list_document_requests(db: Session, webui_user_id: str) -> list[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return []
    rows = (
        db.execute(
            text("""
        SELECT id, requesting_institution, request_reason, document_type, document_subtype,
               status, created_at
        FROM obs_document_requests WHERE student_id = :sid ORDER BY created_at DESC
        """),
            {"sid": spid},
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": _str_id(r["id"]),
            "requesting_institution": r.get("requesting_institution") or "",
            "request_reason": r.get("request_reason") or "",
            "document_type": r.get("document_type") or "",
            "document_subtype": r.get("document_subtype") or "",
            "status": r.get("status") or "",
            "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
        }
        for r in rows
    ]


def create_document_request(
    db: Session,
    webui_user_id: str,
    institution: str,
    reason: str,
    dtype: str,
    subtype: str,
) -> Optional[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None
    rid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_document_requests
        (id, student_id, requesting_institution, request_reason, document_type, document_subtype, status, created_at, updated_at)
        VALUES (:id, :sid, :inst, :reason, :dtype, :subtype, 'bekliyor', NOW(), NOW())
        """),
        {
            "id": rid,
            "sid": spid,
            "inst": institution,
            "reason": reason,
            "dtype": dtype,
            "subtype": subtype,
        },
    )
    db.commit()
    return {
        "id": rid,
        "requesting_institution": institution,
        "request_reason": reason,
        "document_type": dtype,
        "document_subtype": subtype,
        "status": "bekliyor",
        "created_at": datetime.utcnow().isoformat(),
    }


def update_student_profile_fields(
    db: Session, webui_user_id: str, patch: dict[str, Any]
) -> bool:
    allowed = {
        k: patch[k]
        for k in ("phone", "address", "emergency_contact", "emergency_phone")
        if k in patch and patch[k] is not None
    }
    if not allowed:
        return True
    sets = ", ".join(f"{k} = :{k}" for k in allowed)
    params = {**allowed, "uid": webui_user_id}
    db.execute(
        text(
            f"UPDATE obs_student_profiles SET {sets}, updated_at = NOW() WHERE user_id = :uid"
        ),
        params,
    )
    db.commit()
    return True


def available_sections(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> tuple[Optional[str], list[dict[str, Any]]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, []
    tid = term_id
    if not tid:
        row = db.execute(
            text(
                "SELECT id FROM obs_terms WHERE is_active = true ORDER BY start_date DESC LIMIT 1"
            )
        ).first()
        tid = _str_id(row[0]) if row else None
    q = """
        SELECT cs.id, c.id AS course_id, c.code AS course_code, c.name AS course_name,
               c.credits, c.akts, c.class_year, c.curriculum_semester,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity,
               cr.code AS classroom_code, ins_u.name AS instructor_name,
               (SELECT COUNT(*) FROM obs_course_enrollments ce2 WHERE ce2.course_section_id = cs.id AND ce2.status IN ('active', 'pending', 'draft', 'pending_drop')) AS enrolled
        FROM obs_course_sections cs
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" ins_u ON ins_u.id = ap.user_id
        WHERE NOT EXISTS (
            SELECT 1 FROM obs_course_enrollments ce
            WHERE ce.course_section_id = cs.id AND ce.student_id = :spid
              AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')
        )
        """
    params: dict[str, Any] = {"spid": spid}
    if tid:
        q += " AND cs.term_id = :tid"
        params["tid"] = tid
    rows = db.execute(text(q), params).mappings().all()
    out = []
    for r in rows:
        cap = int(r.get("capacity") or 0)
        enr = int(r.get("enrolled") or 0)
        cid = _str_id(r.get("course_id"))
        ptier, plab = (
            registration_priority_tier(db, spid, cid) if cid else (3, "")
        )
        out.append(
            {
                "id": _str_id(r["id"]),
                "course_id": cid or "",
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "credits": int(r.get("credits") or 0),
                "akts": int(r.get("akts") or 0),
                "instructor_name": r.get("instructor_name") or "",
                "day_of_week": normalize_weekday_tr(r.get("day_of_week")),
                "start_time": _fmt_time(r.get("start_time")),
                "end_time": _fmt_time(r.get("end_time")),
                "classroom": r.get("classroom_code") or "",
                "capacity": cap,
                "enrolled": enr,
                "registration_priority_tier": ptier,
                "registration_priority_label": plab,
            }
        )
    out.sort(key=lambda x: (x.get("registration_priority_tier", 9), x.get("course_code", "")))
    return tid, out


def academic_sections(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> list[dict[str, Any]]:
    apid = resolve_academic_profile_id(db, webui_user_id)
    if not apid:
        return []
    q = """
        SELECT cs.id, cs.course_id, c.code AS course_code, c.name AS course_name,
               cs.section_no, cs.term_id, cs.instructor_id, cs.classroom_id,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity,
               cr.code AS classroom_code, u.name AS instructor_name,
               cs.midterm_weight_percent AS midterm_weight_percent,
               cs.final_weight_percent AS final_weight_percent,
               (SELECT COUNT(*) FROM obs_course_enrollments ce WHERE ce.course_section_id = cs.id AND ce.status = 'active') AS enrollment_count
        FROM obs_course_sections cs
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" u ON u.id = ap.user_id
        WHERE cs.instructor_id = :apid
        """
    params: dict[str, Any] = {"apid": apid}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "course_id": _str_id(r["course_id"]),
            "course_code": r.get("course_code") or "",
            "course_name": r.get("course_name") or "",
            "section_code": chr(64 + int(r.get("section_no") or 1)),
            "section_no": int(r.get("section_no") or 1),
            "term_id": _str_id(r["term_id"]),
            "instructor_id": _str_id(r.get("instructor_id")),
            "instructor_name": r.get("instructor_name") or "",
            "classroom": r.get("classroom_code") or "",
            "day_of_week": normalize_weekday_tr(r.get("day_of_week")),
            "start_time": _fmt_time(r.get("start_time")),
            "end_time": _fmt_time(r.get("end_time")),
            "enrollment_count": int(r.get("enrollment_count") or 0),
            "capacity": int(r.get("capacity") or 0),
            "midterm_weight_percent": _mapping_weight_pct(r, "midterm_weight_percent", 40.0),
            "final_weight_percent": _mapping_weight_pct(r, "final_weight_percent", 60.0),
        }
        for r in rows
    ]


def section_meta(db: Session, section_id: str) -> Optional[dict[str, Any]]:
    sec = (
        db.execute(
            text(
                """
        SELECT cs.id, cs.course_id, c.code AS course_code, c.name AS course_name,
               cs.section_no, cs.term_id, cs.instructor_id, cs.classroom_id,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity,
               cs.midterm_weight_percent AS midterm_weight_percent,
               cs.final_weight_percent AS final_weight_percent,
               cr.code AS classroom_code, u.name AS instructor_name,
               (SELECT COUNT(*) FROM obs_course_enrollments ce WHERE ce.course_section_id = cs.id AND ce.status = 'active') AS enrollment_count
        FROM obs_course_sections cs
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" u ON u.id = ap.user_id
        WHERE cs.id = :sid
        """
            ),
            {"sid": section_id},
        )
        .mappings()
        .first()
    )
    if not sec:
        return None
    return {
        "id": _str_id(sec["id"]),
        "course_id": _str_id(sec["course_id"]),
        "course_code": sec.get("course_code") or "",
        "course_name": sec.get("course_name") or "",
        "section_code": chr(64 + int(sec.get("section_no") or 1)),
        "section_no": int(sec.get("section_no") or 1),
        "term_id": _str_id(sec["term_id"]),
        "instructor_id": _str_id(sec.get("instructor_id")),
        "instructor_name": sec.get("instructor_name") or "",
        "classroom": sec.get("classroom_code") or "",
        "day_of_week": normalize_weekday_tr(sec.get("day_of_week")),
        "start_time": _fmt_time(sec.get("start_time")),
        "end_time": _fmt_time(sec.get("end_time")),
        "enrollment_count": int(sec.get("enrollment_count") or 0),
        "capacity": int(sec.get("capacity") or 0),
        "midterm_weight_percent": _mapping_weight_pct(sec, "midterm_weight_percent", 40.0),
        "final_weight_percent": _mapping_weight_pct(sec, "final_weight_percent", 60.0),
    }


def update_section_grade_weights(
    db: Session, section_id: str, midterm_weight_percent: float, final_weight_percent: float
) -> bool:
    db.execute(
        text(
            """
            UPDATE obs_course_sections
            SET midterm_weight_percent = :m, final_weight_percent = :f
            WHERE id = :sid
            """
        ),
        {"sid": section_id, "m": float(midterm_weight_percent), "f": float(final_weight_percent)},
    )
    db.commit()
    return True


def section_owned_by_instructor(
    db: Session, section_id: str, webui_user_id: str
) -> bool:
    apid = resolve_academic_profile_id(db, webui_user_id)
    if not apid:
        return False
    row = db.execute(
        text(
            "SELECT 1 FROM obs_course_sections WHERE id = :sid AND instructor_id = :apid"
        ),
        {"sid": section_id, "apid": apid},
    ).first()
    return row is not None


def section_students(db: Session, section_id: str) -> tuple[Optional[dict], list[dict]]:
    sec = (
        db.execute(
            text("""
        SELECT cs.id, cs.course_id, c.code AS course_code, c.name AS course_name,
               cs.section_no, cs.term_id, cs.instructor_id, cs.classroom_id,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity,
               cr.code AS classroom_code, u.name AS instructor_name,
               (SELECT COUNT(*) FROM obs_course_enrollments ce WHERE ce.course_section_id = cs.id AND ce.status = 'active') AS enrollment_count
        FROM obs_course_sections cs
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" u ON u.id = ap.user_id
        WHERE cs.id = :sid
        """),
            {"sid": section_id},
        )
        .mappings()
        .first()
    )
    if not sec:
        return None, []
    section_dict = {
        "id": _str_id(sec["id"]),
        "course_id": _str_id(sec["course_id"]),
        "course_code": sec.get("course_code") or "",
        "course_name": sec.get("course_name") or "",
        "section_code": chr(64 + int(sec.get("section_no") or 1)),
        "section_no": int(sec.get("section_no") or 1),
        "term_id": _str_id(sec["term_id"]),
        "instructor_id": _str_id(sec.get("instructor_id")),
        "instructor_name": sec.get("instructor_name") or "",
        "classroom": sec.get("classroom_code") or "",
        "day_of_week": normalize_weekday_tr(sec.get("day_of_week")),
        "start_time": _fmt_time(sec.get("start_time")),
        "end_time": _fmt_time(sec.get("end_time")),
        "enrollment_count": int(sec.get("enrollment_count") or 0),
        "capacity": int(sec.get("capacity") or 0),
    }
    rows = (
        db.execute(
            text(f"""
        SELECT ce.id AS enrollment_id, ce.status, sp.student_number, u.name, sp.gpa,
               sp.user_id AS student_user_id
        FROM obs_course_enrollments ce
        JOIN obs_student_profiles sp ON ce.student_id = sp.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        WHERE ce.course_section_id = :sid AND ce.status = 'active'
        """),
            {"sid": section_id},
        )
        .mappings()
        .all()
    )
    students = [
        {
            "student_no": r.get("student_number") or "",
            "name": r.get("name") or "",
            "student_user_id": r.get("student_user_id") or "",
            "enrollment_id": _str_id(r["enrollment_id"]),
            "enrollment_status": r.get("status") or "",
            "gpa": float(r["gpa"]) if r.get("gpa") is not None else 0.0,
        }
        for r in rows
    ]
    return section_dict, students


def section_exams(db: Session, section_id: str) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text("""
        SELECT ex.id, ex.course_section_id, ex.exam_type, ex.exam_date, ex.exam_time,
               ex.weight_percent, cr.code AS classroom_code
        FROM obs_exams ex
        LEFT JOIN obs_classrooms cr ON ex.classroom_id = cr.id
        WHERE ex.course_section_id = :sid
        """),
            {"sid": section_id},
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": _str_id(r["id"]),
            "course_section_id": _str_id(r["course_section_id"]),
            "exam_type": r.get("exam_type") or "",
            "exam_date": _fmt_date(r.get("exam_date")) or "",
            "exam_time": _fmt_time(r.get("exam_time")),
            "classroom": r.get("classroom_code") or "",
            "weight_percent": float(r.get("weight_percent") or 0),
        }
        for r in rows
    ]


def insert_exam(
    db: Session,
    section_id: str,
    exam_type: str,
    exam_date: str,
    exam_time: str,
    classroom: Optional[str],
    weight: float,
) -> dict[str, Any]:
    eid = str(uuid.uuid4())
    cr_id = resolve_classroom_id_by_label(db, classroom)
    db.execute(
        text("""
        INSERT INTO obs_exams (id, course_section_id, exam_type, exam_date, exam_time, classroom_id, weight_percent, is_published, created_at)
        VALUES (:id, :csid, :et, :ed, :etm, :crid, :wp, false, CURRENT_TIMESTAMP)
        """),
        {
            "id": eid,
            "csid": section_id,
            "et": exam_type,
            "ed": exam_date,
            "etm": exam_time or "09:00:00",
            "crid": cr_id,
            "wp": weight,
        },
    )
    db.commit()
    return {
        "id": eid,
        "course_section_id": section_id,
        "exam_type": exam_type,
        "exam_date": exam_date,
        "exam_time": exam_time,
        "classroom": classroom or "",
        "weight_percent": weight,
    }


def get_section_exam_row(
    db: Session, section_id: str, exam_id: str
) -> Optional[dict[str, Any]]:
    r = (
        db.execute(
            text("""
        SELECT ex.id, ex.course_section_id, ex.exam_type, ex.exam_date, ex.exam_time,
               ex.weight_percent, cr.code AS classroom_code
        FROM obs_exams ex
        LEFT JOIN obs_classrooms cr ON ex.classroom_id = cr.id
        WHERE ex.id = :eid AND ex.course_section_id = :sid
        """),
            {"eid": exam_id, "sid": section_id},
        )
        .mappings()
        .first()
    )
    if not r:
        return None
    return {
        "id": _str_id(r["id"]),
        "course_section_id": _str_id(r["course_section_id"]),
        "exam_type": r.get("exam_type") or "",
        "exam_date": _fmt_date(r.get("exam_date")) or "",
        "exam_time": _fmt_time(r.get("exam_time")),
        "classroom": r.get("classroom_code") or "",
        "weight_percent": float(r.get("weight_percent") or 0),
    }


def update_section_exam(
    db: Session, section_id: str, exam_id: str, patch: dict[str, Any]
) -> Optional[dict[str, Any]]:
    exists = db.execute(
        text(
            "SELECT 1 FROM obs_exams WHERE id = :eid AND course_section_id = :sid"
        ),
        {"eid": exam_id, "sid": section_id},
    ).first()
    if not exists:
        return None

    set_parts: list[str] = []
    bind: dict[str, Any] = {"eid": exam_id, "sid": section_id}
    pi = 0

    if "exam_type" in patch:
        set_parts.append(f"exam_type = :p{pi}")
        bind[f"p{pi}"] = str(patch.get("exam_type") or "")
        pi += 1
    if "exam_date" in patch:
        ed = str(patch.get("exam_date") or "").strip()
        if ed:
            set_parts.append(f"exam_date = CAST(:p{pi} AS date)")
            bind[f"p{pi}"] = ed
        else:
            set_parts.append("exam_date = NULL")
        pi += 1
    if "exam_time" in patch:
        et_raw = patch.get("exam_time")
        s = str(et_raw).strip() if et_raw is not None else ""
        tm = s + ":00" if len(s) == 5 and s[2] == ":" else (s if s else "09:00:00")
        set_parts.append(f"exam_time = CAST(:p{pi} AS time)")
        bind[f"p{pi}"] = tm
        pi += 1
    if "weight_percent" in patch:
        set_parts.append(f"weight_percent = :p{pi}")
        bind[f"p{pi}"] = float(patch.get("weight_percent") or 0)
        pi += 1
    if "classroom" in patch:
        classroom_raw = patch.get("classroom")
        cr_id = resolve_classroom_id_by_label(
            db, str(classroom_raw).strip() if classroom_raw else None
        )
        set_parts.append(f"classroom_id = :p{pi}")
        bind[f"p{pi}"] = cr_id
        pi += 1

    if set_parts:
        q = f"UPDATE obs_exams SET {', '.join(set_parts)} WHERE id = :eid AND course_section_id = :sid"
        db.execute(text(q), bind)
        db.commit()
    return get_section_exam_row(db, section_id, exam_id)


def delete_section_exam(db: Session, section_id: str, exam_id: str) -> bool:
    res = db.execute(
        text(
            "DELETE FROM obs_exams WHERE id = :eid AND course_section_id = :sid"
        ),
        {"eid": exam_id, "sid": section_id},
    )
    db.commit()
    return res.rowcount > 0


def section_grade_rows(db: Session, section_id: str) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text(f"""
        SELECT ce.id AS enrollment_id, sp.student_number, u.name,
               g.midterm, g.final, g.letter_grade, g.is_finalized
        FROM obs_course_enrollments ce
        JOIN obs_student_profiles sp ON ce.student_id = sp.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
        WHERE ce.course_section_id = :sid AND ce.status = 'active'
        """),
            {"sid": section_id},
        )
        .mappings()
        .all()
    )
    return [
        {
            "student_no": r.get("student_number") or "",
            "name": r.get("name") or "",
            "enrollment_id": _str_id(r["enrollment_id"]),
            "midterm": _num(r.get("midterm")),
            "final": _num(r.get("final")),
            "letter_grade": r.get("letter_grade"),
            "is_finalized": bool(r.get("is_finalized")),
        }
        for r in rows
    ]


def _letter_from_score(score: float) -> str:
    """
    Ağırlıklı yüzde notu (0–100) → harf notu.
    Tablo: RG 24/8/2021-31578 (Değişik: … — EN düşük / EN yüksek aralığı).
    """
    s = float(score)
    if s >= 95:
        return "A+"
    if s >= 90:
        return "A"
    if s >= 85:
        return "B+"
    if s >= 75:
        return "B"
    if s >= 65:
        return "C+"
    if s >= 55:
        return "C"
    if s >= 45:
        return "D+"
    if s >= 40:
        return "D"
    return "F"


def recompute_section_letter_grades_rg(db: Session, section_id: str) -> None:
    """
    Şube vize/final ağırlıkları + RG tablosuna göre harf notunu yazar.
    Yalnızca vize ve final ikisi de dolu olan (taslak) satırlar güncellenir.
    Kesinleştirme öncesi çağrılır.
    """
    wrow = db.execute(
        text(
            """
            SELECT midterm_weight_percent AS midterm_weight_percent,
                   final_weight_percent AS final_weight_percent
            FROM obs_course_sections
            WHERE id = :sid
            """
        ),
        {"sid": section_id},
    ).mappings().first()
    w_mid = _mapping_weight_pct(wrow, "midterm_weight_percent", 40.0)
    w_fin = _mapping_weight_pct(wrow, "final_weight_percent", 60.0)
    if w_mid + w_fin <= 0:
        w_mid, w_fin = 40.0, 60.0

    rows = db.execute(
        text(
            """
            SELECT g.enrollment_id AS eid, g.midterm AS mid, g."final" AS fin, g.is_finalized AS finz
            FROM obs_grade_entries g
            JOIN obs_course_enrollments ce ON ce.id = g.enrollment_id
            WHERE ce.course_section_id = :sid
              AND ce.status = 'active'
            """
        ),
        {"sid": section_id},
    ).mappings().all()
    for r in rows:
        if bool(r.get("finz")):
            continue
        mid, fin = r.get("mid"), r.get("fin")
        if mid is None or fin is None:
            continue
        try:
            sc = (float(mid) * w_mid + float(fin) * w_fin) / 100.0
        except (TypeError, ValueError):
            continue
        lg = _letter_from_score(sc)
        db.execute(
            text(
                "UPDATE obs_grade_entries SET letter_grade = :lg WHERE enrollment_id = :eid"
            ),
            {"lg": lg, "eid": str(r["eid"])},
        )


def unfinalize_grade_entry(db: Session, section_id: str, enrollment_id: str) -> tuple[bool, str]:
    row = db.execute(
        text(
            """
            SELECT g.is_finalized
            FROM obs_grade_entries g
            JOIN obs_course_enrollments ce ON ce.id = g.enrollment_id
            WHERE g.enrollment_id = :eid AND ce.course_section_id = :sid
            """
        ),
        {"eid": enrollment_id, "sid": section_id},
    ).first()
    if not row:
        return False, "not_found"
    db.execute(
        text(
            """
            UPDATE obs_grade_entries
            SET is_finalized = false, finalized_at = NULL, finalized_by = NULL, updated_at = NOW()
            WHERE enrollment_id = :eid
            """
        ),
        {"eid": enrollment_id},
    )
    db.commit()
    return True, ""


def upsert_grades(
    db: Session, section_id: str, grades: list[dict[str, Any]]
) -> tuple[int, Optional[str]]:
    # Ağırlıklar (şubeden): yoksa 40/60 varsay
    wrow = db.execute(
        text(
            """
            SELECT midterm_weight_percent AS midterm_weight_percent,
                   final_weight_percent AS final_weight_percent
            FROM obs_course_sections
            WHERE id = :sid
            """
        ),
        {"sid": section_id},
    ).mappings().first()
    w_mid = _mapping_weight_pct(wrow, "midterm_weight_percent", 40.0)
    w_fin = _mapping_weight_pct(wrow, "final_weight_percent", 60.0)
    if w_mid + w_fin <= 0:
        w_mid, w_fin = 40.0, 60.0

    n = 0
    for item in grades:
        eid = item.get("enrollment_id")
        if not eid:
            continue
        row = db.execute(
            text(
                "SELECT ce.id FROM obs_course_enrollments ce WHERE ce.id = :eid AND ce.course_section_id = :sid"
            ),
            {"eid": eid, "sid": section_id},
        ).first()
        if not row:
            continue
        mid = item.get("midterm")
        fin = item.get("final")
        exists = db.execute(
            text("SELECT id, is_finalized FROM obs_grade_entries WHERE enrollment_id = :eid"),
            {"eid": eid},
        ).first()
        if exists:
            if bool(exists[1]):
                # Kesinleşmiş kayda update yok (unfinalize endpoint'i kullanılmalı)
                return n, "finalized"

            # Harf notu hesapla (gövdede yoksa veya boşsa)
            computed_lg: Optional[str] = None
            if "letter_grade" not in item or (
                isinstance(item.get("letter_grade"), str)
                and not str(item.get("letter_grade") or "").strip()
            ):
                if mid is not None and fin is not None:
                    try:
                        score = (float(mid) * w_mid + float(fin) * w_fin) / 100.0
                        computed_lg = _letter_from_score(score)
                    except (TypeError, ValueError):
                        computed_lg = None

            # Not: SQLite 3.39+ "final" ayrılmış kelime → tırnaksız UPDATE sözdizimi hatası.
            # PostgreSQL'de de "final"/"midterm" sütun adları için çift tırnak güvenli.
            set_parts = [
                '"midterm" = COALESCE(:m, "midterm")',
                '"final" = COALESCE(:f, "final")',
            ]
            params: dict[str, Any] = {"eid": eid, "m": mid, "f": fin}
            if computed_lg is not None:
                set_parts.insert(2, "letter_grade = :lg")
                params["lg"] = computed_lg
            elif "letter_grade" in item:
                lv = item.get("letter_grade")
                if lv is None or (isinstance(lv, str) and not str(lv).strip()):
                    set_parts.insert(2, "letter_grade = NULL")
                else:
                    set_parts.insert(2, "letter_grade = :lg")
                    params["lg"] = str(lv).strip().upper()[:8]
            db.execute(
                text(
                    f"UPDATE obs_grade_entries SET {', '.join(set_parts)} WHERE enrollment_id = :eid"
                ),
                params,
            )
        else:
            gid = str(uuid.uuid4())
            lg_insert: Optional[str] = None

            # Harf notu (gövdede yoksa) hesapla
            if "letter_grade" not in item or (
                isinstance(item.get("letter_grade"), str)
                and not str(item.get("letter_grade") or "").strip()
            ):
                if mid is not None and fin is not None:
                    try:
                        score2 = (float(mid) * w_mid + float(fin) * w_fin) / 100.0
                        lg_insert = _letter_from_score(score2)
                    except (TypeError, ValueError):
                        lg_insert = None
            elif "letter_grade" in item:
                lv2 = item.get("letter_grade")
                if lv2 is not None and str(lv2).strip():
                    lg_insert = str(lv2).strip().upper()[:8]
            if lg_insert is not None:
                db.execute(
                    text("""
                    INSERT INTO obs_grade_entries (id, enrollment_id, "midterm", "final", letter_grade, is_finalized, is_published, created_at, updated_at)
                    VALUES (:gid, :eid, :m, :f, :lg, false, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """),
                    {"gid": gid, "eid": eid, "m": mid, "f": fin, "lg": lg_insert},
                )
            else:
                db.execute(
                    text("""
                    INSERT INTO obs_grade_entries (id, enrollment_id, "midterm", "final", is_finalized, is_published, created_at, updated_at)
                    VALUES (:gid, :eid, :m, :f, false, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """),
                    {"gid": gid, "eid": eid, "m": mid, "f": fin},
                )
        n += 1
    db.commit()
    return n, None


def delete_grade_entry(
    db: Session, section_id: str, enrollment_id: str
) -> tuple[bool, str]:
    row = db.execute(
        text(
            """
            SELECT g.is_finalized
            FROM obs_grade_entries g
            JOIN obs_course_enrollments ce ON ce.id = g.enrollment_id
            WHERE g.enrollment_id = :eid AND ce.course_section_id = :sid
            """
        ),
        {"eid": enrollment_id, "sid": section_id},
    ).first()
    if not row:
        return False, "not_found"
    if bool(row[0]):
        return False, "finalized"
    db.execute(
        text("DELETE FROM obs_grade_entries WHERE enrollment_id = :eid"),
        {"eid": enrollment_id},
    )
    db.commit()
    return True, ""


def finalize_section_grades(
    db: Session,
    section_id: str,
    finalized_by_user_id: Optional[str] = None,
) -> None:
    """
    Şubedeki aktif kayıtlı öğrencilerin not satırlarını kesinleştirir.

    finalized_by: obs_grade_entries.finalized_by FK genelde Open WebUI `user.id` ile eşleşir
    (obs akademik profil UUID’si değil).

    Not: PostgreSQL `UPDATE ... FROM` ve SQLite uyumu için `WHERE enrollment_id IN (SELECT ...)`
    kullanılır. `NOW()` yerine `CURRENT_TIMESTAMP` (SQLite + PostgreSQL).
    """
    recompute_section_letter_grades_rg(db, section_id)

    set_fb = ""
    params: dict[str, Any] = {"sid": section_id}
    if finalized_by_user_id:
        set_fb = ", finalized_by = :fb"
        params["fb"] = finalized_by_user_id

    db.execute(
        text(
            f"""
            UPDATE obs_grade_entries
            SET is_finalized = true,
                finalized_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
                {set_fb}
            WHERE enrollment_id IN (
                SELECT ce.id
                FROM obs_course_enrollments ce
                WHERE ce.course_section_id = :sid
                  AND ce.status = 'active'
            )
            """
        ),
        params,
    )
    db.commit()


def record_attendance(
    db: Session,
    section_id: str,
    week_no: int,
    records: list[dict[str, Any]],
    recorded_by: str,
) -> int:
    validate_attendance_week_no(week_no)
    for rec in records:
        eid = rec.get("enrollment_id")
        st = _normalize_attendance_status(rec.get("status"))
        row = db.execute(
            text(
                "SELECT student_id FROM obs_course_enrollments WHERE id = :eid AND course_section_id = :sid"
            ),
            {"eid": eid, "sid": section_id},
        ).first()
        if not row:
            continue
        spid = str(row[0])
        db.execute(
            text(
                "DELETE FROM obs_attendance_records WHERE course_section_id = :sid AND week_no = :w AND student_id = :spid"
            ),
            {"sid": section_id, "w": week_no, "spid": spid},
        )
        rid = str(uuid.uuid4())
        db.execute(
            text("""
            INSERT INTO obs_attendance_records (id, student_id, course_section_id, week_no, status, recorded_at, recorded_by)
            VALUES (:id, :spid, :sid, :w, :st, NOW(), :rb)
            """),
            {
                "id": rid,
                "spid": spid,
                "sid": section_id,
                "w": week_no,
                "st": st,
                "rb": recorded_by,
            },
        )
    db.commit()
    return len(records)


def section_attendance_week(
    db: Session, section_id: str, week_no: int
) -> list[dict[str, Any]]:
    """
    Şube + hafta için mevcut yoklamayı döndürür.
    UI tarafı enrollment_id üzerinden çalıştığı için ar kayıtlarını ce.id ile map'ler.
    """
    validate_attendance_week_no(week_no)
    rows = (
        db.execute(
            text(
                """
            SELECT
              ce.id AS enrollment_id,
              ar.status
            FROM obs_attendance_records ar
            JOIN obs_course_enrollments ce
              ON ce.student_id = ar.student_id
             AND ce.course_section_id = ar.course_section_id
            WHERE ar.course_section_id = :sid
              AND ar.week_no = :w
              AND ce.status = 'active'
            """
            ),
            {"sid": section_id, "w": int(week_no)},
        )
        .mappings()
        .all()
    )
    return [
        {
            "enrollment_id": str(r.get("enrollment_id")),
            "status": _normalize_attendance_status(r.get("status")),
        }
        for r in rows
    ]


def academic_advisees(db: Session, webui_user_id: str) -> list[dict[str, Any]]:
    apid = resolve_academic_profile_id(db, webui_user_id)
    if not apid:
        return []
    rows = (
        db.execute(
            text(f"""
        SELECT sp.student_number, u.name, d.code AS dept_code, sp.class_year, sp.gpa, sp.status,
               sp.user_id AS student_user_id
        FROM obs_student_advisors sa
        JOIN obs_student_profiles sp ON sa.student_id = sp.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        LEFT JOIN obs_departments d ON sp.department_id = d.id
        WHERE sa.advisor_id = :apid
          AND (sa.valid_to IS NULL OR sa.valid_to >= CURRENT_DATE)
        """),
            {"apid": apid},
        )
        .mappings()
        .all()
    )
    return [
        {
            "student_no": r.get("student_number") or "",
            "student_user_id": r.get("student_user_id") or "",
            "name": r.get("name") or "",
            "department": r.get("dept_code") or "",
            "class_level": int(r.get("class_year") or 0),
            "gpa": float(r["gpa"]) if r.get("gpa") is not None else 0.0,
            "status": r.get("status") or "",
        }
        for r in rows
    ]


def list_approval_requests_for_academic(
    db: Session, webui_user_id: str, status_filter: Optional[str]
) -> list[dict[str, Any]]:
    q = """
        SELECT ar.id, ar.student_id, ar.request_type, ar.related_enrollment_id, ar.status, ar.note, ar.created_at,
               sp.student_number, sp.user_id AS student_user_id, u.name AS student_name,
               c.code AS course_code, c.name AS course_name
        FROM obs_approval_requests ar
        JOIN obs_student_profiles sp ON ar.student_id = sp.id
        LEFT JOIN "user" u ON u.id = sp.user_id
        LEFT JOIN obs_course_enrollments ce ON ar.related_enrollment_id = ce.id
        LEFT JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        LEFT JOIN obs_courses c ON cs.course_id = c.id
        WHERE ar.approver_id = :aid
        """
    params: dict[str, Any] = {"aid": webui_user_id}
    if status_filter:
        q += " AND ar.status = :st"
        params["st"] = status_filter
    q += " ORDER BY ar.created_at DESC"
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "student_user_id": r.get("student_user_id") or "",
            "student_name": r.get("student_name") or "",
            "student_no": r.get("student_number") or "",
            "request_type": r.get("request_type") or "",
            "related_enrollment_id": _str_id(r.get("related_enrollment_id")),
            "course_code": r.get("course_code"),
            "course_name": r.get("course_name"),
            "status": r.get("status") or "",
            "note": r.get("note"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
        }
        for r in rows
    ]


def _batch_flow_and_term_from_note(note: Optional[str]) -> tuple[Optional[str], str]:
    """İlk satırdan dönem id ve akış: registration | add_drop."""
    if not note:
        return None, ""
    s = str(note).strip()
    if s.startswith(BATCH_ADDDROP_TERM_NOTE_PREFIX):
        rest = s[len(BATCH_ADDDROP_TERM_NOTE_PREFIX) :].split("\n", 1)[0].strip()
        return (rest or None), "add_drop"
    if s.startswith(BATCH_TERM_NOTE_PREFIX):
        rest = s[len(BATCH_TERM_NOTE_PREFIX) :].split("\n", 1)[0].strip()
        return (rest or None), "registration"
    return None, ""


def _ensure_advisor_for_student(
    db: Session, advisor_user_id: str, student_profile_id: str
) -> bool:
    apid = resolve_academic_profile_id(db, advisor_user_id)
    if not apid:
        return False
    row = db.execute(
        text("""
        SELECT 1 FROM obs_student_advisors sa
        WHERE sa.student_id = :spid AND sa.advisor_id = :apid
          AND (sa.valid_to IS NULL OR sa.valid_to >= CURRENT_DATE)
        """),
        {"spid": student_profile_id, "apid": apid},
    ).first()
    return row is not None


def _finalize_pending_enrollments_for_term(
    db: Session, student_profile_id: str, term_id: str
) -> None:
    db.execute(
        text("""
        UPDATE obs_course_enrollments ce SET status = 'active', advisor_approved = true,
            advisor_approved_at = NOW()
        FROM obs_course_sections cs
        WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status = 'pending'
        """),
        {"spid": student_profile_id, "tid": term_id},
    )


def _revert_pending_enrollments_to_draft(
    db: Session, student_profile_id: str, term_id: str
) -> None:
    db.execute(
        text("""
        UPDATE obs_course_enrollments ce SET status = 'draft', advisor_approved = false,
            advisor_approved_at = NULL
        FROM obs_course_sections cs
        WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status = 'pending'
        """),
        {"spid": student_profile_id, "tid": term_id},
    )


def _term_window_allowed(db: Session, term_id: str, mode: str) -> tuple[bool, str]:
    """mode: registration | add_drop"""
    row = (
        db.execute(
            text("""
            SELECT registration_open, registration_start, registration_end,
                   add_drop_open, add_drop_start, add_drop_end
            FROM obs_terms WHERE id = :tid
            """),
            {"tid": term_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return False, "Dönem bulunamadı."
    today = date.today()
    if mode == "registration":
        if row.get("registration_open") is False:
            return False, "Ders kayıt dönemi kapalı."
        rs, re = row.get("registration_start"), row.get("registration_end")
        if rs is not None:
            rs_d = rs.date() if isinstance(rs, datetime) else rs
            if today < rs_d:
                return False, "Ders kayıt tarihleri henüz başlamadı."
        if re is not None:
            re_d = re.date() if isinstance(re, datetime) else re
            if today > re_d:
                return False, "Ders kayıt süresi sona erdi."
        return True, ""
    if row.get("add_drop_open") is False:
        return False, "Ders ekle/bırak dönemi kapalı."
    ads, ade = row.get("add_drop_start"), row.get("add_drop_end")
    if ads is not None:
        ads_d = ads.date() if isinstance(ads, datetime) else ads
        if today < ads_d:
            return False, "Ekle/bırak tarihleri henüz başlamadı."
    if ade is not None:
        ade_d = ade.date() if isinstance(ade, datetime) else ade
        if today > ade_d:
            return False, "Ekle/bırak süresi sona erdi."
    return True, ""


def _finalize_adddrop_batch(
    db: Session, student_profile_id: str, term_id: str
) -> None:
    db.execute(
        text("""
        UPDATE obs_course_enrollments ce SET status = 'active', advisor_approved = true,
            advisor_approved_at = NOW()
        FROM obs_course_sections cs
        WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status = 'pending'
        """),
        {"spid": student_profile_id, "tid": term_id},
    )
    db.execute(
        text("""
        UPDATE obs_course_enrollments ce SET status = 'dropped', dropped_at = NOW()
        FROM obs_course_sections cs
        WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status = 'pending_drop'
        """),
        {"spid": student_profile_id, "tid": term_id},
    )


def _purge_enrollment_row(db: Session, student_profile_id: str, enrollment_id: str) -> None:
    row = db.execute(
        text("""
        SELECT ce.course_section_id FROM obs_course_enrollments ce
        WHERE ce.id = :eid AND ce.student_id = :spid
        """),
        {"eid": enrollment_id, "spid": student_profile_id},
    ).first()
    if not row:
        return
    csid = _str_id(row[0])
    db.execute(
        text("DELETE FROM obs_grade_entries WHERE enrollment_id = :eid"),
        {"eid": enrollment_id},
    )
    if csid:
        db.execute(
            text(
                "DELETE FROM obs_attendance_records WHERE student_id = :spid AND course_section_id = :csid"
            ),
            {"spid": student_profile_id, "csid": csid},
        )
    db.execute(
        text("DELETE FROM obs_approval_requests WHERE related_enrollment_id = :eid"),
        {"eid": enrollment_id},
    )
    db.execute(
        text("DELETE FROM obs_course_enrollments WHERE id = :eid"),
        {"eid": enrollment_id},
    )


def _revert_adddrop_batch(
    db: Session, student_profile_id: str, term_id: str
) -> None:
    db.execute(
        text("""
        UPDATE obs_course_enrollments ce SET status = 'active'
        FROM obs_course_sections cs
        WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status = 'pending_drop'
        """),
        {"spid": student_profile_id, "tid": term_id},
    )
    db.execute(
        text("""
        UPDATE obs_course_enrollments ce SET status = 'draft', advisor_approved = false,
            advisor_approved_at = NULL
        FROM obs_course_sections cs
        WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status = 'pending' AND ce.enrollment_reason = 'add_drop'
        """),
        {"spid": student_profile_id, "tid": term_id},
    )
    adv_rows = (
        db.execute(
            text("""
            SELECT ce.id FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND ce.status = 'pending' AND ce.enrollment_reason = 'advisor_added'
            """),
            {"spid": student_profile_id, "tid": term_id},
        )
        .fetchall()
    )
    for ar in adv_rows:
        _purge_enrollment_row(db, student_profile_id, _str_id(ar[0]))


def add_drop_effective_agno(db: Session, student_profile_id: str) -> Optional[float]:
    """Ekle-bırak AKTS üst sınırı için kullanılan GNO (ağırlıklı hesap öncelikli, yoksa profil)."""
    agno, _ = compute_weighted_agno_totals(db, student_profile_id)
    grow = db.execute(
        text("SELECT gpa FROM obs_student_profiles WHERE id = :id"),
        {"id": student_profile_id},
    ).first()
    profile_gpa = float(grow[0]) if grow and grow[0] is not None else None
    if agno is not None:
        return float(agno)
    return profile_gpa


def add_drop_akts_min_max_for_student(db: Session, student_profile_id: str, term_id: str) -> tuple[int, int]:
    """(min_akts, max_akts) ders ekle-bırak paketi için. Hazırlık sınıfı: yalnızca mevcut tavan."""
    if student_is_prep(db, student_profile_id):
        mx_reg, _, _ = effective_akts_limit_for_student(db, student_profile_id, term_id)
        imx = max(0, int(mx_reg))
        return (imx, imx)
    gpa_eff = add_drop_effective_agno(db, student_profile_id)
    if gpa_eff is not None and gpa_eff >= ADD_DROP_GPA_EXTRA_AKTS_THRESHOLD:
        return (ADD_DROP_AKTS_MIN_NORMAL, ADD_DROP_AKTS_MAX_FROM_THRESHOLD)
    return (ADD_DROP_AKTS_MIN_NORMAL, ADD_DROP_AKTS_MAX_BELOW_THRESHOLD)


def add_drop_projected_load_before_submit(
    db: Session, student_profile_id: str, term_id: str, drop_enrollment_ids: Optional[list[str]]
) -> int:
    """Bırakılacaklar henüz pending_drop değilken: aktif (bırakılacak hariç) + add_drop taslakları."""
    drops = [x for x in (drop_enrollment_ids or []) if x]
    if not drops:
        row = db.execute(
            text("""
            SELECT COALESCE(SUM(c.akts), 0) FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND (
                ce.status = 'active'
                OR (ce.status = 'draft' AND COALESCE(ce.enrollment_reason, '') = 'add_drop')
              )
            """),
            {"spid": student_profile_id, "tid": term_id},
        ).scalar()
        return int(row or 0)
    in_ph = ", ".join(f":d{i}" for i in range(len(drops)))
    bind: dict[str, Any] = {"spid": student_profile_id, "tid": term_id}
    for i, eid in enumerate(drops):
        bind[f"d{i}"] = eid
    row = db.execute(
        text(f"""
            SELECT COALESCE(SUM(c.akts), 0) FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND (
                (ce.status = 'active' AND ce.id NOT IN ({in_ph}))
                OR (ce.status = 'draft' AND COALESCE(ce.enrollment_reason, '') = 'add_drop')
              )
            """),
        bind,
    ).scalar()
    return int(row or 0)


def add_drop_projected_load_pending_review(
    db: Session, student_profile_id: str, term_id: str
) -> int:
    """Danışman onayı beklerken: korunan aktifler + eklenecek pending add_drop (bırakılacaklar hariç)."""
    row = db.execute(
        text("""
        SELECT COALESCE(SUM(c.akts), 0) FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        WHERE ce.student_id = :spid AND cs.term_id = :tid
          AND (
            ce.status = 'active'
            OR (ce.status = 'pending' AND COALESCE(ce.enrollment_reason, '') IN ('add_drop', 'advisor_added'))
          )
        """),
        {"spid": student_profile_id, "tid": term_id},
    ).scalar()
    return int(row or 0)


def validate_add_drop_akts_bounds(
    db: Session, student_profile_id: str, term_id: str, projected_akts: int
) -> tuple[bool, str]:
    mn, mx = add_drop_akts_min_max_for_student(db, student_profile_id, term_id)
    if projected_akts < mn:
        return (
            False,
            f"Danışman onayına göndermek için en az {mn} AKTS olmalıdır (hesaplanan dönem yükü: {projected_akts} AKTS). "
            f"Ders yükünüzü {mn} AKTS ve üzerine tamamlayınız.",
        )
    if projected_akts > mx:
        gno = add_drop_effective_agno(db, student_profile_id)
        gtxt = f"{gno:.2f}" if gno is not None else "—"
        cap = (
            ADD_DROP_AKTS_MAX_FROM_THRESHOLD
            if gno is not None and gno >= ADD_DROP_GPA_EXTRA_AKTS_THRESHOLD
            else ADD_DROP_AKTS_MAX_BELOW_THRESHOLD
        )
        return (
            False,
            f"AKTS üst sınırı {mx} aşıldı (hesaplanan yük: {projected_akts} AKTS). "
            f"Kullanılan GNO: {gtxt}; bu GNO için üst sınır {cap} AKTS olabilir.",
        )
    return True, ""


def _is_student_add_drop_pending_batch(db: Session, student_profile_id: str, term_id: str) -> bool:
    row = db.execute(
        text("""
        SELECT 1 FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        WHERE ce.student_id = :spid AND cs.term_id = :tid
          AND (
            ce.status = 'pending_drop'
            OR (ce.status = 'pending' AND COALESCE(ce.enrollment_reason, '') = 'add_drop')
          )
        LIMIT 1
        """),
        {"spid": student_profile_id, "tid": term_id},
    ).first()
    return row is not None


def build_add_drop_approval_detail(
    db: Session, advisor_user_id: str, student_webui_user_id: str, term_id: str
) -> Optional[dict[str, Any]]:
    """Danışman ekranı: öğrenci özeti + eklenen / bırakılacak / korunan dersler."""
    spid = resolve_student_profile_id(db, student_webui_user_id)
    if not spid or not _ensure_advisor_for_student(db, advisor_user_id, spid):
        return None
    stud = (
        db.execute(
            text("""
            SELECT u.name AS full_name, sp.student_number,
                   d.name AS department_name, d.code AS department_code
            FROM obs_student_profiles sp
            JOIN "user" u ON u.id = sp.user_id
            LEFT JOIN obs_departments d ON d.id = sp.department_id
            WHERE sp.id = :spid
            """),
            {"spid": spid},
        )
        .mappings()
        .first()
    )
    tname = (
        db.execute(
            text("SELECT name FROM obs_terms WHERE id = :tid LIMIT 1"), {"tid": term_id}
        )
        .scalar()
    )
    gno = add_drop_effective_agno(db, spid)
    mn, mx = add_drop_akts_min_max_for_student(db, spid, term_id)
    proj = add_drop_projected_load_pending_review(db, spid, term_id)
    rows = (
        db.execute(
            text("""
            SELECT ce.id AS enrollment_id, ce.status, COALESCE(ce.enrollment_reason, '') AS enrollment_reason,
                   c.code AS course_code, c.name AS course_name, COALESCE(c.akts, 0) AS akts
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND ce.status IN ('active', 'pending', 'pending_drop')
            ORDER BY c.code
            """),
            {"spid": spid, "tid": term_id},
        )
        .mappings()
        .all()
    )
    added: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for r in rows:
        st = r.get("status") or ""
        er = r.get("enrollment_reason") or ""
        item = {
            "enrollment_id": _str_id(r.get("enrollment_id")),
            "course_code": r.get("course_code") or "",
            "course_name": r.get("course_name") or "",
            "akts": int(r.get("akts") or 0),
        }
        if st == "pending_drop":
            dropped.append(item)
        elif st == "pending" and er in ("add_drop", "advisor_added"):
            added.append(item)
        elif st == "active":
            kept.append(item)
    return {
        "student_user_id": student_webui_user_id,
        "student_name": (stud or {}).get("full_name") or "",
        "student_no": (stud or {}).get("student_number") or "",
        "department_name": (stud or {}).get("department_name")
        or (stud or {}).get("department_code")
        or "",
        "term_id": term_id,
        "term_name": str(tname or ""),
        "agno": float(gno) if gno is not None else None,
        "akts_min": mn,
        "akts_max": mx,
        "projected_akts": proj,
        "added_courses": added,
        "dropped_courses": dropped,
        "kept_courses": kept,
    }


def enrich_approval_requests_add_drop(
    db: Session, academic_user_id: str, reqs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    for r in reqs:
        if (r.get("request_type") or "") != "schedule_batch":
            continue
        note = r.get("note") or ""
        tid, flow = _batch_flow_and_term_from_note(note)
        if flow != "add_drop" or not tid:
            continue
        suid = r.get("student_user_id") or ""
        if not suid:
            continue
        det = build_add_drop_approval_detail(db, academic_user_id, str(suid), str(tid))
        if det:
            r["add_drop_detail"] = det
    return reqs


def student_term_scheduled_akts(db: Session, student_profile_id: str, term_id: str) -> int:
    """Dönemdeki yük: active + pending + draft + pending_drop (henüz düşmemiş)."""
    row = db.execute(
        text("""
        SELECT COALESCE(SUM(c.akts), 0) FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        WHERE ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')
        """),
        {"spid": student_profile_id, "tid": term_id},
    ).scalar()
    return int(row or 0)


def effective_akts_limit_for_student(
    db: Session, student_profile_id: str, term_id: str
) -> tuple[int, str, dict[str, Any]]:
    settings = registration_settings_row(db, term_id) or {}
    min_mid = float(settings.get("min_gpa_for_high_akts") or 2.50)
    min_top = float(settings.get("min_gpa_for_top_akts") or 3.50)
    meta = {
        "akts_limit_default": int(settings.get("akts_limit_default") or 30),
        "akts_limit_high": int(settings.get("akts_limit_high") or 36),
        "akts_limit_top": int(settings.get("akts_limit_top") or 45),
        "akts_limit_prep": int(settings.get("akts_limit_prep") or 25),
        "min_gpa_for_high_akts": min_mid,
        "min_gpa_for_top_akts": min_top,
    }
    stud_sem = student_program_semester_number(db, student_profile_id)
    if student_is_prep(db, student_profile_id):
        return (
            meta["akts_limit_prep"],
            "prep",
            {
                **meta,
                "gpa": None,
                "gpa_computed": None,
                "gpa_profile": None,
                "akts_counted_in_gpa": 0,
                "program_semester_number": stud_sem,
            },
        )
    agno, akts_in_gpa = compute_weighted_agno_totals(db, student_profile_id)
    grow = db.execute(
        text("SELECT gpa FROM obs_student_profiles WHERE id = :id"),
        {"id": student_profile_id},
    ).first()
    profile_gpa = float(grow[0]) if grow and grow[0] is not None else None
    gpa_eff = agno if agno is not None else profile_gpa
    meta_out = {
        **meta,
        "gpa": gpa_eff,
        "gpa_computed": agno,
        "gpa_profile": profile_gpa,
        "akts_counted_in_gpa": akts_in_gpa,
        "program_semester_number": stud_sem,
    }
    if stud_sem <= 2:
        return meta["akts_limit_default"], "early_semesters", meta_out
    if gpa_eff is None or gpa_eff < min_mid:
        return meta["akts_limit_default"], "low_gpa", meta_out
    if gpa_eff < min_top:
        return meta["akts_limit_high"], "mid_gpa", meta_out
    return meta["akts_limit_top"], "top_gpa", meta_out


def student_registration_limits_payload(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> Optional[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None
    tid = term_id or resolve_active_term_id(db)
    if not tid:
        agno_e, akts_e = compute_weighted_agno_totals(db, spid)
        grow = db.execute(
            text("SELECT gpa FROM obs_student_profiles WHERE id = :id"),
            {"id": spid},
        ).first()
        pg = float(grow[0]) if grow and grow[0] is not None else None
        gpa_eff = agno_e if agno_e is not None else pg
        psem = student_program_semester_number(db, spid)
        return {
            "student_user_id": webui_user_id,
            "term_id": "",
            "akts_max": 30,
            "rule": "default",
            "gpa": gpa_eff,
            "gpa_computed": agno_e,
            "gpa_profile": pg,
            "akts_counted_in_gpa": akts_e,
            "is_prep": student_is_prep(db, spid),
            "current_term_akts": 0,
            "akts_limit_default": 30,
            "akts_limit_high": 36,
            "akts_limit_top": 45,
            "akts_limit_prep": 25,
            "min_gpa_for_high_akts": 2.50,
            "min_gpa_for_top_akts": 3.50,
            "program_semester_number": psem,
            "add_drop_akts_min": ADD_DROP_AKTS_MIN_NORMAL,
            "add_drop_akts_max": ADD_DROP_AKTS_MAX_BELOW_THRESHOLD,
        }
    akts_max, rule, det = effective_akts_limit_for_student(db, spid, tid)
    load = student_term_scheduled_akts(db, spid, tid)
    ad_mn, ad_mx = add_drop_akts_min_max_for_student(db, spid, tid)
    return {
        "student_user_id": webui_user_id,
        "term_id": tid,
        "akts_max": akts_max,
        "rule": rule,
        "gpa": det.get("gpa"),
        "gpa_computed": det.get("gpa_computed"),
        "gpa_profile": det.get("gpa_profile"),
        "akts_counted_in_gpa": int(det.get("akts_counted_in_gpa") or 0),
        "is_prep": student_is_prep(db, spid),
        "current_term_akts": load,
        "akts_limit_default": det["akts_limit_default"],
        "akts_limit_high": det["akts_limit_high"],
        "akts_limit_top": det["akts_limit_top"],
        "akts_limit_prep": det["akts_limit_prep"],
        "min_gpa_for_high_akts": det["min_gpa_for_high_akts"],
        "min_gpa_for_top_akts": det["min_gpa_for_top_akts"],
        "program_semester_number": int(det.get("program_semester_number") or 1),
        "add_drop_akts_min": ad_mn,
        "add_drop_akts_max": ad_mx,
    }


def upsert_draft_enrollments(
    db: Session,
    webui_user_id: str,
    section_ids: list[str],
    mode: str,
    exclude_drop_enrollment_ids: Optional[list[str]] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Taslak satırlar — obs_course_enrollments.status = draft. mode: registration | add_drop"""
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return [], "Öğrenci profili yok."
    if mode not in ("registration", "add_drop"):
        return [], "Geçersiz kayıt modu."
    out: list[dict[str, Any]] = []
    for sid in section_ids:
        meta = (
            db.execute(
                text("""
                SELECT cs.id, cs.term_id, cs.course_id, cs.capacity, COALESCE(c.akts, 0) AS course_akts,
                  (SELECT COUNT(*) FROM obs_course_enrollments ce
                   WHERE ce.course_section_id = cs.id
                     AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')) AS taken
                FROM obs_course_sections cs
                JOIN obs_courses c ON cs.course_id = c.id
                WHERE cs.id = :csid
                """),
                {"csid": sid},
            )
            .mappings()
            .first()
        )
        if not meta:
            continue
        tid = _str_id(meta["term_id"])
        ok, reason = _term_window_allowed(db, tid, mode)
        if not ok:
            return [], reason
        dup = db.execute(
            text("""
            SELECT 1 FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid AND cs.course_id = :cid
              AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')
            """),
            {
                "spid": spid,
                "tid": tid,
                "cid": str(meta["course_id"]),
            },
        ).first()
        if dup:
            continue
        batch_sids = [str(x["section_id"]) for x in out if x.get("section_id")]
        if mode != "add_drop":
            sc_msg = schedule_conflict_message_for_section(
                db, spid, tid, sid, batch_sids
            )
            if sc_msg:
                return [], sc_msg
        taken = int(meta.get("taken") or 0)
        cap = int(meta.get("capacity") or 0)
        if cap and taken >= cap:
            return [], "Kontenjan dolu."
        new_akts = int(meta.get("course_akts") or 0)
        queued = sum(int(x.get("akts") or 0) for x in out)
        if mode == "add_drop":
            base_proj = add_drop_projected_load_before_submit(
                db, spid, tid, exclude_drop_enrollment_ids
            )
            _, mx_ad = add_drop_akts_min_max_for_student(db, spid, tid)
            if base_proj + queued + new_akts > mx_ad:
                return (
                    [],
                    f"Ders ekle-bırak AKTS üst sınırı ({mx_ad}) aşılır (planlanan yük: {base_proj + queued}, eklenecek: {new_akts} AKTS).",
                )
        else:
            load = student_term_scheduled_akts(db, spid, tid)
            akts_max, _, _ = effective_akts_limit_for_student(db, spid, tid)
            if load + queued + new_akts > akts_max:
                return (
                    [],
                    f"AKTS üst sınırı ({akts_max}) aşılır (mevcut yük: {load + queued}, eklenecek: {new_akts}).",
                )
        eid = str(uuid.uuid4())
        db.execute(
            text("""
            INSERT INTO obs_course_enrollments
            (id, student_id, course_section_id, status, enrollment_reason, advisor_approved)
            VALUES (:id, :spid, :csid, 'draft', :reason, false)
            """),
            {
                "id": eid,
                "spid": spid,
                "csid": sid,
                "reason": mode,
            },
        )
        row = (
            db.execute(
                text("""
            SELECT c.code, c.name, c.akts FROM obs_course_sections cs
            JOIN obs_courses c ON cs.course_id = c.id WHERE cs.id = :csid
            """),
                {"csid": sid},
            )
            .mappings()
            .first()
        )
        out.append(
            {
                "enrollment_id": eid,
                "section_id": sid,
                "course_code": row.get("course_code") if row else "",
                "course_name": row.get("course_name") if row else "",
                "akts": int(row.get("akts") or 0) if row else 0,
                "status": "draft",
            }
        )
    db.commit()
    return out, None


def delete_draft_enrollment(
    db: Session, webui_user_id: str, enrollment_id: str
) -> bool:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return False
    res = db.execute(
        text("""
        DELETE FROM obs_course_enrollments
        WHERE id = :eid AND student_id = :spid AND status = 'draft'
        """),
        {"eid": enrollment_id, "spid": spid},
    )
    db.commit()
    return res.rowcount > 0


def submit_schedule_to_advisor(
    db: Session,
    webui_user_id: str,
    note: Optional[str],
    approver_user_id: Optional[str],
    flow: str = "registration",
    enrollment_ids_to_drop: Optional[list[str]] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Taslakları pending / aktifleri pending_drop yapar; tek schedule_batch talebi oluşturur."""
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, "Öğrenci profili yok."
    if not approver_user_id:
        return None, "Danışman atanmamış."
    flow = flow if flow in ("registration", "add_drop") else "registration"
    eids_drop = list(dict.fromkeys(enrollment_ids_to_drop or []))

    pending_chk = db.execute(
        text("""
        SELECT 1 FROM obs_course_enrollments ce
        WHERE ce.student_id = :spid AND ce.status IN ('pending', 'pending_drop') LIMIT 1
        """),
        {"spid": spid},
    ).first()
    if pending_chk:
        return None, "Onay bekleyen bir listeniz var."

    if flow == "registration":
        term_row = db.execute(
            text("""
            SELECT DISTINCT cs.term_id FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            WHERE ce.student_id = :spid AND ce.status = 'draft'
              AND (ce.enrollment_reason = 'registration' OR ce.enrollment_reason IS NULL) LIMIT 1
            """),
            {"spid": spid},
        ).first()
        if not term_row:
            return None, "Sepette ders yok."
        term_id = _str_id(term_row[0])
        ok, reason = _term_window_allowed(db, term_id, "registration")
        if not ok:
            return None, reason
        akts_max, _, _ = effective_akts_limit_for_student(db, spid, term_id)
        load = student_term_scheduled_akts(db, spid, term_id)
        if load > akts_max:
            return None, f"AKTS toplamı ({load}) üst sınırı ({akts_max}) a çıkamaz; sepeti güncelleyin."
        db.execute(
            text("""
                UPDATE obs_course_enrollments ce SET status = 'pending'
                FROM obs_course_sections cs
                WHERE ce.course_section_id = cs.id AND ce.student_id = :spid
                  AND cs.term_id = :tid AND ce.status = 'draft'
                  AND (ce.enrollment_reason = 'registration' OR ce.enrollment_reason IS NULL)
            """),
            {"spid": spid, "tid": term_id},
        )
        batch_note = BATCH_TERM_NOTE_PREFIX + (term_id or "")
    else:
        drop_terms: set[str] = set()
        for eid in eids_drop:
            drow = (
                db.execute(
                    text("""
                    SELECT cs.term_id FROM obs_course_enrollments ce
                    JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                    WHERE ce.id = :eid AND ce.student_id = :spid AND ce.status = 'active'
                    """),
                    {"eid": eid, "spid": spid},
                )
                .mappings()
                .first()
            )
            if not drow:
                return None, "Bırakılacak kayıtlardan biri geçersiz veya aktif değil."
            ok_drop, deny_reason = enrollment_drop_allowed(db, spid, eid)
            if not ok_drop:
                return None, deny_reason
            drop_terms.add(_str_id(drow["term_id"]))
        if len(drop_terms) > 1:
            return None, "Tüm bırakılacak dersler aynı dönemde olmalı."

        draft_term_rows = db.execute(
            text("""
            SELECT DISTINCT cs.term_id FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            WHERE ce.student_id = :spid AND ce.status = 'draft'
              AND ce.enrollment_reason = 'add_drop'
            """),
            {"spid": spid},
        ).fetchall()
        draft_terms = {_str_id(t[0]) for t in draft_term_rows}
        if len(draft_terms) > 1:
            return None, "Taslak dersler tek döneme ait olmalı."

        term_id: Optional[str] = None
        if draft_terms:
            term_id = next(iter(draft_terms))
        if drop_terms:
            dt = next(iter(drop_terms))
            if term_id and term_id != dt:
                return None, "Eklenecek ve bırakılacak dersler aynı döneme ait olmalı."
            term_id = dt
        if not term_id:
            return None, "Sepette ders veya bırakılacak kayıt yok."
        ok, reason = _term_window_allowed(db, term_id, "add_drop")
        if not ok:
            return None, reason
        proj = add_drop_projected_load_before_submit(db, spid, term_id, eids_drop)
        ok_ak, msg_ak = validate_add_drop_akts_bounds(db, spid, term_id, proj)
        if not ok_ak:
            return None, msg_ak
        if eids_drop:
            if not all(isinstance(x, str) and x for x in eids_drop):
                return None, "Geçersiz bırakma listesi."
            bind = {f"e{i}": eids_drop[i] for i in range(len(eids_drop))}
            in_ph = ", ".join(f":e{i}" for i in range(len(eids_drop)))
            res_drop = db.execute(
                text(f"""
                UPDATE obs_course_enrollments ce SET status = 'pending_drop'
                FROM obs_course_sections cs
                WHERE ce.course_section_id = cs.id AND ce.student_id = :spid
                  AND cs.term_id = :tid AND ce.id IN ({in_ph})
                  AND ce.status = 'active'
                """),
                {"spid": spid, "tid": term_id, **bind},
            )
            if res_drop.rowcount != len(eids_drop):
                db.rollback()
                return None, "Bırakılacak kayıtlar güncellenemedi."
        db.execute(
            text("""
                UPDATE obs_course_enrollments ce SET status = 'pending'
                FROM obs_course_sections cs
                WHERE ce.course_section_id = cs.id AND ce.student_id = :spid
                  AND cs.term_id = :tid AND ce.status = 'draft'
                  AND ce.enrollment_reason = 'add_drop'
            """),
            {"spid": spid, "tid": term_id},
        )
        batch_note = BATCH_ADDDROP_TERM_NOTE_PREFIX + (term_id or "")

    db.execute(
        text("""
            UPDATE obs_approval_requests SET status = 'cancelled', resolved_at = NOW()
            WHERE student_id = :spid AND request_type = 'schedule_batch' AND status = 'pending'
        """),
        {"spid": spid},
    )
    if note and str(note).strip():
        batch_note = batch_note + "\n" + str(note).strip()
    rid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_approval_requests
        (id, student_id, approver_id, request_type, related_enrollment_id, status, note, created_at)
        VALUES (:id, :spid, :appr, 'schedule_batch', NULL, 'pending', :note, NOW())
        """),
        {"id": rid, "spid": spid, "appr": approver_user_id, "note": batch_note},
    )
    db.commit()
    return (
        {
            "batch_request_id": rid,
            "term_id": term_id,
            "status": "pending",
            "flow": flow,
        },
        None,
    )


def list_advisee_enrollments(
    db: Session,
    advisor_user_id: str,
    student_user_id: str,
    term_id: Optional[str],
) -> tuple[Optional[str], list[dict[str, Any]]]:
    spid = resolve_student_profile_id(db, student_user_id)
    if not spid or not _ensure_advisor_for_student(db, advisor_user_id, spid):
        return None, []
    tid = term_id or resolve_active_term_id(db)
    if not tid:
        return spid, []
    _, rows = list_enrollments(
        db, student_user_id, tid, ("draft", "pending", "pending_drop", "active")
    )
    return spid, rows


def advisor_add_enrollment_line(
    db: Session,
    advisor_user_id: str,
    student_user_id: str,
    section_id: str,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    spid = resolve_student_profile_id(db, student_user_id)
    if not spid or not _ensure_advisor_for_student(db, advisor_user_id, spid):
        return None, "Yetkisiz veya öğrenci yok."
    meta = (
        db.execute(
            text("""
            SELECT cs.term_id, cs.course_id, cs.capacity, COALESCE(c.akts, 0) AS course_akts,
              (SELECT COUNT(*) FROM obs_course_enrollments ce
               WHERE ce.course_section_id = cs.id
                 AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')) AS taken
            FROM obs_course_sections cs
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE cs.id = :sid
            """),
            {"sid": section_id},
        )
        .mappings()
        .first()
    )
    if not meta:
        return None, "Şube bulunamadı."
    pending = db.execute(
        text("""
        SELECT 1 FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        WHERE ce.student_id = :spid AND cs.term_id = :tid
          AND ce.status IN ('pending', 'pending_drop') LIMIT 1
        """),
        {"spid": spid, "tid": str(meta["term_id"])},
    ).first()
    if not pending:
        return None, "Öğrencinin onay bekleyen listesi yok."
    tid = _str_id(meta["term_id"])
    dup = db.execute(
        text("""
        SELECT 1 FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        WHERE ce.student_id = :spid AND cs.term_id = :tid AND cs.course_id = :cid
          AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')
        """),
        {"spid": spid, "tid": tid, "cid": str(meta["course_id"])},
    ).first()
    if dup:
        return None, "Bu ders zaten listede."
    if not _is_student_add_drop_pending_batch(db, spid, tid):
        sc_msg = schedule_conflict_message_for_section(
            db, spid, tid, section_id, None
        )
        if sc_msg:
            return None, sc_msg
    taken = int(meta.get("taken") or 0)
    cap = int(meta.get("capacity") or 0)
    if cap and taken >= cap:
        return None, "Kontenjan dolu."
    new_akts = int(meta.get("course_akts") or 0)
    if _is_student_add_drop_pending_batch(db, spid, tid):
        proj = add_drop_projected_load_pending_review(db, spid, tid)
        _, mx_ad = add_drop_akts_min_max_for_student(db, spid, tid)
        if proj + new_akts > mx_ad:
            return (
                None,
                f"Ders ekle-bırak AKTS üst sınırı ({mx_ad}) aşılır (planlanan yük: {proj}, eklenecek: {new_akts}).",
            )
    else:
        load = student_term_scheduled_akts(db, spid, tid)
        akts_max, _, _ = effective_akts_limit_for_student(db, spid, tid)
        if load + new_akts > akts_max:
            return None, f"Öğrencinin AKTS üst sınırı ({akts_max}) aşılır (mevcut: {load})."
    eid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_course_enrollments
        (id, student_id, course_section_id, status, enrollment_reason, advisor_approved)
        VALUES (:id, :spid, :csid, 'pending', 'advisor_added', false)
        """),
        {"id": eid, "spid": spid, "csid": section_id},
    )
    db.execute(
        text("""
        INSERT INTO obs_advisor_actions
        (id, student_user_id, advisor_user_id, term_id, action_type, section_id, approval_request_id, note, created_at)
        VALUES (:id, :su, :au, :tid, 'add_section', :sid, NULL, NULL, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "su": student_user_id,
            "au": advisor_user_id,
            "tid": tid,
            "sid": section_id,
        },
    )
    db.commit()
    return ({"enrollment_id": eid, "section_id": section_id, "status": "pending"}, None)


def advisor_remove_enrollment_line(
    db: Session,
    advisor_user_id: str,
    student_user_id: str,
    enrollment_id: str,
) -> tuple[bool, Optional[str]]:
    spid = resolve_student_profile_id(db, student_user_id)
    if not spid or not _ensure_advisor_for_student(db, advisor_user_id, spid):
        return False, "Yetkisiz."
    row = db.execute(
        text("""
        SELECT ce.status, cs.term_id, ce.course_section_id FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        WHERE ce.id = :eid AND ce.student_id = :spid
        """),
        {"eid": enrollment_id, "spid": spid},
    ).first()
    if not row:
        return False, "Kayıt yok."
    st = row[0]
    tid = _str_id(row[1])
    csid = _str_id(row[2])
    if st == "pending_drop":
        db.execute(
            text("""
            UPDATE obs_course_enrollments SET status = 'active' WHERE id = :eid AND student_id = :spid
            """),
            {"eid": enrollment_id, "spid": spid},
        )
        db.execute(
            text("""
            INSERT INTO obs_advisor_actions
            (id, student_user_id, advisor_user_id, term_id, action_type, section_id, approval_request_id, note, created_at)
            VALUES (:id, :su, :au, :tid, 'remove_section', NULL, NULL, 'undo pending_drop enrollment_id=' || :eid, NOW())
            """),
            {
                "id": str(uuid.uuid4()),
                "su": student_user_id,
                "au": advisor_user_id,
                "tid": tid,
                "eid": enrollment_id,
            },
        )
        db.commit()
        return True, None
    if st != "pending":
        return False, "Yalnızca onay bekleyen satırlar silinebilir."
    db.execute(
        text("DELETE FROM obs_grade_entries WHERE enrollment_id = :eid"),
        {"eid": enrollment_id},
    )
    if csid:
        db.execute(
            text(
                "DELETE FROM obs_attendance_records WHERE student_id = :spid AND course_section_id = :csid"
            ),
            {"spid": spid, "csid": csid},
        )
    db.execute(
        text("DELETE FROM obs_approval_requests WHERE related_enrollment_id = :eid"),
        {"eid": enrollment_id},
    )
    db.execute(
        text("DELETE FROM obs_course_enrollments WHERE id = :eid"),
        {"eid": enrollment_id},
    )
    db.execute(
        text("""
        INSERT INTO obs_advisor_actions
        (id, student_user_id, advisor_user_id, term_id, action_type, section_id, approval_request_id, note, created_at)
        VALUES (:id, :su, :au, :tid, 'remove_section', NULL, NULL, 'enrollment_id=' || :eid, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "su": student_user_id,
            "au": advisor_user_id,
            "tid": tid,
            "eid": enrollment_id,
        },
    )
    db.commit()
    return True, None


def finalize_advisee_schedule(
    db: Session,
    advisor_user_id: str,
    student_user_id: str,
    term_id: str,
) -> tuple[bool, Optional[str]]:
    spid = resolve_student_profile_id(db, student_user_id)
    if not spid or not _ensure_advisor_for_student(db, advisor_user_id, spid):
        return False, "Yetkisiz."
    prow = (
        db.execute(
            text("""
            SELECT note FROM obs_approval_requests
            WHERE student_id = :spid AND request_type = 'schedule_batch' AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
            """),
            {"spid": spid},
        )
        .mappings()
        .first()
    )
    if not prow:
        return False, "Onay bekleyen liste talebi yok."
    tnote, flow = _batch_flow_and_term_from_note(prow.get("note"))
    if not tnote or tnote != term_id:
        return False, "Talep bu dönem ile eşleşmiyor."
    if flow == "add_drop":
        proj = add_drop_projected_load_pending_review(db, spid, term_id)
        ok_b, msg_b = validate_add_drop_akts_bounds(db, spid, term_id, proj)
        if not ok_b:
            return False, msg_b
        _finalize_adddrop_batch(db, spid, term_id)
    else:
        _finalize_pending_enrollments_for_term(db, spid, term_id)
    p1 = BATCH_TERM_NOTE_PREFIX + term_id
    p2 = BATCH_ADDDROP_TERM_NOTE_PREFIX + term_id
    db.execute(
        text("""
        UPDATE obs_approval_requests SET status = 'approved', resolved_at = NOW()
        WHERE student_id = :spid AND request_type = 'schedule_batch' AND status = 'pending'
          AND (note LIKE :p1 || '%' OR note LIKE :p2 || '%')
        """),
        {"spid": spid, "p1": p1, "p2": p2},
    )
    db.execute(
        text("""
        INSERT INTO obs_advisor_actions
        (id, student_user_id, advisor_user_id, term_id, action_type, section_id, approval_request_id, note, created_at)
        VALUES (:id, :su, :au, :tid, 'finalize_schedule', NULL, NULL, NULL, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "su": student_user_id,
            "au": advisor_user_id,
            "tid": term_id,
        },
    )
    db.commit()
    return True, None


def reject_advisee_schedule(
    db: Session,
    advisor_user_id: str,
    student_user_id: str,
    term_id: str,
) -> tuple[bool, Optional[str]]:
    spid = resolve_student_profile_id(db, student_user_id)
    if not spid or not _ensure_advisor_for_student(db, advisor_user_id, spid):
        return False, "Yetkisiz."
    prow = (
        db.execute(
            text("""
            SELECT note FROM obs_approval_requests
            WHERE student_id = :spid AND request_type = 'schedule_batch' AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
            """),
            {"spid": spid},
        )
        .mappings()
        .first()
    )
    if not prow:
        return False, "Onay bekleyen liste talebi yok."
    tnote, flow = _batch_flow_and_term_from_note(prow.get("note"))
    if not tnote or tnote != term_id:
        return False, "Talep bu dönem ile eşleşmiyor."
    if flow == "add_drop":
        _revert_adddrop_batch(db, spid, term_id)
    else:
        _revert_pending_enrollments_to_draft(db, spid, term_id)
    p1 = BATCH_TERM_NOTE_PREFIX + term_id
    p2 = BATCH_ADDDROP_TERM_NOTE_PREFIX + term_id
    db.execute(
        text("""
        UPDATE obs_approval_requests SET status = 'rejected', resolved_at = NOW()
        WHERE student_id = :spid AND request_type = 'schedule_batch' AND status = 'pending'
          AND (note LIKE :p1 || '%' OR note LIKE :p2 || '%')
        """),
        {"spid": spid, "p1": p1, "p2": p2},
    )
    db.commit()
    return True, None


def admin_update_term_registration_windows(
    db: Session,
    term_id: str,
    registration_open: Optional[bool],
    registration_start: Optional[str],
    registration_end: Optional[str],
    add_drop_open: Optional[bool],
    add_drop_start: Optional[str],
    add_drop_end: Optional[str],
) -> Optional[dict[str, Any]]:
    def dval(s: Optional[str]) -> Any:
        if s is None or str(s).strip() == "":
            return None
        return str(s).strip()

    db.execute(
        text("""
        UPDATE obs_terms SET
            registration_open = COALESCE(:ro, registration_open),
            registration_start = COALESCE(CAST(:rs AS date), registration_start),
            registration_end = COALESCE(CAST(:re AS date), registration_end),
            add_drop_open = COALESCE(:ado, add_drop_open),
            add_drop_start = COALESCE(CAST(:ads AS date), add_drop_start),
            add_drop_end = COALESCE(CAST(:ade AS date), add_drop_end)
        WHERE id = :tid
        """),
        {
            "tid": term_id,
            "ro": registration_open,
            "rs": dval(registration_start),
            "re": dval(registration_end),
            "ado": add_drop_open,
            "ads": dval(add_drop_start),
            "ade": dval(add_drop_end),
        },
    )
    db.commit()
    rows = list_terms(db)
    for t in rows:
        if t.get("id") == term_id:
            return t
    return None


def resolve_approval(
    db: Session,
    request_id: str,
    approver_user_id: str,
    approve: bool,
    note: Optional[str],
) -> tuple[bool, Optional[str]]:
    row = (
        db.execute(
            text("""
            SELECT id, student_id, request_type, related_enrollment_id, status, note
            FROM obs_approval_requests
            WHERE id = :rid AND approver_id = :aid
            """),
            {"rid": request_id, "aid": approver_user_id},
        )
        .mappings()
        .first()
    )
    if not row or (row.get("status") or "") != "pending":
        return False, None
    req_type = row.get("request_type") or ""
    spid_prof = str(row["student_id"])
    if approve and req_type == "drop_request" and row.get("related_enrollment_id"):
        db.execute(
            text("""
            UPDATE obs_course_enrollments SET status = 'dropped', dropped_at = NOW()
            WHERE id = :eid AND student_id = :spid
            """),
            {"eid": row["related_enrollment_id"], "spid": spid_prof},
        )
    if req_type == "schedule_batch":
        if not _ensure_advisor_for_student(db, approver_user_id, spid_prof):
            return False, None
        term_id, flow = _batch_flow_and_term_from_note(row.get("note"))
        if not term_id:
            return False, None
        if approve:
            if flow == "add_drop":
                proj = add_drop_projected_load_pending_review(db, spid_prof, term_id)
                ok_b, msg_b = validate_add_drop_akts_bounds(db, spid_prof, term_id, proj)
                if not ok_b:
                    db.rollback()
                    return False, msg_b
                _finalize_adddrop_batch(db, spid_prof, term_id)
            else:
                _finalize_pending_enrollments_for_term(db, spid_prof, term_id)
        else:
            if flow == "add_drop":
                _revert_adddrop_batch(db, spid_prof, term_id)
            else:
                _revert_pending_enrollments_to_draft(db, spid_prof, term_id)
    st = "approved" if approve else "rejected"
    res = db.execute(
        text("""
        UPDATE obs_approval_requests SET status = :st, note = COALESCE(:note, note), resolved_at = NOW()
        WHERE id = :rid AND approver_id = :aid
        """),
        {"st": st, "note": note, "rid": request_id, "aid": approver_user_id},
    )
    db.commit()
    if res.rowcount > 0:
        return True, None
    return False, None


def _announcement_target_student_select_sql(db: Session) -> str:
    col = obs_announcements_target_student_column(db)
    bind = db.get_bind()
    null_sql = (
        "CAST(NULL AS TEXT) AS target_student_no"
        if bind.dialect.name == "sqlite"
        else "CAST(NULL AS VARCHAR) AS target_student_no"
    )
    if not col:
        return null_sql
    return f"a.{col} AS target_student_no"


def insert_announcement(
    db: Session,
    created_by: str,
    title: str,
    content: str,
    audience_type: str,
    department_id: Optional[str],
    course_section_id: Optional[str],
    student_number: Optional[str] = None,
) -> str:
    aid = str(uuid.uuid4())
    title = clamp_announcement_varchar(title)
    content = clamp_announcement_varchar(content)
    at_norm = (audience_type or "").strip().lower()
    did_n = optional_uuid_param(department_id, "Bölüm kimliği")
    csid_n = optional_uuid_param(course_section_id, "Şube kimliği")
    snv: Optional[str] = None
    if student_number is not None:
        s = str(student_number).strip()
        snv = s[:64] if s else None
    sn_col = obs_announcements_target_student_column(db)
    params: dict[str, Any] = {
        "id": aid,
        "cb": created_by,
        "t": title,
        "c": content,
        "at": at_norm,
        "did": did_n,
        "csid": csid_n,
    }
    if sn_col:
        q = f"""
        INSERT INTO obs_announcements
        (id, created_by_user_id, title, content, audience_type, department_id, course_section_id, {sn_col}, is_active, published_at, created_at)
        VALUES (:id, :cb, :t, :c, :at, :did, :csid, :snv, true, NOW(), NOW())
        """
        params["snv"] = snv
    else:
        q = """
        INSERT INTO obs_announcements
        (id, created_by_user_id, title, content, audience_type, department_id, course_section_id, is_active, published_at, created_at)
        VALUES (:id, :cb, :t, :c, :at, :did, :csid, true, NOW(), NOW())
        """
    try:
        db.execute(text(q), params)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return aid


def _announcement_mgmt_row(r: Any) -> dict[str, Any]:
    return {
        "id": _str_id(r["id"]),
        "title": r.get("title") or "",
        "content": r.get("content") or "",
        "audience_type": r.get("audience_type") or "",
        "department_id": _str_id(r.get("department_id")),
        "course_section_id": _str_id(r.get("course_section_id")),
        "student_no": (
            (str(r.get("target_student_no")).strip() or None)
            if r.get("target_student_no") is not None
            else None
        ),
        "is_active": bool(r.get("is_active")),
        "published_at": (
            r.get("published_at").isoformat() if r.get("published_at") else None
        ),
        "created_at": (
            r.get("created_at").isoformat() if r.get("created_at") else None
        ),
        "created_by": r.get("created_by_user_id"),
        "created_by_name": r.get("creator_name") or "",
    }


def list_announcements_created_by(
    db: Session, user_id: str, limit: int = 500
) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text(
                f"""
                SELECT a.id, a.title, a.content, a.audience_type, a.department_id, a.course_section_id,
                       {_announcement_target_student_select_sql(db)},
                       a.is_active, a.published_at, a.created_at, a.created_by_user_id,
                       u.name AS creator_name
                FROM obs_announcements a
                LEFT JOIN {USER_TBL} u ON u.id = a.created_by_user_id
                WHERE a.created_by_user_id = :uid
                ORDER BY a.created_at DESC NULLS LAST, a.published_at DESC NULLS LAST
                LIMIT :lim
                """
            ),
            {"uid": user_id, "lim": limit},
        )
        .mappings()
        .all()
    )
    return [_announcement_mgmt_row(r) for r in rows]


def list_announcements_all_admin(db: Session, limit: int = 500) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text(
                f"""
                SELECT a.id, a.title, a.content, a.audience_type, a.department_id, a.course_section_id,
                       {_announcement_target_student_select_sql(db)},
                       a.is_active, a.published_at, a.created_at, a.created_by_user_id,
                       u.name AS creator_name
                FROM obs_announcements a
                LEFT JOIN {USER_TBL} u ON u.id = a.created_by_user_id
                ORDER BY a.created_at DESC NULLS LAST, a.published_at DESC NULLS LAST
                LIMIT :lim
                """
            ),
            {"lim": limit},
        )
        .mappings()
        .all()
    )
    return [_announcement_mgmt_row(r) for r in rows]


def get_announcement_mgmt_by_id(
    db: Session, announcement_id: str
) -> Optional[dict[str, Any]]:
    row = (
        db.execute(
            text(
                f"""
                SELECT a.id, a.title, a.content, a.audience_type, a.department_id, a.course_section_id,
                       {_announcement_target_student_select_sql(db)},
                       a.is_active, a.published_at, a.created_at, a.created_by_user_id,
                       u.name AS creator_name
                FROM obs_announcements a
                LEFT JOIN {USER_TBL} u ON u.id = a.created_by_user_id
                WHERE a.id = :id
                """
            ),
            {"id": announcement_id},
        )
        .mappings()
        .first()
    )
    return _announcement_mgmt_row(row) if row else None


def update_announcement_owned(
    db: Session,
    announcement_id: str,
    actor_user_id: str,
    updates: dict[str, Any],
    require_creator: bool,
) -> tuple[bool, str]:
    sel = db.execute(
        text("SELECT created_by_user_id FROM obs_announcements WHERE id = :id"),
        {"id": announcement_id},
    ).first()
    if not sel:
        return False, "not_found"
    if require_creator and str(sel[0]) != str(actor_user_id):
        return False, "forbidden"

    upd = dict(updates)
    sn_col = obs_announcements_target_student_column(db)
    if sn_col and "student_no" in upd:
        raw_sn = upd.pop("student_no")
        if raw_sn is None:
            upd[sn_col] = None
        else:
            t = str(raw_sn).strip()[:64]
            upd[sn_col] = t if t else None
    for uk in ("department_id", "course_section_id"):
        if uk in upd and upd[uk] is not None:
            s = str(upd[uk]).strip()
            upd[uk] = s or None
    if "title" in upd and upd["title"] is not None:
        upd["title"] = clamp_announcement_varchar(str(upd["title"]))
    if "content" in upd and upd["content"] is not None:
        upd["content"] = clamp_announcement_varchar(str(upd["content"]))

    allowed_cols = {
        "title",
        "content",
        "audience_type",
        "department_id",
        "course_section_id",
        "is_active",
    }
    if sn_col:
        allowed_cols.add(sn_col)
    set_parts: list[str] = []
    params: dict[str, Any] = {"id": announcement_id}

    for key, val in upd.items():
        if key not in allowed_cols:
            continue
        set_parts.append(f"{key} = :{key}")
        params[key] = val

    if not set_parts:
        return False, "no_fields"

    if require_creator:
        stmt = (
            f"UPDATE obs_announcements SET {', '.join(set_parts)} "
            "WHERE id = :id AND created_by_user_id = :actor"
        )
        params["actor"] = actor_user_id
    else:
        stmt = f"UPDATE obs_announcements SET {', '.join(set_parts)} WHERE id = :id"

    res = db.execute(text(stmt), params)
    db.commit()
    if res.rowcount > 0:
        return True, ""
    return False, "not_found"


def delete_announcement_owned(
    db: Session,
    announcement_id: str,
    actor_user_id: str,
    require_creator: bool,
) -> tuple[bool, str]:
    if require_creator:
        res = db.execute(
            text(
                "DELETE FROM obs_announcements WHERE id = :id AND created_by_user_id = :uid"
            ),
            {"id": announcement_id, "uid": actor_user_id},
        )
    else:
        res = db.execute(
            text("DELETE FROM obs_announcements WHERE id = :id"),
            {"id": announcement_id},
        )
    db.commit()
    if res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_counts(db: Session) -> dict[str, int]:
    def c(table: str) -> int:
        return db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0

    return {
        "departments": c("obs_departments"),
        "terms": c("obs_terms"),
        "courses": c("obs_courses"),
        "classrooms": c("obs_classrooms"),
        "sections": c("obs_course_sections"),
        "announcements": c("obs_announcements"),
    }


def registration_settings_row(db: Session, term_id: Optional[str]) -> Optional[dict]:
    if term_id:
        row = (
            db.execute(
                text(
                    "SELECT * FROM obs_registration_settings WHERE term_id = :t LIMIT 1"
                ),
                {"t": term_id},
            )
            .mappings()
            .first()
        )
    else:
        row = db.execute(text("""
            SELECT rs.* FROM obs_registration_settings rs
            INNER JOIN obs_terms tm ON rs.term_id = tm.id
            WHERE tm.is_active = true
            LIMIT 1
            """)).mappings().first()
    return dict(row) if row else None


def resolve_active_term_id(db: Session) -> Optional[str]:
    row = db.execute(
        text(
            "SELECT id FROM obs_terms WHERE is_active = true ORDER BY start_date DESC LIMIT 1"
        )
    ).first()
    return _str_id(row[0]) if row else None


def upsert_registration_settings(
    db: Session, term_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    cur = registration_settings_row(db, term_id) or {}
    m: dict[str, Any] = {**cur, **body}

    if m.get("max_akts") is not None and m.get("akts_limit_default") in (None, ""):
        m["akts_limit_default"] = m["max_akts"]
    if m.get("bonus_akts") is not None and m.get("akts_limit_high") in (None, ""):
        base = int(m.get("max_akts") or m.get("akts_limit_default") or 30)
        m["akts_limit_high"] = base + int(m["bonus_akts"])
    if m.get("gpa_threshold") is not None and m.get("min_gpa_for_high_akts") in (None, ""):
        m["min_gpa_for_high_akts"] = m["gpa_threshold"]

    akts_limit_default = int(m.get("akts_limit_default") or 30)
    akts_limit_high = int(m.get("akts_limit_high") or 36)
    akts_limit_top = int(m.get("akts_limit_top") or 45)
    akts_limit_prep = int(m.get("akts_limit_prep") or 25)
    min_gpa = float(m.get("min_gpa_for_high_akts") or 2.50)
    min_gpa_top = float(m.get("min_gpa_for_top_akts") or 3.50)

    existing = db.execute(
        text("SELECT id FROM obs_registration_settings WHERE term_id = :tid LIMIT 1"),
        {"tid": term_id},
    ).first()
    params = {
        "tid": term_id,
        "ald": akts_limit_default,
        "alh": akts_limit_high,
        "altop": akts_limit_top,
        "alp": akts_limit_prep,
        "mg": min_gpa,
        "mgtop": min_gpa_top,
    }
    if existing:
        db.execute(
            text("""
                UPDATE obs_registration_settings SET
                    akts_limit_default = :ald,
                    akts_limit_high = :alh,
                    akts_limit_top = :altop,
                    akts_limit_prep = :alp,
                    min_gpa_for_high_akts = :mg,
                    min_gpa_for_top_akts = :mgtop
                WHERE term_id = :tid
                """),
            params,
        )
    else:
        rid = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO obs_registration_settings
                    (id, term_id, akts_limit_default, akts_limit_high, akts_limit_top, akts_limit_prep,
                     min_gpa_for_high_akts, min_gpa_for_top_akts)
                VALUES
                    (:id, :tid, :ald, :alh, :altop, :alp, :mg, :mgtop)
                """),
            {**params, "id": rid},
        )
    db.commit()
    return registration_settings_row(db, term_id) or {}


def list_audit_logs(db: Session, limit: int) -> tuple[list, int]:
    rows = (
        db.execute(
            text(
                "SELECT * FROM obs_audit_logs ORDER BY created_at DESC NULLS LAST LIMIT :lim"
            ),
            {"lim": limit},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows], len(rows)


def list_document_requests_admin(
    db: Session, status_filter: Optional[str]
) -> tuple[list, int]:
    q = "SELECT dr.*, sp.user_id AS student_user_id FROM obs_document_requests dr JOIN obs_student_profiles sp ON dr.student_id = sp.id WHERE 1=1"
    params: dict[str, Any] = {}
    if status_filter:
        q += " AND dr.status = :st"
        params["st"] = status_filter
    q += " ORDER BY dr.created_at DESC"
    rows = db.execute(text(q), params).mappings().all()
    out = [
        {
            "id": _str_id(r["id"]),
            "requesting_institution": r.get("requesting_institution") or "",
            "request_reason": r.get("request_reason") or "",
            "document_type": r.get("document_type") or "",
            "document_subtype": r.get("document_subtype") or "",
            "status": r.get("status") or "",
            "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
        }
        for r in rows
    ]
    return out, len(out)


def patch_document_request(db: Session, request_id: str, new_status: str) -> bool:
    res = db.execute(
        text(
            "UPDATE obs_document_requests SET status = :st, completed_at = NOW(), updated_at = NOW() WHERE id = :id"
        ),
        {"st": new_status, "id": request_id},
    )
    db.commit()
    return res.rowcount > 0


def list_instructors(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text(f"""
        SELECT ap.user_id, u.email, u.name, u.role
        FROM obs_academic_profiles ap
        LEFT JOIN {USER_TBL} u ON u.id = ap.user_id
        """),
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": _str_id(r.get("user_id")),
            "email": r.get("email") or "",
            "full_name": r.get("name") or "",
            "role": r.get("role") or "user",
        }
        for r in rows
    ]


def user_info_obs_role(user_info: Optional[dict]) -> Optional[str]:
    if not user_info or not isinstance(user_info, dict):
        return None
    return user_info.get("obs_role") or user_info.get("obsRole")


def create_enrollment_requests(
    db: Session,
    webui_user_id: str,
    student_display_name: str,
    section_ids: list[str],
    note: Optional[str],
    approver_user_id: Optional[str],
) -> list[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return []
    sp_row = db.execute(
        text("SELECT student_number FROM obs_student_profiles WHERE id = :id"),
        {"id": spid},
    ).first()
    student_no = sp_row[0] if sp_row else ""
    out = []
    for sid in section_ids:
        row = (
            db.execute(
                text("""
            SELECT c.code, c.name FROM obs_course_sections cs
            JOIN obs_courses c ON cs.course_id = c.id WHERE cs.id = :csid
            """),
                {"csid": sid},
            )
            .mappings()
            .first()
        )
        cc = row.get("course_code") if row else ""
        cn = row.get("course_name") if row else ""
        rid = str(uuid.uuid4())
        db.execute(
            text("""
            INSERT INTO obs_approval_requests
            (id, student_id, approver_id, request_type, related_enrollment_id, status, note, created_at)
            VALUES (:id, :spid, :appr, 'enrollment_request', NULL, 'pending', :note, NOW())
            """),
            {
                "id": rid,
                "spid": spid,
                "appr": approver_user_id,
                "note": note,
            },
        )
        out.append(
            {
                "id": rid,
                "student_user_id": webui_user_id,
                "section_id": sid,
                "course_code": cc,
                "course_name": cn,
                "request_type": "enrollment_request",
                "status": "pending",
                "student_name": student_display_name,
                "student_no": student_no,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
    db.commit()
    return out


def create_drop_request(
    db: Session,
    webui_user_id: str,
    student_display_name: str,
    enrollment_id: str,
    reason: Optional[str],
    approver_user_id: Optional[str],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, "Öğrenci profili yok."
    row = db.execute(
        text(
            "SELECT id FROM obs_course_enrollments WHERE id = :eid AND student_id = :spid"
        ),
        {"eid": enrollment_id, "spid": spid},
    ).first()
    if not row:
        return None, "Kayıt bulunamadı."
    ok_drop, deny_reason = enrollment_drop_allowed(db, spid, enrollment_id)
    if not ok_drop:
        return None, deny_reason or "Bu ders için bırakma onaylanamaz."
    sp_row = db.execute(
        text("SELECT student_number FROM obs_student_profiles WHERE id = :id"),
        {"id": spid},
    ).first()
    student_no = sp_row[0] if sp_row else ""
    rid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_approval_requests
        (id, student_id, approver_id, request_type, related_enrollment_id, status, note, created_at)
        VALUES (:id, :spid, :appr, 'drop_request', :eid, 'pending', :reason, NOW())
        """),
        {
            "id": rid,
            "spid": spid,
            "appr": approver_user_id,
            "eid": enrollment_id,
            "reason": reason,
        },
    )
    db.commit()
    return (
        {
            "id": rid,
            "student_user_id": webui_user_id,
            "enrollment_id": enrollment_id,
            "request_type": "drop_request",
            "status": "pending",
            "reason": reason,
            "student_name": student_display_name,
            "student_no": student_no,
            "created_at": datetime.utcnow().isoformat(),
        },
        None,
    )


def list_roles_with_permissions(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT rp.role_name, p.code
        FROM obs_role_permissions rp
        JOIN obs_permissions p ON p.id = rp.permission_id
        ORDER BY rp.role_name, p.code
        """)).mappings().all()
    by_role: dict[str, list[str]] = {}
    for r in rows:
        by_role.setdefault(r["role_name"] or "", []).append(r["code"] or "")
    out = []
    for i, (name, perms) in enumerate(sorted(by_role.items()), start=1):
        rid = f"role-{name.lower().replace(' ', '-')}" if name else f"role-{i}"
        out.append(
            {
                "id": rid,
                "name": name,
                "description": "",
                "permissions": perms,
            }
        )
    return out


def update_role_permissions(db: Session, role_id: str, permissions: list[str]) -> bool:
    _ = role_id
    _ = permissions
    return False


def admin_insert_department(db: Session, code: str, name: str) -> dict[str, Any]:
    did = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO obs_departments (id, code, name, created_at) VALUES (:id, :c, :n, NOW())"
        ),
        {"id": did, "c": code, "n": name},
    )
    db.commit()
    return {"id": did, "code": code, "name": name}


def admin_insert_term(
    db: Session,
    name: str,
    academic_year: str,
    season: str,
    starts_at: str,
    ends_at: str,
    is_active: bool,
) -> dict[str, Any]:
    _ = academic_year
    _ = season
    tid = str(uuid.uuid4())
    sd = starts_at if starts_at else None
    ed = ends_at if ends_at else None
    db.execute(
        text("""
        INSERT INTO obs_terms (id, name, start_date, end_date, is_active, created_at)
        VALUES (:id, :name, CAST(:sd AS date), CAST(:ed AS date), :ia, NOW())
        """),
        {"id": tid, "name": name, "sd": sd, "ed": ed, "ia": is_active},
    )
    db.commit()
    return {
        "id": tid,
        "name": name,
        "academic_year": academic_year,
        "season": season,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "is_active": is_active,
    }


def admin_insert_course(
    db: Session,
    department_id: str,
    code: str,
    name: str,
    credits: int,
    akts: int,
    class_year: int,
    course_type: str,
    theory_hours: str,
    language: str,
) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_courses (id, department_id, code, name, credits, akts, class_year, type, theory_hours, language, created_at)
        VALUES (:id, :did, :code, :name, :cr, :ak, :cy, :typ, :th, :lang, NOW())
        """),
        {
            "id": cid,
            "did": department_id,
            "code": code,
            "name": name,
            "cr": credits,
            "ak": akts,
            "cy": class_year,
            "typ": course_type,
            "th": theory_hours,
            "lang": language,
        },
    )
    db.commit()
    return {
        "id": cid,
        "department_id": department_id,
        "code": code,
        "name": name,
        "credits": credits,
        "akts": akts,
        "class_year": class_year,
        "type": course_type,
        "theory_hours": theory_hours,
        "language": language,
    }


def admin_insert_classroom(
    db: Session, building: str, name: str, capacity: int, is_online: bool
) -> dict[str, Any]:
    rid = str(uuid.uuid4())
    code = name or rid[:8]
    db.execute(
        text("""
        INSERT INTO obs_classrooms (id, code, name, building, capacity, is_online)
        VALUES (:id, :code, :name, :b, :cap, :io)
        """),
        {
            "id": rid,
            "code": code,
            "name": name,
            "b": building,
            "cap": capacity,
            "io": is_online,
        },
    )
    db.commit()
    return {
        "id": rid,
        "building": building,
        "name": name,
        "capacity": capacity,
        "is_online": is_online,
    }


def resolve_classroom_id_by_code(db: Session, code: str) -> Optional[str]:
    row = db.execute(
        text("SELECT id FROM obs_classrooms WHERE code = :c LIMIT 1"), {"c": code}
    ).first()
    return str(row[0]) if row else None


def admin_insert_section(
    db: Session,
    course_id: str,
    term_id: str,
    section_no: int,
    instructor_user_id: Optional[str],
    classroom_id: Optional[str],
    day_of_week: str,
    start_time: str,
    end_time: str,
    capacity: int,
) -> dict[str, Any]:
    apid = None
    if instructor_user_id:
        try:
            apid = ensure_academic_profile_for_user(db, instructor_user_id)
        except ValueError as ex:
            if str(ex) == "no_department_for_stub_profile":
                raise ValueError("no_department_for_stub_profile") from ex
            raise
    sid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_course_sections
        (id, course_id, term_id, instructor_id, section_no, classroom_id, day_of_week, start_time, end_time, capacity, created_at)
        VALUES (:id, :cid, :tid, :iid, :sn, :crid, :dow, CAST(:st AS time), CAST(:et AS time), :cap, NOW())
        """),
        {
            "id": sid,
            "cid": course_id,
            "tid": term_id,
            "iid": apid,
            "sn": section_no,
            "crid": classroom_id,
            "dow": day_of_week,
            "st": start_time + ":00" if len(start_time) == 5 else start_time,
            "et": end_time + ":00" if len(end_time) == 5 else end_time,
            "cap": capacity,
        },
    )
    db.commit()
    return {"id": sid}


def admin_insert_calendar_event(
    db: Session,
    term_id: str,
    event_type: str,
    title: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    db.execute(
        text("""
        INSERT INTO obs_calendar_events (id, term_id, event_type, title, start_date, end_date, created_at)
        VALUES (:id, :tid, :et, :ti, CAST(:sd AS date), CAST(:ed AS date), NOW())
        """),
        {
            "id": cid,
            "tid": term_id,
            "et": event_type,
            "ti": title,
            "sd": start_date,
            "ed": end_date,
        },
    )
    db.commit()
    return {
        "id": cid,
        "term_id": term_id,
        "event_type": event_type,
        "title": title,
        "start_date": start_date,
        "end_date": end_date,
    }


def list_courses_raw(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("SELECT * FROM obs_courses ORDER BY code")).mappings().all()
    return [dict(r) for r in rows]


def list_classrooms_raw(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.execute(text("SELECT * FROM obs_classrooms ORDER BY code")).mappings().all()
    )
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = _str_id(d.get("id"))
        out.append(d)
    return out


def list_classrooms_dropdown(db: Session) -> list[dict[str, Any]]:
    """
    Sınav formu select: code doluysa kod, değilse name ile anahtar.
    Boş satırlar atlanır; sıralama görünen ada göre.
    """
    rows = (
        db.execute(
            text(
                "SELECT id, code, name, building, capacity FROM obs_classrooms"
            )
        )
        .mappings()
        .all()
    )
    packed: list[tuple[str, dict[str, Any]]] = []
    for r in rows:
        code = (r.get("code") or "").strip()
        name = (r.get("name") or "").strip()
        key = code or name
        if not key:
            continue
        cap = r.get("capacity")
        cap_i = int(cap) if cap is not None else None
        bl = (r.get("building") or "").strip()
        label = key
        if cap_i is not None:
            label = f"{key} · {cap_i} kişi"
        if bl:
            label = f"{label} · {bl}"
        packed.append(
            (
                key.lower(),
                {
                    "id": _str_id(r["id"]),
                    "code": key,
                    "label": label,
                    "capacity": cap_i,
                },
            )
        )
    packed.sort(key=lambda x: x[0])
    return [p[1] for p in packed]


def resolve_classroom_id_by_label(db: Session, label: Optional[str]) -> Optional[str]:
    """Dropdown veya serbest metin: önce code, sonra name ile obs_classrooms eşlemesi."""
    if not label:
        return None
    s = str(label).strip()
    if not s:
        return None
    row = db.execute(
        text("SELECT id FROM obs_classrooms WHERE TRIM(code) = :c LIMIT 1"),
        {"c": s},
    ).first()
    if row:
        return str(row[0])
    row = db.execute(
        text("SELECT id FROM obs_classrooms WHERE TRIM(name) = :n LIMIT 1"),
        {"n": s},
    ).first()
    if row:
        return str(row[0])
    return None


def list_sections_raw(db: Session, term_id: Optional[str]) -> list[dict[str, Any]]:
    q = """
        SELECT cs.id, cs.course_id, cs.term_id, cs.section_no, cs.instructor_id, cs.classroom_id,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity, cs.created_at,
               c.code AS course_code, c.name AS course_name,
               cr.code AS classroom_code,
               ins_u.name AS instructor_label,
               ap.user_id AS instructor_user_id
        FROM obs_course_sections cs
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" ins_u ON ins_u.id = ap.user_id
        WHERE 1=1
        """
    params: dict[str, Any] = {}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    q += " ORDER BY c.code, cs.section_no"
    rows = db.execute(text(q), params).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["id"] = _str_id(d.get("id"))
        d["course_id"] = _str_id(d.get("course_id"))
        d["term_id"] = _str_id(d.get("term_id"))
        d["instructor_id"] = _str_id(d.get("instructor_id"))
        d["instructor_user_id"] = _str_id(d.get("instructor_user_id"))
        d["classroom_id"] = _str_id(d.get("classroom_id"))
        d["start_time"] = _fmt_time(d.get("start_time"))
        d["end_time"] = _fmt_time(d.get("end_time"))
        d["day_of_week"] = normalize_weekday_tr(d.get("day_of_week"))
        if d.get("created_at"):
            d["created_at"] = (
                d["created_at"].isoformat()
                if hasattr(d["created_at"], "isoformat")
                else str(d["created_at"])
            )
        out.append(d)
    return out


def list_academic_instructors_dropdown(
    obs_db: Session,
    primary_db: Session,
    department_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Akademisyenler — obs_academic_profiles üzerinden; ad/e-posta ana WebUI user tablosundan."""
    from open_webui.models.users import User

    params: dict[str, Any] = {}
    dept_sql = ""
    if department_id and str(department_id).strip():
        dept_sql = " AND ap.department_id = :did"
        params["did"] = str(department_id).strip()
    q = f"""
        SELECT ap.id AS academic_profile_id, ap.user_id, ap.title,
               ap.department_id, d.name AS department_name, d.code AS department_code
        FROM obs_academic_profiles ap
        LEFT JOIN obs_departments d ON ap.department_id = d.id
        WHERE 1=1 {dept_sql}
        ORDER BY d.code NULLS LAST, ap.id
        LIMIT 1000
        """
    rows = obs_db.execute(text(q), params).mappings().all()
    uid_set: set[str] = set()
    for r in rows:
        u = _str_id(r.get("user_id"))
        if u:
            uid_set.add(u)
    nm_em: dict[str, tuple[str, str]] = {}
    if uid_set:
        for uid_row, nm, em in (
            primary_db.query(User.id, User.name, User.email)
            .filter(User.id.in_(list(uid_set)))
            .all()
        ):
            nm_em[str(uid_row)] = (nm or "", em or "")
    out: list[dict[str, Any]] = []
    for r in rows:
        uid = _str_id(r.get("user_id"))
        fn, em = nm_em.get(uid or "", ("", "")) if uid else ("", "")
        out.append(
            {
                "academic_profile_id": _str_id(r.get("academic_profile_id")),
                "user_id": uid,
                "title": r.get("title") or "",
                "full_name": fn,
                "email": em,
                "department_id": _str_id(r.get("department_id")),
                "department_name": r.get("department_name") or "",
                "department_code": r.get("department_code") or "",
            }
        )
    out.sort(
        key=lambda x: (
            (x.get("department_code") or "").lower(),
            (x.get("full_name") or "").lower(),
        )
    )
    return out


def augment_instructors_with_primary_academicians(
    existing: list[dict[str, Any]],
    primary_db: Session,
    department_id: Optional[str],
) -> list[dict[str, Any]]:
    """
    obs_academic_profiles boş kalsa bile ana DB'de rolü academician olan kullanıcıları listeye ekler.
    Bölüm filtresi varken yalnızca OBS sonucunu kullanır (tutarlılık).
    """
    if department_id and str(department_id).strip():
        return existing
    from open_webui.models.users import User

    seen: set[str] = set()
    for r in existing:
        uid = _str_id(r.get("user_id"))
        if uid:
            seen.add(uid)
    out = list(existing)
    rows = (
        primary_db.query(User)
        .filter(func.lower(func.coalesce(User.role, "")) == "academician")
        .order_by(User.name)
        .limit(500)
        .all()
    )
    for u in rows:
        uid = _str_id(u.id)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(
            {
                "academic_profile_id": None,
                "user_id": uid,
                "title": "",
                "full_name": u.name or "",
                "email": u.email or "",
                "department_id": None,
                "department_name": "",
                "department_code": "",
            }
        )
    return out


def list_calendar_raw(db: Session, term_id: Optional[str]) -> list[dict[str, Any]]:
    q = "SELECT * FROM obs_calendar_events WHERE 1=1"
    params: dict[str, Any] = {}
    if term_id:
        q += " AND term_id = :tid"
        params["tid"] = term_id
    q += " ORDER BY start_date"
    rows = db.execute(text(q), params).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = _str_id(d.get("id"))
        d["term_id"] = _str_id(d.get("term_id"))
        d["start_date"] = _fmt_date(d.get("start_date")) or ""
        d["end_date"] = _fmt_date(d.get("end_date")) or ""
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Admin katalog CRUD (PUT/DELETE)
# ---------------------------------------------------------------------------


def admin_update_department(
    db: Session, dept_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    allowed = {"code", "name", "faculty_name"}
    parts: list[str] = []
    params: dict[str, Any] = {"id": dept_id}
    for k, v in updates.items():
        if k not in allowed:
            continue
        parts.append(f"{k} = :{k}")
        params[k] = v
    if not parts:
        return None
    res = db.execute(
        text(f"UPDATE obs_departments SET {', '.join(parts)} WHERE id = :id"),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    row = (
        db.execute(
            text("SELECT id, code, name FROM obs_departments WHERE id = :id"),
            {"id": dept_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return {
        "id": _str_id(row["id"]),
        "code": row.get("code") or "",
        "name": row.get("name") or "",
    }


def admin_delete_department(db: Session, dept_id: str) -> tuple[bool, str]:
    n = int(
        db.execute(
            text("SELECT COUNT(*) FROM obs_courses WHERE department_id = :id"),
            {"id": dept_id},
        ).scalar()
        or 0
    )
    if n > 0:
        return False, "in_use"
    res = db.execute(
        text("DELETE FROM obs_departments WHERE id = :id"), {"id": dept_id}
    )
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_term(db: Session, term_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    u: dict[str, Any] = {}
    if "name" in updates:
        u["name"] = updates["name"]
    if "is_active" in updates:
        u["is_active"] = bool(updates["is_active"])
    if "start_date" in updates or "starts_at" in updates:
        v = updates.get("start_date", updates.get("starts_at"))
        u["start_date"] = None if v in (None, "") else v
    if "end_date" in updates or "ends_at" in updates:
        v = updates.get("end_date", updates.get("ends_at"))
        u["end_date"] = None if v in (None, "") else v
    parts: list[str] = []
    params: dict[str, Any] = {"id": term_id}
    if "name" in u:
        parts.append("name = :name")
        params["name"] = u["name"]
    if "is_active" in u:
        parts.append("is_active = :is_active")
        params["is_active"] = u["is_active"]
    if "start_date" in u:
        parts.append("start_date = CAST(:start_date AS date)")
        params["start_date"] = u["start_date"]
    if "end_date" in u:
        parts.append("end_date = CAST(:end_date AS date)")
        params["end_date"] = u["end_date"]
    if not parts:
        return None
    res = db.execute(
        text(f"UPDATE obs_terms SET {', '.join(parts)} WHERE id = :id"),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    rows = list_terms(db)
    for t in rows:
        if t.get("id") == term_id:
            return t
    return None


def admin_delete_term(db: Session, term_id: str) -> tuple[bool, str]:
    n = int(
        db.execute(
            text("SELECT COUNT(*) FROM obs_course_sections WHERE term_id = :id"),
            {"id": term_id},
        ).scalar()
        or 0
    )
    if n > 0:
        return False, "in_use"
    db.execute(
        text("DELETE FROM obs_calendar_events WHERE term_id = :id"),
        {"id": term_id},
    )
    db.execute(
        text("DELETE FROM obs_registration_settings WHERE term_id = :id"),
        {"id": term_id},
    )
    res = db.execute(text("DELETE FROM obs_terms WHERE id = :id"), {"id": term_id})
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_course(db: Session, course_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    allowed = {
        "department_id",
        "code",
        "name",
        "credits",
        "akts",
        "class_year",
        "type",
        "theory_hours",
        "language",
        "is_mandatory",
        "semester_no",
        "curriculum_semester",
    }
    parts: list[str] = []
    params: dict[str, Any] = {"id": course_id}
    for k, v in updates.items():
        if k not in allowed:
            continue
        parts.append(f"{k} = :{k}")
        params[k] = v
    if not parts:
        return None
    res = db.execute(
        text(f"UPDATE obs_courses SET {', '.join(parts)} WHERE id = :id"),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    row = (
        db.execute(text("SELECT * FROM obs_courses WHERE id = :id"), {"id": course_id})
        .mappings()
        .first()
    )
    return dict(row) if row else None


def admin_delete_course(db: Session, course_id: str) -> tuple[bool, str]:
    n = int(
        db.execute(
            text("SELECT COUNT(*) FROM obs_course_sections WHERE course_id = :id"),
            {"id": course_id},
        ).scalar()
        or 0
    )
    if n > 0:
        return False, "in_use"
    res = db.execute(text("DELETE FROM obs_courses WHERE id = :id"), {"id": course_id})
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_classroom(
    db: Session, classroom_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    allowed = {"code", "name", "building", "floor", "capacity", "is_online"}
    parts: list[str] = []
    params: dict[str, Any] = {"id": classroom_id}
    for k, v in updates.items():
        if k not in allowed:
            continue
        parts.append(f"{k} = :{k}")
        params[k] = v
    if not parts:
        return None
    res = db.execute(
        text(f"UPDATE obs_classrooms SET {', '.join(parts)} WHERE id = :id"),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    rows = list_classrooms_raw(db)
    for r in rows:
        if r.get("id") == classroom_id:
            return r
    return None


def admin_delete_classroom(db: Session, classroom_id: str) -> tuple[bool, str]:
    n = int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM obs_course_sections WHERE classroom_id = :id"
            ),
            {"id": classroom_id},
        ).scalar()
        or 0
    )
    if n > 0:
        return False, "in_use"
    res = db.execute(
        text("DELETE FROM obs_classrooms WHERE id = :id"), {"id": classroom_id}
    )
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_course_section(
    db: Session, section_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    params: dict[str, Any] = {"id": section_id}
    set_sql: list[str] = []

    u = dict(updates)
    if "instructor_user_id" in u:
        uid = u.pop("instructor_user_id")
        if uid:
            try:
                apid = ensure_academic_profile_for_user(db, str(uid))
            except ValueError as ex:
                if str(ex) == "no_department_for_stub_profile":
                    raise ValueError("no_department_for_stub_profile") from ex
                raise
            u["instructor_id"] = apid
        else:
            u["instructor_id"] = None

    allowed = {
        "course_id",
        "term_id",
        "instructor_id",
        "section_no",
        "classroom_id",
        "day_of_week",
        "capacity",
    }
    for k in ("start_time", "end_time"):
        if k in u:
            tv = str(u[k] or "")
            if len(tv) == 5:
                tv = tv + ":00"
            u[k] = tv

    if "day_of_week" in u and u.get("day_of_week"):
        u["day_of_week"] = normalize_weekday_tr(str(u["day_of_week"]))

    for k, v in u.items():
        if k not in allowed and k not in ("start_time", "end_time"):
            continue
        if k in ("start_time", "end_time"):
            set_sql.append(f"{k} = CAST(:{k} AS time)")
        else:
            set_sql.append(f"{k} = :{k}")
        params[k] = v

    if not set_sql:
        return None
    res = db.execute(
        text(f"UPDATE obs_course_sections SET {', '.join(set_sql)} WHERE id = :id"),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    rows = list_sections_raw(db, None)
    for r in rows:
        if r.get("id") == section_id:
            return r
    return None


def admin_delete_course_section(db: Session, section_id: str) -> tuple[bool, str]:
    checks = [
        (
            "SELECT COUNT(*) FROM obs_course_enrollments WHERE course_section_id = :id",
            "enrollments",
        ),
        ("SELECT COUNT(*) FROM obs_exams WHERE course_section_id = :id", "exams"),
        (
            "SELECT COUNT(*) FROM obs_attendance_records WHERE course_section_id = :id",
            "attendance",
        ),
    ]
    for q, _ in checks:
        n = int(db.execute(text(q), {"id": section_id}).scalar() or 0)
        if n > 0:
            return False, "in_use"
    res = db.execute(
        text("DELETE FROM obs_course_sections WHERE id = :id"), {"id": section_id}
    )
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_calendar_event(
    db: Session, event_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    allowed = {"term_id", "event_type", "title", "start_date", "end_date"}
    parts: list[str] = []
    params: dict[str, Any] = {"id": event_id}
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k in ("start_date", "end_date"):
            parts.append(f"{k} = CAST(:{k} AS date)")
        else:
            parts.append(f"{k} = :{k}")
        params[k] = v
    if not parts:
        return None
    res = db.execute(
        text(f"UPDATE obs_calendar_events SET {', '.join(parts)} WHERE id = :id"),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    row = (
        db.execute(
            text("SELECT * FROM obs_calendar_events WHERE id = :id"), {"id": event_id}
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    d = dict(row)
    d["id"] = _str_id(d.get("id"))
    d["term_id"] = _str_id(d.get("term_id"))
    d["start_date"] = _fmt_date(d.get("start_date")) or ""
    d["end_date"] = _fmt_date(d.get("end_date")) or ""
    return d


def admin_delete_calendar_event(db: Session, event_id: str) -> tuple[bool, str]:
    res = db.execute(
        text("DELETE FROM obs_calendar_events WHERE id = :id"), {"id": event_id}
    )
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_academic_profile_by_user_id(
    db: Session, user_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    allowed = {"staff_number", "title", "department_id", "office", "phone"}
    parts: list[str] = []
    params: dict[str, Any] = {"uid": user_id}
    for k, v in updates.items():
        if k not in allowed:
            continue
        parts.append(f"{k} = :{k}")
        params[k] = v
    if not parts:
        return None
    res = db.execute(
        text(
            f"UPDATE obs_academic_profiles SET {', '.join(parts)} WHERE user_id = :uid"
        ),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    row = (
        db.execute(
            text(
                """
                SELECT ap.id, ap.user_id, ap.staff_number, ap.title, ap.department_id,
                       ap.office, ap.phone, ap.created_at
                FROM obs_academic_profiles ap WHERE ap.user_id = :uid
                """
            ),
            {"uid": user_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return {
        "id": _str_id(row.get("id")),
        "user_id": _str_id(row.get("user_id")),
        "staff_number": row.get("staff_number") or "",
        "title": row.get("title") or "",
        "department_id": _str_id(row.get("department_id")),
        "office": row.get("office") or "",
        "phone": row.get("phone") or "",
        "created_at": (
            row.get("created_at").isoformat() if row.get("created_at") else None
        ),
    }


def admin_delete_academic_profile_by_user_id(
    db: Session, user_id: str
) -> tuple[bool, str]:
    apid = resolve_academic_profile_id(db, user_id)
    if not apid:
        return False, "not_found"
    n = int(
        db.execute(
            text(
                "SELECT COUNT(*) FROM obs_course_sections WHERE instructor_id = :id"
            ),
            {"id": apid},
        ).scalar()
        or 0
    )
    if n > 0:
        return False, "in_use"
    res = db.execute(
        text("DELETE FROM obs_academic_profiles WHERE user_id = :uid"),
        {"uid": user_id},
    )
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


def admin_update_student_profile_by_user_id(
    db: Session, user_id: str, updates: dict[str, Any]
) -> Optional[dict[str, Any]]:
    allowed = {
        "student_number",
        "department_id",
        "enrollment_date",
        "class_year",
        "program",
        "gpa",
        "completed_akts",
        "total_akts_required",
        "status",
        "is_financially_eligible",
        "phone",
        "address",
        "emergency_contact",
        "emergency_phone",
        "program_semester_number",
    }
    parts: list[str] = []
    params: dict[str, Any] = {"uid": user_id}
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "enrollment_date":
            parts.append("enrollment_date = CAST(:enrollment_date AS date)")
            params["enrollment_date"] = v if v not in (None, "") else None
        else:
            parts.append(f"{k} = :{k}")
            params[k] = v
    if not parts:
        return None
    parts.append("updated_at = NOW()")
    res = db.execute(
        text(
            f"UPDATE obs_student_profiles SET {', '.join(parts)} WHERE user_id = :uid"
        ),
        params,
    )
    db.commit()
    if res.rowcount == 0:
        return None
    row = (
        db.execute(
            text("SELECT id, user_id, student_number, department_id FROM obs_student_profiles WHERE user_id = :uid"),
            {"uid": user_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return {
        "id": _str_id(row.get("id")),
        "user_id": _str_id(row.get("user_id")),
        "student_number": row.get("student_number") or "",
        "department_id": _str_id(row.get("department_id")),
    }


def _obs_opt_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _obs_opt_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _obs_parse_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def ensure_mirror_openwebui_user_row(
    obs_db: Session,
    *,
    user_id: str,
    email: str,
    name: str,
    role: str,
    profile_image_url: Optional[str] = None,
) -> None:
    """
    OBS_DATABASE_URL ana DATABASE_URL'den farklıysa obs_* FK'ları \"user\".id ile bağlanır;
    yeni WebUI kullanıcısı yalnızca ana DB'de olduğundan burada satır yoksa minimal INSERT yapılır.
    """
    from time import time as wall_time

    import logging

    from open_webui.internal.obs_db import OBS_USES_PRIMARY_DATABASE

    log = logging.getLogger(__name__)
    if OBS_USES_PRIMARY_DATABASE:
        return

    hit = obs_db.execute(
        text(f"SELECT 1 FROM {USER_TBL} WHERE id = :id LIMIT 1"),
        {"id": user_id},
    ).first()
    if hit:
        return

    now_ts = int(wall_time())
    img = (profile_image_url or "").strip() or "/user.png"
    obs_db.execute(
        text(
            f"""
            INSERT INTO {USER_TBL} (
                id, email, role, name, profile_image_url,
                created_at, updated_at, last_active_at
            ) VALUES (
                :id, :email, :role, :name, :img,
                :ca, :ua, :la
            )
            """
        ),
        {
            "id": user_id,
            "email": email,
            "role": role,
            "name": name,
            "img": img,
            "ca": now_ts,
            "ua": now_ts,
            "la": now_ts,
        },
    )
    obs_db.commit()
    log.info(
        'OBS ayrı DB: "user" satırı yansıtıldı (user_id=%s)',
        user_id,
    )


def admin_insert_student_profile(
    db: Session,
    user_id: str,
    data: dict[str, Any],
) -> str:
    """
    obs_student_profiles için ilk kayıt. Zaten varsa mevcut id döner (idempotent).
    """
    existing = resolve_student_profile_id(db, user_id)
    if existing:
        return existing

    sn = _obs_opt_str(data.get("student_number"))
    did = _obs_opt_str(data.get("department_id"))
    if not sn or not did:
        raise ValueError("Öğrenci için öğrenci numarası ve bölüm (department_id) zorunludur.")

    pid = str(uuid.uuid4())
    enrollment_date = _obs_parse_date(data.get("enrollment_date"))
    birth_date = _obs_parse_date(data.get("birth_date"))

    cy = int(data.get("class_year") or 1)
    try:
        cy = max(1, min(20, cy))
    except (TypeError, ValueError):
        cy = 1

    gpa = float(data.get("gpa") or 0)
    cakts = int(data.get("completed_akts") or 0)
    takts = int(data.get("total_akts_required") or 240)
    st = _obs_opt_str(data.get("status")) or "active"
    ife = bool(data.get("is_financially_eligible", True))
    prog = _obs_opt_str(data.get("program")) or "Lisans"
    psn = int(data.get("program_semester_number") or 1)
    try:
        psn = max(1, min(40, psn))
    except (TypeError, ValueError):
        psn = 1

    hsy = _obs_opt_int(data.get("high_school_graduation_year"))

    db.execute(
        text(
            """
            INSERT INTO obs_student_profiles (
                id, user_id, student_number, department_id, enrollment_date, class_year, program,
                gpa, completed_akts, total_akts_required, status, is_financially_eligible,
                phone, address, emergency_contact, emergency_phone, tc_kimlik_no,
                created_at, updated_at, birth_date, birth_place, nationality,
                mother_name, father_name, high_school_name, high_school_graduation_year,
                program_semester_number
            ) VALUES (
                :id, :uid, :sn, :did, CAST(:ed AS date), :cy, :prog,
                :gpa, :cakts, :takts, :st, :ife,
                :phone, :addr, :ec, :ep, :tc,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CAST(:bd AS date),
                :bp, :nat, :mn, :fn, :hsn, :hsy, :psn
            )
            """
        ),
        {
            "id": pid,
            "uid": user_id,
            "sn": sn,
            "did": did,
            "ed": enrollment_date,
            "cy": cy,
            "prog": prog,
            "gpa": gpa,
            "cakts": cakts,
            "takts": takts,
            "st": st,
            "ife": ife,
            "phone": _obs_opt_str(data.get("phone")),
            "addr": _obs_opt_str(data.get("address")),
            "ec": _obs_opt_str(data.get("emergency_contact")),
            "ep": _obs_opt_str(data.get("emergency_phone")),
            "tc": _obs_opt_str(data.get("tc_kimlik_no")),
            "bd": birth_date,
            "bp": _obs_opt_str(data.get("birth_place")),
            "nat": _obs_opt_str(data.get("nationality")),
            "mn": _obs_opt_str(data.get("mother_name")),
            "fn": _obs_opt_str(data.get("father_name")),
            "hsn": _obs_opt_str(data.get("high_school_name")),
            "hsy": hsy,
            "psn": psn,
        },
    )
    db.commit()
    return pid


def admin_insert_academic_profile(
    db: Session,
    user_id: str,
    data: dict[str, Any],
) -> str:
    """obs_academic_profiles ilk kayıt; kayıt varsa mevcut id döner."""
    existing = resolve_academic_profile_id(db, user_id)
    if existing:
        return existing

    did = _obs_opt_str(data.get("department_id"))
    if not did:
        raise ValueError("Akademisyen için bölüm (department_id) zorunludur.")

    aid = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO obs_academic_profiles (
                id, user_id, staff_number, title, department_id, office, phone, created_at
            ) VALUES (
                :id, :uid, :staff, :title, :did, :office, :phone, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": aid,
            "uid": user_id,
            "staff": _obs_opt_str(data.get("staff_number")) or "",
            "title": _obs_opt_str(data.get("title")) or "",
            "did": did,
            "office": _obs_opt_str(data.get("office")) or "",
            "phone": _obs_opt_str(data.get("phone")) or "",
        },
    )
    db.commit()
    return aid


def admin_delete_student_profile_by_user_id(
    db: Session, user_id: str
) -> tuple[bool, str]:
    spid = resolve_student_profile_id(db, user_id)
    if not spid:
        return False, "not_found"
    n = int(
        db.execute(
            text("SELECT COUNT(*) FROM obs_course_enrollments WHERE student_id = :id"),
            {"id": spid},
        ).scalar()
        or 0
    )
    if n > 0:
        return False, "in_use"
    db.execute(
        text("DELETE FROM obs_student_advisors WHERE student_id = :id"),
        {"id": spid},
    )
    db.execute(
        text("DELETE FROM obs_document_requests WHERE student_id = :id"),
        {"id": spid},
    )
    res = db.execute(
        text("DELETE FROM obs_student_profiles WHERE id = :id"), {"id": spid}
    )
    db.commit()
    if res.rowcount and res.rowcount > 0:
        return True, ""
    return False, "not_found"


# ---------------------------------------------------------------------------
# Admin — Danışman Atama (obs_student_advisors)
# ---------------------------------------------------------------------------

def list_students_with_advisor(
    obs_db: Session,
    primary_db: Session,
    *,
    search: Optional[str] = None,
    department_id: Optional[str] = None,
    advisor_filter: Optional[str] = None,
    only_unassigned: bool = False,
) -> list[dict[str, Any]]:
    """Tüm öğrencileri ve aktif danışmanlarını döndürür.

    `obs_student_advisors` üzerinden `valid_to IS NULL OR valid_to >= CURRENT_DATE` olan
    en güncel kayıt aktif danışman olarak alınır. Ad/e-posta WebUI `user` tablosundan
    yüklenir. `advisor_filter` verilirse o danışman_user_id'sine atanmış öğrenciler
    döner. `only_unassigned=True` ise yalnızca aktif danışmanı olmayan öğrenciler.
    """
    from open_webui.models.users import User

    params: dict[str, Any] = {}
    where_parts: list[str] = ["1=1"]
    if department_id and str(department_id).strip():
        where_parts.append("sp.department_id = :did")
        params["did"] = str(department_id).strip()

    sql = f"""
        SELECT sp.id AS student_profile_id,
               sp.user_id,
               sp.student_number,
               sp.department_id,
               sp.class_year,
               sp.program,
               sp.gpa,
               sp.status,
               d.code AS department_code,
               d.name AS department_name,
               sa.id AS advisor_assignment_id,
               sa.advisor_id AS advisor_profile_id,
               sa.valid_from AS advisor_valid_from,
               sa.valid_to AS advisor_valid_to,
               ap.user_id AS advisor_user_id,
               ap.title AS advisor_title
        FROM obs_student_profiles sp
        LEFT JOIN obs_departments d ON sp.department_id = d.id
        LEFT JOIN LATERAL (
            SELECT sa.id, sa.advisor_id, sa.valid_from, sa.valid_to
            FROM obs_student_advisors sa
            WHERE sa.student_id = sp.id
              AND (sa.valid_to IS NULL OR sa.valid_to >= CURRENT_DATE)
            ORDER BY sa.valid_from DESC NULLS LAST, sa.id DESC
            LIMIT 1
        ) sa ON TRUE
        LEFT JOIN obs_academic_profiles ap ON sa.advisor_id = ap.id
        WHERE {" AND ".join(where_parts)}
        ORDER BY sp.student_number NULLS LAST, sp.id
        LIMIT 5000
        """

    bind = obs_db.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite LATERAL desteklemediği için yedek (sadece test/dev içindir).
        sql = f"""
            SELECT sp.id AS student_profile_id,
                   sp.user_id,
                   sp.student_number,
                   sp.department_id,
                   sp.class_year,
                   sp.program,
                   sp.gpa,
                   sp.status,
                   d.code AS department_code,
                   d.name AS department_name,
                   sa.id AS advisor_assignment_id,
                   sa.advisor_id AS advisor_profile_id,
                   sa.valid_from AS advisor_valid_from,
                   sa.valid_to AS advisor_valid_to,
                   ap.user_id AS advisor_user_id,
                   ap.title AS advisor_title
            FROM obs_student_profiles sp
            LEFT JOIN obs_departments d ON sp.department_id = d.id
            LEFT JOIN obs_student_advisors sa ON sa.student_id = sp.id
                 AND (sa.valid_to IS NULL OR sa.valid_to >= CURRENT_DATE)
            LEFT JOIN obs_academic_profiles ap ON sa.advisor_id = ap.id
            WHERE {" AND ".join(where_parts)}
            ORDER BY sp.student_number, sp.id
            LIMIT 5000
            """

    rows = obs_db.execute(text(sql), params).mappings().all()

    # WebUI user tablosundan ad/e-posta ekle.
    student_uids: set[str] = set()
    advisor_uids: set[str] = set()
    for r in rows:
        sid = _str_id(r.get("user_id"))
        if sid:
            student_uids.add(sid)
        aid = _str_id(r.get("advisor_user_id"))
        if aid:
            advisor_uids.add(aid)

    user_lookup: dict[str, tuple[str, str]] = {}
    all_uids = list(student_uids | advisor_uids)
    if all_uids:
        for uid_row, nm, em in (
            primary_db.query(User.id, User.name, User.email)
            .filter(User.id.in_(all_uids))
            .all()
        ):
            user_lookup[str(uid_row)] = (nm or "", em or "")

    out: list[dict[str, Any]] = []
    s = (search or "").strip().lower()
    for r in rows:
        sid = _str_id(r.get("user_id")) or ""
        s_name, s_email = user_lookup.get(sid, ("", ""))
        adv_uid = _str_id(r.get("advisor_user_id")) or ""
        a_name, a_email = (
            user_lookup.get(adv_uid, ("", "")) if adv_uid else ("", "")
        )
        # Filtreler
        if advisor_filter and adv_uid != str(advisor_filter):
            continue
        if only_unassigned and adv_uid:
            continue
        if s:
            hay = " ".join(
                [
                    s_name.lower(),
                    s_email.lower(),
                    str(r.get("student_number") or "").lower(),
                ]
            )
            if s not in hay:
                continue
        out.append(
            {
                "student_profile_id": _str_id(r.get("student_profile_id")),
                "user_id": sid,
                "full_name": s_name,
                "email": s_email,
                "student_number": r.get("student_number") or "",
                "department_id": _str_id(r.get("department_id")),
                "department_code": r.get("department_code") or "",
                "department_name": r.get("department_name") or "",
                "class_year": int(r.get("class_year") or 0),
                "program": r.get("program") or "",
                "gpa": _num(r.get("gpa")) if r.get("gpa") is not None else None,
                "status": r.get("status") or "",
                "advisor_assignment_id": _str_id(r.get("advisor_assignment_id")),
                "advisor_profile_id": _str_id(r.get("advisor_profile_id")),
                "advisor_user_id": adv_uid,
                "advisor_full_name": a_name,
                "advisor_email": a_email,
                "advisor_title": r.get("advisor_title") or "",
                "advisor_valid_from": _fmt_date(r.get("advisor_valid_from")),
                "advisor_valid_to": _fmt_date(r.get("advisor_valid_to")),
            }
        )
    return out


def assign_student_advisor(
    obs_db: Session,
    student_user_id: str,
    advisor_user_id: Optional[str],
) -> tuple[bool, str]:
    """Öğrenciye danışman atar / değiştirir / kaldırır.

    `advisor_user_id` boş/None ise mevcut aktif danışmanlık kapatılır.
    Aktif kaydı kapatırken:
      - `valid_from = bugün` olan satırlar (gün içinde eklenip iptal edilenler) silinir
        — aksi halde `valid_to < valid_from` üreterek geçersiz aralık oluşur.
      - Diğer satırların `valid_to` değeri `dün` olarak işaretlenir, çünkü listeleme
        sorgusu (`get_advisor_api`, vs.) `valid_to >= CURRENT_DATE` kullanır ve
        bugünü hâlâ "aktif" sayar; "kaldır" sonucu hemen yansımaz.
    Akademisyenin obs_academic_profiles kaydı yoksa stub oluşturulur.
    """
    if not student_user_id:
        log.warning("[advisor-assign] missing_student")
        return False, "missing_student"
    spid = resolve_student_profile_id(obs_db, str(student_user_id).strip())
    if not spid:
        log.warning(
            "[advisor-assign] student_profile_not_found user_id=%s",
            student_user_id,
        )
        return False, "student_profile_not_found"

    target_apid: Optional[str] = None
    adv_uid_norm: Optional[str] = None
    if advisor_user_id and str(advisor_user_id).strip():
        adv_uid_norm = str(advisor_user_id).strip()
        target_apid = resolve_academic_profile_id(obs_db, adv_uid_norm)
        if not target_apid:
            try:
                target_apid = ensure_academic_profile_for_user(obs_db, adv_uid_norm)
            except ValueError:
                log.warning(
                    "[advisor-assign] advisor_no_department_for_stub adv_uid=%s",
                    adv_uid_norm,
                )
                return False, "advisor_no_department_for_stub"
            except Exception:
                log.exception(
                    "[advisor-assign] ensure_academic_profile_for_user failed adv_uid=%s",
                    adv_uid_norm,
                )
                return False, "advisor_profile_not_found"
        if not target_apid:
            return False, "advisor_profile_not_found"

    try:
        # Aynı kişi zaten aktifse no-op.
        if target_apid:
            existing = obs_db.execute(
                text(
                    """
                    SELECT id FROM obs_student_advisors
                    WHERE student_id = :sid AND advisor_id = :apid
                      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
                    LIMIT 1
                    """
                ),
                {"sid": spid, "apid": target_apid},
            ).first()
            if existing:
                log.info(
                    "[advisor-assign] noop already_active student_user_id=%s spid=%s adv_uid=%s apid=%s",
                    student_user_id,
                    spid,
                    adv_uid_norm,
                    target_apid,
                )
                return True, ""

        # 1) Bugün açılmış aktif satırları SİL (aksi halde valid_to<valid_from olur).
        del_res = obs_db.execute(
            text(
                """
                DELETE FROM obs_student_advisors
                WHERE student_id = :sid
                  AND valid_from = CURRENT_DATE
                  AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
                """
            ),
            {"sid": spid},
        )
        # 2) Önceki aktif satırların valid_to değerini DÜN olarak işaretle.
        upd_res = obs_db.execute(
            text(
                """
                UPDATE obs_student_advisors
                SET valid_to = CURRENT_DATE - INTERVAL '1 day'
                WHERE student_id = :sid
                  AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
                """
            ),
            {"sid": spid},
        )
        log.info(
            "[advisor-assign] closed previous student_user_id=%s spid=%s deleted=%s updated=%s",
            student_user_id,
            spid,
            getattr(del_res, "rowcount", None),
            getattr(upd_res, "rowcount", None),
        )

        if target_apid:
            new_id = str(uuid.uuid4())
            obs_db.execute(
                text(
                    """
                    INSERT INTO obs_student_advisors (
                        id, student_id, advisor_id, valid_from, valid_to
                    ) VALUES (
                        :id, :sid, :apid, CURRENT_DATE, NULL
                    )
                    """
                ),
                {
                    "id": new_id,
                    "sid": spid,
                    "apid": target_apid,
                },
            )
            log.info(
                "[advisor-assign] inserted new student_user_id=%s spid=%s adv_uid=%s apid=%s row_id=%s",
                student_user_id,
                spid,
                adv_uid_norm,
                target_apid,
                new_id,
            )
        else:
            log.info(
                "[advisor-assign] cleared advisor student_user_id=%s spid=%s",
                student_user_id,
                spid,
            )
        obs_db.commit()
        return True, ""
    except Exception as ex:
        try:
            obs_db.rollback()
        except Exception:
            pass
        log.exception(
            "[advisor-assign] db_error student_user_id=%s adv_uid=%s",
            student_user_id,
            adv_uid_norm,
        )
        return False, f"db_error: {ex}"


def bulk_assign_student_advisor(
    obs_db: Session,
    student_user_ids: list[str],
    advisor_user_id: Optional[str],
) -> dict[str, Any]:
    """Birden çok öğrenciye aynı danışmanı atar (veya advisor_user_id boşsa hepsini kaldırır)."""
    updated = 0
    failed: list[dict[str, str]] = []
    for sid in student_user_ids or []:
        ok, err = assign_student_advisor(obs_db, sid, advisor_user_id)
        if ok:
            updated += 1
        else:
            failed.append({"student_user_id": str(sid), "error": err})
    return {"updated": updated, "failed": failed}
