"""
Faz 2–4 Akademik Mock API

Veritabanı tablosu veya migration YOK; tüm yanıtlar bellek içi sabit veridir.
Üretime geçişte her endpoint gerçek servis/repository katmanıyla değiştirilir.

Router prefix haritası:
  public_router        → /api/v1           (giriş yapmış herkes)
  student_router       → /api/v1/student   (öğrenci; şimdilik token yeterli)
  academic_user_router → /api/v1/academic  (akademisyen)
  admin_router         → /api/v1/admin     (sadece admin)
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from open_webui.utils.auth import get_admin_user, get_verified_user, create_token
from open_webui.utils.utils import get_password_hash
from open_webui.models.auths import Auths
from open_webui.models.users import Users
from open_webui.internal.db import get_db

# ---------------------------------------------------------------------------
# Bellek içi sabit veri
# ---------------------------------------------------------------------------

_DEPARTMENTS: list[dict[str, Any]] = [
    {"id": "dept-1", "code": "MUH",  "name": "Mühendislik Fakültesi"},
    {"id": "dept-2", "code": "IIBF", "name": "İktisadi ve İdari Bilimler Fakültesi"},
    {"id": "dept-3", "code": "YBS",  "name": "Yönetim Bilişim Sistemleri"},
]

_TERMS: list[dict[str, Any]] = [
    {
        "id": "term-1",
        "name": "2025-2026 Güz",
        "academic_year": "2025-2026",
        "season": "fall",
        "starts_at": "2025-09-15",
        "ends_at": "2026-01-31",
        "is_active": False,
    },
    {
        "id": "term-2",
        "name": "2025-2026 Bahar",
        "academic_year": "2025-2026",
        "season": "spring",
        "starts_at": "2026-02-10",
        "ends_at": "2026-06-30",
        "is_active": True,
    },
]

_CLASSROOMS: list[dict[str, Any]] = [
    {"id": "room-1", "building": "A Blok", "name": "A-101", "capacity": 40, "is_online": False},
    {"id": "room-2", "building": "B Blok", "name": "B-205", "capacity": 60, "is_online": False},
    {"id": "room-3", "building": "Lab",    "name": "L-01",  "capacity": 30, "is_online": False},
    {"id": "room-4", "building": "Online", "name": "DouOnline", "capacity": 200, "is_online": True},
]

_COURSES: list[dict[str, Any]] = [
    {"id": "crs-1", "department_id": "dept-1", "code": "BLM101", "name": "Programlamaya Giriş",           "credits": 4, "akts": 6, "class_year": 1, "type": "Z", "theory_hours": "3+1", "language": "Türkçe"},
    {"id": "crs-2", "department_id": "dept-1", "code": "BLM102", "name": "Veri Yapıları",                 "credits": 4, "akts": 6, "class_year": 2, "type": "Z", "theory_hours": "3+1", "language": "Türkçe"},
    {"id": "crs-3", "department_id": "dept-3", "code": "YBS492", "name": "Bitirme Projesi",               "credits": 2, "akts": 7, "class_year": 4, "type": "Z", "theory_hours": "0+2", "language": "Türkçe"},
    {"id": "crs-4", "department_id": "dept-3", "code": "YBS301", "name": "Veritabanı Yönetim Sistemleri", "credits": 3, "akts": 5, "class_year": 3, "type": "Z", "theory_hours": "2+2", "language": "Türkçe"},
    {"id": "crs-5", "department_id": "dept-3", "code": "YBS201", "name": "Sistem Analizi ve Tasarım",     "credits": 3, "akts": 5, "class_year": 2, "type": "Z", "theory_hours": "3+0", "language": "Türkçe"},
]

_SECTIONS: list[dict[str, Any]] = [
    {
        "id": "sec-1", "course_id": "crs-1", "course_code": "BLM101",
        "course_name": "Programlamaya Giriş", "section_code": "A", "section_no": 1,
        "term_id": "term-2", "instructor_id": "mock-acad-1",
        "instructor_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
        "classroom": "A-101", "day_of_week": "Pazartesi",
        "start_time": "09:00", "end_time": "10:50",
        "enrollment_count": 42, "capacity": 50,
    },
    {
        "id": "sec-2", "course_id": "crs-2", "course_code": "BLM102",
        "course_name": "Veri Yapıları", "section_code": "B", "section_no": 2,
        "term_id": "term-2", "instructor_id": "mock-acad-1",
        "instructor_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
        "classroom": "B-205", "day_of_week": "Çarşamba",
        "start_time": "13:00", "end_time": "14:50",
        "enrollment_count": 38, "capacity": 60,
    },
    {
        "id": "sec-3", "course_id": "crs-3", "course_code": "YBS492",
        "course_name": "Bitirme Projesi", "section_code": "A", "section_no": 1,
        "term_id": "term-2", "instructor_id": "mock-acad-2",
        "instructor_name": "Doç. Dr. Mehmet Kaya",
        "classroom": "L-01", "day_of_week": "Cuma",
        "start_time": "10:00", "end_time": "11:50",
        "enrollment_count": 12, "capacity": 30,
    },
    {
        "id": "sec-4", "course_id": "crs-4", "course_code": "YBS301",
        "course_name": "Veritabanı Yönetim Sistemleri", "section_code": "A", "section_no": 1,
        "term_id": "term-2", "instructor_id": "mock-acad-2",
        "instructor_name": "Doç. Dr. Mehmet Kaya",
        "classroom": "B-205", "day_of_week": "Salı",
        "start_time": "11:00", "end_time": "12:50",
        "enrollment_count": 35, "capacity": 60,
    },
    {
        "id": "sec-5", "course_id": "crs-5", "course_code": "YBS201",
        "course_name": "Sistem Analizi ve Tasarım", "section_code": "A", "section_no": 1,
        "term_id": "term-2", "instructor_id": "mock-acad-1",
        "instructor_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
        "classroom": "A-101", "day_of_week": "Perşembe",
        "start_time": "14:00", "end_time": "15:50",
        "enrollment_count": 28, "capacity": 40,
    },
]

_ADVISOR = {
    "academic_user_id": "mock-acad-1",
    "name":             "Dr. Öğr. Üyesi Ayşe Yılmaz",
    "title":            "Dr. Öğr. Üyesi",
    "email":            "ayse.yilmaz@example.edu",
    "department_id":    "dept-3",
    "department_name":  "Yönetim Bilişim Sistemleri",
    "office":           "A-215",
    "phone":            "+90 216 000 00 01",
}

_EXAM_TYPES = ["midterm", "final", "makeup", "project"]

_CALENDAR_EVENTS: list[dict[str, Any]] = [
    {"id": "cal-1", "term_id": "term-2", "event_type": "ENROLLMENT",          "title": "Ders Kayıt Dönemi",         "start_date": "2026-02-01", "end_date": "2026-02-15"},
    {"id": "cal-2", "term_id": "term-2", "event_type": "ADD_DROP",            "title": "Ders Ekle/Bırak",           "start_date": "2026-02-16", "end_date": "2026-02-22"},
    {"id": "cal-3", "term_id": "term-2", "event_type": "MIDTERM_GRADE_ENTRY", "title": "Vize Not Girişi",           "start_date": "2026-04-14", "end_date": "2026-04-25"},
    {"id": "cal-4", "term_id": "term-2", "event_type": "FINAL_GRADE_ENTRY",   "title": "Final Not Girişi",          "start_date": "2026-06-10", "end_date": "2026-06-25"},
    {"id": "cal-5", "term_id": "term-2", "event_type": "ADVISOR_APPROVAL",    "title": "Danışman Onay Penceresi",   "start_date": "2026-02-15", "end_date": "2026-02-28"},
    {"id": "cal-6", "term_id": "term-2", "event_type": "GRADE_PUBLISH",       "title": "Not Yayınlama",             "start_date": "2026-06-28", "end_date": "2026-06-30"},
    {"id": "cal-7", "term_id": "term-2", "event_type": "ATTENDANCE_ENTRY",    "title": "Yoklama Giriş Penceresi",   "start_date": "2026-02-10", "end_date": "2026-06-30"},
]

_REGISTRATION_SETTINGS: dict[str, Any] = {
    "id": "rs-1",
    "term_id": "term-2",
    "max_akts": 30,
    "bonus_akts": 6,
    "gpa_threshold": 2.50,
    "enrollment_deadline": "2026-02-15",
    "add_drop_deadline": "2026-02-22",
}

_ANNOUNCEMENTS: list[dict[str, Any]] = [
    {
        "id": "ann-1",
        "title": "2025-2026 Bahar Dönemi Ders Kayıt Tarihleri",
        "content": "Bahar dönemi ders kayıt işlemleri 1-15 Şubat 2026 tarihleri arasında gerçekleştirilecektir.",
        "audience_type": "all",
        "department_id": None,
        "is_active": True,
        "published_at": "2026-01-20T09:00:00",
        "created_by": "Admin",
    },
    {
        "id": "ann-2",
        "title": "YBS Bölümü Bitirme Projesi Danışman Atamaları",
        "content": "Bitirme Projesi danışman atamaları 10 Şubat 2026 tarihine kadar tamamlanacaktır.",
        "audience_type": "department",
        "department_id": "dept-3",
        "is_active": True,
        "published_at": "2026-01-25T10:00:00",
        "created_by": "Dr. Öğr. Üyesi Ayşe Yılmaz",
    },
    {
        "id": "ann-3",
        "title": "Harç Ödeme Son Tarihi Hatırlatması",
        "content": "2025-2026 Bahar dönemi harç ödemelerinin 20 Şubat 2026 tarihine kadar tamamlanması gerekmektedir.",
        "audience_type": "all",
        "department_id": None,
        "is_active": True,
        "published_at": "2026-01-28T08:00:00",
        "created_by": "Admin",
    },
]

_MESSAGES: list[dict[str, Any]] = [
    {
        "id": "msg-1",
        "sender_user_id": "mock-acad-1",
        "sender_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
        "sender_type": "akademisyen",
        "receiver_type": "öğrenci",
        "subject": "Danışmanlık Görüşmesi",
        "body": "Merhaba, bu haftaki danışmanlık görüşmemiz için Perşembe 14:00'de A-215 numaralı odama gelebilir misiniz?",
        "is_read": False,
        "status": "new",
        "sent_at": "2026-04-15T10:30:00",
    },
    {
        "id": "msg-2",
        "sender_user_id": "mock-admin",
        "sender_name": "Öğrenci İşleri",
        "sender_type": "sistem",
        "receiver_type": "öğrenci",
        "subject": "Kayıt Yenileme Hatırlatması",
        "body": "Sayın öğrencimiz, 2025-2026 Bahar dönemi ders kaydınızı yenilemeyi unutmayınız.",
        "is_read": True,
        "status": "read",
        "sent_at": "2026-01-20T09:00:00",
    },
]

_SENT_MESSAGES: list[dict[str, Any]] = [
    {
        "id": "msg-3",
        "receiver_user_id": "mock-acad-1",
        "receiver_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
        "receiver_type": "akademisyen",
        "sender_type": "öğrenci",
        "subject": "Danışmanlık Toplantısı Talebi",
        "body": "Hocam, müsait olduğunuzda bir görüşme ayarlayabilir miyiz?",
        "is_read": True,
        "status": "active",
        "sent_at": "2026-04-10T14:22:00",
    },
]

_DOCUMENT_REQUESTS: list[dict[str, Any]] = [
    {
        "id": "doc-1",
        "requesting_institution": "İş Bankası",
        "request_reason": "Burs başvurusu",
        "document_type": "öğrenci_belgesi",
        "document_subtype": "Türkçe",
        "status": "tamamlandı",
        "created_at": "2026-01-05T11:00:00",
    },
]

_APPROVAL_REQUESTS: list[dict[str, Any]] = [
    {
        "id": "apr-1",
        "student_name": "Ali Veli",
        "student_no": "20240001",
        "request_type": "enrollment",
        "related_enrollment_id": "enr-1",
        "course_code": "BLM101",
        "course_name": "Programlamaya Giriş",
        "status": "pending",
        "note": None,
        "created_at": "2026-02-12T10:00:00",
    },
    {
        "id": "apr-2",
        "student_name": "Fatma Kaya",
        "student_no": "20240002",
        "request_type": "enrollment",
        "related_enrollment_id": "enr-2",
        "course_code": "YBS301",
        "course_name": "Veritabanı Yönetim Sistemleri",
        "status": "approved",
        "note": "Onaylandı",
        "created_at": "2026-02-11T09:00:00",
    },
]

# Oturum ömrü boyunca biriken CRUD kayıtları
_created: dict[str, list[dict[str, Any]]] = {
    "departments":     [],
    "terms":           [],
    "courses":         [],
    "classrooms":      [],
    "course_sections": [],
    "calendar_events": [],
    "document_requests": [],
    "messages":        [],
}

# ---------------------------------------------------------------------------
# Router tanımları
# ---------------------------------------------------------------------------

public_router        = APIRouter(tags=["dou-mock-public"])
student_router       = APIRouter(tags=["dou-mock-student"])
academic_user_router = APIRouter(tags=["dou-mock-academic"])
admin_router         = APIRouter(tags=["dou-mock-admin"])


# ===========================================================================
# DEV / TEST — şifresiz seed
# ===========================================================================

_DEV_ACCOUNTS = [
    {"email": "ogrenci@dou.edu.tr",     "name": "Ramazan Öğrenci",   "password": "Obs1234!",  "role": "user"},
    {"email": "akademisyen@dou.edu.tr", "name": "Dr. Ayşe Yılmaz",   "password": "Obs1234!",  "role": "user"},
    {"email": "admin@dou.edu.tr",       "name": "Sistem Yöneticisi", "password": "Obs1234!",  "role": "admin"},
]

# OBS rolü (obsRole field) — Open WebUI'nin "role" alanı admin/user, OBS rolü ayrı tutulur
_OBS_ROLE_MAP = {
    "ogrenci@dou.edu.tr":     "ogrenci",
    "akademisyen@dou.edu.tr": "Akademisyen",
    "admin@dou.edu.tr":       "Admin",
}


@public_router.post("/dev/seed-users", summary="[DEV] Test kullanıcıları oluştur veya döndür", include_in_schema=True)
async def dev_seed_users(db: Session = Depends(get_db)):
    """
    Geliştirme ortamı için 3 test hesabı oluşturur.
    Hesap zaten varsa atlar. Oluşturulan / mevcut hesap bilgilerini döndürür.
    """
    result = []
    for acc in _DEV_ACCOUNTS:
        email = acc["email"]
        existing = Users.get_user_by_email(email, db=db)
        if not existing:
            hashed = get_password_hash(acc["password"])
            new_user = Auths.insert_new_auth(
                email=email,
                password=hashed,
                name=acc["name"],
                profile_image_url="",
                role=acc["role"],
                db=db,
            )
            if new_user:
                # admin@dou.edu.tr'yi admin yap
                if acc["role"] == "admin":
                    Users.update_user_role_by_id(new_user.id, "admin", db=db)
            user_id = new_user.id if new_user else "?"
        else:
            user_id = existing.id
        result.append({
            "email":    email,
            "password": acc["password"],
            "name":     acc["name"],
            "obs_role": _OBS_ROLE_MAP[email],
            "user_id":  user_id,
            "existed":  existing is not None,
        })
    return {"accounts": result, "_mock": True}


@public_router.get("/dev/obs-role", summary="[DEV] Kullanıcının OBS rolünü döndür")
async def dev_obs_role(user=Depends(get_verified_user)):
    """Giriş yapan kullanıcının e-postasına göre OBS rolünü döndürür."""
    email = getattr(user, "email", "") or ""
    obs_role = _OBS_ROLE_MAP.get(email)
    if not obs_role:
        # Admin Open WebUI rolü varsa Admin OBS rolü ver
        role = getattr(user, "role", "user")
        if role == "admin":
            obs_role = "Admin"
        else:
            obs_role = "ogrenci"
    return {"obs_role": obs_role, "email": email, "_mock": True}


# ===========================================================================
# ORTAK (giriş yapmış herkes)
# ===========================================================================

@public_router.get("/terms", summary="Dönem listesi")
async def list_terms(_user=Depends(get_verified_user)):
    return _TERMS + _created["terms"]


@public_router.get("/terms/{term_id}/calendar", summary="Dönem takvim etkinlikleri")
async def term_calendar(term_id: str, _user=Depends(get_verified_user)):
    events = [e for e in _CALENDAR_EVENTS + _created["calendar_events"] if e["term_id"] == term_id]
    return {"term_id": term_id, "events": events, "_mock": True}


@public_router.get("/departments", summary="Bölüm listesi")
async def list_departments(_user=Depends(get_verified_user)):
    return _DEPARTMENTS + _created["departments"]


@public_router.get("/announcements", summary="Duyuru listesi (hedefli)")
async def list_announcements(
    audience_type: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    _user=Depends(get_verified_user),
):
    result = [a for a in _ANNOUNCEMENTS if a["is_active"]]
    if audience_type:
        result = [a for a in result if a["audience_type"] in (audience_type, "all")]
    if department_id:
        result = [a for a in result if a["department_id"] in (department_id, None)]
    return {"announcements": result, "_mock": True}


# ===========================================================================
# MESAJLAR (giriş yapmış herkes)
# ===========================================================================

@public_router.get("/messages/inbox", summary="Gelen mesajlar")
async def messages_inbox(
    sender_type: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    msgs = [m for m in _MESSAGES if m.get("status") != "deleted"]
    if sender_type:
        msgs = [m for m in msgs if m.get("sender_type") == sender_type]
    return {"user_id": user.id, "messages": msgs, "total": len(msgs), "_mock": True}


@public_router.get("/messages/sent", summary="Gönderilen mesajlar")
async def messages_sent(
    receiver_type: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    msgs = [m for m in _SENT_MESSAGES if m.get("status") != "deleted"]
    if receiver_type:
        msgs = [m for m in msgs if m.get("receiver_type") == receiver_type]
    return {"user_id": user.id, "messages": msgs, "total": len(msgs), "_mock": True}


class MessageCreate(BaseModel):
    receiver_user_id: Optional[str] = None
    receiver_name: str = ""
    receiver_type: str = "akademisyen"
    subject: str
    body: str


@public_router.post("/messages", status_code=status.HTTP_201_CREATED, summary="Mesaj gönder")
async def send_message(body: MessageCreate, user=Depends(get_verified_user)):
    row = {
        "id":               f"msg-{uuid.uuid4().hex[:8]}",
        "receiver_user_id": body.receiver_user_id,
        "receiver_name":    body.receiver_name,
        "receiver_type":    body.receiver_type,
        "sender_type":      "öğrenci",
        "subject":          body.subject,
        "body":             body.body,
        "is_read":          False,
        "status":           "active",
        "sent_at":          "2026-04-19T12:00:00",
    }
    _created["messages"].append(row)
    return row


@public_router.patch("/messages/{message_id}/read", summary="Okundu işaretle")
async def mark_read(message_id: str, _user=Depends(get_verified_user)):
    for m in _MESSAGES:
        if m["id"] == message_id:
            m["is_read"] = True
            m["status"]  = "read"
            return {"id": message_id, "is_read": True, "_mock": True}
    raise HTTPException(status_code=404, detail="Mesaj bulunamadı")


@public_router.delete("/messages/{message_id}", summary="Mesaj sil (soft)")
async def delete_message(message_id: str, _user=Depends(get_verified_user)):
    for m in _MESSAGES + _SENT_MESSAGES:
        if m["id"] == message_id:
            m["status"] = "deleted"
            return {"id": message_id, "status": "deleted", "_mock": True}
    raise HTTPException(status_code=404, detail="Mesaj bulunamadı")


# ===========================================================================
# ÖĞRENCİ
# ===========================================================================

@student_router.get("/me/profile", summary="Öğrenci profili")
async def student_me_profile(user=Depends(get_verified_user)):
    overrides = _STUDENT_PROFILE_OVERRIDES.get(user.id, {})
    base = {
        "user_id":          user.id,
        "email":            user.email,
        "full_name":        getattr(user, "name", "Ad Soyad"),
        "student_no":       "20240001",
        "department_id":    "dept-3",
        "department_name":  "Yönetim Bilişim Sistemleri",
        "faculty_name":     "İktisadi ve İdari Bilimler Fakültesi",
        "program":          "Lisans",
        "class_level":      3,
        "gpa":              3.21,   # AGNO — kümülatif
        "dno":              3.42,   # dönem not ortalaması (aktif dönem)
        "completed_akts":   87,
        "total_akts_required": 120,
        "phone":            "",
        "address":          "",
        "emergency_contact": "",
        "emergency_phone":  "",
        "status":           "active",
        "enrollment_date":  "2021-09-15",
        "is_financially_eligible": True,
        "_mock":            True,
    }
    base.update(overrides)
    return base


@student_router.get("/me/advisor", summary="Danışman bilgisi")
async def student_me_advisor(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "advisor":         _ADVISOR,
        "valid_from":      "2021-09-15",
        "valid_to":        None,
        "_mock":           True,
    }


@student_router.get("/me/enrollments", summary="Ders kayıtları")
async def student_me_enrollments(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    rows = [
        {
            "id": "enr-1", "student_id": user.id, "section_id": "sec-1",
            "course_code": "BLM101", "course_name": "Programlamaya Giriş",
            "instructor_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
            "credits": 4, "akts": 6, "term_id": "term-2",
            "classroom": "A-101", "day_of_week": "Pazartesi",
            "start_time": "09:00", "end_time": "10:50",
            "section_no": 1, "theory_hours": "3+1", "language": "Türkçe",
            "class_year": 1, "type": "Z", "status": "active",
        },
        {
            "id": "enr-2", "student_id": user.id, "section_id": "sec-2",
            "course_code": "BLM102", "course_name": "Veri Yapıları",
            "instructor_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
            "credits": 4, "akts": 6, "term_id": "term-2",
            "classroom": "B-205", "day_of_week": "Çarşamba",
            "start_time": "13:00", "end_time": "14:50",
            "section_no": 2, "theory_hours": "3+1", "language": "Türkçe",
            "class_year": 2, "type": "Z", "status": "active",
        },
        {
            "id": "enr-3", "student_id": user.id, "section_id": "sec-3",
            "course_code": "YBS492", "course_name": "Bitirme Projesi",
            "instructor_name": "Doç. Dr. Mehmet Kaya",
            "credits": 2, "akts": 7, "term_id": "term-2",
            "classroom": "L-01", "day_of_week": "Cuma",
            "start_time": "10:00", "end_time": "11:50",
            "section_no": 1, "theory_hours": "0+2", "language": "Türkçe",
            "class_year": 4, "type": "Z", "status": "active",
        },
        {
            "id": "enr-4", "student_id": user.id, "section_id": "sec-4",
            "course_code": "YBS301", "course_name": "Veritabanı Yönetim Sistemleri",
            "instructor_name": "Doç. Dr. Mehmet Kaya",
            "credits": 3, "akts": 5, "term_id": "term-2",
            "classroom": "B-205", "day_of_week": "Salı",
            "start_time": "11:00", "end_time": "12:50",
            "section_no": 1, "theory_hours": "2+2", "language": "Türkçe",
            "class_year": 3, "type": "Z", "status": "active",
        },
        {
            "id": "enr-5", "student_id": user.id, "section_id": "sec-5",
            "course_code": "YBS201", "course_name": "Sistem Analizi ve Tasarım",
            "instructor_name": "Dr. Öğr. Üyesi Ayşe Yılmaz",
            "credits": 3, "akts": 5, "term_id": "term-2",
            "classroom": "A-101", "day_of_week": "Perşembe",
            "start_time": "14:00", "end_time": "15:50",
            "section_no": 1, "theory_hours": "3+0", "language": "Türkçe",
            "class_year": 2, "type": "Z", "status": "active",
        },
    ]
    if term_id:
        rows = [r for r in rows if r["term_id"] == term_id]
    total_akts = sum(r["akts"] for r in rows if r["status"] == "active")
    return {"student_user_id": user.id, "term_id_filter": term_id, "enrollments": rows, "total_akts": total_akts, "_mock": True}


@student_router.get("/me/schedule", summary="Haftalık ders programı")
async def student_me_schedule(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    schedule = [
        {"day": "Pazartesi",  "start": "09:00", "end": "10:50", "course_code": "BLM101", "course_name": "Programlamaya Giriş",           "classroom": "A-101", "instructor": "Dr. Öğr. Üy. Ayşe Yılmaz"},
        {"day": "Salı",       "start": "11:00", "end": "12:50", "course_code": "YBS301", "course_name": "Veritabanı Yönetim Sistemleri", "classroom": "B-205", "instructor": "Doç. Dr. Mehmet Kaya"},
        {"day": "Çarşamba",   "start": "13:00", "end": "14:50", "course_code": "BLM102", "course_name": "Veri Yapıları",                 "classroom": "B-205", "instructor": "Dr. Öğr. Üy. Ayşe Yılmaz"},
        {"day": "Perşembe",   "start": "14:00", "end": "15:50", "course_code": "YBS201", "course_name": "Sistem Analizi ve Tasarım",     "classroom": "A-101", "instructor": "Dr. Öğr. Üy. Ayşe Yılmaz"},
        {"day": "Cuma",       "start": "10:00", "end": "11:50", "course_code": "YBS492", "course_name": "Bitirme Projesi",               "classroom": "L-01",  "instructor": "Doç. Dr. Mehmet Kaya"},
    ]
    return {"student_user_id": user.id, "term_id": term_id or "term-2", "schedule": schedule, "_mock": True}


@student_router.get("/me/exams", summary="Sınav takvimi")
async def student_me_exams(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    exams = [
        {"id": "ex-1", "course_code": "BLM101", "course_name": "Programlamaya Giriş",           "exam_type": "midterm", "exam_date": "2026-04-20", "exam_time": "09:00", "classroom": "A-101", "weight_percent": 40},
        {"id": "ex-2", "course_code": "BLM102", "course_name": "Veri Yapıları",                 "exam_type": "midterm", "exam_date": "2026-04-21", "exam_time": "13:00", "classroom": "B-205", "weight_percent": 40},
        {"id": "ex-3", "course_code": "YBS301", "course_name": "Veritabanı Yönetim Sistemleri", "exam_type": "midterm", "exam_date": "2026-04-22", "exam_time": "11:00", "classroom": "B-205", "weight_percent": 40},
        {"id": "ex-4", "course_code": "YBS201", "course_name": "Sistem Analizi ve Tasarım",     "exam_type": "midterm", "exam_date": "2026-04-23", "exam_time": "14:00", "classroom": "A-101", "weight_percent": 40},
        {"id": "ex-5", "course_code": "YBS492", "course_name": "Bitirme Projesi",               "exam_type": "project", "exam_date": "2026-04-25", "exam_time": "10:00", "classroom": "L-01",  "weight_percent": 100},
        {"id": "ex-6", "course_code": "BLM101", "course_name": "Programlamaya Giriş",           "exam_type": "final",   "exam_date": "2026-06-15", "exam_time": "09:00", "classroom": "A-101", "weight_percent": 60},
        {"id": "ex-7", "course_code": "BLM102", "course_name": "Veri Yapıları",                 "exam_type": "final",   "exam_date": "2026-06-17", "exam_time": "13:00", "classroom": "B-205", "weight_percent": 60},
    ]
    return {"student_user_id": user.id, "exams": exams, "_mock": True}


@student_router.get("/me/grades", summary="Not listesi")
async def student_me_grades(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    rows = [
        {"enrollment_id": "enr-1", "course_code": "BLM101", "course_name": "Programlamaya Giriş",           "term_id": "term-2", "midterm": 75, "final": 82, "letter_grade": "BB", "is_published": True,  "is_finalized": True},
        {"enrollment_id": "enr-2", "course_code": "BLM102", "course_name": "Veri Yapıları",                 "term_id": "term-2", "midterm": 88, "final": None, "letter_grade": None, "is_published": False, "is_finalized": False},
        {"enrollment_id": "enr-3", "course_code": "YBS492", "course_name": "Bitirme Projesi",               "term_id": "term-2", "midterm": None, "final": None, "letter_grade": None, "is_published": False, "is_finalized": False},
        {"enrollment_id": "enr-4", "course_code": "YBS301", "course_name": "Veritabanı Yönetim Sistemleri", "term_id": "term-2", "midterm": 91, "final": None,  "letter_grade": None, "is_published": False, "is_finalized": False},
        {"enrollment_id": "enr-5", "course_code": "YBS201", "course_name": "Sistem Analizi ve Tasarım",     "term_id": "term-2", "midterm": 68, "final": None,  "letter_grade": None, "is_published": False, "is_finalized": False},
    ]
    if term_id:
        rows = [r for r in rows if r["term_id"] == term_id]
    return {"student_user_id": user.id, "grades": rows, "_mock": True}


@student_router.get("/me/gpa-summary", summary="GPA özeti")
async def student_me_gpa_summary(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    terms_gpa = [
        {"term_id": "term-1", "term_name": "2025-2026 Güz",   "term_gpa": 3.42, "akts_completed": 28, "akts_passed": 28},
        {"term_id": "term-2", "term_name": "2025-2026 Bahar", "term_gpa": None, "akts_completed": 0,  "akts_passed": 0},
    ]
    return {
        "student_user_id": user.id,
        "cumulative_gpa":  3.21,
        "total_akts_completed": 87,
        "class_level": 3,
        "terms": terms_gpa,
        "_mock": True,
    }


@student_router.get("/me/transcript", summary="Transkript")
async def student_me_transcript(user=Depends(get_verified_user)):
    transcript = [
        {
            "term_name": "2024-2025 Güz",
            "courses": [
                {"code": "BLM001", "name": "Matematik I",           "credits": 4, "akts": 6, "letter": "AA", "grade_point": 4.0},
                {"code": "BLM002", "name": "Fizik I",               "credits": 3, "akts": 5, "letter": "BA", "grade_point": 3.5},
                {"code": "YBS100", "name": "İşletmeye Giriş",       "credits": 3, "akts": 4, "letter": "BB", "grade_point": 3.0},
            ],
            "term_gpa": 3.53, "term_akts": 15,
        },
        {
            "term_name": "2024-2025 Bahar",
            "courses": [
                {"code": "BLM003", "name": "Matematik II",          "credits": 4, "akts": 6, "letter": "CB", "grade_point": 2.5},
                {"code": "BLM004", "name": "Veri Tabanı Temelleri", "credits": 3, "akts": 5, "letter": "BB", "grade_point": 3.0},
                {"code": "YBS110", "name": "Bilgi Sistemleri",      "credits": 3, "akts": 4, "letter": "BA", "grade_point": 3.5},
            ],
            "term_gpa": 3.01, "term_akts": 15,
        },
        {
            "term_name": "2025-2026 Güz",
            "courses": [
                {"code": "BLM101", "name": "Programlamaya Giriş",   "credits": 4, "akts": 6, "letter": "BB", "grade_point": 3.0},
                {"code": "BLM102", "name": "Veri Yapıları",         "credits": 4, "akts": 6, "letter": "BA", "grade_point": 3.5},
                {"code": "YBS201", "name": "Sistem Analizi",        "credits": 3, "akts": 5, "letter": "AA", "grade_point": 4.0},
                {"code": "YBS301", "name": "Veritabanı YS",         "credits": 3, "akts": 5, "letter": "BB", "grade_point": 3.0},
            ],
            "term_gpa": 3.42, "term_akts": 22,
        },
    ]
    return {
        "student_user_id": user.id,
        "cumulative_gpa":  3.21,
        "total_akts":      87,
        "transcript":      transcript,
        "_mock":           True,
    }


@student_router.get("/me/attendance", summary="Devamsızlık durumu")
async def student_me_attendance(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    rows = [
        {"course_code": "BLM101", "course_name": "Programlamaya Giriş",           "total_weeks": 14, "absent_count": 2, "attendance_pct": 85.7, "status": "ok"},
        {"course_code": "BLM102", "course_name": "Veri Yapıları",                 "total_weeks": 14, "absent_count": 5, "attendance_pct": 64.3, "status": "warning"},
        {"course_code": "YBS492", "course_name": "Bitirme Projesi",               "total_weeks": 14, "absent_count": 0, "attendance_pct": 100.0,"status": "ok"},
        {"course_code": "YBS301", "course_name": "Veritabanı Yönetim Sistemleri", "total_weeks": 14, "absent_count": 1, "attendance_pct": 92.9, "status": "ok"},
        {"course_code": "YBS201", "course_name": "Sistem Analizi ve Tasarım",     "total_weeks": 14, "absent_count": 4, "attendance_pct": 71.4, "status": "warning"},
    ]
    return {"student_user_id": user.id, "attendance": rows, "_mock": True}


@student_router.get("/me/document-requests", summary="Belge talepleri")
async def student_me_document_requests(user=Depends(get_verified_user)):
    return {"student_user_id": user.id, "requests": _DOCUMENT_REQUESTS + _created["document_requests"], "_mock": True}


class DocumentRequestCreate(BaseModel):
    requesting_institution: str
    request_reason: str
    document_type: str = Field(..., description="transkript / öğrenci_belgesi / disiplin_belgesi")
    document_subtype: str = Field(..., description="Resmi / Onaysız / Türkçe / İngilizce")


_VALID_SUBTYPE_MAP: dict[str, list[str]] = {
    "transkript":       ["Resmi", "Onaysız"],
    "öğrenci_belgesi":  ["Türkçe", "İngilizce"],
    "disiplin_belgesi": ["Türkçe", "İngilizce"],
}


@student_router.post("/me/document-requests", status_code=status.HTTP_201_CREATED, summary="Belge talebi gönder")
async def student_create_document_request(body: DocumentRequestCreate, user=Depends(get_verified_user)):
    valid_subs = _VALID_SUBTYPE_MAP.get(body.document_type, [])
    if body.document_subtype not in valid_subs:
        raise HTTPException(status_code=400, detail=f"{body.document_type} için geçerli alt tipler: {valid_subs}")
    row = {
        "id":                     f"doc-{uuid.uuid4().hex[:8]}",
        "student_user_id":        user.id,
        "requesting_institution": body.requesting_institution,
        "request_reason":         body.request_reason,
        "document_type":          body.document_type,
        "document_subtype":       body.document_subtype,
        "status":                 "bekliyor",
        "created_at":             "2026-04-19T12:00:00",
    }
    _created["document_requests"].append(row)
    return row


@student_router.get("/me/announcements", summary="Öğrenciye yönelik duyurular")
async def student_me_announcements(user=Depends(get_verified_user)):
    result = [a for a in _ANNOUNCEMENTS if a["is_active"] and a["audience_type"] in ("all", "department")]
    return {"student_user_id": user.id, "announcements": result, "_mock": True}


class StudentProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None


_STUDENT_PROFILE_OVERRIDES: dict[str, dict] = {}


@student_router.get("/available-courses", summary="Açılan ders listesi (kayıt dönemi)")
async def student_available_courses(
    term_id: Optional[str] = Query(None),
    _user=Depends(get_verified_user),
):
    already_enrolled_codes = {"BLM101", "BLM102", "YBS492", "YBS301", "YBS201"}
    available = [
        s for s in _SECTIONS
        if s["course_code"] not in already_enrolled_codes
        and (not term_id or s.get("term_id") == term_id)
    ]
    if not available:
        available = [
            {"id": "sec-a1", "course_code": "YBS401", "course_name": "Proje Yönetimi",            "credits": 3, "akts": 5,  "instructor_name": "Dr. Ayşe Yılmaz",    "day_of_week": "Pazartesi", "start_time": "13:00", "end_time": "16:00", "classroom": "B-201", "capacity": 30, "enrolled": 22},
            {"id": "sec-a2", "course_code": "YBS402", "course_name": "Bilgi Güvenliği",           "credits": 3, "akts": 5,  "instructor_name": "Dr. Mehmet Demir",   "day_of_week": "Salı",      "start_time": "11:00", "end_time": "14:00", "classroom": "A-301", "capacity": 25, "enrolled": 18},
            {"id": "sec-a3", "course_code": "YBS403", "course_name": "Yapay Zeka",                "credits": 3, "akts": 6,  "instructor_name": "Prof. Ahmet Kaya",   "day_of_week": "Çarşamba",  "start_time": "09:00", "end_time": "12:00", "classroom": "B-101", "capacity": 35, "enrolled": 35},
            {"id": "sec-a4", "course_code": "BLM301", "course_name": "Ağ ve İletişim Sistemleri", "credits": 3, "akts": 5,  "instructor_name": "Dr. Zeynep Demir",   "day_of_week": "Perşembe",  "start_time": "14:00", "end_time": "17:00", "classroom": "A-201", "capacity": 30, "enrolled": 10},
            {"id": "sec-a5", "course_code": "BLM302", "course_name": "Mobil Uygulama Geliştirme", "credits": 3, "akts": 5,  "instructor_name": "Öğr. Gör. Can Aydın","day_of_week": "Cuma",      "start_time": "10:00", "end_time": "13:00", "classroom": "Lab-3", "capacity": 20, "enrolled": 15},
            {"id": "sec-a6", "course_code": "YBS490", "course_name": "Staj",                      "credits": 0, "akts": 4,  "instructor_name": "—",                  "day_of_week": "—",         "start_time": "—",     "end_time": "—",     "classroom": "—",    "capacity": 99, "enrolled": 30},
        ]
    return {"term_id": term_id, "sections": available, "_mock": True}


class EnrollmentRequest(BaseModel):
    section_ids: list[str]
    note: Optional[str] = None


@student_router.post("/me/enrollment-requests", status_code=status.HTTP_201_CREATED, summary="Ders kayıt isteği gönder")
async def student_enrollment_request(body: EnrollmentRequest, user=Depends(get_verified_user)):
    requests = []
    for sid in body.section_ids:
        section = next((s for s in _SECTIONS if s["id"] == sid), None)
        req_id = f"enr-req-{uuid.uuid4().hex[:8]}"
        req = {
            "id": req_id,
            "student_user_id": user.id,
            "section_id": sid,
            "course_code": section["course_code"] if section else sid,
            "course_name": section["course_name"] if section else "Bilinmiyor",
            "request_type": "enrollment_request",
            "status": "pending",
            "created_at": "2026-04-19T12:00:00",
        }
        requests.append(req)
        _APPROVAL_REQUESTS.append({**req, "student_name": getattr(user, "name", "Öğrenci"), "note": body.note})
    return {"requests": requests, "count": len(requests), "_mock": True}


class DropRequest(BaseModel):
    enrollment_id: str
    reason: Optional[str] = None


@student_router.post("/me/drop-requests", status_code=status.HTTP_201_CREATED, summary="Ders bırakma isteği")
async def student_drop_request(body: DropRequest, user=Depends(get_verified_user)):
    req_id = f"drop-req-{uuid.uuid4().hex[:8]}"
    req = {
        "id": req_id,
        "student_user_id": user.id,
        "enrollment_id": body.enrollment_id,
        "request_type": "drop_request",
        "status": "pending",
        "reason": body.reason,
        "created_at": "2026-04-19T12:00:00",
    }
    _APPROVAL_REQUESTS.append({**req, "student_name": getattr(user, "name", "Öğrenci")})
    return req


@student_router.put("/me/profile", summary="Öğrenci profili güncelle")
async def student_update_profile(body: StudentProfileUpdate, user=Depends(get_verified_user)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    _STUDENT_PROFILE_OVERRIDES.setdefault(user.id, {}).update(patch)
    return {
        "user_id":           user.id,
        "full_name":         patch.get("full_name", getattr(user, "name", "Ad Soyad")),
        "phone":             patch.get("phone", "—"),
        "address":           patch.get("address", "—"),
        "emergency_contact": patch.get("emergency_contact", "—"),
        "emergency_phone":   patch.get("emergency_phone", "—"),
        "_mock": True,
    }


@student_router.get("/me/graduation-status", summary="Mezuniyet onay bilgileri")
async def student_graduation_status(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "cumulative_gpa": 3.21,
        "total_akts_completed": 87,
        "total_akts_required": 120,
        "total_credits_completed": 63,
        "total_credits_required": 90,
        "status": "devam_ediyor",
        "status_label": "Devam Ediyor",
        "eligible_for_graduation": False,
        "missing_akts": 33,
        "missing_credits": 27,
        "requirements": [
            {"category": "Zorunlu Dersler",     "completed": 12, "required": 18, "akts_completed": 48, "akts_required": 72, "met": False},
            {"category": "Seçmeli Dersler",     "completed": 4,  "required": 6,  "akts_completed": 20, "akts_required": 30, "met": False},
            {"category": "Teknik Seçmeli",      "completed": 2,  "required": 4,  "akts_completed": 10, "akts_required": 20, "met": False},
            {"category": "Sosyal Seçmeli",      "completed": 1,  "required": 2,  "akts_completed": 4,  "akts_required": 8,  "met": False},
            {"category": "Staj",                "completed": 0,  "required": 1,  "akts_completed": 0,  "akts_required": 6,  "met": False},
            {"category": "Bitirme Projesi",     "completed": 0,  "required": 1,  "akts_completed": 0,  "akts_required": 8,  "met": False},
        ],
        "approval_steps": [
            {"step": "Bölüm Danışmanı Onayı",   "status": "pending", "updated_at": None},
            {"step": "Bölüm Başkanı Onayı",     "status": "pending", "updated_at": None},
            {"step": "Fakülte Yönetim Kurulu",  "status": "pending", "updated_at": None},
            {"step": "Öğrenci İşleri",          "status": "pending", "updated_at": None},
        ],
        "_mock": True,
    }


@student_router.get("/me/financial", summary="Harç ve mali bilgiler")
async def student_financial(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "is_financially_eligible": True,
        "academic_year": "2025-2026",
        "terms": [
            {
                "term_name": "2025-2026 Güz",
                "tuition_fee": 12500.00,
                "amount_paid": 12500.00,
                "balance": 0.0,
                "payment_status": "ödendi",
                "due_date": "2025-10-01",
                "paid_at": "2025-09-28",
                "receipt_no": "RCP-20250928-001",
            },
            {
                "term_name": "2025-2026 Bahar",
                "tuition_fee": 12500.00,
                "amount_paid": 12500.00,
                "balance": 0.0,
                "payment_status": "ödendi",
                "due_date": "2026-03-01",
                "paid_at": "2026-02-25",
                "receipt_no": "RCP-20260225-042",
            },
        ],
        "scholarships": [
            {"name": "YÖK Burs",      "amount": 3000.00, "period": "2025-2026", "status": "aktif"},
            {"name": "Kurumsal İndirim", "amount": 1500.00, "period": "2025-2026", "status": "aktif"},
        ],
        "total_paid": 25000.00,
        "total_scholarship": 4500.00,
        "_mock": True,
    }


@student_router.get("/me/curriculum-status", summary="Müfredat tamamlanma durumu")
async def student_curriculum_status(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "program": "Yönetim Bilişim Sistemleri",
        "catalog_year": "2023-2024",
        "overall_progress_pct": 72.5,
        "categories": [
            {
                "name": "Zorunlu Dersler",
                "courses": [
                    {"code": "YBS101", "name": "Bilgisayar Programlama I",       "akts": 6, "status": "tamamlandi", "grade": "BB"},
                    {"code": "YBS102", "name": "Bilgisayar Programlama II",      "akts": 6, "status": "tamamlandi", "grade": "BA"},
                    {"code": "YBS201", "name": "Sistem Analizi ve Tasarım",      "akts": 5, "status": "tamamlandi", "grade": "AA"},
                    {"code": "YBS301", "name": "Veritabanı Yönetim Sistemleri", "akts": 5, "status": "tamamlandi", "grade": "BB"},
                    {"code": "YBS401", "name": "Proje Yönetimi",                 "akts": 5, "status": "devam_ediyor", "grade": None},
                    {"code": "YBS492", "name": "Bitirme Projesi",                "akts": 8, "status": "alinmadi",    "grade": None},
                ],
            },
            {
                "name": "Teknik Seçmeli",
                "courses": [
                    {"code": "YBS305", "name": "Yapay Zeka",           "akts": 5, "status": "tamamlandi",    "grade": "CB"},
                    {"code": "YBS310", "name": "Makine Öğrenmesi",     "akts": 5, "status": "devam_ediyor",  "grade": None},
                    {"code": "YBS315", "name": "Büyük Veri Analizi",   "akts": 5, "status": "alinmadi",      "grade": None},
                    {"code": "YBS320", "name": "Bulut Bilişim",        "akts": 5, "status": "alinmadi",      "grade": None},
                ],
            },
            {
                "name": "Sosyal Seçmeli",
                "courses": [
                    {"code": "ING101", "name": "İngilizce I",     "akts": 3, "status": "tamamlandi",  "grade": "BA"},
                    {"code": "ING102", "name": "İngilizce II",    "akts": 3, "status": "tamamlandi",  "grade": "BB"},
                    {"code": "ATA101", "name": "Atatürk İlkeleri","akts": 2, "status": "tamamlandi",  "grade": "AA"},
                    {"code": "TRK101", "name": "Türk Dili I",     "akts": 2, "status": "alinmadi",    "grade": None},
                ],
            },
        ],
        "_mock": True,
    }


@student_router.get("/me/todo-list", summary="Yapılacaklar listesi")
async def student_todo_list(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "todos": [
            {"id": "todo-1", "title": "Ders kaydını tamamla",         "category": "kayit",   "due_date": "2026-04-25", "is_done": False, "priority": "high"},
            {"id": "todo-2", "title": "Staj başvurusunu yap",         "category": "staj",    "due_date": "2026-05-01", "is_done": False, "priority": "high"},
            {"id": "todo-3", "title": "Bitirme projesi danışman görüşmesi", "category": "proje", "due_date": "2026-04-22", "is_done": False, "priority": "medium"},
            {"id": "todo-4", "title": "Burs belgesi teslim et",       "category": "mali",    "due_date": "2026-04-20", "is_done": True,  "priority": "medium"},
            {"id": "todo-5", "title": "YBS401 ödevi gönder",          "category": "ders",    "due_date": "2026-04-19", "is_done": False, "priority": "urgent"},
            {"id": "todo-6", "title": "Mezuniyet fotoğrafı yükle",    "category": "ozluk",   "due_date": "2026-06-01", "is_done": False, "priority": "low"},
        ],
        "_mock": True,
    }


class ApplicationCreate(BaseModel):
    application_type: str
    term_id: Optional[str] = None
    course_code: Optional[str] = None
    notes: Optional[str] = None
    extra: Optional[dict] = None


_APPLICATIONS: list[dict] = [
    {
        "id": "app-001", "application_type": "mazeret_sinav",
        "status": "onaylandi", "submitted_at": "2026-03-10T14:00:00",
        "course_code": "YBS201", "notes": "Sağlık raporu ektedir.",
        "reviewed_by": "Dr. Ayşe Yılmaz", "reviewed_at": "2026-03-12T10:00:00",
    },
]


@student_router.get("/me/applications", summary="Başvuru listesi")
async def student_list_applications(
    application_type: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    apps = _APPLICATIONS + _created.setdefault("applications", [])
    if application_type:
        apps = [a for a in apps if a["application_type"] == application_type]
    return {"student_user_id": user.id, "applications": apps, "_mock": True}


@student_router.post("/me/applications", status_code=status.HTTP_201_CREATED, summary="Başvuru gönder")
async def student_create_application(body: ApplicationCreate, user=Depends(get_verified_user)):
    row = {
        "id": f"app-{uuid.uuid4().hex[:8]}",
        "student_user_id": user.id,
        "application_type": body.application_type,
        "term_id": body.term_id,
        "course_code": body.course_code,
        "notes": body.notes or "",
        "extra": body.extra or {},
        "status": "bekliyor",
        "submitted_at": "2026-04-19T12:00:00",
        "reviewed_by": None,
        "reviewed_at": None,
        "_mock": True,
    }
    _created.setdefault("applications", []).append(row)
    return row


# --- Hazırlık ---

@student_router.get("/me/prep/schedule", summary="Hazırlık ders programı")
async def student_prep_schedule(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "schedule": [
            {"day": "Pazartesi", "start": "09:00", "end": "10:50", "course_code": "ENG101", "course_name": "İngilizce Hazırlık I",  "classroom": "D-101", "instructor": "Öğr. Gör. Sarah Johnson"},
            {"day": "Pazartesi", "start": "13:00", "end": "14:50", "course_code": "ENG103", "course_name": "Dinleme ve Konuşma I",  "classroom": "D-201", "instructor": "Öğr. Gör. John Smith"},
            {"day": "Salı",      "start": "09:00", "end": "10:50", "course_code": "ENG101", "course_name": "İngilizce Hazırlık I",  "classroom": "D-101", "instructor": "Öğr. Gör. Sarah Johnson"},
            {"day": "Çarşamba",  "start": "11:00", "end": "12:50", "course_code": "ENG102", "course_name": "Okuma ve Yazma I",      "classroom": "D-302", "instructor": "Öğr. Gör. Emily Brown"},
            {"day": "Perşembe",  "start": "09:00", "end": "10:50", "course_code": "ENG103", "course_name": "Dinleme ve Konuşma I",  "classroom": "D-201", "instructor": "Öğr. Gör. John Smith"},
            {"day": "Cuma",      "start": "10:00", "end": "11:50", "course_code": "ENG102", "course_name": "Okuma ve Yazma I",      "classroom": "D-302", "instructor": "Öğr. Gör. Emily Brown"},
        ],
        "_mock": True,
    }


@student_router.get("/me/prep/exams", summary="Hazırlık sınav takvimi")
async def student_prep_exams(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "exams": [
            {"course_code": "ENG101", "course_name": "İngilizce Hazırlık I",  "exam_type": "midterm", "exam_date": "2026-04-28", "exam_time": "09:00", "classroom": "A-101", "weight_percent": 40},
            {"course_code": "ENG102", "course_name": "Okuma ve Yazma I",      "exam_type": "midterm", "exam_date": "2026-04-30", "exam_time": "11:00", "classroom": "A-102", "weight_percent": 40},
            {"course_code": "ENG103", "course_name": "Dinleme ve Konuşma I",  "exam_type": "midterm", "exam_date": "2026-05-02", "exam_time": "14:00", "classroom": "A-103", "weight_percent": 40},
            {"course_code": "ENG101", "course_name": "İngilizce Hazırlık I",  "exam_type": "final",   "exam_date": "2026-06-10", "exam_time": "09:00", "classroom": "A-101", "weight_percent": 60},
            {"course_code": "ENG102", "course_name": "Okuma ve Yazma I",      "exam_type": "final",   "exam_date": "2026-06-12", "exam_time": "11:00", "classroom": "A-102", "weight_percent": 60},
            {"course_code": "ENG103", "course_name": "Dinleme ve Konuşma I",  "exam_type": "final",   "exam_date": "2026-06-14", "exam_time": "14:00", "classroom": "A-103", "weight_percent": 60},
        ],
        "_mock": True,
    }


@student_router.get("/me/prep/grades", summary="Hazırlık not listesi")
async def student_prep_grades(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "grades": [
            {"course_code": "ENG101", "course_name": "İngilizce Hazırlık I",  "midterm": 72, "final": None, "letter_grade": None, "is_published": False, "is_finalized": False},
            {"course_code": "ENG102", "course_name": "Okuma ve Yazma I",      "midterm": 68, "final": None, "letter_grade": None, "is_published": False, "is_finalized": False},
            {"course_code": "ENG103", "course_name": "Dinleme ve Konuşma I",  "midterm": 80, "final": None, "letter_grade": None, "is_published": False, "is_finalized": False},
        ],
        "_mock": True,
    }


@student_router.get("/me/prep/attendance", summary="Hazırlık devamsızlık")
async def student_prep_attendance(user=Depends(get_verified_user)):
    return {
        "student_user_id": user.id,
        "attendance": [
            {"course_code": "ENG101", "course_name": "İngilizce Hazırlık I",  "total_weeks": 14, "absent_count": 1, "attendance_pct": 92.9, "status": "ok"},
            {"course_code": "ENG102", "course_name": "Okuma ve Yazma I",      "total_weeks": 14, "absent_count": 3, "attendance_pct": 78.6, "status": "ok"},
            {"course_code": "ENG103", "course_name": "Dinleme ve Konuşma I",  "total_weeks": 14, "absent_count": 0, "attendance_pct": 100.0,"status": "ok"},
        ],
        "_mock": True,
    }


# --- Staj ---

class InternshipCreate(BaseModel):
    company_name: str
    company_address: str
    supervisor_name: str
    supervisor_email: str
    start_date: str
    end_date: str
    internship_type: str = "zorunlu"
    notes: Optional[str] = None


_INTERNSHIPS: list[dict] = [
    {
        "id": "int-001",
        "company_name": "ABC Teknoloji A.Ş.",
        "company_address": "Ankara / Çankaya",
        "supervisor_name": "Mühendis Mehmet Demir",
        "supervisor_email": "mdemir@abctech.com.tr",
        "start_date": "2025-07-01",
        "end_date": "2025-08-31",
        "internship_type": "zorunlu",
        "status": "tamamlandi",
        "submitted_at": "2025-06-15T10:00:00",
        "notes": "",
    },
]


@student_router.get("/me/internship", summary="Staj bilgileri")
async def student_internship(user=Depends(get_verified_user)):
    apps = _INTERNSHIPS + _created.setdefault("internships", [])
    return {"student_user_id": user.id, "internships": apps, "_mock": True}


@student_router.post("/me/internship", status_code=status.HTTP_201_CREATED, summary="Staj başvurusu")
async def student_create_internship(body: InternshipCreate, user=Depends(get_verified_user)):
    row = {
        "id": f"int-{uuid.uuid4().hex[:8]}",
        "student_user_id": user.id,
        **body.model_dump(),
        "status": "bekliyor",
        "submitted_at": "2026-04-19T12:00:00",
        "_mock": True,
    }
    _created.setdefault("internships", []).append(row)
    return row


# --- İntibak / Kredi Transfer ---

class CreditTransferCreate(BaseModel):
    source_institution: str
    source_course_code: str
    source_course_name: str
    source_credits: float
    target_course_code: str
    target_course_name: str
    notes: Optional[str] = None


@student_router.get("/me/credit-transfer", summary="İntibak başvuruları")
async def student_credit_transfer(user=Depends(get_verified_user)):
    apps = _created.setdefault("credit_transfers", [])
    return {"student_user_id": user.id, "transfers": apps, "_mock": True}


@student_router.post("/me/credit-transfer", status_code=status.HTTP_201_CREATED, summary="İntibak başvurusu gönder")
async def student_create_credit_transfer(body: CreditTransferCreate, user=Depends(get_verified_user)):
    row = {
        "id": f"ct-{uuid.uuid4().hex[:8]}",
        "student_user_id": user.id,
        **body.model_dump(),
        "status": "bekliyor",
        "submitted_at": "2026-04-19T12:00:00",
        "_mock": True,
    }
    _created.setdefault("credit_transfers", []).append(row)
    return row


# ===========================================================================
# AKADEMİSYEN
# ===========================================================================

@academic_user_router.get("/me/sections", summary="Akademisyen şubeleri")
async def academic_me_sections(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    sections = [s for s in _SECTIONS if s["instructor_id"] == "mock-acad-1"]
    if term_id:
        sections = [s for s in sections if s["term_id"] == term_id]
    return {"academic_user_id": user.id, "term_id_filter": term_id, "sections": sections, "_mock": True}


@academic_user_router.get("/me/sections/{section_id}/students", summary="Şube öğrenci listesi")
async def academic_section_students(section_id: str, _user=Depends(get_verified_user)):
    section = next((s for s in _SECTIONS if s["id"] == section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="Şube bulunamadı")
    students = [
        {"student_no": "20240001", "name": "Ali Veli",     "enrollment_id": "enr-1", "enrollment_status": "active", "gpa": 3.21},
        {"student_no": "20240002", "name": "Fatma Kaya",   "enrollment_id": "enr-2", "enrollment_status": "active", "gpa": 3.45},
        {"student_no": "20240003", "name": "Mehmet Demir", "enrollment_id": "enr-3", "enrollment_status": "active", "gpa": 2.88},
        {"student_no": "20240004", "name": "Zeynep Arslan","enrollment_id": "enr-4", "enrollment_status": "active", "gpa": 3.72},
        {"student_no": "20240005", "name": "Can Yıldız",   "enrollment_id": "enr-5", "enrollment_status": "active", "gpa": 2.55},
    ]
    return {"section_id": section_id, "section": section, "students": students, "_mock": True}


@academic_user_router.get("/sections/{section_id}/exams", summary="Şube sınav listesi")
async def academic_section_exams(section_id: str, _user=Depends(get_verified_user)):
    exams = [e for e in _EXAMS if e.get("course_section_id") == section_id]
    if not exams:
        # fallback: ilk iki sınavı döndür
        exams = _EXAMS[:2]
    return {"section_id": section_id, "exams": exams, "_mock": True}


@academic_user_router.get("/sections/{section_id}/grades", summary="Şube not listesi")
async def academic_section_grades(section_id: str, _user=Depends(get_verified_user)):
    students = [
        {"student_no": "20240001", "name": "Ali Veli",     "enrollment_id": "enr-1", "midterm": 72, "final": None, "letter_grade": None, "is_finalized": False},
        {"student_no": "20240002", "name": "Fatma Kaya",   "enrollment_id": "enr-2", "midterm": 85, "final": None, "letter_grade": None, "is_finalized": False},
        {"student_no": "20240003", "name": "Mehmet Demir", "enrollment_id": "enr-3", "midterm": 60, "final": None, "letter_grade": None, "is_finalized": False},
        {"student_no": "20240004", "name": "Zeynep Arslan","enrollment_id": "enr-4", "midterm": 90, "final": None, "letter_grade": None, "is_finalized": False},
        {"student_no": "20240005", "name": "Can Yıldız",   "enrollment_id": "enr-5", "midterm": 55, "final": None, "letter_grade": None, "is_finalized": False},
    ]
    return {"section_id": section_id, "students": students, "_mock": True}


class ExamCreate(BaseModel):
    exam_type: str = Field(..., description="midterm / final / makeup / project")
    exam_date: str
    exam_time: str = "09:00"
    classroom: Optional[str] = None
    weight_percent: float = 40.0


@academic_user_router.post("/sections/{section_id}/exams", status_code=status.HTTP_201_CREATED, summary="Sınav tanımla")
async def academic_create_exam(section_id: str, body: ExamCreate, _user=Depends(get_verified_user)):
    row = {
        "id": f"exam-{uuid.uuid4().hex[:8]}",
        "course_section_id": section_id,
        "exam_type":     body.exam_type,
        "exam_date":     body.exam_date,
        "exam_time":     body.exam_time,
        "classroom":     body.classroom or "A-101",
        "weight_percent": body.weight_percent,
        "_mock": True,
    }
    _created.setdefault("exams", []).append(row)
    return row


@academic_user_router.post("/sections/{section_id}/grades/finalize", summary="Notları kesinleştir")
async def academic_finalize_grades(section_id: str, _user=Depends(get_verified_user)):
    return {"section_id": section_id, "finalized": True, "_mock": True}


@academic_user_router.get("/me/advisees", summary="Danışmanlık öğrencileri")
async def academic_me_advisees(user=Depends(get_verified_user)):
    advisees = [
        {"student_no": "20240001", "name": "Ali Veli",     "department": "YBS", "class_level": 3, "gpa": 3.21, "status": "active"},
        {"student_no": "20240004", "name": "Zeynep Arslan","department": "YBS", "class_level": 2, "gpa": 2.88, "status": "active"},
        {"student_no": "20240005", "name": "Can Yıldız",   "department": "YBS", "class_level": 4, "gpa": 3.65, "status": "active"},
    ]
    return {"academic_user_id": user.id, "advisees": advisees, "_mock": True}


@academic_user_router.get("/me/approval-requests", summary="Bekleyen onay talepleri")
async def academic_me_approval_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    user=Depends(get_verified_user),
):
    reqs = list(_APPROVAL_REQUESTS)
    if status_filter:
        reqs = [r for r in reqs if r["status"] == status_filter]
    return {"academic_user_id": user.id, "requests": reqs, "total": len(reqs), "_mock": True}


class ApprovalAction(BaseModel):
    action: str = Field(..., description="approve / reject")
    note: Optional[str] = None


@academic_user_router.patch("/approval-requests/{request_id}", summary="Onayla / Reddet")
async def academic_approve_request(request_id: str, body: ApprovalAction, user=Depends(get_verified_user)):
    for r in _APPROVAL_REQUESTS:
        if r["id"] == request_id:
            r["status"]       = "approved" if body.action == "approve" else "rejected"
            r["note"]         = body.note
            r["resolved_at"]  = "2026-04-19T12:00:00"
            return {"id": request_id, "status": r["status"], "_mock": True}
    raise HTTPException(status_code=404, detail="Talep bulunamadı")


class GradeInput(BaseModel):
    grades: list[dict[str, Any]]


@academic_user_router.put("/sections/{section_id}/grades", summary="Toplu not girişi")
async def academic_put_grades(section_id: str, body: GradeInput, user=Depends(get_verified_user)):
    section = next((s for s in _SECTIONS if s["id"] == section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="Şube bulunamadı")
    if section["instructor_id"] != "mock-acad-1":
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return {"section_id": section_id, "updated": len(body.grades), "_mock": True}


class AttendanceInput(BaseModel):
    week_no: int
    records: list[dict[str, Any]]


@academic_user_router.put("/sections/{section_id}/attendance", summary="Yoklama girişi")
async def academic_put_attendance(section_id: str, body: AttendanceInput, user=Depends(get_verified_user)):
    section = next((s for s in _SECTIONS if s["id"] == section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="Şube bulunamadı")
    return {"section_id": section_id, "week_no": body.week_no, "recorded": len(body.records), "_mock": True}


class AcademicAnnouncementCreate(BaseModel):
    title: str
    content: str
    # section   → o şubedeki tüm öğrencilere
    # advisees  → danışmanlık öğrencilerine
    # student   → belirli bir öğrenciye (student_no veya student_id ile)
    # all       → tüm öğrencilere
    audience_type: str = "section"
    department_id: Optional[str] = None
    course_section_id: Optional[str] = None
    student_no: Optional[str] = None  # audience_type=student için


@academic_user_router.post("/announcements", status_code=status.HTTP_201_CREATED, summary="Duyuru oluştur")
async def academic_create_announcement(body: AcademicAnnouncementCreate, user=Depends(get_verified_user)):
    row = {
        "id":               f"ann-{uuid.uuid4().hex[:8]}",
        "title":            body.title,
        "content":          body.content,
        "audience_type":    body.audience_type,
        "department_id":    body.department_id,
        "course_section_id": body.course_section_id,
        "student_no":       body.student_no,
        "is_active":        True,
        "published_at":     "2026-04-19T12:00:00",
        "created_by":       user.id,
        "created_by_name":  getattr(user, "name", "Akademisyen"),
        "_mock":            True,
    }
    _ANNOUNCEMENTS.append(row)

    # Bildirim: hedef öğrenciye mesaj düşür (mock)
    target_info = ""
    if body.audience_type == "section" and body.course_section_id:
        sec = next((s for s in _SECTIONS if s["id"] == body.course_section_id), None)
        target_info = f"({sec['course_code']} şubesi)" if sec else ""
    elif body.audience_type == "advisees":
        target_info = "(danışmanlık öğrencileri)"
    elif body.audience_type == "student" and body.student_no:
        target_info = f"(Öğrenci: {body.student_no})"
    elif body.audience_type == "all":
        target_info = "(tüm öğrenciler)"

    notif_msg = {
        "id":              f"msg-ann-{uuid.uuid4().hex[:8]}",
        "sender_user_id":  user.id,
        "sender_name":     getattr(user, "name", "Akademisyen"),
        "sender_type":     "akademisyen",
        "receiver_type":   "öğrenci",
        "subject":         f"[Duyuru] {body.title}",
        "body":            body.content,
        "is_read":         False,
        "status":          "new",
        "sent_at":         "2026-04-19T12:00:00",
        "audience_type":   body.audience_type,
        "note":            target_info,
    }
    _MESSAGES.append(notif_msg)
    return row


# ===========================================================================
# ADMİN
# ===========================================================================

class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1)


class TermCreate(BaseModel):
    name:          str
    academic_year: str
    season:        str = "fall"
    starts_at:     str = ""
    ends_at:       str = ""
    is_active:     bool = False


class CourseCreate(BaseModel):
    department_id: str
    code:          str
    name:          str
    credits:       int = 3
    akts:          int = 5
    class_year:    int = 1
    course_type:   str = "Z"
    theory_hours:  str = "3+0"
    language:      str = "Türkçe"


class ClassroomCreate(BaseModel):
    building:  str
    name:      str
    capacity:  int = 30
    is_online: bool = False


class CourseSectionCreate(BaseModel):
    course_id:        str
    course_code:      str = ""
    course_name:      str = ""
    term_id:          str
    term_name:        str = ""
    section_no:       int = 1
    classroom_id:     str = ""
    classroom_code:   str = ""
    instructor_id:    str = ""
    instructor_label: str = "Mock Eğitmen"
    day_of_week:      str = "Pazartesi"
    start_time:       str = "09:00"
    end_time:         str = "10:50"
    capacity:         int = 40


class CalendarEventCreate(BaseModel):
    term_id:    str
    event_type: str
    title:      str
    start_date: str
    end_date:   str


class RegistrationSettingsUpdate(BaseModel):
    max_akts:             int = 30
    bonus_akts:           int = 6
    gpa_threshold:        float = 2.50
    enrollment_deadline:  str = ""
    add_drop_deadline:    str = ""


class AdminAnnouncementCreate(BaseModel):
    title:         str
    content:       str
    audience_type: str = "all"
    department_id: Optional[str] = None


# --- Bölüm ---

@admin_router.get("/departments")
async def admin_list_departments(_user=Depends(get_admin_user)):
    return _DEPARTMENTS + _created["departments"]


@admin_router.post("/departments", status_code=status.HTTP_201_CREATED)
async def admin_create_department(body: DepartmentCreate, _user=Depends(get_admin_user)):
    row = {"id": f"dept-{uuid.uuid4().hex[:8]}", "code": body.code, "name": body.name}
    _created["departments"].append(row)
    return row


# --- Dönem ---

@admin_router.get("/terms")
async def admin_list_terms(_user=Depends(get_admin_user)):
    return _TERMS + _created["terms"]


@admin_router.post("/terms", status_code=status.HTTP_201_CREATED)
async def admin_create_term(body: TermCreate, _user=Depends(get_admin_user)):
    row = {
        "id": f"term-{uuid.uuid4().hex[:8]}",
        "name": body.name, "academic_year": body.academic_year,
        "season": body.season, "starts_at": body.starts_at,
        "ends_at": body.ends_at, "is_active": body.is_active,
    }
    _created["terms"].append(row)
    return row


# --- Ders ---

@admin_router.get("/courses")
async def admin_list_courses(_user=Depends(get_admin_user)):
    return _COURSES + _created["courses"]


@admin_router.post("/courses", status_code=status.HTTP_201_CREATED)
async def admin_create_course(body: CourseCreate, _user=Depends(get_admin_user)):
    dept_ids = {d["id"] for d in _DEPARTMENTS + _created["departments"]}
    if body.department_id not in dept_ids:
        raise HTTPException(status_code=400, detail="Geçersiz department_id")
    row = {
        "id": f"crs-{uuid.uuid4().hex[:8]}",
        "department_id": body.department_id, "code": body.code,
        "name": body.name, "credits": body.credits, "akts": body.akts,
        "class_year": body.class_year, "type": body.course_type,
        "theory_hours": body.theory_hours, "language": body.language,
    }
    _created["courses"].append(row)
    return row


# --- Derslik ---

@admin_router.get("/classrooms")
async def admin_list_classrooms(_user=Depends(get_admin_user)):
    return _CLASSROOMS + _created["classrooms"]


@admin_router.post("/classrooms", status_code=status.HTTP_201_CREATED)
async def admin_create_classroom(body: ClassroomCreate, _user=Depends(get_admin_user)):
    row = {
        "id": f"room-{uuid.uuid4().hex[:8]}",
        "building": body.building, "name": body.name,
        "capacity": body.capacity, "is_online": body.is_online,
    }
    _created["classrooms"].append(row)
    return row


# --- Şube ---

@admin_router.get("/instructors")
async def admin_list_instructors(_user=Depends(get_admin_user)):
    """Akademisyen listesi — şube atamada kullanılır."""
    all_users = _MOCK_USERS + _created.get("users", [])
    instructors = [u for u in all_users if u.get("role") == "Akademisyen"]
    return instructors


@admin_router.get("/course-sections")
async def admin_list_sections(
    term_id: Optional[str] = Query(None),
    _user=Depends(get_admin_user),
):
    all_sections = _SECTIONS + _created["course_sections"]
    if term_id:
        all_sections = [s for s in all_sections if s.get("term_id") == term_id]
    return all_sections


@admin_router.post("/course-sections", status_code=status.HTTP_201_CREATED)
async def admin_create_section(body: CourseSectionCreate, _user=Depends(get_admin_user)):
    row = {
        "id": f"sec-{uuid.uuid4().hex[:8]}",
        **body.model_dump(), "enrollment_count": 0,
    }
    _created["course_sections"].append(row)
    return row


# --- Akademik Takvim ---

@admin_router.get("/calendar-events")
async def admin_list_calendar_events(
    term_id: Optional[str] = Query(None),
    _user=Depends(get_admin_user),
):
    events = _CALENDAR_EVENTS + _created["calendar_events"]
    if term_id:
        events = [e for e in events if e["term_id"] == term_id]
    return events


@admin_router.post("/calendar-events", status_code=status.HTTP_201_CREATED)
async def admin_create_calendar_event(body: CalendarEventCreate, _user=Depends(get_admin_user)):
    row = {"id": f"cal-{uuid.uuid4().hex[:8]}", **body.model_dump()}
    _created["calendar_events"].append(row)
    return row


# --- Kayıt Kuralları ---

@admin_router.get("/registration-settings")
async def admin_get_registration_settings(
    term_id: Optional[str] = Query(None),
    _user=Depends(get_admin_user),
):
    return _REGISTRATION_SETTINGS


@admin_router.post("/registration-settings")
async def admin_update_registration_settings(body: RegistrationSettingsUpdate, _user=Depends(get_admin_user)):
    _REGISTRATION_SETTINGS.update(body.model_dump())
    return {**_REGISTRATION_SETTINGS, "_mock": True}


# --- Duyuru ---

@admin_router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def admin_create_announcement(body: AdminAnnouncementCreate, _user=Depends(get_admin_user)):
    row = {
        "id": f"ann-{uuid.uuid4().hex[:8]}",
        "title": body.title, "content": body.content,
        "audience_type": body.audience_type,
        "department_id": body.department_id,
        "is_active": True, "published_at": "2026-04-19T12:00:00",
        "created_by": "admin", "_mock": True,
    }
    _ANNOUNCEMENTS.append(row)
    return row


# --- Belge Talepleri ---

@admin_router.get("/document-requests")
async def admin_list_document_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    _user=Depends(get_admin_user),
):
    reqs = _DOCUMENT_REQUESTS + _created["document_requests"]
    if status_filter:
        reqs = [r for r in reqs if r["status"] == status_filter]
    return {"requests": reqs, "total": len(reqs), "_mock": True}


@admin_router.patch("/document-requests/{request_id}")
async def admin_complete_document_request(request_id: str, _user=Depends(get_admin_user)):
    for r in _DOCUMENT_REQUESTS + _created["document_requests"]:
        if r["id"] == request_id:
            r["status"] = "tamamlandı"
            return {"id": request_id, "status": "tamamlandı", "_mock": True}
    raise HTTPException(status_code=404, detail="Talep bulunamadı")


# --- Audit Logs ---

@admin_router.get("/audit-logs")
async def admin_audit_logs(
    limit: int = Query(20, ge=1, le=100),
    _user=Depends(get_admin_user),
):
    logs = [
        {"id": f"log-{i}", "action": act, "entity_type": ent, "user": usr, "created_at": ts}
        for i, (act, ent, usr, ts) in enumerate([
            ("grade_update",     "grade_entries",    "Dr. Öğr. Üy. Ayşe Yılmaz", "2026-04-15T10:00:00"),
            ("enrollment_create","course_enrollments","Ali Veli",                  "2026-02-12T09:30:00"),
            ("password_change",  "users",             "Fatma Kaya",               "2026-03-01T14:22:00"),
            ("approval_create",  "approval_requests", "Ali Veli",                 "2026-02-12T10:05:00"),
        ], 1)
    ]
    return {"logs": logs[:limit], "total": len(logs), "_mock": True}


# --- Kullanıcı Yönetimi ---

_MOCK_USERS: list[dict] = [
    {"id": "usr-1", "email": "ali.veli@dou.edu.tr",      "full_name": "Ali Veli",          "role": "Öğrenci",     "is_active": True,  "created_at": "2024-09-01"},
    {"id": "usr-2", "email": "fatma.kaya@dou.edu.tr",    "full_name": "Fatma Kaya",         "role": "Öğrenci",     "is_active": True,  "created_at": "2024-09-01"},
    {"id": "usr-3", "email": "ayse.yilmaz@dou.edu.tr",   "full_name": "Dr. Ayşe Yılmaz",    "role": "Akademisyen", "is_active": True,  "created_at": "2023-01-15"},
    {"id": "usr-4", "email": "mehmet.demir@dou.edu.tr",  "full_name": "Prof. Mehmet Demir", "role": "Akademisyen", "is_active": True,  "created_at": "2022-09-01"},
    {"id": "usr-5", "email": "admin@dou.edu.tr",         "full_name": "Sistem Yöneticisi",  "role": "Admin",       "is_active": True,  "created_at": "2020-01-01"},
    {"id": "usr-6", "email": "zeynep.arslan@dou.edu.tr", "full_name": "Zeynep Arslan",      "role": "Öğrenci",     "is_active": False, "created_at": "2024-09-01"},
]

_MOCK_ROLES: list[dict] = [
    {
        "id": "role-1", "name": "Admin", "description": "Tam yetki",
        "permissions": ["users.manage","roles.manage","catalog.manage","sections.manage","calendar.manage","audit.read","grades.put","announcements.post","document_requests.manage"],
    },
    {
        "id": "role-2", "name": "Akademisyen", "description": "Not, yoklama, danışmanlık",
        "permissions": ["grades.get","grades.put","attendance.get","attendance.put","enrollments.approve","sections.get","exams.get","exams.post","messages.get","messages.post","messages.delete","announcements.get","announcements.post","calendar.get","auth.change_password"],
    },
    {
        "id": "role-3", "name": "Öğrenci", "description": "Kendi verilerini görme ve ders kayıt",
        "permissions": ["courses.get","grades.get","attendance.get","enrollments.post","messages.get","messages.post","messages.delete","document_requests.post","document_requests.get","announcements.get","calendar.get","auth.change_password"],
    },
]


class UserCreate(BaseModel):
    email: str
    full_name: str
    role: str = "Öğrenci"
    password: str = "Abc123!"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@admin_router.get("/users")
async def admin_list_users(
    role_filter: Optional[str] = Query(None, alias="role"),
    search: Optional[str] = Query(None),
    _user=Depends(get_admin_user),
):
    users = _MOCK_USERS + _created.setdefault("users", [])
    if role_filter:
        users = [u for u in users if u["role"] == role_filter]
    if search:
        s = search.lower()
        users = [u for u in users if s in u["full_name"].lower() or s in u["email"].lower()]
    return {"users": users, "total": len(users), "_mock": True}


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(body: UserCreate, _user=Depends(get_admin_user)):
    row = {
        "id": f"usr-{uuid.uuid4().hex[:8]}",
        "email":     body.email,
        "full_name": body.full_name,
        "role":      body.role,
        "is_active": True,
        "created_at": "2026-04-19",
        "_mock": True,
    }
    _created.setdefault("users", []).append(row)
    return row


@admin_router.patch("/users/{user_id}")
async def admin_update_user(user_id: str, body: UserUpdate, _user=Depends(get_admin_user)):
    for u in _MOCK_USERS + _created.get("users", []):
        if u["id"] == user_id:
            if body.full_name is not None: u["full_name"] = body.full_name
            if body.role      is not None: u["role"]      = body.role
            if body.is_active is not None: u["is_active"] = body.is_active
            return {**u, "_mock": True}
    raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")


@admin_router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, _user=Depends(get_admin_user)):
    return {"user_id": user_id, "temp_password": "Abc123!", "_mock": True}


# --- Rol Yönetimi ---

class RolePermissionsUpdate(BaseModel):
    permissions: list[str]


@admin_router.get("/roles")
async def admin_list_roles(_user=Depends(get_admin_user)):
    return {"roles": _MOCK_ROLES, "_mock": True}


@admin_router.put("/roles/{role_id}/permissions")
async def admin_update_role_permissions(role_id: str, body: RolePermissionsUpdate, _user=Depends(get_admin_user)):
    for r in _MOCK_ROLES:
        if r["id"] == role_id:
            r["permissions"] = body.permissions
            return {**r, "_mock": True}
    raise HTTPException(status_code=404, detail="Rol bulunamadı")


# --- Genel İstatistik ---

@admin_router.get("/stats")
async def admin_stats(_user=Depends(get_admin_user)):
    all_users = _MOCK_USERS + _created.get("users", [])
    return {
        "departments": len(_DEPARTMENTS) + len(_created["departments"]),
        "terms":       len(_TERMS)       + len(_created["terms"]),
        "courses":     len(_COURSES)     + len(_created["courses"]),
        "classrooms":  len(_CLASSROOMS)  + len(_created["classrooms"]),
        "sections":    len(_SECTIONS)    + len(_created["course_sections"]),
        "announcements": len(_ANNOUNCEMENTS),
        "users_total": len(all_users),
        "users_active": len([u for u in all_users if u.get("is_active", True)]),
        "_mock": True,
    }
