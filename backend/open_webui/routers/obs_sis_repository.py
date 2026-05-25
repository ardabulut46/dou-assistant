"""Mevcut PostgreSQL obs_* şeması için SIS sorguları (UUID FK'lar, user_id varchar)."""

from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional

from collections import defaultdict

from sqlalchemy import func, or_, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

USER_TBL = '"user"'


def _str_id(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)


def _coerce_db_bool_optional(v: Any) -> Optional[bool]:
    """``is_mandatory`` sütunu bazen PostgreSQL ``boolean``, bazen ``0``/``1`` (SMALLINT) olabilir."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    try:
        if isinstance(v, (int, float, Decimal)):
            i = int(v)
            if i == 1:
                return True
            if i == 0:
                return False
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        s = str(v).strip().lower()
        if s in {"1", "true", "t", "yes", "evet", "e"}:
            return True
        if s in {"0", "false", "f", "no", "hayır", "hayir", "", "n"}:
            return False
    return None


def _fold_tr_course_type_key(course_type: str) -> str:
    """Türk aksanı + boşluktan tek anahtar: ``seçmeli`` → ``secmeli``."""
    u = unicodedata.normalize("NFKC", (course_type or "").strip()).lower().replace(" ", "_")
    for a, b in (
        ("ş", "s"),
        ("ğ", "g"),
        ("ı", "i"),
        ("ö", "o"),
        ("ü", "u"),
        ("ç", "c"),
    ):
        u = u.replace(a, b)
    return u


def course_row_is_mandatory(is_mandatory_db: Any, course_type: Optional[str]) -> bool:
    """Kayıtta zorunlu sayılan ders mi; seçmeliler (teknik/sosyal/diğer) ayrı gösterilir.

    ``is_mandatory`` = 0 olsa bile ``type`` (Z, zorunlu, …) açıksa zorunlu kabul edilir — import/eski kayıtta
    kolon–metin uyumsuzluğu olunca açılan liste ile sepet aynı “Tür”ü göstersin."""
    imb = _coerce_db_bool_optional(is_mandatory_db)
    raw = _fold_tr_course_type_key(str(course_type) if course_type is not None else "")

    def type_says_mandatory() -> bool:
        if not raw:
            return False
        if raw == "z" or raw in ("zorunlu", "required", "mandatory"):
            return True
        if raw.startswith("zorunlu"):
            return True
        return False

    def type_says_elective() -> bool:
        if not raw:
            return False
        if raw == "s" or raw in ("secmeli", "elective"):
            return True
        if "secmeli" in raw or raw.endswith("_secmeli") or raw.startswith("elective"):
            return True
        return False

    if imb is True:
        return True
    if imb is False:
        if type_says_mandatory():
            return True
        return False
    if type_says_mandatory():
        return True
    if type_says_elective():
        return False
    return False


def _norm_term_date_iso(d: Any) -> Optional[str]:
    """Süre eşlemesi için yalın tarih anahtarı (NULL = henüz yok)."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    if isinstance(d, str) and len(d.strip()) >= 10:
        return d.strip()[:10]
    return None


def _norm_term_uuid_key(v: Any) -> str:
    return str(v or "").replace("{", "").replace("}", "").replace("-", "").lower()


def _norm_term_label(nm: Any) -> str:
    """Süre adı karşılaştırması: NFKC + casefold + boşluk sadeleştirme (Türkçe I/ı gibi farklar için .lower() yetmez)."""
    s = unicodedata.normalize("NFKC", str(nm or "")).strip().casefold()
    return " ".join(s.split()) if s else ""


def _norm_term_label_loose(nm: Any) -> str:
    """Unicode tire (en/em dash vb.) dahil süre görünür ad anahtarı — panel ile şube adı uyuşmazlığı."""
    base = _norm_term_label(nm)
    if not base:
        return ""
    for dash in ("\u2013", "\u2014", "\u2212", "\uff0d"):
        base = base.replace(dash, "-")
    return base


def candidate_term_ids_for_dropdown(db: Session, term_id: str) -> list[str]:
    """`/terms` seçili `obs_terms.id`'si için `obs_course_sections.term_id`'de görünebilecek tüm süre UUID'leri.

    Tekil PK kopyası, eski/import veri uyumsuzlukları ve boş tarih alanlarında ad tabanlı yedek eşlemeyi içerir."""
    raw = str(term_id or "").strip()
    if not raw:
        return []
    rows = (
        db.execute(text("SELECT id, name, start_date FROM obs_terms")).mappings().all()
    )
    sel = None
    rk = _norm_term_uuid_key(raw)
    for r in rows:
        rid = _str_id(r.get("id")) or ""
        if not rid:
            continue
        if rid == raw or _norm_term_uuid_key(rid) == rk:
            sel = r
            break
    if sel is None:
        log.warning(
            "[OBS] candidate_term_ids: obs_terms'te seçilen süre PK yok raw=%s | satır=%s",
            raw,
            len(rows),
        )
        return [raw]
    canon_lbl = _norm_term_label_loose(sel.get("name"))
    canon_sd = _norm_term_date_iso(sel.get("start_date"))
    strict: list[str] = []
    loose: list[str] = []
    for r in rows:
        rid = _str_id(r.get("id"))
        if not rid:
            continue
        lbl = _norm_term_label_loose(r.get("name"))
        if lbl != canon_lbl:
            continue
        loose.append(rid)
        sd = _norm_term_date_iso(r.get("start_date"))
        if sd == canon_sd or (canon_sd is None and sd is None):
            strict.append(rid)
    use = strict or loose or [_str_id(sel.get("id")) or raw]
    out: list[str] = []
    seen: set[str] = set()
    for x in use:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _candidate_term_ids_for_normalized_start_date(
    db: Session, target_iso: Optional[str]
) -> list[str]:
    """Tüm `obs_terms` içinde normalize edilmiş `start_date == target_iso` olan PK'lar."""
    if not target_iso:
        return []
    rows = db.execute(text("SELECT id, start_date FROM obs_terms")).mappings().all()
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if _norm_term_date_iso(r.get("start_date")) != target_iso:
            continue
        rid = _str_id(r.get("id")) or ""
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _candidate_term_ids_same_start_date_cohort(db: Session, term_id: str) -> list[str]:
    """Seçilen süre satırının `obs_terms.start_date` değeriyle aynı başlangıç tarihindeki süre PK'leri."""
    raw = str(term_id or "").strip()
    if not raw:
        return []
    sd = db.execute(
        text(
            """
            SELECT start_date FROM obs_terms
            WHERE LOWER(TRIM(CAST(id AS text))) = LOWER(TRIM(:tid))
            LIMIT 1
            """
        ),
        {"tid": raw},
    ).scalar()
    return _candidate_term_ids_for_normalized_start_date(db, _norm_term_date_iso(sd))


def candidate_term_ids_for_student_dropdown(
    db: Session, student_profile_id: Optional[str], term_id: str
) -> list[str]:
    """Süre filtresi: süre takvimi UUID öbeği + start_date kümesi + öğrencinin derslerinde çıkan tarih/ad yedekleri."""
    raw_tid = str(term_id or "").strip()
    lbl_row = db.execute(
        text(
            """
            SELECT name FROM obs_terms
            WHERE LOWER(TRIM(CAST(id AS text))) = LOWER(TRIM(:tid))
            LIMIT 1
            """
        ),
        {"tid": raw_tid},
    ).scalar()
    canon = _norm_term_label_loose(lbl_row or "") if lbl_row else ""

    chunks: list[str] = []
    chunks.extend(candidate_term_ids_for_dropdown(db, raw_tid))
    chunks.extend(_candidate_term_ids_same_start_date_cohort(db, raw_tid))

    # Dropdown satırındaki tarih yanlış/NULL olabilir: öğrencinin süre kayıtlarından tarih çıkar.
    if student_profile_id and canon:
        enrol_dates = db.execute(
            text(
                """
                SELECT DISTINCT ot.start_date AS sd, ot.name AS nm
                FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                LEFT JOIN obs_terms ot ON ot.id = cs.term_id
                WHERE ce.student_id = :spid
                """
            ),
            {"spid": student_profile_id},
        ).mappings().all()
        sd_used: set[str] = set()
        for er in enrol_dates:
            if _norm_term_label_loose(er.get("nm")) != canon:
                continue
            dsi = _norm_term_date_iso(er.get("sd"))
            if not dsi or dsi in sd_used:
                continue
            sd_used.add(dsi)
            chunks.extend(_candidate_term_ids_for_normalized_start_date(db, dsi))

    merged: list[str] = []
    seen_m: set[str] = set()
    for x in chunks:
        sx = str(x).strip()
        if sx and sx not in seen_m:
            seen_m.add(sx)
            merged.append(sx)

    if not student_profile_id or not canon:
        return merged

    extra_rows = db.execute(
        text(
            """
            SELECT DISTINCT cs.term_id AS tid, ot.name AS nm
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            LEFT JOIN obs_terms ot ON ot.id = cs.term_id
            WHERE ce.student_id = :spid
            """
        ),
        {"spid": student_profile_id},
    ).mappings().all()
    out = [*merged]
    for er in extra_rows:
        if _norm_term_label_loose(er.get("nm")) != canon:
            continue
        tid = _str_id(er.get("tid"))
        if tid and tid not in seen_m:
            seen_m.add(tid)
            out.append(tid)
    return out


def _sql_cs_term_id_in_bindings(candidates: list[str]) -> tuple[str, dict[str, Any]]:
    """`cs.term_id IN (...)`."""
    if not candidates:
        return "", {}
    binds: dict[str, Any] = {}
    ph: list[str] = []
    for i, c in enumerate(candidates):
        key = f"tcand{i}"
        binds[key] = c
        ph.append(f":{key}")
    return " AND cs.term_id IN (" + ",".join(ph) + ")", binds


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


def _canonical_half_from_program_semester(ps: int) -> tuple[int, int]:
    """Klasik 4×2 program için (sınıf, yıl‑içi yarıyıl 1‑2).

    Ör. PS 1 → (1,1), …, PS 8 → (4,2). Veritabanındaki ``sinif`` / ``yariyil`` grupla sorgunuza karşılık gelir."""

    try:
        p = int(ps)
    except (TypeError, ValueError):
        p = 1
    p = max(1, min(128, p))
    idx0 = p - 1
    cy = idx0 // 2 + 1
    hn = idx0 % 2 + 1
    return (cy, hn)


def _catalog_row_labels_tr(
    eff_program_sem_ix: Optional[int],
    semester_no_any: Any,
    class_year_any: Any,
) -> tuple[str, str]:
    """Katalog/liste tablolarında sınıf ve Güz/Bahar sütunları."""

    clab_main = ""
    halb_main = ""
    if eff_program_sem_ix is not None:
        try:
            ps = max(1, int(eff_program_sem_ix))
            cn_cy, cn_hf = _canonical_half_from_program_semester(ps)
            clab_main = f"{int(cn_cy)}. sınıf"
            halb_main = "Güz" if int(cn_hf) == 1 else "Bahar"
        except (TypeError, ValueError):
            clab_main, halb_main = "", ""

    if not clab_main:
        try:
            cy = int(class_year_any or 0)
            clab_main = f"{cy}. sınıf" if cy >= 1 else "—"
        except (TypeError, ValueError):
            clab_main = "—"
    hf_l = "—"
    try:
        sn = int(semester_no_any)
        if sn == 1:
            hf_l = "Güz"
        elif sn == 2:
            hf_l = "Bahar"
    except (TypeError, ValueError):
        pass
    if not halb_main or halb_main == "—":
        halb_main = hf_l
    return clab_main, halb_main


def _course_placement_visible_for_student(
    student_dept_id: Optional[str],
    student_program_semester: int,
    course_dept_id: Optional[str],
    curriculum_semester: Any,
    semester_no: Any,
    class_year: Any,
) -> bool:
    """Bölüm eşiti + kart (program yılı) süzümü.

    ``_effective_course_program_semester_index`` öğrenci ``program_semester_number`` ile
    uyuyorsa kabul edilir.

    Ek olarak kolon uyumsuzluğunda ``class_year`` + ``semester_no`` (klasik 1–4 sınıf, 1–2 yarıyıl)
    öğrencinin program yarıyılına karşı düşüyorsa müfredat satırı rakamı yüzünden süzülmez.
    İndeks üretilemiyorsa yalnızca bu klasik ikili kullanılır.
    """

    if not student_dept_id or not course_dept_id:
        return True
    if str(student_dept_id) != str(course_dept_id):
        return False
    try:
        stud_ps_i = max(1, int(student_program_semester))
    except (TypeError, ValueError):
        stud_ps_i = 1

    canon_cy, canon_sn_half = _canonical_half_from_program_semester(stud_ps_i)

    try:
        ccy = int(class_year or 0)
    except (TypeError, ValueError):
        ccy = 0
    csn_int: Optional[int] = None
    if semester_no is not None:
        try:
            n = int(semester_no)
            if n >= 1:
                csn_int = n
        except (TypeError, ValueError):
            csn_int = None

    eff = _effective_course_program_semester_index(
        curriculum_semester, semester_no, class_year
    )
    canonical_ok = False
    if ccy >= 1 and csn_int is not None and 1 <= csn_int <= 2:
        canonical_ok = (ccy, csn_int) == (canon_cy, canon_sn_half)

    if eff is not None and eff == stud_ps_i:
        return True
    # Katalogda ``curriculum_semester`` rakamı yanlış/çakışılı dolduysa tek başına filtreyi koparır;
    # ``class_year`` + ``semester_no`` ikilisi kullanıcı yarıyılıyla örtüşüyorsa yine uygun say.
    if canonical_ok:
        return True

    if eff is not None:
        return False
    return False


def _effective_course_program_semester_index(
    curriculum_semester: Any,
    semester_no: Any,
    class_year: Any,
) -> Optional[int]:
    """Ders kartının program yarıyılı indeksi (1‑taban) — şube listesi süzgeci için.

    ``curriculum_semester`` ile ``semester_no`` çakışırsa (eski/yanlış etiket), müfredat satırı
    olarak ``semester_no`` alınır.
    """
    v_cur: Optional[int] = None
    if curriculum_semester is not None:
        try:
            n = int(curriculum_semester)
            if n >= 1:
                v_cur = n
        except (TypeError, ValueError):
            pass
    v_sem: Optional[int] = None
    if semester_no is not None:
        try:
            n = int(semester_no)
            if n >= 1:
                v_sem = n
        except (TypeError, ValueError):
            pass
    if v_cur is not None and v_sem is not None and v_cur != v_sem:
        return v_sem
    if v_cur is not None:
        return v_cur
    if v_sem is not None:
        return v_sem
    return _course_semester_index(class_year, None)


def _catalog_display_program_semester_index(
    curriculum_semester: Any,
    semester_no: Any,
    class_year: Any,
) -> Optional[int]:
    """Tablo «Sınıf / Yarıyıl» için indeks: önce ``_course_semester_index`` (`registration_priority_tier` ile aynı mantık), eksiklerde etkin indeks."""

    idx = _course_semester_index(class_year, curriculum_semester)
    if idx is not None:
        return idx
    return _effective_course_program_semester_index(
        curriculum_semester, semester_no, class_year
    )


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


def _row_letter_grade_is_pass(lg_raw: Optional[Any]) -> bool:
    """Transkript/AGNO ile uyumlu: harfi 4'lük puana çevrilebiyorsa ve ≥ 2.0 ise başarılı say."""
    lg = (str(lg_raw).strip() if lg_raw is not None else "") or ""
    if not lg:
        return False
    pt = letter_to_point(lg)
    return pt is not None and pt >= 2.0


def has_passing_grade_for_course(
    db: Session, student_profile_id: str, course_id: str
) -> bool:
    """Öğrencinin bu ``course_id`` için transkripte giren başarılı (≥CB) kaydı var mı."""
    rows = db.execute(
        text(
            f"""
            SELECT TRIM(BOTH FROM g.letter_grade) AS letter_grade
            {_OBS_AGNO_ELIGIBLE_FROM}
              AND cs.course_id = :cid
            """
        ),
        {"spid": student_profile_id, "cid": course_id},
    ).fetchall()
    for (lg_raw,) in rows:
        if _row_letter_grade_is_pass(lg_raw):
            return True
    return False


def has_passing_grade_for_course_code_in_department(
    db: Session, student_profile_id: str, department_id: str, course_code: str
) -> bool:
    """Aynı kodlu eski/tekrar ``obs_courses`` satırından geçmişte geçilmişse müfredat deliği oluşmasın."""
    cc = (course_code or "").strip()
    if not cc or not department_id:
        return False
    rows = db.execute(
        text(
            f"""
            SELECT TRIM(BOTH FROM g.letter_grade) AS letter_grade
            {_OBS_AGNO_ELIGIBLE_FROM}
              AND CAST(c.department_id AS TEXT) = CAST(:did AS TEXT)
              AND TRIM(BOTH FROM COALESCE(c.code, '')) = TRIM(BOTH FROM :cc)
            """
        ),
        {"spid": student_profile_id, "did": department_id, "cc": cc},
    ).fetchall()
    for (lg_raw,) in rows:
        if _row_letter_grade_is_pass(lg_raw):
            return True
    return False


def student_dept_and_program_semester(
    db: Session, student_profile_id: str
) -> tuple[Optional[str], int]:
    row = (
        db.execute(
            text("SELECT department_id FROM obs_student_profiles WHERE id = :id LIMIT 1"),
            {"id": student_profile_id},
        )
        .mappings()
        .first()
    )
    did = _str_id(row.get("department_id")) if row else None
    psn = student_program_semester_number(db, student_profile_id)
    return (did if did else None, psn)


def student_term_enrolled_course_ids(
    db: Session, student_profile_id: str, term_id: str
) -> set[str]:
    if not student_profile_id or not term_id:
        return set()
    rows = (
        db.execute(
            text("""
            SELECT DISTINCT cs.course_id::text AS cid
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND ce.status IN ('active', 'pending', 'draft', 'pending_drop')
            """),
            {"spid": student_profile_id, "tid": term_id},
        )
        .fetchall()
    )
    return {str(r[0]) for r in rows if r and r[0]}


def mandatory_course_ids_program_semester(
    db: Session, department_id: str, program_semester: int
) -> set[str]:
    """Öğrencinin kartı ile aynı ``(class_year, semester_no)`` (veya yedek kümülatif konum) olan zorunlular."""

    ps = max(1, int(program_semester))
    rows = (
        db.execute(
            text(
                """
            SELECT id, COALESCE(type, '') AS ctype, is_mandatory,
                   curriculum_semester, semester_no, class_year
            FROM obs_courses
            WHERE CAST(department_id AS text) = CAST(:did AS text)
            """
            ),
            {"did": department_id},
        )
        .mappings()
        .all()
    )
    out: set[str] = set()
    for r in rows:
        cid = _str_id(r.get("id"))
        if not cid:
            continue
        if not course_row_is_mandatory(r.get("is_mandatory"), str(r.get("ctype") or "")):
            continue
        if _course_placement_visible_for_student(
            department_id,
            ps,
            department_id,
            r.get("curriculum_semester"),
            r.get("semester_no"),
            r.get("class_year"),
        ):
            out.add(cid)
    return out


def _course_matches_student_program_semester_card(
    stud_dept_id: Optional[str],
    program_semester: int,
    course_department_id: Optional[str],
    curriculum_semester: Any,
    semester_no: Any,
    class_year: Any,
    is_mandatory: Any,
    course_type: Optional[str],
    *,
    listing_mode: str = "registration",
) -> bool:
    _ = listing_mode, is_mandatory, course_type
    return _course_placement_visible_for_student(
        stud_dept_id,
        program_semester,
        course_department_id,
        curriculum_semester,
        semester_no,
        class_year,
    )


OBS_MANDATORY_PLAN_DENIED_MSG_TR = (
    "Döneminize göre bu zorunlu dersleri almanız gerekmektedir."
)


def planned_course_ids_for_mandatory_gate_submit(
    db: Session,
    student_profile_id: str,
    term_id: str,
    *,
    flow: str,
    enrollment_ids_to_drop: Optional[list[str]] = None,
) -> set[str]:
    """Danışman onayına göndermeden önce: bu dönemin planında hangi ``course_id``'ler yer alıyor.

    ``registration``: taslak (kayıt) + henüz bırakılmayan aktif/onay bekleyen satırlar (ekle‑bırak taslakları hariç).
    ``add_drop``: bırakma listesinden çıkarılmış aktifler + ``add_drop`` taslakları; ``pending_drop`` sayılmaz."""

    tid = str(term_id or "").strip()
    raw_flow = flow if flow in ("registration", "add_drop") else "registration"
    drop_set = {
        str(x).strip().lower().replace("{", "").replace("}", "").replace("-", "")
        for x in (enrollment_ids_to_drop or [])
        if str(x).strip()
    }

    rows = (
        db.execute(
            text(
                """
                SELECT cs.course_id::text AS cid, ce.status AS st,
                       COALESCE(ce.enrollment_reason, '') AS enr_reason,
                       LOWER(TRIM(BOTH FROM ce.id::text)) AS eid
                FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                WHERE ce.student_id = :spid
                  AND LOWER(TRIM(BOTH FROM cs.term_id::text)) = LOWER(TRIM(BOTH FROM :tid))
                """
            ),
            {"spid": student_profile_id, "tid": tid},
        )
        .mappings()
        .all()
    )
    out: set[str] = set()
    for r in rows:
        st_raw = str(r.get("st") or "").strip().lower()
        cid_raw = _str_id(r.get("cid"))
        if not cid_raw:
            continue
        er = str(r.get("enr_reason") or "").strip().lower()
        eid = str(r.get("eid") or "").strip()

        def _nid(s: str) -> str:
            return s.lower().replace("{", "").replace("}", "").replace("-", "")

        eid_cmp = _nid(eid) if eid else ""

        if st_raw == "dropped":
            continue
        if st_raw == "pending_drop":
            continue
        if st_raw == "active" and eid_cmp and eid_cmp in drop_set:
            continue

        if raw_flow == "registration":
            if st_raw == "draft" and er in ("", "registration"):
                out.add(cid_raw)
                continue
            if st_raw in ("active", "pending") and er != "add_drop":
                out.add(cid_raw)
        else:
            if st_raw == "active":
                out.add(cid_raw)
            elif st_raw == "draft" and er == "add_drop":
                out.add(cid_raw)
            elif st_raw == "pending" and er == "add_drop":
                out.add(cid_raw)
    return out


def mandate_backlog_remaining(
    db: Session,
    student_profile_id: str,
    department_id: str,
    program_semester: int,
    planned_course_ids: set[str],
) -> tuple[bool, list[dict[str, Any]]]:
    """Tek program yarıyılı kartına ait zorunlulardan eksikler (önceki yarıyıl kümülasyonu yok)."""

    ps = max(1, int(program_semester))
    mids = mandatory_course_ids_program_semester(db, department_id, ps)
    curriculum_slot_by_cid: dict[str, int] = {cid: ps for cid in mids}
    holes: list[dict[str, Any]] = []
    for cid in mids:
        if cid in planned_course_ids:
            continue
        if has_passing_grade_for_course(db, student_profile_id, cid):
            continue
        row = (
            db.execute(
                text(
                    "SELECT code, name, akts, curriculum_semester, semester_no, class_year "
                    "FROM obs_courses WHERE id::text = :id LIMIT 1"
                ),
                {"id": cid},
            )
            .mappings()
            .first()
        )
        if not row:
            continue
        cc_key = str(row.get("code") or "").strip()
        if cc_key and has_passing_grade_for_course_code_in_department(
            db, student_profile_id, department_id, cc_key
        ):
            continue
        eff_cs = _effective_course_program_semester_index(
            row.get("curriculum_semester"),
            row.get("semester_no"),
            row.get("class_year"),
        )
        if eff_cs is None:
            eff_cs = curriculum_slot_by_cid.get(cid)
        if eff_cs is None:
            eff_cs = ps
        holes.append(
            {
                "course_id": cid,
                "course_code": row.get("code") or "",
                "course_name": row.get("name") or "",
                "akts": int(row.get("akts") or 0),
                "curriculum_semester": eff_cs,
            }
        )
    holes.sort(key=lambda x: (x.get("course_code") or ""))
    return bool(holes), holes


def registration_is_elective_style_add_for_gate(
    db: Session,
    student_profile_id: str,
    department_id: Optional[str],
    program_semester: int,
    course_id: str,
) -> bool:
    """True ise 'önce müfredat zorunlularını bu dönem planla' seçmeli kapısı uygulanır."""
    if not department_id:
        return False
    mids = mandatory_course_ids_program_semester(db, department_id, program_semester)
    if course_id not in mids:
        return True
    # Aynı yarıyıl zorunlusunu daha önce geçtiyse (veya yazılımla tekrar) kapı seçmeli gibidir
    return bool(has_passing_grade_for_course(db, student_profile_id, course_id))


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
        return False, "Aktif dönem zorunlu dersleri bırakılamaz."
    stud_sem = student_program_semester_number(db, student_profile_id)
    csem = _course_semester_index(cy, csem_raw)
    prior_n = _prior_enrollment_count_same_course(
        db, student_profile_id, cid, enrollment_id
    )
    if csem is not None and csem < stud_sem and prior_n == 0:
        return (False, "Aktif dönem zorunlu dersleri bırakılamaz.")
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
            return 2, "Zorunlu dönem dersi (henüz geçilmemiş)"
        if csem == stud_sem:
            return 3, "Kendi yarıyılı dersi"
        return 4, "Üst yarıyıl dersi"
    try:
        cy_i = int(cy or 0)
        st_year = max(1, (stud_sem + 1) // 2)
    except (TypeError, ValueError):
        cy_i, st_year = 0, 1
    if cy_i > 0 and cy_i < st_year and not passed:
        return 2, "Zorunlu dönem dersi (henüz geçilmemiş)"
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
    # Ders çakışma kontrolü devre dışı bırakıldı (kullanıcı talebi)
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
    """Aynı `user_id` ile birden fazla kartta en mantıklı `obs_student_profiles.id`.

    Öncelik: öğrenci numarası (`student_number`) dolu satır → daha çok OBS kaydı
    (enrollment) → `updated_at` / `created_at` / PK.
    """
    row = db.execute(
        text(
            """
            SELECT sp.id
            FROM obs_student_profiles sp
            WHERE sp.user_id = :u
            ORDER BY
                CASE
                    WHEN length(trim(coalesce(CAST(sp.student_number AS TEXT), ''))) > 0
                    THEN 1 ELSE 0
                END DESC,
                (
                    SELECT COUNT(*) FROM obs_course_enrollments ce
                    WHERE ce.student_id = sp.id
                ) DESC,
                sp.updated_at DESC NULLS LAST,
                sp.created_at DESC NULLS LAST,
                sp.id DESC
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
                id, user_id, staff_number, title, department_id, office, phone,
                consulting_hours, created_at
            ) VALUES (
                :id, :uid, '', '', :did, '', '', '', CURRENT_TIMESTAMP
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
    """`/me/profile` ile notların aynı `obs_student_profiles` satırını kullanması gerekir."""
    pid = resolve_student_profile_id(db, webui_user_id)
    if not pid:
        return None
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
        WHERE sp.id = :pid
        """),
            {"pid": pid},
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
               ap.department_id, d.name AS department_name, ap.office, ap.phone,
               ap.consulting_hours
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
        "consulting_hours": row.get("consulting_hours") or "",
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


def _registration_gate_effective_open(val: Any) -> bool:
    """Admin listesi ile uyum: `registration_open` yalnızca False ise kapalı (null dahil ≠ False → açık)."""
    return val is not False


def _add_drop_gate_effective_open(val: Any) -> bool:
    """Ekle–bırak: yönetimde yalnızca True iken «açık»."""
    return val is True


def _snapshot_term_registration_flags(
    db: Session, term_id: str
) -> Optional[dict[str, Any]]:
    row = (
        db.execute(
            text("""
                SELECT id, name, registration_open, add_drop_open,
                       registration_start, registration_end, add_drop_start, add_drop_end
                FROM obs_terms WHERE id = :tid LIMIT 1
                """),
            {"tid": term_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def _broadcast_messages_to_all_students(
    db: Session, sender_user_id: str, subject: str, body: str
) -> int:
    """obs_student_profiles.user_id için gelen kutusu mesajı; hatalı satırlar atlanır."""
    rows = (
        db.execute(
            text("""
                SELECT DISTINCT user_id FROM obs_student_profiles
                WHERE user_id IS NOT NULL AND LENGTH(TRIM(user_id)) > 0
                """)
        )
        .fetchall()
    )
    n_ok = 0
    for (uid,) in rows:
        u = _str_id(uid)
        if not u:
            continue
        try:
            insert_message(db, sender_user_id, u, subject, body)
            n_ok += 1
        except Exception:
            log.exception("[OBS] Toplu OBS mesajı gönderilemedi (alıcı=%s)", u[:12])
    log.info("[OBS] Dönem penceresi duyurusu gönderildi: %s öğrenci", n_ok)
    return n_ok


def _maybe_notify_registration_window_changes(
    db: Session,
    *,
    prev: Optional[dict[str, Any]],
    curr: Optional[dict[str, Any]],
    acting_user_id: Optional[str],
) -> None:
    if not acting_user_id or not prev or not curr:
        return
    tn = str(curr.get("name") or "").strip() or str(curr.get("id") or "")

    pr, cr = prev.get("registration_open"), curr.get("registration_open")
    p_reg = _registration_gate_effective_open(pr)
    c_reg = _registration_gate_effective_open(cr)

    pd, cd = prev.get("add_drop_open"), curr.get("add_drop_open")
    p_ad = _add_drop_gate_effective_open(pd)
    c_ad = _add_drop_gate_effective_open(cd)

    def rng(label: str, start: Any, end: Any) -> str:
        sa = _fmt_date(start) or "—"
        eb = _fmt_date(end) or "—"
        return f"Takvim ({label}): {sa} → {eb}\n"

    msgs: list[tuple[str, str]] = []
    if p_reg != c_reg:
        if c_reg:
            msgs.append(
                (
                    "[OBS] Ders kayıt penceresi açıldı",
                    f"{tn}\n\nDers Kayıt penceresi aktif oldu. OBS üzerinden ders seçebilirsiniz.\n"
                    "Sayfa: /obs/ogrenci/ders-kayit\n\n"
                    + rng(
                        "kayıt",
                        curr.get("registration_start"),
                        curr.get("registration_end"),
                    ),
                )
            )
        else:
            msgs.append(
                (
                    "[OBS] Ders kayıt penceresi kapatıldı",
                    f"{tn}\n\nDers Kayıt penceresi kapatıldı. Güncellenmiş bir liste "
                    "göndermediyseniz veya süre içinde işlem yapılmadıysa sistem yönetimiyle görüşün.\n\n"
                    + rng(
                        "kayıt",
                        curr.get("registration_start"),
                        curr.get("registration_end"),
                    ),
                )
            )

    if p_ad != c_ad:
        if c_ad:
            msgs.append(
                (
                    "[OBS] Ders ekle-bırak penceresi açıldı",
                    f"{tn}\n\nDers ekle / bırak dönemi aktif oldu.\nSayfa: /obs/ogrenci/ders-ekle-birak\n\n"
                    + rng(
                        "ekle-bırak",
                        curr.get("add_drop_start"),
                        curr.get("add_drop_end"),
                    ),
                )
            )
        else:
            msgs.append(
                (
                    "[OBS] Ders ekle-bırak penceresi kapatıldı",
                    f"{tn}\n\nDers ekle / bırak penceresi kapatıldı.\n\n"
                    + rng(
                        "ekle-bırak",
                        curr.get("add_drop_start"),
                        curr.get("add_drop_end"),
                    ),
                )
            )

    for subj, bod in msgs:
        _broadcast_messages_to_all_students(db, acting_user_id, subj, bod)


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
    *,
    include_completed_semesters: bool = False,
) -> tuple[Optional[str], list[dict[str, Any]]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, []
    allowed = {"draft", "pending", "pending_drop", "active", "dropped", "rejected"}
    if include_completed_semesters:
        status_clause = "(ce.status IS NULL OR ce.status NOT IN ('draft', 'rejected'))"
    else:
        st = tuple(s for s in (statuses or ("active",)) if s in allowed)
        if not st:
            st = ("active",)
        in_clause = ", ".join(f"'{x}'" for x in st)
        status_clause = f"ce.status IN ({in_clause})"
    q = f"""
        SELECT ce.id AS enrollment_id, ce.status, COALESCE(ce.enrollment_reason, '') AS enrollment_reason,
               c.id AS course_id, c.code AS course_code, c.name AS course_name, c.credits, c.akts,
               c.theory_hours, c.language, c.class_year,
               CAST(c.department_id AS TEXT) AS course_department_id,
               c.curriculum_semester, c.semester_no,
               c.type, c.is_mandatory,
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
        WHERE ce.student_id = :spid AND ({status_clause})
        """
    params: dict[str, Any] = {"spid": spid}
    if term_id:
        cand_ids = candidate_term_ids_for_student_dropdown(db, spid, term_id)
        tcl, binds = _sql_cs_term_id_in_bindings(cand_ids)
        q += tcl
        params.update(binds)
    rows = db.execute(text(q), params).mappings().all()
    stud_dept_ln, psn_ln = student_dept_and_program_semester(db, spid)
    out = []
    for r in rows:
        room = r.get("classroom_code") or r.get("classroom_name") or ""
        cid_en = _str_id(r.get("course_id"))
        ptier, _ = (
            registration_priority_tier(db, spid, cid_en) if cid_en else (3, "")
        )
        ct_raw = r.get("type") or ""
        im_raw = r.get("is_mandatory")
        cdid_ln = _str_id(r.get("course_department_id")) or ""
        slot_ok = True
        if stud_dept_ln and cdid_ln:
            slot_ok = _course_matches_student_program_semester_card(
                stud_dept_ln,
                psn_ln,
                cdid_ln,
                r.get("curriculum_semester"),
                r.get("semester_no"),
                r.get("class_year"),
                im_raw,
                str(ct_raw) if ct_raw else None,
                listing_mode="add_drop",
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
                "type": ct_raw,
                "is_mandatory_course": course_row_is_mandatory(im_raw, str(ct_raw) if ct_raw else None),
                "status": r.get("status") or "",
                "enrollment_reason": r.get("enrollment_reason") or "",
                "registration_priority_tier": ptier,
                "registration_priority_label": "",
                "add_drop_curriculum_slot_match": slot_ok,
            }
        )
    total_akts = sum(x["akts"] for x in out if x["status"] == "active")
    for x in out:
        x["_total_akts_computed"] = total_akts
    return spid, out


def schedule_from_enrollments(
    rows: list[dict[str, Any]],
    *,
    only_term_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    sched = []
    for r in rows:
        rtid = _str_id(r.get("term_id")) or ""
        if only_term_id and rtid != str(only_term_id):
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
        cand_ids = candidate_term_ids_for_student_dropdown(db, spid, term_id)
        tcl, binds = _sql_cs_term_id_in_bindings(cand_ids)
        q += tcl
        params.update(binds)
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


def _pg_norm_term_visible_name(col: str) -> str:
    """Python `_norm_term_label_loose` ile yakın: Unicode tireleri '-' yap, whitespace TOPARLA, küçült."""
    dash_chain = (
        f"REPLACE(REPLACE(REPLACE(REPLACE({col}::text, CHR(8211), '-'), "
        f"CHR(8212), '-'), CHR(8722), '-'), CHR(65293), '-')"
    )
    return (
        f"LOWER(TRIM(REGEXP_REPLACE({dash_chain}, '[[:space:]]+', ' ', 'g')))"
    )


def _sql_grade_term_equivalent_clause_postgresql() -> tuple[str, str]:
    """Seçilen süre ile aynı görünür adlı tüm `obs_terms` PK'leri (PG)."""
    a = _pg_norm_term_visible_name("ot2.name")
    b = _pg_norm_term_visible_name("sel.name")
    return (
        f"""
        AND cs.term_id IN (
            SELECT ot2.id
            FROM obs_terms ot2
            INNER JOIN obs_terms sel
                ON {a} = {b}
               AND sel.id = CAST(:grade_sel_term AS uuid)
        )
        """,
        "grade_sel_term",
    )


def list_student_grades(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> list[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return []
    # Ham SQL ile aynı: ce–cs–courses–terms–grade_entries zinciri (t.id = cs.term_id)
    q = """
        SELECT ce.id AS enrollment_id, c.code AS course_code, c.name AS course_name,
               cs.term_id, ot.name AS term_name,
               cs.midterm_weight_percent AS midterm_weight_percent,
               cs.final_weight_percent AS final_weight_percent,
               g.midterm, g.final, g.makeup, g.letter_grade, g.is_published, g.is_finalized
        FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        JOIN obs_terms ot ON ot.id = cs.term_id
        LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
        WHERE ce.student_id = :spid
        """
    bind = db.get_bind()
    params: dict[str, Any] = {"spid": spid}

    cand_for_log: Optional[list[str]] = None
    term_raw = str(term_id or "").strip()

    if term_raw:
        if bind.dialect.name == "postgresql":
            clause, pkey = _sql_grade_term_equivalent_clause_postgresql()
            q += clause
            params[pkey] = term_raw
        else:
            cand_for_log = candidate_term_ids_for_student_dropdown(db, spid, term_raw)
            tcl, binds = _sql_cs_term_id_in_bindings(cand_for_log)
            q += tcl
            params.update(binds)

    rows = db.execute(text(q), params).mappings().all()

    if term_raw and not rows and bind.dialect.name == "postgresql":
        cand_for_log = candidate_term_ids_for_student_dropdown(db, spid, term_raw)
        if cand_for_log:
            tcl_fb, binds_fb = _sql_cs_term_id_in_bindings(cand_for_log)
            q_fb = q.split("WHERE ce.student_id")[0]
            q_fb += """WHERE ce.student_id = :spid""" + tcl_fb
            fb_params: dict[str, Any] = {"spid": spid}
            fb_params.update(binds_fb)
            rows = db.execute(text(q_fb), fb_params).mappings().all()
            if rows:
                log.info(
                    "[OBS grades] süre görünür ad PG eşleşmesi boştu; UUID aday kümesi ile %s satır (spid=%s term_rq=%s)",
                    len(rows),
                    spid,
                    term_raw,
                )

    if term_raw and not rows:
        cand_for_log = cand_for_log or candidate_term_ids_for_student_dropdown(
            db, spid, term_raw
        )
        log.warning(
            "[OBS grades] sıfır satır | spid=%s term_rq=%s dialect=%s aday_UUID_n=%s aday_UUID=%s",
            spid,
            term_raw,
            getattr(bind.dialect, "name", "?"),
            len(cand_for_log or []),
            cand_for_log,
        )
    return [
        {
            "enrollment_id": _str_id(r["enrollment_id"]),
            "course_code": r.get("course_code") or "",
            "course_name": r.get("course_name") or "",
            "term_id": _str_id(r["term_id"]),
            "term_name": r.get("term_name") or "",
            "midterm_weight_percent": _mapping_weight_pct(
                r, "midterm_weight_percent", 40.0
            ),
            "final_weight_percent": _mapping_weight_pct(r, "final_weight_percent", 60.0),
            "midterm": _num(r.get("midterm")),
            "final": _num(r.get("final")),
            "makeup": _num(r.get("makeup")),
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
        # Yönerge: dönem N hafta ise en fazla %30 devamsızlık (yaklaşık floor(N*0.30) yoklama);
        # devam oranı %70 altı = risk (mevcut renk / ObsShell ile uyumlu).
        allowed_abs_30 = int(math.floor(float(tw) * 0.30 + 1e-9)) if tw > 0 else 0
        abs_over_30 = max(0, ab - allowed_abs_30)
        abs_remain_under_30 = max(0, allowed_abs_30 - ab)
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
                "allowed_absences_30pct": allowed_abs_30,
                "absences_over_30pct": abs_over_30,
                "absences_remain_under_30pct": abs_remain_under_30,
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
    db: Session,
    webui_user_id: str,
    term_id: Optional[str],
    *,
    listing_mode: str = "registration",
) -> tuple[Optional[str], list[dict[str, Any]], dict[str, Any]]:
    empty_meta: dict[str, Any] = {
        "program_semester_number": 1,
        "department_id": "",
        "curriculum_filter_active": False,
        "canonical_class_year": 1,
        "canonical_semester_half": 1,
    }
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, [], empty_meta
    stud_dept, psn_student = student_dept_and_program_semester(db, spid)
    tid = term_id
    if not tid:
        row = db.execute(
            text(
                "SELECT id FROM obs_terms WHERE is_active = true ORDER BY start_date DESC LIMIT 1"
            )
        ).first()
        tid = _str_id(row[0]) if row else None
    if listing_mode == "add_drop" and not tid:
        ccy_can, csn_half_can = _canonical_half_from_program_semester(int(psn_student))
        meta_side_early_nt = {
            "program_semester_number": int(psn_student),
            "department_id": stud_dept or "",
            "curriculum_filter_active": bool(stud_dept),
            "canonical_class_year": ccy_can,
            "canonical_semester_half": csn_half_can,
            "sections_in_terms_total": 0,
            "sections_query_rows_student": 0,
            "real_section_rows_emitted": 0,
            "offer_placeholder_rows": 0,
            "courses_pending_sections": [],
            "add_drop_sections_empty_hint": "Dönem seçilmemiş.",
            "registration_sections_empty_hint": "",
        }
        return None, [], meta_side_early_nt
    if listing_mode == "add_drop" and not stud_dept:
        ccy_can, csn_half_can = _canonical_half_from_program_semester(int(psn_student))
        meta_side_early = {
            "program_semester_number": int(psn_student),
            "department_id": "",
            "curriculum_filter_active": False,
            "canonical_class_year": ccy_can,
            "canonical_semester_half": csn_half_can,
            "sections_in_terms_total": 0,
            "sections_query_rows_student": 0,
            "real_section_rows_emitted": 0,
            "offer_placeholder_rows": 0,
            "courses_pending_sections": [],
            "add_drop_sections_empty_hint": "Öğrenci kaydına bölüm atanmamış; ders listesi oluşturulamıyor.",
            "registration_sections_empty_hint": "",
        }
        return tid, [], meta_side_early

    if listing_mode == "registration" and not stud_dept:
        ccy_can, csn_half_can = _canonical_half_from_program_semester(int(psn_student))
        meta_side_early_reg = {
            "program_semester_number": int(psn_student),
            "department_id": "",
            "curriculum_filter_active": False,
            "canonical_class_year": ccy_can,
            "canonical_semester_half": csn_half_can,
            "sections_in_terms_total": 0,
            "sections_query_rows_student": 0,
            "real_section_rows_emitted": 0,
            "offer_placeholder_rows": 0,
            "courses_pending_sections": [],
            "add_drop_sections_empty_hint": "",
            "registration_sections_empty_hint": (
                "Öğrenci kaydına bölüm atanmamış; ders listesi oluşturulamıyor."
            ),
        }
        return tid, [], meta_side_early_reg

    tcands_list: list[str] = []
    params: dict[str, Any] = {"spid": spid}
    # Kayıt + ekle-bırakta öğrenci bölümü ve dönem uygunsa liste ``obs_courses`` + LEFT JOIN şube:
    # katalog mantığı — şubesiz kodlar da tabloda satır olarak görünür.
    listing_catalog = False
    if tid:
        tcands_raw = candidate_term_ids_for_student_dropdown(db, spid, str(tid).strip())
        tcands_list = [_str_id(x) for x in (tcands_raw or []) if _str_id(x)]
        anchor = _str_id(tid)
        if anchor and anchor not in tcands_list:
            tcands_list.insert(0, anchor)
        if not tcands_list and anchor:
            tcands_list = [anchor]
        term_ph = ",".join(f":tsec{i}" for i in range(len(tcands_list)))
        for i, xid in enumerate(tcands_list):
            params[f"tsec{i}"] = xid

        listing_catalog = bool(
            listing_mode in ("add_drop", "registration") and bool(stud_dept)
        )

        if listing_catalog:
            # PostgreSQL: IN (('a','b')) bir satır (record) sayılır; IN ('a','b') olmalı.
            enr_clause = "'active', 'pending', 'draft', 'pending_drop'"
            q = f"""
        SELECT cs.id AS id,
               c.id AS course_id,
               CAST(c.department_id AS TEXT) AS course_department_id,
               c.code AS course_code,
               c.name AS course_name,
               c.credits,
               c.akts,
               c.class_year,
               c.curriculum_semester,
               c.semester_no,
               COALESCE(c.type, '') AS course_type,
               c.is_mandatory,
               cs.day_of_week,
               cs.start_time,
               cs.end_time,
               COALESCE(cs.capacity, 0) AS capacity,
               cr.code AS classroom_code,
               ins_u.name AS instructor_name,
               CASE WHEN cs.id IS NULL THEN 0 ELSE (
                   (SELECT COUNT(*) FROM obs_course_enrollments ce2
                    WHERE ce2.course_section_id = cs.id
                      AND ce2.status IN ({enr_clause})
                   )
               ) END AS enrolled
        FROM obs_courses c
        INNER JOIN obs_departments dep ON dep.id = c.department_id
        LEFT JOIN obs_course_sections cs
          ON cs.course_id = c.id
         AND cs.term_id IN ({term_ph})
         AND NOT EXISTS (
            SELECT 1 FROM obs_course_enrollments ce_own
            WHERE ce_own.course_section_id = cs.id
              AND ce_own.student_id = :spid
              AND ce_own.status IN ({enr_clause})
         )
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" ins_u ON ins_u.id = ap.user_id
        WHERE CAST(c.department_id AS TEXT) = CAST(:ad_student_dept AS TEXT)
          AND NOT EXISTS (
            SELECT 1 FROM obs_course_enrollments cex
            JOIN obs_course_sections csx ON cex.course_section_id = csx.id
            WHERE cex.student_id = :spid
              AND csx.course_id = c.id
              AND csx.term_id IN ({term_ph})
              AND cex.status IN ({enr_clause})
          )
        ORDER BY COALESCE(dep.name, ''),
                 c.class_year NULLS LAST,
                 c.semester_no NULLS LAST,
                 c.is_mandatory DESC NULLS LAST,
                 COALESCE(TRIM(BOTH FROM c.name), '')
        """
            params["ad_student_dept"] = stud_dept

    if not listing_catalog:
        q = """
        SELECT cs.id, c.id AS course_id,
               CAST(c.department_id AS TEXT) AS course_department_id,
               c.code AS course_code, c.name AS course_name,
               c.credits, c.akts, c.class_year, c.curriculum_semester, c.semester_no,
               COALESCE(c.type, '') AS course_type, c.is_mandatory,
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
        if tid:
            term_ph_l = ",".join(f":tsec{i}" for i in range(len(tcands_list)))
            q += f" AND cs.term_id IN ({term_ph_l})"
            q += f"""
        AND NOT EXISTS (
            SELECT 1 FROM obs_course_enrollments cex
            JOIN obs_course_sections csx ON cex.course_section_id = csx.id
            WHERE cex.student_id = :spid
              AND csx.course_id = c.id
              AND csx.term_id IN ({term_ph_l})
              AND cex.status IN ('active', 'pending', 'draft', 'pending_drop')
        )
        """

    sections_in_terms_total = 0
    if tcands_list:
        tcount_ph = ",".join(f":tcnt{i}" for i in range(len(tcands_list)))
        pb_cnt = {f"tcnt{i}": tcands_list[i] for i in range(len(tcands_list))}
        sections_in_terms_total = int(
            db.execute(
                text(
                    f"SELECT COUNT(*)::int FROM obs_course_sections cs "
                    f"WHERE cs.term_id IN ({tcount_ph})"
                ),
                pb_cnt,
            ).scalar()
            or 0
        )

    backlog_bypass_course_ids: set[str] = set()
    # Aynı ders kodu için birden fazla obs_courses.id satırı varsa mor liste bir id,
    # şube ise başka course_id kullanır; sırf id ile bypass boş kalır — kod kümesini de bağla.
    backlog_bypass_codes: set[str] = set()
    bl_rows_ad: list[dict[str, Any]] = []
    planned_union_ad: set[str] = set()
    if listing_mode in ("add_drop", "registration") and stud_dept and tid and spid:
        cand_for_plan = tcands_list if tcands_list else ([_str_id(tid)] if tid else [])
        for xterm in cand_for_plan:
            planned_union_ad.update(student_term_enrolled_course_ids(db, spid, xterm))
        _, bl_rows_ad = mandate_backlog_remaining(
            db, spid, stud_dept, psn_student, planned_union_ad
        )
        for br in bl_rows_ad:
            bci = _str_id(br.get("course_id"))
            if bci:
                backlog_bypass_course_ids.add(bci)
            bcod = str(br.get("course_code") or "").strip()
            if bcod:
                backlog_bypass_codes.add(bcod)

    # Öğrenci listesi sorgusu, aynı dönemde o dersten zaten kayıtlı/taaslak varsa TÜM şubeleri
    # dışarı atar; kümeği bu satırlardan doldurmak «şube yok» placeholder'ını yanlış tetikler.
    # Placeholder yalnızca seçilen süre öbeğinde gerçekten hiç şube satırı yoksa gösterilir.
    codes_with_section_in_sql_query: set[str] = set()
    if tcands_list:
        tcode_ph = ",".join(f":tccd{i}" for i in range(len(tcands_list)))
        pb_codes = {f"tccd{i}": tcands_list[i] for i in range(len(tcands_list))}
        if listing_mode in ("add_drop", "registration") and stud_dept:
            pb_codes["cc_dept_ad"] = stud_dept
        for cr in db.execute(
            text(
                f"""
                SELECT DISTINCT c.code AS course_code
                FROM obs_course_sections cs
                JOIN obs_courses c ON cs.course_id = c.id
                WHERE cs.term_id IN ({tcode_ph})
                  AND COALESCE(TRIM(c.code), '') <> ''
                  {"" if not (listing_mode in ("add_drop", "registration") and stud_dept) else "AND CAST(c.department_id AS TEXT) = CAST(:cc_dept_ad AS TEXT) "}
                """
            ),
            pb_codes,
        ).mappings().all():
            qccc = str(cr.get("course_code") or "").strip()
            if qccc:
                codes_with_section_in_sql_query.add(qccc)

    rows = db.execute(text(q), params).mappings().all()

    ccy_can, csn_half_can = _canonical_half_from_program_semester(int(psn_student))
    meta_side = {
        "program_semester_number": int(psn_student),
        "department_id": stud_dept or "",
        "curriculum_filter_active": bool(stud_dept),
        "canonical_class_year": ccy_can,
        "canonical_semester_half": csn_half_can,
    }

    n_raw = len(rows)
    n_drop_placement = 0
    n_bypass_kept = 0
    n_drop_pass_course = 0
    n_drop_pass_code_dept = 0
    sample_drop_placement: list[str] = []

    out = []
    for r in rows:
        cap = int(r.get("capacity") or 0)
        enr = int(r.get("enrolled") or 0)
        cid = _str_id(r.get("course_id"))
        cdept = _str_id(r.get("course_department_id"))
        cs_raw = r.get("curriculum_semester")
        ct_avail = r.get("course_type") or ""
        im_avail = r.get("is_mandatory")
        eff_cs_ix = _effective_course_program_semester_index(
            cs_raw, r.get("semester_no"), r.get("class_year")
        )
        cur_sem_disp: Optional[int] = eff_cs_ix

        placement_ok = listing_catalog or _course_placement_visible_for_student(
            stud_dept,
            psn_student,
            cdept,
            cs_raw,
            r.get("semester_no"),
            r.get("class_year"),
        )
        dept_ok_ad = True
        if stud_dept and cdept and str(stud_dept) != str(cdept):
            dept_ok_ad = False

        cc_list = (r.get("course_code") or "").strip()
        backlog_bypass = (
            listing_mode in ("add_drop", "registration")
            and dept_ok_ad
            and (
                ((bool(backlog_bypass_course_ids) and cid in backlog_bypass_course_ids))
                or (bool(backlog_bypass_codes) and bool(cc_list) and cc_list in backlog_bypass_codes)
            )
        )
        if not placement_ok:
            if backlog_bypass:
                n_bypass_kept += 1
            else:
                n_drop_placement += 1
                if len(sample_drop_placement) < 8 and cc_list:
                    eff = eff_cs_ix
                    sample_drop_placement.append(
                        f"{cc_list}(cy={r.get('class_year')} sn={r.get('semester_no')} "
                        f"cs={cs_raw} eff={eff} cdept={cdept})"
                    )
                continue

        man_flag = course_row_is_mandatory(
            im_avail, str(ct_avail) if ct_avail else None
        )
        if man_flag and cid:
            if has_passing_grade_for_course(db, spid, cid):
                n_drop_pass_course += 1
                continue
            if stud_dept and cc_list and has_passing_grade_for_course_code_in_department(
                db, spid, stud_dept, cc_list
            ):
                n_drop_pass_code_dept += 1
                continue

        ptier, _ = (
            registration_priority_tier(db, spid, cid) if cid else (3, "")
        )
        sec_id_here = _str_id(r.get("id"))
        no_section_catalog = bool(listing_catalog and not sec_id_here)
        plab_eff = "Şube yok" if no_section_catalog else ""
        catalog_ps_display = _catalog_display_program_semester_index(
            cs_raw, r.get("semester_no"), r.get("class_year")
        )
        cat_cls_tr, cat_half_tr = _catalog_row_labels_tr(
            catalog_ps_display,
            r.get("semester_no"),
            r.get("class_year"),
        )
        out.append(
            {
                "id": sec_id_here,
                "course_id": cid or "",
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "credits": int(r.get("credits") or 0),
                "akts": int(r.get("akts") or 0),
                "type": ct_avail,
                "curriculum_semester": cur_sem_disp,
                "is_mandatory_course": man_flag,
                "catalog_class_label": cat_cls_tr,
                "catalog_half_label": cat_half_tr,
                "instructor_name": r.get("instructor_name") or "",
                "day_of_week": normalize_weekday_tr(r.get("day_of_week")),
                "start_time": _fmt_time(r.get("start_time")),
                "end_time": _fmt_time(r.get("end_time")),
                "classroom": r.get("classroom_code") or "",
                "capacity": cap,
                "enrolled": enr,
                "registration_priority_tier": ptier,
                "registration_priority_label": plab_eff,
                **({"offer_placeholder": True} if no_section_catalog else {}),
            }
        )

    elective_slot_locked = bool(bl_rows_ad)
    if listing_mode in ("add_drop", "registration") and stud_dept and not listing_catalog:
        codes_seen_offer: set[str] = {(x.get("course_code") or "").strip() for x in out if x.get("course_code")}
        mids_ps = mandatory_course_ids_program_semester(db, stud_dept, psn_student)

        def _should_skip_prior_pass(cid_h: Optional[str], cc_plain: str, man_here: bool) -> bool:
            if not cid_h:
                return False
            if man_here and has_passing_grade_for_course(db, spid, cid_h):
                return True
            if cc_plain and stud_dept and has_passing_grade_for_course_code_in_department(
                db, spid, stud_dept, cc_plain
            ):
                return True
            return False

        # Zorunlu deliği (`obs_course_sections` olmasa bile) tabloda satır olarak göster
        for br in bl_rows_ad:
            cid_hole = _str_id(br.get("course_id"))
            cc_plain = str(br.get("course_code") or "").strip()
            if not cc_plain or cc_plain in codes_seen_offer:
                continue
            if cc_plain in codes_with_section_in_sql_query:
                continue
            rb = (
                db.execute(
                    text(
                        "SELECT code, name, credits, akts, COALESCE(type,'') AS course_type, is_mandatory, "
                        "curriculum_semester, semester_no, class_year "
                        "FROM obs_courses WHERE id::text = :id LIMIT 1"
                    ),
                    {"id": cid_hole},
                )
                .mappings()
                .first()
                if cid_hole
                else None
            )
            man_hole = (
                course_row_is_mandatory(
                    rb.get("is_mandatory") if rb else None,
                    str((rb.get("course_type") or "") if rb else "") or "",
                )
                if rb
                else True
            )
            if cid_hole and _should_skip_prior_pass(cid_hole, cc_plain, man_hole):
                continue
            eff_hole = (
                _effective_course_program_semester_index(
                    rb.get("curriculum_semester"),
                    rb.get("semester_no"),
                    rb.get("class_year"),
                )
                if rb
                else br.get("curriculum_semester")
            )
            cr = int(rb.get("credits") or 0) if rb else 0
            ak = int(rb.get("akts") or br.get("akts") or 0) if (rb or br) else int(br.get("akts") or 0)
            ptier_ph, _ = (
                registration_priority_tier(db, spid, cid_hole) if cid_hole else (9, "")
            )
            catalog_ps_hole = (
                _catalog_display_program_semester_index(
                    rb.get("curriculum_semester"),
                    rb.get("semester_no"),
                    rb.get("class_year"),
                )
                if rb
                else None
            )
            if catalog_ps_hole is None and eff_hole is not None:
                try:
                    catalog_ps_hole = int(eff_hole)
                except (TypeError, ValueError):
                    catalog_ps_hole = None
            ch_cls, ch_half = _catalog_row_labels_tr(
                catalog_ps_hole,
                rb.get("semester_no") if rb else None,
                rb.get("class_year") if rb else None,
            )
            out.append(
                {
                    "id": "",
                    "course_id": cid_hole or "",
                    "course_code": cc_plain,
                    "course_name": (rb and rb.get("name")) or br.get("course_name") or "",
                    "credits": cr,
                    "akts": ak,
                    "type": str((rb.get("course_type") or "") if rb else ""),
                    "curriculum_semester": eff_hole,
                    "is_mandatory_course": True,
                    "catalog_class_label": ch_cls,
                    "catalog_half_label": ch_half,
                    "instructor_name": "",
                    "day_of_week": "",
                    "start_time": "",
                    "end_time": "",
                    "classroom": "",
                    "capacity": 0,
                    "enrolled": 0,
                    "registration_priority_tier": ptier_ph,
                    "registration_priority_label": "Şube yok",
                    "offer_placeholder": True,
                }
            )
            codes_seen_offer.add(cc_plain)

        # Zorunlu kapısı açıkken: aynı yarıyıl kartına oturan seçmeliler (SQL’de henüz şubesi görünmeyen)
        if not elective_slot_locked:
            crs_dep = (
                db.execute(
                    text(
                        """
                        SELECT id, code, name, credits, akts,
                               COALESCE(type, '') AS course_type, is_mandatory,
                               curriculum_semester, semester_no, class_year
                        FROM obs_courses
                        WHERE CAST(department_id AS text) = CAST(:did AS text)
                        """
                    ),
                    {"did": stud_dept},
                )
                .mappings()
                .all()
            )
            for crw in crs_dep:
                cid_e = _str_id(crw.get("id"))
                cc_e = str(crw.get("code") or "").strip()
                if not cid_e or not cc_e or cc_e in codes_seen_offer:
                    continue
                if cid_e in mids_ps:
                    continue
                if course_row_is_mandatory(
                    crw.get("is_mandatory"),
                    str(crw.get("course_type") or ""),
                ):
                    continue
                if cc_e in codes_with_section_in_sql_query:
                    continue
                if not _course_placement_visible_for_student(
                    stud_dept,
                    psn_student,
                    stud_dept,
                    crw.get("curriculum_semester"),
                    crw.get("semester_no"),
                    crw.get("class_year"),
                ):
                    continue
                if registration_is_elective_style_add_for_gate(
                    db, spid, stud_dept, psn_student, cid_e
                ):
                    _, bl_quick = mandate_backlog_remaining(
                        db, spid, stud_dept, psn_student, planned_union_ad
                    )
                    if bool(bl_quick):
                        continue
                if _should_skip_prior_pass(cid_e, cc_e, False):
                    continue
                eff_e = _effective_course_program_semester_index(
                    crw.get("curriculum_semester"),
                    crw.get("semester_no"),
                    crw.get("class_year"),
                )
                ptier_e, _ = registration_priority_tier(db, spid, cid_e)
                ct_e = str(crw.get("course_type") or "")
                em_flag = False
                disp_e = _catalog_display_program_semester_index(
                    crw.get("curriculum_semester"),
                    crw.get("semester_no"),
                    crw.get("class_year"),
                )
                ec_cls, ec_half = _catalog_row_labels_tr(
                    disp_e,
                    crw.get("semester_no"),
                    crw.get("class_year"),
                )
                out.append(
                    {
                        "id": "",
                        "course_id": cid_e,
                        "course_code": cc_e,
                        "course_name": crw.get("name") or "",
                        "credits": int(crw.get("credits") or 0),
                        "akts": int(crw.get("akts") or 0),
                        "type": ct_e,
                        "curriculum_semester": eff_e,
                        "is_mandatory_course": em_flag,
                        "catalog_class_label": ec_cls,
                        "catalog_half_label": ec_half,
                        "instructor_name": "",
                        "day_of_week": "",
                        "start_time": "",
                        "end_time": "",
                        "classroom": "",
                        "capacity": 0,
                        "enrolled": 0,
                        "registration_priority_tier": ptier_e,
                        "registration_priority_label": "Şube yok",
                        "offer_placeholder": True,
                    }
                )
                codes_seen_offer.add(cc_e)

    # Katalog (kayıt + ekle-bırak) SQL sırasını korur; diğer listede sıra özetlenir.
    if not listing_catalog:
        out.sort(
            key=lambda x: (
                0 if x.get("offer_placeholder") else 1,
                0 if x.get("is_mandatory_course") else 1,
                x.get("registration_priority_tier", 9),
                (x.get("course_code") or "").strip().lower(),
            )
        )

    offer_placeholder_rows = sum(1 for x in out if x.get("offer_placeholder"))
    real_section_rows = len(out) - offer_placeholder_rows

    log.info(
        "available_sections student=%s mode=%s term_resolved=%s term_cands=%d ps=%d dept=%s "
        "raw_sql_rows=%d emitted=%d real_sections=%d offer_placeholders=%d backlog_holes=%d bypass_ids=%d bypass_codes=%d "
        "drop_placement=%d bypass_kept_rows=%d drop_pass_by_course_id=%d "
        "drop_pass_by_code_in_dept=%d placement_drop_samples=%s",
        spid,
        listing_mode,
        tid,
        len(tcands_list),
        int(psn_student),
        stud_dept or "-",
        n_raw,
        len(out),
        real_section_rows,
        offer_placeholder_rows,
        len(bl_rows_ad),
        len(backlog_bypass_course_ids),
        len(backlog_bypass_codes),
        n_drop_placement,
        n_bypass_kept,
        n_drop_pass_course,
        n_drop_pass_code_dept,
        sample_drop_placement or "-",
    )

    add_drop_sections_empty_hint = ""
    registration_sections_empty_hint = ""
    if listing_mode == "add_drop":
        if real_section_rows > 0:
            if offer_placeholder_rows > 0:
                add_drop_sections_empty_hint = (
                    f"Bazı ders kodları şube satırı olmadan görünüyor ({offer_placeholder_rows}). «Ders ekle» için şube gereklidir."
                )
        elif offer_placeholder_rows > 0:
            add_drop_sections_empty_hint = (
                f"Liste yalnızca müfredat yer tutucu ({offer_placeholder_rows} kod); bu dönemde şube açılmış satır çıkmıyor."
            )
        elif sections_in_terms_total == 0:
            add_drop_sections_empty_hint = "Seçilen dönem için açılmış şube tanımı yok."
        elif n_raw == 0:
            add_drop_sections_empty_hint = (
                "Bu dönemde bölümünüze bağlı seçilebilir şube görünmüyor "
                "(tüm uygun şubeler dolu/taşlakta kayıtlı veya bloklu olabilir)."
            )
        elif not out:
            add_drop_sections_empty_hint = (
                "Gösterilecek seçilebilir şube satırı kalmadı (mezun olmuş kodlar dahil sıradan süzüm)."
            )
    if listing_mode == "registration":
        if real_section_rows > 0:
            if offer_placeholder_rows > 0:
                registration_sections_empty_hint = (
                    f"Bazı satırların bu dönemde `obs_course_sections` bağlantısı yok ({offer_placeholder_rows} müfredat). "
                    "«Ders ekle» ancak gerçek şube satırında açıktır."
                )
        elif offer_placeholder_rows > 0:
            registration_sections_empty_hint = (
                f"Müfredatınıza uygun dersler listelendi fakat seçilen sürede şube kaydı yok ({offer_placeholder_rows}). "
                "OBS’te şube açılınca sepet eklemesi yapılabilir."
            )
        elif sections_in_terms_total == 0:
            registration_sections_empty_hint = (
                "Bu dönem öbeği için `obs_course_sections` kaydı yok; katalog ile şube yükleme uyumsuz."
            )
        elif n_raw == 0:
            registration_sections_empty_hint = (
                "Şube tablosunda kayıt var ama seçilebilir satır çıkmıyor (aynı dersten blok vb.)."
            )
        elif not out:
            registration_sections_empty_hint = (
                "Şubeler filtrelendi; kart veya diploma kontrollerine takılmış olabilir."
            )

    meta_side.update(
        {
            "sections_in_terms_total": sections_in_terms_total,
            "sections_query_rows_student": n_raw,
            "real_section_rows_emitted": real_section_rows,
            "offer_placeholder_rows": offer_placeholder_rows,
            "courses_pending_sections": [],
            "add_drop_sections_empty_hint": (
                add_drop_sections_empty_hint if listing_mode == "add_drop" else ""
            ),
            "registration_sections_empty_hint": (
                registration_sections_empty_hint if listing_mode == "registration" else ""
            ),
        }
    )

    return tid, out, meta_side


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
               g.midterm, g.final, g.makeup, g.letter_grade, g.is_finalized
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
            "makeup": _num(r.get("makeup")),
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
            SELECT g.enrollment_id AS eid, g.midterm AS mid, g."final" AS fin, g.makeup AS mup, g.is_finalized AS finz
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
        mid, fin, mup = r.get("mid"), r.get("fin"), r.get("mup")
        if mid is None or (fin is None and mup is None):
            continue
        try:
            # Eğer büt girilmişse final yerine büt kullanılır (ağırlığı aynı)
            eff_fin = mup if mup is not None else (fin if fin is not None else 0)
            sc = (float(mid) * w_mid + float(eff_fin) * w_fin) / 100.0
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
            SET is_finalized = false,
                is_published = false,
                finalized_at = NULL,
                finalized_by = NULL,
                updated_at = NOW()
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
        mup = item.get("makeup")
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
                if mid is not None and (fin is not None or mup is not None):
                    try:
                        eff_fin2 = mup if mup is not None else (fin if fin is not None else 0)
                        score = (float(mid) * w_mid + float(eff_fin2) * w_fin) / 100.0
                        computed_lg = _letter_from_score(score)
                    except (TypeError, ValueError):
                        computed_lg = None

            # Not: SQLite 3.39+ "final" ayrılmış kelime → tırnaksız UPDATE sözdizimi hatası.
            # PostgreSQL'de de "final"/"midterm" sütun adları için çift tırnak güvenli.
            set_parts = [
                '"midterm" = COALESCE(:m, "midterm")',
                '"final" = COALESCE(:f, "final")',
                '"makeup" = COALESCE(:mup, "makeup")',
            ]
            params: dict[str, Any] = {"eid": eid, "m": mid, "f": fin, "mup": mup}
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
                if mid is not None and (fin is not None or mup is not None):
                    try:
                        eff_fin3 = mup if mup is not None else (fin if fin is not None else 0)
                        score2 = (float(mid) * w_mid + float(eff_fin3) * w_fin) / 100.0
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


def _resolve_grade_notification_sender_uid(
    db: Session,
    section_id: str,
    finalized_by_webui_uid: Optional[str],
) -> Optional[str]:
    """Gelen kutusu mesajında gönderen: kesinleştiren akademisyen Open WebUI user.id veya şube hocası."""
    u = (_str_id(finalized_by_webui_uid) if finalized_by_webui_uid else "") or ""
    if u.strip():
        return u.strip()
    row = db.execute(
        text(
            """
            SELECT ap.user_id
            FROM obs_course_sections cs
            LEFT JOIN obs_academic_profiles ap ON ap.id = cs.instructor_id
            WHERE cs.id = :sid
            LIMIT 1
            """
        ),
        {"sid": section_id},
    ).first()
    return (_str_id(row[0]) or "").strip() if row else None


def _grade_finalize_inbox_targets(
    db: Session, section_id: str
) -> list[dict[str, Any]]:
    """Bu işlem öncesi kesinleşmemiş (is_finalized hariç True) aktif kayıtlar — kutuya bildirim gidecek liste."""
    rows = db.execute(
        text(
            """
            SELECT sp.user_id AS student_uid, c.code AS course_code,
                   c.name AS course_name, cs.section_no, g.is_finalized, g.letter_grade
            FROM obs_grade_entries g
            INNER JOIN obs_course_enrollments ce ON ce.id = g.enrollment_id
            INNER JOIN obs_student_profiles sp ON sp.id = ce.student_id
            INNER JOIN obs_course_sections cs ON cs.id = ce.course_section_id
            INNER JOIN obs_courses c ON c.id = cs.course_id
            WHERE ce.course_section_id = :sid
              AND ce.status = 'active'
              AND sp.user_id IS NOT NULL
            """
        ),
        {"sid": section_id},
    ).mappings().all()
    return [dict(r) for r in rows if not bool(r.get("is_finalized"))]


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

    notify_targets = _grade_finalize_inbox_targets(db, section_id)

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
                is_published = true,
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

    sender_uid = _resolve_grade_notification_sender_uid(
        db, section_id, finalized_by_user_id
    )
    if not sender_uid or not notify_targets:
        return

    seen_receivers: set[str] = set()
    for r in notify_targets:
        recv = (_str_id(r.get("student_uid")) or "").strip()
        if not recv or recv in seen_receivers:
            continue
        seen_receivers.add(recv)
        code = (str(r.get("course_code") or "").strip()) or "(ders)"
        cname = (str(r.get("course_name") or "").strip()) or code
        sn = r.get("section_no")
        sec_txt = ""
        if sn is not None and str(sn).strip():
            sec_txt = f" — Şube {str(sn).strip()}"
        lg_raw = r.get("letter_grade")
        lg_s = (str(lg_raw).strip() if lg_raw is not None else "") or ""
        line_grade = f"\nHarf notu: {lg_s}" if lg_s else ""
        subject = f"Not kesinleştirildi: {code}"
        body = (
            f"{cname}{sec_txt}\n"
            "Bu derse ilişkin notlarınız kesinleştirildi."
            f"{line_grade}\n\n"
            "Detay için OBS › Notlar / Transkript ekranından kontrol edebilirsiniz."
        )
        try:
            insert_message(db, sender_uid, recv, subject, body)
        except Exception:
            log.exception(
                "Not kesinleştirme sonrası gelen kutusu bildirimi yazılamadı "
                "section_id=%s receiver=%s",
                section_id,
                recv,
            )


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
    """Not metninden dönem id ve akış: registration | add_drop.

    Eski: not yalın ``BATCH_TERM:<uuid>`` ile başlıyordu (:func:`startswith`).
    Güncel: ``submit_schedule_to_advisor`` sonuna ``\\n---\\nSistem Notu: BATCH_TERM:<uuid>`` yazılır;
    bu yüzden ek olarak ``find(BATCH_TERM:)`` kullanılır.
    """
    if not note:
        return None, ""
    s = str(note).strip()

    idx_ad = s.find(BATCH_ADDDROP_TERM_NOTE_PREFIX)
    if idx_ad >= 0:
        rest = (
            s[idx_ad + len(BATCH_ADDDROP_TERM_NOTE_PREFIX) :].split("\n", 1)[0].strip()
        )
        return (rest or None), "add_drop"

    idx_reg = s.find(BATCH_TERM_NOTE_PREFIX)
    if idx_reg >= 0:
        rest = (
            s[idx_reg + len(BATCH_TERM_NOTE_PREFIX) :].split("\n", 1)[0].strip()
        )
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
    """Bırakılacaklar henüz pending_drop değilken: **aktif** satırlar (kart etiketi uyuşmazsa bile)
    dâhildir; yalnızca ``add_drop`` taslakları müfredat kartına uymuyorsa özet AKTS'e eklenmez."""

    stud_dept, psn = student_dept_and_program_semester(db, student_profile_id)
    drops = [x for x in (drop_enrollment_ids or []) if x]
    params: dict[str, Any] = {"spid": student_profile_id, "tid": term_id}

    sel = """
            SELECT ce.status, COALESCE(c.akts, 0) AS akts,
                   CAST(c.department_id AS TEXT) AS cdept,
                   c.curriculum_semester, c.semester_no, c.class_year,
                   COALESCE(c.type, '') AS ctype, c.is_mandatory
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND (
                ce.status = 'active'
                OR (ce.status = 'draft' AND COALESCE(ce.enrollment_reason, '') = 'add_drop')
              )
        """
    if not drops:
        rows = db.execute(text(sel), params).mappings().all()
    else:
        in_ph = ", ".join(f":d{i}" for i in range(len(drops)))
        for i, eid in enumerate(drops):
            params[f"d{i}"] = eid
        rows = db.execute(
            text(
                sel
                + f"""
              AND NOT (ce.status = 'active' AND ce.id IN ({in_ph}))
            """
            ),
            params,
        ).mappings().all()

    total = 0
    for r in rows:
        st = str(r.get("status") or "")
        if st == "active":
            total += int(r.get("akts") or 0)
            continue
        if not stud_dept:
            total += int(r.get("akts") or 0)
            continue
        if _course_matches_student_program_semester_card(
            stud_dept,
            psn,
            _str_id(r.get("cdept")),
            r.get("curriculum_semester"),
            r.get("semester_no"),
            r.get("class_year"),
            r.get("is_mandatory"),
            str(r.get("ctype") or "") or None,
            listing_mode="add_drop",
        ):
            total += int(r.get("akts") or 0)
    return total


def add_drop_projected_load_pending_review(
    db: Session, student_profile_id: str, term_id: str
) -> int:
    """Danışman onayı beklerken: korunan aktifler + eklenecek pending add_drop (bırakılacaklar hariç)."""

    stud_dept, psn = student_dept_and_program_semester(db, student_profile_id)
    rows = db.execute(
        text("""
        SELECT ce.status, COALESCE(ce.enrollment_reason, '') AS enrollment_reason,
               COALESCE(c.akts, 0) AS akts,
               CAST(c.department_id AS TEXT) AS cdept,
               c.curriculum_semester, c.semester_no, c.class_year,
               COALESCE(c.type, '') AS ctype, c.is_mandatory
        FROM obs_course_enrollments ce
        JOIN obs_course_sections cs ON ce.course_section_id = cs.id
        JOIN obs_courses c ON cs.course_id = c.id
        WHERE ce.student_id = :spid AND cs.term_id = :tid
          AND (
            ce.status = 'active'
            OR (ce.status = 'pending' AND COALESCE(ce.enrollment_reason, '') IN ('add_drop', 'advisor_added'))
          )
        """),
        {"spid": student_profile_id, "tid": term_id},
    ).mappings().all()
    total = 0
    for r in rows:
        st = str(r.get("status") or "")
        if st == "active":
            total += int(r.get("akts") or 0)
            continue
        if not stud_dept:
            total += int(r.get("akts") or 0)
            continue
        if _course_matches_student_program_semester_card(
            stud_dept,
            psn,
            _str_id(r.get("cdept")),
            r.get("curriculum_semester"),
            r.get("semester_no"),
            r.get("class_year"),
            r.get("is_mandatory"),
            str(r.get("ctype") or "") or None,
            listing_mode="add_drop",
        ):
            total += int(r.get("akts") or 0)
    return total


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
            "curriculum_mandatory_remaining": [],
            "curriculum_elective_locked": False,
        }
    akts_max, rule, det = effective_akts_limit_for_student(db, spid, tid)
    load = student_term_scheduled_akts(db, spid, tid)
    ad_mn, ad_mx = add_drop_akts_min_max_for_student(db, spid, tid)
    dept_lm, psn_lm = student_dept_and_program_semester(db, spid)
    curriculum_mandatory_remaining: list[dict[str, Any]] = []
    curriculum_elective_locked = False
    if dept_lm and tid:
        plm = student_term_enrolled_course_ids(db, spid, tid)
        curriculum_elective_locked, curriculum_mandatory_remaining = (
            mandate_backlog_remaining(db, spid, dept_lm, psn_lm, plm)
        )
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
        "curriculum_mandatory_remaining": curriculum_mandatory_remaining,
        "curriculum_elective_locked": curriculum_elective_locked,
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
    stud_dept, psn_student = student_dept_and_program_semester(db, spid)
    canonical_tid: Optional[str] = None
    planned_course_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    for sid in section_ids:
        meta = (
            db.execute(
                text("""
                SELECT cs.id, cs.term_id, cs.course_id, cs.capacity, COALESCE(c.akts, 0) AS course_akts,
                  CAST(c.department_id AS TEXT) AS course_department_id,
                  c.curriculum_semester, c.semester_no, c.class_year,
                  COALESCE(c.type, '') AS course_type, c.is_mandatory,
                  c.code AS course_code_plain,
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
        if canonical_tid is None:
            canonical_tid = tid
            planned_course_ids = student_term_enrolled_course_ids(db, spid, tid)
        elif tid != canonical_tid:
            return (
                [],
                "Tüm seçilen şubeler aynı akademik süreye (döneme) ait olmalı.",
            )
        cid_gate = _str_id(meta.get("course_id")) or ""
        ok, reason = _term_window_allowed(db, tid, mode)
        if not ok:
            print(f"DEBUG: Pencere kapalı! Reason: {reason}")
            return [], reason
        cdept_meta = _str_id(meta.get("course_department_id")) or ""
        if stud_dept and cdept_meta and not _course_matches_student_program_semester_card(
            stud_dept,
            psn_student,
            cdept_meta,
            meta.get("curriculum_semester"),
            meta.get("semester_no"),
            meta.get("class_year"),
            meta.get("is_mandatory"),
            str(meta.get("course_type") or "") or None,
            listing_mode=mode,
        ):
            cc_plain = str(meta.get("course_code_plain") or "").strip()
            return [], (
                f"{cc_plain or 'Bu ders'} mevcut program yarıyılınız ({psn_student}. program yarıyılı kartı) "
                "ile eşleşmiyor. Yalnızca müfredatta bu yarıyıla etiketlenmiş dersler için şube seçilebilir."
            )
        if cid_gate and stud_dept:
            if registration_is_elective_style_add_for_gate(
                db, spid, stud_dept, psn_student, cid_gate
            ):
                bl_nonempty, bl_rows = mandate_backlog_remaining(
                    db, spid, stud_dept, psn_student, planned_course_ids
                )
                if bl_nonempty:
                    return [], OBS_MANDATORY_PLAN_DENIED_MSG_TR
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
            print(f"DEBUG: Duplicate course found for CID: {meta['course_id']}")
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
            print(f"DEBUG: Kontenjan dolu! Taken: {taken}, Cap: {cap}")
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
        # Exact section kontrolü: varolan kayda göre davran
        existing_row = (
            db.execute(
                text("""
                SELECT id, status FROM obs_course_enrollments
                WHERE student_id = :spid AND course_section_id = :csid
                LIMIT 1
                """),
                {"spid": spid, "csid": sid},
            )
            .mappings()
            .first()
        )
        if existing_row:
            existing_status = str(existing_row.get("status") or "")
            if existing_status != "dropped":
                continue  # active/pending/draft/pending_drop → zaten kayıtlı, atla
            # dropped → yeniden ekle: UPDATE
            eid = str(existing_row["id"])
            db.execute(
                text("""
                UPDATE obs_course_enrollments
                SET status = 'draft', enrollment_reason = :reason,
                    advisor_approved = false, dropped_at = NULL
                WHERE id = :eid
                """),
                {"eid": eid, "reason": mode},
            )
        else:
            eid = str(uuid.uuid4())
            db.execute(
                text("""
                INSERT INTO obs_course_enrollments
                (id, student_id, course_section_id, status, enrollment_reason, advisor_approved)
                VALUES (:id, :spid, :csid, 'draft', :reason, false)
                """),
                {"id": eid, "spid": spid, "csid": sid, "reason": mode},
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
        if cid_gate:
            planned_course_ids.add(cid_gate)
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

        stud_reg, ps_reg = student_dept_and_program_semester(db, spid)
        reg_drafts = db.execute(
            text("""
            SELECT c.code AS course_code,
                   CAST(c.department_id AS TEXT) AS cdept,
                   c.curriculum_semester, c.semester_no, c.class_year,
                   COALESCE(c.type, '') AS ctype, c.is_mandatory
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND ce.status = 'draft'
              AND (ce.enrollment_reason = 'registration' OR ce.enrollment_reason IS NULL)
            """),
            {"spid": spid, "tid": term_id},
        ).mappings().all()
        if stud_reg:
            for dr in reg_drafts:
                cdp = _str_id(dr.get("cdept")) or ""
                if cdp and not _course_matches_student_program_semester_card(
                    stud_reg,
                    ps_reg,
                    cdp,
                    dr.get("curriculum_semester"),
                    dr.get("semester_no"),
                    dr.get("class_year"),
                    dr.get("is_mandatory"),
                    str(dr.get("ctype") or "") or None,
                    listing_mode="registration",
                ):
                    cod = str(dr.get("course_code") or "").strip()
                    return None, (
                        f"Kayıt sepetinde mevcut program yarıyılınıza uygun olmayan taslak var: "
                        f"{cod or '(kodsuz)'}. Önce iptal edin; yalnızca müfredatta bu yarıyıla "
                        "etiketlenmiş ders seçilebilir."
                    )

        planned_mand_reg = planned_course_ids_for_mandatory_gate_submit(
            db, spid, term_id, flow="registration"
        )
        if stud_reg and mandate_backlog_remaining(
            db, spid, stud_reg, ps_reg, planned_mand_reg
        )[0]:
            return None, OBS_MANDATORY_PLAN_DENIED_MSG_TR

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
        # Yeni ders listesini not içeriği için hazırla
        enr_rows = db.execute(
            text("""
                SELECT c.code, c.name, c.akts
                FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                JOIN obs_courses c ON cs.course_id = c.id
                WHERE ce.student_id = :spid AND cs.term_id = :tid
                  AND ce.status = 'pending'
            """),
            {"spid": spid, "tid": term_id},
        ).fetchall()
        
        course_list_str = "\n".join([f"• {r[0]} - {r[1]} ({r[2]} AKTS)" for r in enr_rows])
        batch_note = f"Ders Kayıt (Danışman Onayı)\n\nSeçilen Dersler:\n{course_list_str}"
    else:
        # --- EKLE-BIRAK MANTIĞINI GERİ YÜKLE ---
        drop_terms: set[str] = set()
        for eid in eids_drop:
            drow = db.execute(
                text("""
                SELECT cs.term_id FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                WHERE ce.id = :eid AND ce.student_id = :spid AND ce.status = 'active'
                """),
                {"eid": eid, "spid": spid},
            ).mappings().first()
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

        # Kayıt penceresi kontrolü
        ok, reason = _term_window_allowed(db, term_id, "add_drop")
        if not ok:
            return None, reason

        stud_ad, ps_ad = student_dept_and_program_semester(db, spid)
        bad_add_drop = db.execute(
            text("""
            SELECT c.code AS course_code,
                   CAST(c.department_id AS TEXT) AS cdept,
                   c.curriculum_semester, c.semester_no, c.class_year,
                   COALESCE(c.type, '') AS ctype, c.is_mandatory
            FROM obs_course_enrollments ce
            JOIN obs_course_sections cs ON ce.course_section_id = cs.id
            JOIN obs_courses c ON cs.course_id = c.id
            WHERE ce.student_id = :spid AND cs.term_id = :tid
              AND ce.status = 'draft' AND COALESCE(ce.enrollment_reason, '') = 'add_drop'
            """),
            {"spid": spid, "tid": term_id},
        ).mappings().all()
        if stud_ad:
            for bd in bad_add_drop:
                cdp = _str_id(bd.get("cdept")) or ""
                if cdp and not _course_matches_student_program_semester_card(
                    stud_ad,
                    ps_ad,
                    cdp,
                    bd.get("curriculum_semester"),
                    bd.get("semester_no"),
                    bd.get("class_year"),
                    bd.get("is_mandatory"),
                    str(bd.get("ctype") or "") or None,
                    listing_mode="add_drop",
                ):
                    cod = str(bd.get("course_code") or "").strip()
                    return None, (
                        "Pakette mevcut program yarıyılınıza uygun olmayan taslak satırı var: "
                        f"{cod or '(kodsuz)'}.\nÖnce listede «Eklemeyi iptal edin» ile kaldırın; "
                        "yalnızca bu yarıyıl müfredat kartına etiketli dersler eklenebilir."
                    )

        # AKTS Sınırı Kontrolü
        proj = add_drop_projected_load_before_submit(db, spid, term_id, eids_drop)
        ok_ak, msg_ak = validate_add_drop_akts_bounds(db, spid, term_id, proj)
        if not ok_ak:
            return None, msg_ak

        planned_mand_ad = planned_course_ids_for_mandatory_gate_submit(
            db, spid, term_id, flow="add_drop", enrollment_ids_to_drop=eids_drop
        )
        if stud_ad and mandate_backlog_remaining(
            db, spid, stud_ad, ps_ad, planned_mand_ad
        )[0]:
            return None, OBS_MANDATORY_PLAN_DENIED_MSG_TR

        # İşlemleri Gerçekleştir (Bırakma)
        if eids_drop:
            bind = {f"e{i}": eids_drop[i] for i in range(len(eids_drop))}
            in_ph = ", ".join(f":e{i}" for i in range(len(eids_drop)))
            db.execute(
                text(f"""
                UPDATE obs_course_enrollments ce SET status = 'pending_drop'
                FROM obs_course_sections cs
                WHERE ce.course_section_id = cs.id AND ce.student_id = :spid
                  AND cs.term_id = :tid AND ce.id IN ({in_ph})
                  AND ce.status = 'active'
                """),
                {"spid": spid, "tid": term_id, **bind},
            )

        # İşlemleri Gerçekleştir (Ekleme)
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

        # --- Onay notunu oluştur ---
        added_rows = db.execute(
            text("""
                SELECT c.code, c.name, c.akts
                FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                JOIN obs_courses c ON cs.course_id = c.id
                WHERE ce.student_id = :spid AND cs.term_id = :tid
                  AND ce.status = 'pending' AND ce.enrollment_reason = 'add_drop'
            """),
            {"spid": spid, "tid": term_id},
        ).fetchall()
        
        dropped_rows = db.execute(
            text("""
                SELECT c.code, c.name
                FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                JOIN obs_courses c ON cs.course_id = c.id
                WHERE ce.student_id = :spid AND cs.term_id = :tid
                  AND ce.status = 'pending_drop'
            """),
            {"spid": spid, "tid": term_id},
        ).fetchall()
        
        added_str = "\n".join([f"• [EKLE] {r[0]} - {r[1]} ({r[2]} AKTS)" for r in added_rows]) if added_rows else "(Yeni ders eklenmedi)"
        dropped_str = "\n".join([f"• [BIRAK] {r[0]} - {r[1]}" for r in dropped_rows]) if dropped_rows else "(Ders bırakılmadı)"
        batch_note = f"Ders Ekle/Bırak Talebi\n\nDeğişiklikler:\n{added_str}\n{dropped_str}"

    db.execute(
        text("""
            DELETE FROM obs_approval_requests
            WHERE student_id = :spid AND request_type = 'schedule_batch' AND status = 'pending'
        """),
        {"spid": spid},
    )
    
    # Teknik izleme notu (arka planda çalışması için gizli formatta sona ekle)
    tracking_prefix = BATCH_ADDDROP_TERM_NOTE_PREFIX if flow == "add_drop" else BATCH_TERM_NOTE_PREFIX
    batch_note += f"\n\n---\nSistem Notu: {tracking_prefix}{term_id}"

    if note and str(note).strip():
        batch_note = batch_note + "\n\nÖğrenci Notu: " + str(note).strip()
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
              CAST(c.department_id AS TEXT) AS course_department_id,
              c.curriculum_semester, c.semester_no, c.class_year,
              COALESCE(c.type, '') AS course_type, c.is_mandatory,
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
    stud_adv, ps_adv = student_dept_and_program_semester(db, spid)
    cdept_adv = _str_id(meta.get("course_department_id")) or ""
    if stud_adv and cdept_adv and not _course_matches_student_program_semester_card(
        stud_adv,
        ps_adv,
        cdept_adv,
        meta.get("curriculum_semester"),
        meta.get("semester_no"),
        meta.get("class_year"),
        meta.get("is_mandatory"),
        str(meta.get("course_type") or "") or None,
        listing_mode="add_drop",
    ):
        return None, (
            f"Bu şube öğrencinin mevcut program yarıyılı ({ps_adv}) müfredat kartına göre seçilemez. "
            "Yalnızca müfredatta bu yarıyıla etiketlenmiş dersler eklenebilir."
        )
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
          AND (note LIKE '%' || :p1 OR note LIKE '%' || :p2)
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
          AND (note LIKE '%' || :p1 OR note LIKE '%' || :p2)
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
    *,
    acting_user_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    def dval(s: Optional[str]) -> Any:
        if s is None or str(s).strip() == "":
            return None
        return str(s).strip()

    prev = _snapshot_term_registration_flags(db, term_id)
    if prev is None:
        return None

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
    curr = _snapshot_term_registration_flags(db, term_id)
    if curr is not None:
        try:
            _maybe_notify_registration_window_changes(
                db, prev=prev, curr=curr, acting_user_id=acting_user_id
            )
        except Exception:
            log.exception(
                "[OBS] Kayıt/ekle-bırak penceresi bildirimi atlandı (term_id=%s)", term_id
            )

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
            return False, "Danışman talebinde dönem bilgisi okunamadı (önizleme notu biçimi)."
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


# --- Audit kayıtları (obs_audit_logs): kritik işlemler izole bağlantıda yazılır ---

OBS_AUDIT_DETAILS_MAX_CHARS = 12_000
_obs_audit_col_cache: dict[int, dict[str, str]] = {}
_obs_audit_schema_committed_bindings: set[int] = set()
_obs_audit_migration_done: set[int] = set()
_obs_audit_standalone_bootstrapped = False
_UUID_LIKE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _audit_quote_ident(raw: str) -> str:
    s = str(raw or "").strip()
    return '"' + s.replace('"', "") + '"'


def _audit_looks_like_uuid(value: Any) -> bool:
    s = str(value or "").strip()
    return bool(s and _UUID_LIKE_RE.match(s))


def _audit_err_is_uuid_mismatch(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "invalid input syntax for type uuid" in msg


def _pg_obs_audit_column_udt(db: Session, column_name: str) -> Optional[str]:
    """PostgreSQL: information_schema.columns.udt_name (uuid, text, ...)."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return None
    try:
        row = db.execute(
            text(
                """
                SELECT udt_name::text
                FROM information_schema.columns
                WHERE table_schema = ANY (current_schemas(true))
                  AND table_name = 'obs_audit_logs'
                  AND lower(column_name) = lower(:cn)
                LIMIT 1
                """
            ),
            {"cn": column_name},
        ).fetchone()
        return str(row[0]).lower() if row and row[0] else None
    except Exception:
        return None


def _migrate_obs_audit_logs_text_columns(
    db: Session, *, commit_now: bool, force: bool = False
) -> None:
    """Eski şemada UUID olan kolonları TEXT'e çevirir (URL yolu kaydı için)."""
    bind = db.get_bind()
    key = id(bind)
    if not force and key in _obs_audit_migration_done:
        return
    if bind.dialect.name != "postgresql":
        _obs_audit_migration_done.add(key)
        return
    cols_to_check = (
        "entity_id",
        "resource_id",
        "object_id",
        "target_id",
        "actor_user_id",
        "user_id",
        "impersonated_by_user_id",
    )
    migrated: list[str] = []
    try:
        for logical in cols_to_check:
            row = db.execute(
                text(
                    """
                    SELECT column_name::text, udt_name::text
                    FROM information_schema.columns
                    WHERE table_schema = ANY (current_schemas(true))
                      AND table_name = 'obs_audit_logs'
                      AND lower(column_name) = lower(:cn)
                    LIMIT 1
                    """
                ),
                {"cn": logical},
            ).fetchone()
            if not row:
                continue
            actual_name, udt = str(row[0]), str(row[1]).lower()
            if udt != "uuid":
                continue
            qcol = _audit_quote_ident(actual_name)
            db.execute(
                text(
                    f"ALTER TABLE obs_audit_logs ALTER COLUMN {qcol} "
                    f"TYPE TEXT USING {qcol}::text"
                )
            )
            migrated.append(actual_name)
        if migrated:
            log.info(
                "[OBS Audit] obs_audit_logs kolonları UUID→TEXT: %s",
                ", ".join(migrated),
            )
        if commit_now:
            db.commit()
        _obs_audit_col_cache.pop(key, None)
        _obs_audit_migration_done.add(key)
    except Exception:
        log.exception("[OBS Audit] UUID→TEXT migrasyonu başarısız")
        try:
            db.rollback()
        except Exception:
            pass


def _audit_safe_entity_id_value(
    db: Session, colmap: dict[str, str], value: Optional[str]
) -> Optional[str]:
    """entity_id hâlâ UUID ise yalnızca gerçek UUID değerlerini döndürür."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    actual = colmap.get("entity_id")
    if not actual:
        return s[:128]
    udt = _pg_obs_audit_column_udt(db, actual)
    if udt == "uuid" and not _audit_looks_like_uuid(s):
        return None
    return s[:128]


def obs_audit_logs_column_map(db: Session) -> dict[str, str]:
    """Kolon adları: küçük harf anahtar → veritabanındaki gerçek ad."""
    bind = db.get_bind()
    key = id(bind)
    if key in _obs_audit_col_cache:
        return _obs_audit_col_cache[key]
    names: list[str] = []
    try:
        if bind.dialect.name == "sqlite":
            rows = db.execute(text("PRAGMA table_info(obs_audit_logs)")).fetchall()
            names = [str(r[1]) for r in rows]
        else:
            rows = db.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = ANY (current_schemas(true))
                      AND table_name = 'obs_audit_logs'
                    """
                )
            ).fetchall()
            names = [str(r[0]) for r in rows]
            if not names:
                rows2 = db.execute(
                    text(
                        """
                        SELECT a.attname::text
                        FROM pg_attribute a
                        JOIN pg_class c ON c.oid = a.attrelid
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relname = 'obs_audit_logs'
                          AND n.nspname = ANY (current_schemas(true))
                          AND a.attnum > 0
                          AND NOT a.attisdropped
                        """
                    )
                ).fetchall()
                names = [str(r[0]) for r in rows2]
    except Exception:
        log.exception("[OBS Audit] obs_audit_logs kolonları okunamadı")
    colmap = {n.lower(): n for n in names if n.strip()}
    _obs_audit_col_cache[key] = colmap
    return colmap


def _audit_add_mapping(
    colmap: dict[str, str],
    out: dict[str, Any],
    candidates: tuple[str, ...],
    value: Any,
    *,
    skip_none: bool = True,
) -> None:
    if skip_none and value is None:
        return
    for c in candidates:
        actual = colmap.get(c.lower())
        if actual and actual not in out:
            out[actual] = value
            return


def _audit_display_label_from_parts(
    name: str, email: str, student_no: str, user_id: str
) -> str:
    name = (name or "").strip()
    email = (email or "").strip()
    student_no = (student_no or "").strip()
    parts: list[str] = []
    if name:
        parts.append(name)
    if email:
        parts.append(f"<{email}>")
    if student_no:
        parts.append(f"№{student_no}")
    if parts:
        return " ".join(parts)
    return (user_id or "Bilinmeyen kullanıcı")[:512]


def _audit_parse_display_identity(label: str) -> tuple[str, str]:
    """'Ad Soyad <e@posta.com>' veya yalnızca e-posta → (ad, e-posta)."""
    s = (label or "").strip()
    if not s:
        return "", ""
    m = re.search(r"<([^>@\s]+@[^>]+)>", s)
    if m:
        return s[: m.start()].strip(), m.group(1).strip()
    if "@" in s and " " not in s:
        return "", s.strip()
    return s, ""


def _audit_webui_user_lookup(user_ids: list[str]) -> dict[str, dict[str, str]]:
    """obs_audit_logs.user_id → Open WebUI kullanıcı e-posta/ad."""
    unique = list({str(x).strip() for x in user_ids if x and str(x).strip()})
    if not unique:
        return {}
    try:
        from open_webui.models.users import Users

        out: dict[str, dict[str, str]] = {}
        for u in Users.get_users_by_user_ids(unique):
            uid = str(u.id)
            out[uid] = {
                "email": str(getattr(u, "email", "") or "").strip(),
                "name": str(getattr(u, "name", "") or "").strip(),
            }
        return out
    except Exception:
        log.debug("[OBS Audit] webui kullanıcı lookup başarısız", exc_info=True)
        return {}


def _enrich_audit_row_identity(
    row: dict[str, Any], user_lookup: dict[str, dict[str, str]]
) -> dict[str, Any]:
    uid = _str_id(
        row.get("actor_user_id") or row.get("user_id") or row.get("subject_id")
    )
    email = str(row.get("email") or "").strip()
    name = str(row.get("name") or "").strip()

    if uid and uid in user_lookup:
        if not email:
            email = user_lookup[uid].get("email", "")
        if not name:
            name = user_lookup[uid].get("name", "")

    if not email or not name:
        for src in (
            row.get("user"),
            row.get("actor_display"),
            row.get("actor_name"),
            row.get("username"),
            row.get("user_name"),
        ):
            n2, e2 = _audit_parse_display_identity(str(src or ""))
            if not name and n2:
                name = n2
            if not email and e2:
                email = e2
            if name and email:
                break

    msg = str(row.get("summary") or row.get("message") or "").strip()
    if (not email or not name) and " | " in msg:
        n3, e3 = _audit_parse_display_identity(msg.split(" | ", 1)[0])
        if not name and n3:
            name = n3
        if not email and e3:
            email = e3

    row["email"] = email
    row["name"] = name
    if email or name:
        row["user"] = _audit_display_label_from_parts(
            name,
            email,
            str(row.get("student_no") or ""),
            uid or "",
        )
    elif uid and not row.get("user"):
        row["user"] = uid
    return row


def _audit_action_label_tr(action: str) -> str:
    a = (action or "").strip()
    labels = {
        "obs.crud.read": "Veri okuma (GET)",
        "obs.crud.create": "Oluşturma (POST)",
        "obs.crud.update": "Güncelleme (PUT/PATCH)",
        "obs.crud.delete": "Silme (DELETE)",
        "ui.page_view": "Sayfa görüntüleme",
    }
    if a in labels:
        return labels[a]
    if a.startswith("obs.http."):
        return f"API isteği ({a.replace('obs.http.', '')})"
    return a


def _audit_summary_line(
    *,
    action: str,
    actor_label: str,
    actor_user_id: Optional[str],
    entity_type: Optional[str],
    entity_id: Optional[str],
    details: Optional[dict[str, Any]],
    source: str,
) -> str:
    """Admin listesinde okunacak tek satır özet (Türkçe)."""
    if details and isinstance(details, dict):
        em = str(details.get("email") or "").strip()
        nm = str(details.get("name") or "").strip()
        sno = str(details.get("student_no") or "").strip()
        if em or nm or sno:
            who = _audit_display_label_from_parts(
                nm, em, sno, str(actor_user_id or "")
            )
        else:
            who = (actor_label or "").strip()
    else:
        who = (actor_label or "").strip()
    if not who and actor_user_id:
        who = str(actor_user_id)[:36]
    if not who:
        who = "Bilinmeyen kullanıcı"
    act_tr = _audit_action_label_tr(action)
    target = ""
    if details and isinstance(details, dict):
        target = (
            str(details.get("page_label") or "")
            or str(details.get("label") or "")
            or str(details.get("path") or "")
            or str(details.get("api_label") or "")
        ).strip()
    if not target and entity_id:
        eid = str(entity_id)
        if not eid.startswith("GET:") and not eid.startswith("POST:"):
            target = eid
        elif ":" in eid:
            target = eid.split(":", 1)[1]
    if not target and entity_type:
        target = str(entity_type)
    src = (source or "").strip()
    src_tr = {"http": "API", "client": "Arayüz", "api": "Sistem"}.get(src, src)
    parts = [who, act_tr]
    if target:
        parts.append(target)
    if src_tr:
        parts.append(f"({src_tr})")
    if details and isinstance(details, dict):
        crud = details.get("crud")
        method = details.get("http_method")
        status = details.get("status_code")
        if method and crud:
            parts.append(f"[{method} → {crud}]")
        if status is not None:
            parts.append(f"HTTP {status}")
    return " · ".join(p for p in parts if p)


def ensure_obs_audit_logs_schema(db: Session, *, commit_now: bool) -> None:
    """Tabloyu oluşturur. commit_now=True ise ayrı izole oturumlarda kullanılmalıdır."""
    bind = db.get_bind()
    key = id(bind)
    need_create = key not in _obs_audit_schema_committed_bindings
    if need_create:
        dialect = bind.dialect.name
        if dialect == "sqlite":
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS obs_audit_logs (
                        id TEXT PRIMARY KEY NOT NULL,
                        action TEXT NOT NULL,
                        entity_type TEXT,
                        entity_id TEXT,
                        actor_display TEXT NOT NULL DEFAULT '',
                        actor_user_id TEXT,
                        details TEXT,
                        source TEXT,
                        impersonated_by_user_id TEXT,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                    """
                )
            )
        else:
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS obs_audit_logs (
                        id UUID PRIMARY KEY,
                        action TEXT NOT NULL,
                        entity_type TEXT,
                        entity_id TEXT,
                        actor_display TEXT NOT NULL DEFAULT '',
                        actor_user_id TEXT,
                        details TEXT,
                        source TEXT,
                        impersonated_by_user_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
        if commit_now:
            db.commit()
        _obs_audit_schema_committed_bindings.add(key)
        _obs_audit_col_cache.pop(key, None)
    _migrate_obs_audit_logs_text_columns(db, commit_now=commit_now)


def ensure_obs_audit_logs_schema_standalone() -> None:
    """Liste uçları mevcut request oturumuna dokunmadan tabloyu garanti altına alır."""
    global _obs_audit_standalone_bootstrapped
    if _obs_audit_standalone_bootstrapped:
        return
    from open_webui.internal.obs_db import ObsSessionLocal

    session = ObsSessionLocal()
    try:
        ensure_obs_audit_logs_schema(session, commit_now=True)
        _obs_audit_standalone_bootstrapped = True
    except Exception:
        log.exception("[OBS Audit] standalone şema oluşturulamadı")
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


def record_obs_audit_event_isolated(
    *,
    actor_user_id: Optional[str] = None,
    actor_label: str = "",
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    source: str = "api",
    impersonated_by_user_id: Optional[str] = None,
    plain_message: Optional[str] = None,
) -> None:
    """Ana OBS işlemini etkilememek için ayrı Session ile audit INSERT + commit."""
    from open_webui.internal.obs_db import ObsSessionLocal

    act = (action or "").strip()
    if not act:
        return
    details_str: Optional[str] = None
    if details is not None:
        try:
            details_str = json.dumps(details, ensure_ascii=False, default=str)
        except TypeError:
            details_str = json.dumps({"_raw": str(details)}, ensure_ascii=False)
        if len(details_str) > OBS_AUDIT_DETAILS_MAX_CHARS:
            details_str = json.dumps(
                {
                    "_truncated": True,
                    "preview": details_str[:8000],
                },
                ensure_ascii=False,
                default=str,
            )

    det_dict = details if isinstance(details, dict) else None
    if det_dict:
        em = str(det_dict.get("email") or "").strip()
        nm = str(det_dict.get("name") or "").strip()
        sno = str(det_dict.get("student_no") or "").strip()
        if em or nm or sno:
            label = _audit_display_label_from_parts(
                nm, em, sno, str(actor_user_id or "")
            )
        else:
            label = (actor_label or actor_user_id or "").strip() or "—"
    else:
        label = (actor_label or actor_user_id or "").strip() or "—"
    src = (source or "api").strip() or "api"
    summary_line = (plain_message or "").strip() or _audit_summary_line(
        action=act,
        actor_label=label,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        details=det_dict,
        source=src,
    )

    session = ObsSessionLocal()
    try:
        ensure_obs_audit_logs_schema(session, commit_now=True)
        colmap = obs_audit_logs_column_map(session)
        if not colmap:
            log.warning("[OBS Audit] tablo kolonları okunamadı, kayıt atlanıyor")
            return

        row_vals: dict[str, Any] = {}
        eid = str(uuid.uuid4())
        _audit_add_mapping(
            colmap, row_vals, ("id",), eid, skip_none=False
        )
        _audit_add_mapping(
            colmap,
            row_vals,
            ("action", "event", "event_type", "operation", "type"),
            act[:512],
            skip_none=False,
        )
        et_display = (entity_type or "")[:255] or None
        eid_display = _audit_safe_entity_id_value(session, colmap, entity_id)
        if details and isinstance(details, dict):
            pl = str(details.get("page_label") or details.get("api_label") or "").strip()
            pp = str(details.get("path") or "").strip()
            if pl and not et_display:
                et_display = pl[:255]
            if pp and not eid_display:
                eid_display = _audit_safe_entity_id_value(session, colmap, pp)
        _audit_add_mapping(
            colmap,
            row_vals,
            ("entity_type", "resource_type", "object_type", "target_type"),
            et_display,
        )
        _audit_add_mapping(
            colmap,
            row_vals,
            ("entity_id", "resource_id", "object_id", "target_id"),
            eid_display,
        )
        _audit_add_mapping(
            colmap, row_vals, ("user",), label[:512], skip_none=False
        )
        _audit_add_mapping(
            colmap,
            row_vals,
            ("actor_display", "actor_name", "username", "user_name", "full_name"),
            label[:512],
            skip_none=False,
        )
        _audit_add_mapping(
            colmap, row_vals, ("actor_user_id", "user_id", "subject_id"), actor_user_id
        )
        _audit_add_mapping(
            colmap,
            row_vals,
            ("details", "payload", "metadata", "log_data", "changes"),
            details_str,
        )
        for text_col in ("message", "description", "note", "comment"):
            _audit_add_mapping(colmap, row_vals, (text_col,), summary_line[:4000])
        _audit_add_mapping(colmap, row_vals, ("source", "origin"), src[:64], skip_none=False)
        _audit_add_mapping(
            colmap, row_vals, ("impersonated_by_user_id",), impersonated_by_user_id
        )

        if not row_vals:
            return

        def _execute_insert(rows: dict[str, Any]) -> None:
            qc = ", ".join(_audit_quote_ident(c) for c in rows.keys())
            params_i: dict[str, Any] = {}
            php: list[str] = []
            for i, (c, v) in enumerate(rows.items()):
                key_i = f"p{i}"
                php.append(f":{key_i}")
                params_i[key_i] = v
            session.execute(
                text(f"INSERT INTO obs_audit_logs ({qc}) VALUES ({', '.join(php)})"),
                params_i,
            )

        inserted = False
        last_exc: Optional[BaseException] = None
        try:
            _execute_insert(row_vals)
            session.commit()
            inserted = True
        except Exception as e0:
            last_exc = e0
            session.rollback()
            if _audit_err_is_uuid_mismatch(e0):
                _migrate_obs_audit_logs_text_columns(
                    session, commit_now=True, force=True
                )
                colmap = obs_audit_logs_column_map(session)
                eid_display = _audit_safe_entity_id_value(
                    session, colmap, entity_id
                )
                if details and isinstance(details, dict):
                    pl = str(
                        details.get("page_label")
                        or details.get("api_label")
                        or ""
                    ).strip()
                    pp = str(details.get("path") or "").strip()
                    if pl and not et_display:
                        et_display = pl[:255]
                    if pp and not eid_display:
                        eid_display = _audit_safe_entity_id_value(
                            session, colmap, pp
                        )
                row_vals = {}
                _audit_add_mapping(
                    colmap, row_vals, ("id",), eid, skip_none=False
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    ("action", "event", "event_type", "operation", "type"),
                    act[:512],
                    skip_none=False,
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    ("entity_type", "resource_type", "object_type", "target_type"),
                    et_display,
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    ("entity_id", "resource_id", "object_id", "target_id"),
                    eid_display,
                )
                _audit_add_mapping(
                    colmap, row_vals, ("user",), label[:512], skip_none=False
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    (
                        "actor_display",
                        "actor_name",
                        "username",
                        "user_name",
                        "full_name",
                    ),
                    label[:512],
                    skip_none=False,
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    ("actor_user_id", "user_id", "subject_id"),
                    actor_user_id,
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    ("details", "payload", "metadata", "log_data", "changes"),
                    details_str,
                )
                for text_col in ("message", "description", "note", "comment"):
                    _audit_add_mapping(
                        colmap, row_vals, (text_col,), summary_line[:4000]
                    )
                _audit_add_mapping(
                    colmap, row_vals, ("source", "origin"), src[:64], skip_none=False
                )
                _audit_add_mapping(
                    colmap,
                    row_vals,
                    ("impersonated_by_user_id",),
                    impersonated_by_user_id,
                )
                try:
                    _execute_insert(row_vals)
                    session.commit()
                    inserted = True
                    last_exc = None
                except Exception as e_retry:
                    last_exc = e_retry
                    session.rollback()
            if not inserted and "id" in row_vals:
                without_id = {k: v for k, v in row_vals.items() if k != "id"}
                if without_id:
                    try:
                        _execute_insert(without_id)
                        session.commit()
                        inserted = True
                    except Exception as e1:
                        last_exc = e1
                        session.rollback()
            if not inserted:
                mini = {}
                _audit_add_mapping(
                    colmap,
                    mini,
                    ("action", "event", "event_type", "operation", "type"),
                    act[:512],
                    skip_none=False,
                )
                _audit_add_mapping(
                    colmap,
                    mini,
                    ("user", "actor_display", "username", "user_name"),
                    label[:512],
                    skip_none=False,
                )
                _audit_add_mapping(
                    colmap,
                    mini,
                    ("actor_user_id", "user_id", "subject_id"),
                    actor_user_id,
                )
                _audit_add_mapping(
                    colmap,
                    mini,
                    ("entity_type", "resource_type"),
                    et_display,
                )
                _audit_add_mapping(
                    colmap,
                    mini,
                    ("entity_id", "resource_id"),
                    eid_display,
                )
                for text_col in (
                    "message",
                    "description",
                    "details",
                    "payload",
                    "metadata",
                    "note",
                ):
                    _audit_add_mapping(
                        colmap,
                        mini,
                        (text_col,),
                        summary_line[:4000] if not details_str else summary_line[:2000],
                    )
                if details_str:
                    _audit_add_mapping(
                        colmap,
                        mini,
                        ("details", "payload", "metadata"),
                        details_str,
                    )
                if mini:
                    try:
                        _execute_insert(mini)
                        session.commit()
                        inserted = True
                    except Exception as e2:
                        last_exc = e2
                        session.rollback()
            if not inserted and last_exc is not None:
                raise last_exc
    except Exception:
        log.warning(
            "[OBS Audit] kayıt yazılamadı action=%s",
            act,
            exc_info=True,
        )
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


def _audit_parse_details_blob(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def normalize_audit_log_row(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in r.items()}
    out["id"] = _str_id(out.get("id")) or ""
    disp = (
        out.get("user")
        or out.get("actor_display")
        or out.get("actor_name")
        or out.get("username")
        or out.get("user_label")
        or ""
    )
    uid = out.get("actor_user_id") or out.get("user_id") or out.get("subject_id")
    if not disp and uid:
        disp = str(uid)
    out["user"] = str(disp) if disp is not None else ""
    action_raw = str(
        out.get("action")
        or out.get("event")
        or out.get("event_type")
        or out.get("operation")
        or ""
    )
    out["action"] = action_raw
    out["action_label"] = _audit_action_label_tr(action_raw)
    et = (
        out.get("entity_type")
        or out.get("resource_type")
        or out.get("object_type")
        or ""
    )
    out["entity_type"] = str(et)
    eid = (
        out.get("entity_id")
        or out.get("resource_id")
        or out.get("object_id")
        or ""
    )
    out["entity_id"] = str(eid) if eid else ""
    ca = out.get("created_at")
    if hasattr(ca, "isoformat"):
        out["created_at"] = ca.isoformat()
    else:
        out["created_at"] = str(ca or "")

    det_parsed = _audit_parse_details_blob(out.get("details"))
    if not det_parsed:
        for alt in ("payload", "metadata", "log_data", "changes"):
            det_parsed = _audit_parse_details_blob(out.get(alt))
            if det_parsed:
                break
    page_path = (
        str(det_parsed.get("path") or "")
        or str(det_parsed.get("route") or "")
        or ""
    ).strip()
    if not page_path and out["entity_id"] and not str(out["entity_id"]).startswith(
        ("GET:", "POST:", "PUT:", "PATCH:", "DELETE:")
    ):
        page_path = str(out["entity_id"])
    if page_path.startswith("GET:") or page_path.startswith("POST:"):
        if ":" in page_path:
            page_path = page_path.split(":", 1)[1]
    page_label = (
        str(det_parsed.get("page_label") or "")
        or str(det_parsed.get("api_label") or "")
        or str(det_parsed.get("label") or "")
        or str(et or "")
    ).strip()
    out["page_path"] = page_path
    out["page_label"] = page_label

    msg = str(
        out.get("message") or out.get("description") or out.get("note") or ""
    ).strip()
    if det_parsed:
        out["details"] = json.dumps(det_parsed, ensure_ascii=False, default=str)
    elif out.get("details") is not None:
        out["details"] = str(out.get("details") or "")
    else:
        out["details"] = ""

    email = str(det_parsed.get("email") or "").strip()
    name = str(det_parsed.get("name") or "").strip()
    student_no = str(det_parsed.get("student_no") or "").strip()
    if email or name or student_no:
        out["user"] = _audit_display_label_from_parts(
            name, email, student_no, _str_id(uid) or ""
        )
    out["email"] = email
    out["name"] = name
    out["student_no"] = student_no
    out["http_method"] = str(det_parsed.get("http_method") or "")

    if msg:
        out["summary"] = msg
        if " | " in msg:
            segments = [s.strip() for s in msg.split(" | ") if s.strip()]
            if segments and (
                not out["user"] or out["user"] == _str_id(uid)
            ):
                out["user"] = segments[0]
            for seg in segments:
                up = seg.upper()
                if up.startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE ")):
                    bits = seg.split(None, 1)
                    if len(bits) == 2:
                        out["http_method"] = bits[0]
                        if not page_path:
                            page_path = bits[1].split("?", 1)[0]
                            out["page_path"] = page_path
                elif seg.startswith("HTTP ") and not out.get("status_code"):
                    try:
                        out["status_code"] = int(seg.replace("HTTP ", "").strip())
                    except ValueError:
                        pass
                elif not page_label and seg and seg != segments[0] and not seg.upper().startswith("HTTP"):
                    if not seg.startswith("?"):
                        page_label = seg
                        out["page_label"] = page_label
    else:
        out["summary"] = _audit_summary_line(
            action=action_raw,
            actor_label=out["user"],
            actor_user_id=_str_id(uid),
            entity_type=et or None,
            entity_id=out["entity_id"] or None,
            details=det_parsed or None,
            source=str(out.get("source") or out.get("origin") or ""),
        )
    uid_str = _str_id(uid)
    if uid_str:
        out["actor_user_id"] = uid_str
        out["user_id"] = uid_str
    return _enrich_audit_row_identity(out, {})


def _normalize_audit_log_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup_ids: list[str] = []
    for r in rows:
        uid = r.get("actor_user_id") or r.get("user_id") or r.get("subject_id")
        if uid:
            lookup_ids.append(str(uid))
    user_lookup = _audit_webui_user_lookup(lookup_ids)
    out: list[dict[str, Any]] = []
    for r in rows:
        n = normalize_audit_log_row(dict(r))
        out.append(_enrich_audit_row_identity(n, user_lookup))
    return out


def list_audit_logs(db: Session, limit: int) -> tuple[list, int]:
    try:
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
        raw = [dict(r) for r in rows]
        normalized = _normalize_audit_log_rows(raw)
        return normalized, len(normalized)
    except (ProgrammingError, OperationalError):
        ensure_obs_audit_logs_schema_standalone()
        try:
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
            raw = [dict(r) for r in rows]
            normalized = _normalize_audit_log_rows(raw)
            return normalized, len(normalized)
        except Exception:
            log.exception("[OBS Audit] liste okunamadı (retry sonrası)")
            return [], 0
    except Exception:
        log.exception("[OBS Audit] liste okunamadı")
        return [], 0


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
    allowed = {
        "staff_number",
        "title",
        "department_id",
        "office",
        "phone",
        "consulting_hours",
    }
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
                       ap.office, ap.phone, ap.consulting_hours, ap.created_at
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
        "consulting_hours": row.get("consulting_hours") or "",
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
                id, user_id, staff_number, title, department_id, office, phone,
                consulting_hours, created_at
            ) VALUES (
                :id, :uid, :staff, :title, :did, :office, :phone, :consulting_hours,
                CURRENT_TIMESTAMP
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
            "consulting_hours": _obs_opt_str(data.get("consulting_hours")) or "",
        },
    )
    db.commit()
    return aid


def get_academic_own_consulting_hours(
    db: Session, webui_user_id: str
) -> dict[str, Any]:
    """Akademisyen paneli: danışmanlık saatleri için mevcut metin."""
    row = (
        db.execute(
            text(
                "SELECT consulting_hours FROM obs_academic_profiles "
                "WHERE user_id = :uid LIMIT 1"
            ),
            {"uid": webui_user_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return {
            "academic_user_id": webui_user_id,
            "consulting_hours": "",
            "profile_exists": False,
        }
    return {
        "academic_user_id": webui_user_id,
        "consulting_hours": row.get("consulting_hours") or "",
        "profile_exists": True,
    }


def update_academic_own_consulting_hours(
    db: Session, webui_user_id: str, consulting_hours: str
) -> dict[str, Any]:
    """Akademisyen kendi danışmanlık saati metnini günceller; profil yoksa stub açar."""
    if not resolve_academic_profile_id(db, webui_user_id):
        ensure_academic_profile_for_user(db, webui_user_id)
    ch = consulting_hours if consulting_hours is not None else ""
    db.execute(
        text(
            "UPDATE obs_academic_profiles SET consulting_hours = :ch "
            "WHERE user_id = :uid"
        ),
        {"ch": ch or "", "uid": webui_user_id},
    )
    db.commit()
    row = (
        db.execute(
            text(
                "SELECT consulting_hours FROM obs_academic_profiles "
                "WHERE user_id = :uid LIMIT 1"
            ),
            {"uid": webui_user_id},
        )
        .mappings()
        .first()
    )
    return {
        "academic_user_id": webui_user_id,
        "consulting_hours": (row.get("consulting_hours") if row else "") or "",
        "profile_exists": True,
    }


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
