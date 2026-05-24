"""OBS akademik API — mevcut PostgreSQL obs_* tabloları (UUID, academic/student profiller)."""

from __future__ import annotations

import datetime
import logging
import math
import numbers
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import ENV
from open_webui.internal.db import get_session
from open_webui.internal.obs_db import (
    OBS_ENGINE_URL_SAFE,
    OBS_USES_PRIMARY_DATABASE,
    get_obs_session,
)
from open_webui.models.auths import Auths
from open_webui.models.users import Users
from open_webui.routers import obs_sis_repository as repo
from open_webui.utils.auth import get_password_hash, get_verified_user

log = logging.getLogger(__name__)


def _sanitize_for_json(obj: Any) -> Any:
    """Starlette JSONResponse varsayılanında NaN/Infinity geçerli JSON değildir; tarayıcı parse edemez."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, numbers.Real):
        x = float(obj)
        if math.isnan(x) or math.isinf(x):
            return None
        return obj
    return obj


def _parse_grade_upsert_return(raw: Any) -> tuple[int, Optional[str]]:
    """
    upsert_grades geçmişte yalnızca int döndü; şimdi (n, err) tuple.
    İki atama (n, err = tek_int) patlamasını kesin olarak önlemek için tek yerden normalize et.
    """
    if isinstance(raw, tuple):
        if not raw:
            return 0, None
        err_part = raw[1] if len(raw) > 1 else None
        try:
            return int(raw[0]), (
                err_part
                if err_part is None or isinstance(err_part, str)
                else str(err_part)
            )
        except (TypeError, ValueError):
            return 0, None
    if isinstance(raw, list):
        if not raw:
            return 0, None
        err_part = raw[1] if len(raw) > 1 else None
        try:
            return int(raw[0]), (
                err_part
                if err_part is None or isinstance(err_part, str)
                else str(err_part)
            )
        except (TypeError, ValueError):
            return 0, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return 0, None


public_router = APIRouter(tags=["dou-obs-public"])
student_router = APIRouter(tags=["dou-obs-student"])
academic_user_router = APIRouter(tags=["dou-obs-academic"])
admin_router = APIRouter(tags=["dou-obs-admin"])

_OBS_ROLE_EMAIL = {
    "ogrenci@dou.edu.tr": "ogrenci",
    "akademisyen@dou.edu.tr": "Akademisyen",
    "admin@dou.edu.tr": "Admin",
}


def _obs_role_for_user(user) -> str:
    info = getattr(user, "info", None) or {}
    if isinstance(info, dict):
        r = repo.user_info_obs_role(info)
        if r:
            return r
    email = getattr(user, "email", "") or ""
    if email in _OBS_ROLE_EMAIL:
        return _OBS_ROLE_EMAIL[email]
    role = getattr(user, "role", "") or ""
    if role == "admin":
        return "Admin"
    if role == "academician":
        return "Akademisyen"
    return "ogrenci"


def get_obs_admin_user(user=Depends(get_verified_user)):
    """Open WebUI `admin` veya kullanıcı bilgisinde OBS `Admin` rolü."""
    if getattr(user, "role", None) == "admin":
        return user
    if str(_obs_role_for_user(user) or "").strip().lower() == "admin":
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
    )


# ---------------------------------------------------------------------------
# DEV
# ---------------------------------------------------------------------------

_DEV_ACCOUNTS = [
    {
        "email": "ogrenci@dou.edu.tr",
        "name": "Ramazan Öğrenci",
        "password": "Obs1234!",
        "role": "user",
    },
    {
        "email": "akademisyen@dou.edu.tr",
        "name": "Dr. Ayşe Yılmaz",
        "password": "Obs1234!",
        "role": "user",
    },
    {
        "email": "admin@dou.edu.tr",
        "name": "Sistem Yöneticisi",
        "password": "Obs1234!",
        "role": "admin",
    },
]


@public_router.post("/dev/seed-users", summary="[DEV] Test kullanıcıları")
async def dev_seed_users(db: Session = Depends(get_session)):
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
            if new_user and acc["role"] == "admin":
                Users.update_user_role_by_id(new_user.id, "admin", db=db)
            user_id = new_user.id if new_user else "?"
        else:
            user_id = existing.id
        result.append(
            {
                "email": email,
                "password": acc["password"],
                "name": acc["name"],
                "obs_role": _OBS_ROLE_EMAIL.get(email, "ogrenci"),
                "user_id": user_id,
                "existed": existing is not None,
            }
        )
    return {"accounts": result}


@public_router.get("/dev/obs-role", summary="[DEV] OBS rolü")
async def dev_obs_role(user=Depends(get_verified_user)):
    email = getattr(user, "email", "") or ""
    return {"obs_role": _obs_role_for_user(user), "email": email}


@public_router.get("/dev/obs-db-ping", summary="[DEV] OBS DB bağlantı testi")
async def dev_obs_db_ping(obs_db: Session = Depends(get_obs_session)):
    # OBS DB gerçekten erişilebilir mi? (bağlantı / auth / network)
    try:
        obs_db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}


@public_router.post(
    "/dev/clear-my-student-enrollments",
    summary="[DEV] Oturumdaki öğrencinin ders kayıtlarını temizle",
)
async def dev_clear_my_student_enrollments(
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    """Yalnızca ENV != prod. PostgreSQL'deki demo kayıtlarını kaldırır; arayüz mock'u yoktur."""
    if ENV == "prod":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return repo.clear_student_enrollments_and_related(obs_db, user.id)


# ---------------------------------------------------------------------------
# Ortak
# ---------------------------------------------------------------------------


@public_router.get("/terms")
async def list_terms(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_verified_user)
):
    return repo.list_terms(obs_db)


@public_router.get("/terms/{term_id}/calendar")
async def term_calendar(
    term_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_verified_user),
):
    return {"term_id": term_id, "events": repo.term_calendar(obs_db, term_id)}


@public_router.get("/departments")
async def list_departments(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_verified_user)
):
    return repo.list_departments(obs_db)


@public_router.get("/announcements")
async def list_announcements(
    audience_type: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_verified_user),
):
    return {
        "announcements": repo.list_announcements_filtered(
            obs_db, audience_type, department_id
        )
    }


@public_router.get("/messages/inbox")
async def messages_inbox(
    sender_type: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    msgs = repo.messages_inbox(obs_db, user.id, sender_type)
    return {"user_id": user.id, "messages": msgs, "total": len(msgs)}


@public_router.get("/messages/sent")
async def messages_sent(
    receiver_type: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    msgs = repo.messages_sent(obs_db, user.id, receiver_type)
    return {"user_id": user.id, "messages": msgs, "total": len(msgs)}


class MessageCreate(BaseModel):
    receiver_user_id: Optional[str] = None
    receiver_name: str = ""
    receiver_type: str = "akademisyen"
    subject: str
    body: str


@public_router.post("/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    body: MessageCreate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    rid = body.receiver_user_id or ""
    if not rid:
        raise HTTPException(status_code=400, detail="receiver_user_id gerekli")
    return repo.insert_message(obs_db, user.id, rid, body.subject, body.body)


@public_router.patch("/messages/{message_id}/read")
async def mark_read(
    message_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok = repo.mark_message_read(obs_db, message_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    return {"id": message_id, "is_read": True}


@public_router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok = repo.soft_delete_message(obs_db, message_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    return {"id": message_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Öğrenci
# ---------------------------------------------------------------------------


@student_router.get("/me/profile")
async def student_me_profile(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
):
    row = repo.get_student_profile_api(obs_db, user.id)
    if row:
        return row
    # Hesap var ama obs_student_profiles satırı yok (yanlış oluşturma yolu, rollback vb.)
    role = getattr(user, "role", None)
    if role not in ("user", "pending"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Öğrenci profili bulunamadı"
        )
    urow = Users.get_user_by_id(user.id, db=db)
    if not urow:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    info_raw = getattr(urow, "info", None)
    info_phone = ""
    if isinstance(info_raw, dict):
        info_phone = str(info_raw.get("phone") or "").strip()
    return {
        "user_id": user.id,
        "email": urow.email or "",
        "full_name": urow.name or "",
        "student_no": "",
        "department_id": "",
        "department_name": "Özlük kaydı oluşturulmadı",
        "faculty_name": "",
        "program": "—",
        "class_level": 0,
        "program_semester_number": 1,
        "gpa": 0.0,
        "status": "pending_profile",
        "enrollment_date": None,
        "is_financially_eligible": True,
        "phone": info_phone,
        "address": "",
        "emergency_contact": "",
        "emergency_phone": "",
        "completed_akts": 0,
        "total_akts_required": 240,
        "dno": None,
        "_obs_profile_missing": True,
    }


@student_router.get("/me/advisor")
async def student_me_advisor(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    return repo.get_advisor_api(obs_db, user.id)


@student_router.get("/me/registration-limits")
async def student_me_registration_limits(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    row = repo.student_registration_limits_payload(obs_db, user.id, term_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Öğrenci profili bulunamadı")
    return row


@student_router.get("/me/enrollments")
async def student_me_enrollments(
    term_id: Optional[str] = Query(None),
    statuses: str = Query(
        "active",
        description="Virgülle: draft,pending,active",
    ),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    st = tuple(s.strip() for s in statuses.split(",") if s.strip())
    if not st:
        st = ("active",)
    spid, rows = repo.list_enrollments(obs_db, user.id, term_id, st)
    if spid is None:
        log.info(
            "[OBS-DATA] GET /student/me/enrollments user=%s spid=None rows=0 | SQL: obs_course_enrollments | db=%s | obs_primary_ile_ayni=%s",
            user.id,
            OBS_ENGINE_URL_SAFE,
            OBS_USES_PRIMARY_DATABASE,
        )
        return {
            "student_user_id": user.id,
            "term_id_filter": term_id,
            "enrollments": [],
            "total_akts": 0,
        }
    total_akts = sum(r["akts"] for r in rows if r.get("status") == "active")
    log.info(
        "[OBS-DATA] GET /student/me/enrollments user=%s spid=%s rows=%s active_akts=%s | SQL: obs_course_enrollments+join | db=%s | obs_primary_ile_ayni=%s",
        user.id,
        spid,
        len(rows),
        total_akts,
        OBS_ENGINE_URL_SAFE,
        OBS_USES_PRIMARY_DATABASE,
    )
    return {
        "student_user_id": user.id,
        "term_id_filter": term_id,
        "enrollments": rows,
        "total_akts": total_akts,
    }


@student_router.get("/me/schedule")
async def student_me_schedule(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    spid, rows = repo.list_enrollments(
        obs_db,
        user.id,
        term_id,
        ("active", "pending_drop", "dropped"),
        include_completed_semesters=True,
    )
    if spid is None:
        return {"student_user_id": user.id, "term_id": term_id or "", "schedule": []}
    response_tid = term_id or (rows[0]["term_id"] if rows else "")
    if not rows:
        sched = []
    elif term_id:
        # SQL seçili dönemle filtrelendi; satır bazlı term_id seçim id'si ile farklı olabilir (paralel UUID)
        sched = repo.schedule_from_enrollments(rows)
    else:
        sched = (
            repo.schedule_from_enrollments(rows, only_term_id=response_tid)
            if response_tid
            else []
        )
    return {"student_user_id": user.id, "term_id": response_tid, "schedule": sched}


@student_router.get("/me/exams")
async def student_me_exams(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    exams = repo.list_student_exams(obs_db, user.id, term_id)
    log.info(
        "[OBS-DATA] GET /student/me/exams user=%s count=%s | SQL: obs_exams+enrollments | db=%s | obs_primary_ile_ayni=%s",
        user.id,
        len(exams),
        OBS_ENGINE_URL_SAFE,
        OBS_USES_PRIMARY_DATABASE,
    )
    return {"student_user_id": user.id, "exams": exams}


@student_router.get("/me/grades")
async def student_me_grades(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    grades = repo.list_student_grades(obs_db, user.id, term_id)
    return {"student_user_id": user.id, "grades": grades}


@student_router.get("/me/gpa-summary")
async def student_me_gpa(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    return repo.gpa_summary(obs_db, user.id, term_id)


@student_router.get("/me/transcript")
async def student_me_transcript(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    return repo.transcript(obs_db, user.id)


@student_router.get("/me/attendance")
async def student_me_attendance(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    rows = repo.attendance_summary(obs_db, user.id, term_id)
    return {"student_user_id": user.id, "attendance": rows}


@student_router.get("/me/document-requests")
async def student_doc_req(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    rows = repo.list_document_requests(obs_db, user.id)
    return {"student_user_id": user.id, "requests": rows}


class DocReqCreate(BaseModel):
    requesting_institution: str
    request_reason: str
    document_type: str
    document_subtype: str


@student_router.post("/me/document-requests", status_code=status.HTTP_201_CREATED)
async def student_doc_create(
    body: DocReqCreate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    row = repo.create_document_request(
        obs_db,
        user.id,
        body.requesting_institution,
        body.request_reason,
        body.document_type,
        body.document_subtype,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Öğrenci profili bulunamadı")
    return row


@student_router.get("/me/announcements")
async def student_me_announcements(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    anns = repo.list_student_feed_announcements(obs_db, user.id)
    return {"student_user_id": user.id, "announcements": anns}


@student_router.get("/available-courses")
async def student_available_courses(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    tid, sections = repo.available_sections(obs_db, user.id, term_id)
    return {"term_id": tid, "sections": sections}


class EnrollmentRequest(BaseModel):
    section_ids: list[str]
    note: Optional[str] = None


@student_router.post("/me/enrollment-requests", status_code=status.HTTP_201_CREATED)
async def student_enrollment_request(
    body: EnrollmentRequest,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    adv = repo.get_advisor_api(obs_db, user.id)
    appr = (adv.get("advisor") or {}).get("academic_user_id")
    reqs = repo.create_enrollment_requests(
        obs_db,
        user.id,
        getattr(user, "name", "") or "",
        body.section_ids,
        body.note,
        appr,
    )
    if not reqs and not repo.resolve_student_profile_id(obs_db, user.id):
        raise HTTPException(status_code=404, detail="Öğrenci profili bulunamadı")
    return {"requests": reqs, "count": len(reqs)}


class DraftEnrollmentsBody(BaseModel):
    section_ids: list[str]
    mode: str = "registration"
    exclude_drop_enrollment_ids: list[str] = Field(default_factory=list)


@student_router.post(
    "/me/draft-enrollments", status_code=status.HTTP_201_CREATED
)
async def student_draft_enrollments(
    body: DraftEnrollmentsBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    rows, err = repo.upsert_draft_enrollments(
        obs_db,
        user.id,
        body.section_ids,
        body.mode,
        body.exclude_drop_enrollment_ids or None,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    if not rows and body.section_ids:
        raise HTTPException(
            status_code=400,
            detail="Ders eklenemedi (kontenjan, tekrar veya pencere).",
        )
    return {"created": rows, "count": len(rows)}


@student_router.delete("/me/draft-enrollments/{enrollment_id}")
async def student_delete_draft_enrollment(
    enrollment_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok = repo.delete_draft_enrollment(obs_db, user.id, enrollment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Taslak kayıt bulunamadı")
    return {"id": enrollment_id, "deleted": True}


class SubmitScheduleBody(BaseModel):
    note: Optional[str] = None
    flow: str = "registration"
    enrollment_ids_to_drop: list[str] = Field(default_factory=list)


@student_router.post(
    "/me/submit-schedule", status_code=status.HTTP_201_CREATED
)
async def student_submit_schedule(
    body: SubmitScheduleBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    adv = repo.get_advisor_api(obs_db, user.id)
    appr = (adv.get("advisor") or {}).get("academic_user_id")
    data, err = repo.submit_schedule_to_advisor(
        obs_db,
        user.id,
        body.note,
        appr,
        body.flow,
        body.enrollment_ids_to_drop,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return data


class DropRequest(BaseModel):
    enrollment_id: str
    reason: Optional[str] = None


@student_router.post("/me/drop-requests", status_code=status.HTTP_201_CREATED)
async def student_drop_request(
    body: DropRequest,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    adv = repo.get_advisor_api(obs_db, user.id)
    appr = (adv.get("advisor") or {}).get("academic_user_id")
    row, drop_err = repo.create_drop_request(
        obs_db,
        user.id,
        getattr(user, "name", "") or "",
        body.enrollment_id,
        body.reason,
        appr,
    )
    if drop_err:
        raise HTTPException(status_code=400, detail=drop_err)
    if not row:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return row


class StudentProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None


@student_router.put("/me/profile")
async def student_update_profile(
    body: StudentProfileUpdate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
    db: Session = Depends(get_session),
):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if body.full_name is not None:
        Users.update_user_by_id(user.id, {"name": body.full_name}, db=db)
    sub = {k: v for k, v in patch.items() if k != "full_name"}
    if sub:
        repo.update_student_profile_fields(obs_db, user.id, sub)
    return {
        "user_id": user.id,
        "full_name": body.full_name or getattr(user, "name", ""),
        "phone": body.phone or "",
        "address": body.address or "",
        "emergency_contact": body.emergency_contact or "",
        "emergency_phone": body.emergency_phone or "",
    }


def _empty_graduation(user_id: str, prof: Optional[dict]) -> dict[str, Any]:
    gpa = float(prof["gpa"]) if prof and prof.get("gpa") is not None else 0.0
    ak = int(prof.get("completed_akts") or 0) if prof else 0
    req = int(prof.get("total_akts_required") or 120) if prof else 120
    return {
        "student_user_id": user_id,
        "cumulative_gpa": gpa,
        "total_akts_completed": ak,
        "total_akts_required": req,
        "total_credits_completed": 0,
        "total_credits_required": 90,
        "status": "devam_ediyor",
        "status_label": "Devam Ediyor",
        "eligible_for_graduation": False,
        "missing_akts": max(0, req - ak),
        "missing_credits": 0,
        "requirements": [],
        "approval_steps": [],
    }


@student_router.get("/me/graduation-status")
async def student_graduation(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    prof = repo.get_student_profile_api(obs_db, user.id)
    return _empty_graduation(user.id, prof)


@student_router.get("/me/financial")
async def student_financial(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    _ = obs_db
    return {
        "student_user_id": user.id,
        "is_financially_eligible": True,
        "academic_year": "",
        "terms": [],
        "scholarships": [],
        "total_paid": 0,
        "total_scholarship": 0,
    }


@student_router.get("/me/curriculum-status")
async def student_curriculum(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    data = repo.student_curriculum_status(obs_db, user.id)
    cats = data.get("categories") or []
    n_courses = sum(len(c.get("courses") or []) for c in cats)
    log.info(
        "[OBS-DATA] GET /student/me/curriculum-status user=%s kategori=%s toplam_ders_satiri=%s yuzde=%s | SQL: obs_course_enrollments | db=%s | obs_primary_ile_ayni=%s",
        user.id,
        len(cats),
        n_courses,
        data.get("overall_progress_pct"),
        OBS_ENGINE_URL_SAFE,
        OBS_USES_PRIMARY_DATABASE,
    )
    return data


@student_router.get("/me/todo-list")
async def student_todo(user=Depends(get_verified_user)):
    return {"student_user_id": user.id, "todos": []}


@student_router.get("/me/applications")
async def student_applications(
    application_type: Optional[str] = Query(None),
    user=Depends(get_verified_user),
):
    _ = application_type
    return {"student_user_id": user.id, "applications": []}


class ApplicationCreate(BaseModel):
    application_type: str
    term_id: Optional[str] = None
    course_code: Optional[str] = None
    notes: Optional[str] = None
    extra: Optional[dict[str, Any]] = None


@student_router.post("/me/applications", status_code=status.HTTP_201_CREATED)
async def student_applications_create(
    body: ApplicationCreate, user=Depends(get_verified_user)
):
    return {
        "id": str(uuid.uuid4()),
        "application_type": body.application_type,
        "status": "pending",
        "submitted_at": datetime.datetime.utcnow().isoformat(),
        "course_code": body.course_code,
        "notes": body.notes,
    }


def _prep_guard(obs_db: Session, user_id: str):
    spid = repo.resolve_student_profile_id(obs_db, user_id)
    if not spid or not repo.student_is_prep(obs_db, spid):
        raise HTTPException(status_code=404, detail="Hazırlık öğrencisi değil")


@student_router.get("/me/prep/schedule")
async def prep_schedule(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    _prep_guard(obs_db, user.id)
    _, rows = repo.list_enrollments(obs_db, user.id, term_id, ("active", "pending_drop"))
    response_tid = term_id or (rows[0]["term_id"] if rows else "")
    if not rows:
        sched = []
    elif term_id:
        sched = repo.schedule_from_enrollments(rows)
    else:
        sched = (
            repo.schedule_from_enrollments(rows, only_term_id=response_tid)
            if response_tid
            else []
        )
    return {"student_user_id": user.id, "schedule": sched}


@student_router.get("/me/prep/exams")
async def prep_exams(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    _prep_guard(obs_db, user.id)
    exams = repo.list_student_exams(obs_db, user.id, term_id)
    return {"student_user_id": user.id, "exams": exams}


@student_router.get("/me/prep/grades")
async def prep_grades(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    _prep_guard(obs_db, user.id)
    grades = repo.list_student_grades(obs_db, user.id, None)
    out = []
    for g in grades:
        out.append(
            {
                "course_code": g["course_code"],
                "course_name": g["course_name"],
                "midterm": g["midterm"],
                "final": g["final"],
                "letter_grade": g["letter_grade"],
                "is_published": g["is_published"],
                "is_finalized": g["is_finalized"],
            }
        )
    return {"student_user_id": user.id, "grades": out}


@student_router.get("/me/prep/attendance")
async def prep_attendance(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    _prep_guard(obs_db, user.id)
    rows = repo.attendance_summary(obs_db, user.id, term_id)
    return {"student_user_id": user.id, "attendance": rows}


@student_router.get("/me/internship")
async def student_internship(user=Depends(get_verified_user)):
    return {"student_user_id": user.id, "internships": []}


@student_router.post("/me/internship", status_code=status.HTTP_201_CREATED)
async def student_internship_post(user=Depends(get_verified_user)):
    return {"id": str(uuid.uuid4()), "student_user_id": user.id, "status": "pending"}


@student_router.get("/me/credit-transfer")
async def student_credit_transfer(user=Depends(get_verified_user)):
    return {"student_user_id": user.id, "transfers": []}


@student_router.post("/me/credit-transfer", status_code=status.HTTP_201_CREATED)
async def student_credit_transfer_post(user=Depends(get_verified_user)):
    return {"id": str(uuid.uuid4()), "student_user_id": user.id, "status": "bekliyor"}


# ---------------------------------------------------------------------------
# Akademisyen
# ---------------------------------------------------------------------------


@academic_user_router.get("/me/sections")
async def academic_me_sections(
    term_id: Optional[str] = Query(None),
    include_classrooms: bool = Query(False),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    sections = repo.academic_sections(obs_db, user.id, term_id)
    out: dict[str, Any] = {
        "academic_user_id": user.id,
        "term_id_filter": term_id,
        "sections": sections,
    }
    if include_classrooms:
        out["classrooms"] = repo.list_classrooms_dropdown(obs_db)
    return out


def _academic_classrooms_payload(obs_db: Session) -> dict[str, Any]:
    """Dropdown: code veya name dolu tüm derslikler; label ile görünen metin."""
    return {"classrooms": repo.list_classrooms_dropdown(obs_db)}


@academic_user_router.get("/classrooms")
async def academic_list_classrooms(
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    """Sınav tanımlamada derslik seçimi (obs_classrooms)."""
    return _academic_classrooms_payload(obs_db)


@academic_user_router.get("/me/classrooms")
async def academic_list_classrooms_me(
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    """`/me/sections` ile aynı çatı — proxy/cache uyumu için ikinci yol."""
    return _academic_classrooms_payload(obs_db)


@academic_user_router.get("/me/sections/{section_id}/students")
async def academic_section_students(
    section_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    sec, students = repo.section_students(obs_db, section_id)
    if not sec:
        raise HTTPException(status_code=404, detail="Şube bulunamadı")
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return {"section_id": section_id, "section": sec, "students": students}


@academic_user_router.get("/sections/{section_id}/exams")
async def academic_section_exams(
    section_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return {"section_id": section_id, "exams": repo.section_exams(obs_db, section_id)}


def _normalize_exam_date_for_db(raw: Optional[str]) -> str:
    """PostgreSQL date için yyyy-mm-dd üret; boş/geçersizde 400."""
    s = (raw or "").strip()
    if not s:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sınav tarihi zorunludur. Lütfen takvimden bir tarih seçin.",
        )
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            datetime.date.fromisoformat(s[:10])
            return s[:10]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sınav tarihi geçersiz. Lütfen geçerli bir gün seçin.",
            )
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sınav tarihi geçersiz (gün veya ay hatalı).",
            )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Sınav tarihi anlaşılamadı. Takvimden seçin veya yyyy-mm-dd (ör. 2026-04-13) girin.",
    )


def _normalize_exam_time_for_db(raw: Optional[str]) -> str:
    """PostgreSQL time için HH:MM:SS."""
    s = (raw or "").strip()
    if not s:
        return "09:00:00"
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s)
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sınav saati geçersiz. Örnek: 09:00 veya 14:30.",
        )
    h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if h > 23 or mi > 59 or sec > 59:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sınav saati geçersiz (saat 0–23, dakika ve saniye 0–59).",
        )
    return f"{h:02d}:{mi:02d}:{sec:02d}"


def _validate_exam_weight(wp: float) -> float:
    try:
        x = float(wp)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ağırlık yüzdesi sayı olmalıdır.",
        )
    if x <= 0 or x > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ağırlık yüzdesi 0'dan büyük ve en fazla 100 olmalıdır.",
        )
    return x


def _normalize_exam_patch_dates(patch: dict[str, Any]) -> dict[str, Any]:
    """PUT gövdesindeki tarih/saat/ağırlığı güvenli biçime çevir."""
    out = dict(patch)
    if "exam_date" in out:
        ed = out.get("exam_date")
        if ed is None:
            pass
        elif str(ed).strip() == "":
            out["exam_date"] = ""
        else:
            out["exam_date"] = _normalize_exam_date_for_db(str(ed))
    if "exam_time" in out:
        et = out.get("exam_time")
        if et is None:
            pass
        elif str(et).strip() == "":
            out["exam_time"] = "09:00:00"
        else:
            out["exam_time"] = _normalize_exam_time_for_db(str(et))
    if "weight_percent" in out and out.get("weight_percent") is not None:
        out["weight_percent"] = _validate_exam_weight(float(out["weight_percent"]))
    return out


class ExamCreate(BaseModel):
    exam_type: str = "midterm"
    exam_date: str
    exam_time: str = "09:00"
    classroom: Optional[str] = None
    weight_percent: float = 40.0


@academic_user_router.post(
    "/sections/{section_id}/exams", status_code=status.HTTP_201_CREATED
)
async def academic_create_exam(
    section_id: str,
    body: ExamCreate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    exam_date_iso = _normalize_exam_date_for_db(body.exam_date)
    exam_time_norm = _normalize_exam_time_for_db(body.exam_time)
    weight = _validate_exam_weight(body.weight_percent)
    etype = (body.exam_type or "midterm").strip() or "midterm"
    try:
        return repo.insert_exam(
            obs_db,
            section_id,
            etype,
            exam_date_iso,
            exam_time_norm,
            body.classroom,
            weight,
        )
    except SQLAlchemyError:
        obs_db.rollback()
        log.warning("insert_exam SQLAlchemyError", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sınav kaydedilemedi. Tarih ve saati kontrol edin; zorunlu alanları doldurun.",
        ) from None


class ExamUpdate(BaseModel):
    exam_type: Optional[str] = None
    exam_date: Optional[str] = None
    exam_time: Optional[str] = None
    classroom: Optional[str] = None
    weight_percent: Optional[float] = None


@academic_user_router.put("/sections/{section_id}/exams/{exam_id}")
async def academic_update_exam(
    section_id: str,
    exam_id: str,
    body: ExamUpdate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    patch = _normalize_exam_patch_dates(patch)
    try:
        row = repo.update_section_exam(obs_db, section_id, exam_id, patch)
    except SQLAlchemyError:
        obs_db.rollback()
        log.warning("update_section_exam SQLAlchemyError", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sınav güncellenemedi. Tarih ve saat biçimini kontrol edin.",
        ) from None
    if not row:
        raise HTTPException(status_code=404, detail="Sınav bulunamadı")
    return row


@academic_user_router.delete("/sections/{section_id}/exams/{exam_id}")
async def academic_delete_exam(
    section_id: str,
    exam_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    ok = repo.delete_section_exam(obs_db, section_id, exam_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sınav bulunamadı")
    return {"section_id": section_id, "exam_id": exam_id, "deleted": True}


@academic_user_router.get("/sections/{section_id}/grades")
async def academic_section_grades(
    section_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    sec = repo.section_meta(obs_db, section_id)
    return {
        "section_id": section_id,
        "section": sec,
        "students": repo.section_grade_rows(obs_db, section_id),
    }


class GradeInput(BaseModel):
    grades: list[dict[str, Any]]


@academic_user_router.put("/sections/{section_id}/grades")
async def academic_put_grades(
    section_id: str,
    body: GradeInput,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    try:
        # repo.upsert_grades dönüşünü doğrudan "n, err = ..." ile ayırma (eski int dönüş TypeError veriyordu).
        n, err = _parse_grade_upsert_return(
            repo.upsert_grades(obs_db, section_id, body.grades)
        )
    except Exception as e:
        log.exception(
            "upsert_grades başarısız section_id=%s user=%s",
            section_id,
            getattr(user, "id", None),
        )
        # Tarayıcıda / network tab'da gerçek DB-SQL mesajını görmek için (kısaltılmış)
        hint = str(e).strip().replace("\n", " ")
        if len(hint) > 280:
            hint = hint[:277] + "..."
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Not kaydı yazılamadı: {hint}",
        )
    if err == "finalized":
        raise HTTPException(status_code=409, detail="Kesinleşmiş not güncellenemez")
    return {"section_id": section_id, "updated": n}


@academic_user_router.delete("/sections/{section_id}/grades/{enrollment_id}")
async def academic_delete_grade(
    section_id: str,
    enrollment_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    ok, err = repo.delete_grade_entry(obs_db, section_id, enrollment_id)
    if not ok and err == "not_found":
        raise HTTPException(status_code=404, detail="Not kaydı bulunamadı")
    if not ok and err == "finalized":
        raise HTTPException(
            status_code=409,
            detail="Kesinleşmiş not silinemez",
        )
    return {"section_id": section_id, "enrollment_id": enrollment_id, "deleted": True}


@academic_user_router.post("/sections/{section_id}/grades/finalize")
async def academic_finalize_grades(
    section_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    # finalized_by FK → Open WebUI "user" tablosu (obs akademik profil UUID’si değil).
    try:
        repo.finalize_section_grades(obs_db, section_id, str(user.id))
    except Exception:
        log.exception(
            "finalize_section_grades başarısız section_id=%s user=%s",
            section_id,
            getattr(user, "id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Notlar kesinleştirilemedi (sunucu / veritabanı). Yönetici konsoluna bakın.",
        )
    return {"section_id": section_id, "finalized": True}


class GradeWeightsUpdate(BaseModel):
    midterm_weight_percent: float
    final_weight_percent: float


@academic_user_router.put("/sections/{section_id}/grade-weights")
@academic_user_router.post("/sections/{section_id}/grade-weights")
async def academic_update_grade_weights(
    section_id: str,
    body: GradeWeightsUpdate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    if body.midterm_weight_percent + body.final_weight_percent != 100:
        raise HTTPException(status_code=400, detail="Toplam %100 olmalı")
    repo.update_section_grade_weights(
        obs_db, section_id, body.midterm_weight_percent, body.final_weight_percent
    )
    sec = repo.section_meta(obs_db, section_id)
    return {"section_id": section_id, "section": sec}


@academic_user_router.post("/sections/{section_id}/grades/{enrollment_id}/unfinalize")
@academic_user_router.put("/sections/{section_id}/grades/{enrollment_id}/unfinalize")
async def academic_unfinalize_grade(
    section_id: str,
    enrollment_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    ok, err = repo.unfinalize_grade_entry(obs_db, section_id, enrollment_id)
    if not ok and err == "not_found":
        raise HTTPException(status_code=404, detail="Not kaydı bulunamadı")
    return {"section_id": section_id, "enrollment_id": enrollment_id, "unfinalized": True}


class AttendanceInput(BaseModel):
    week_no: int
    records: list[dict[str, Any]]


class AttendanceRecordsInput(BaseModel):
    records: list[dict[str, Any]]


@academic_user_router.get("/sections/{section_id}/attendance/{week_no}")
async def academic_get_attendance(
    section_id: str,
    week_no: int,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    try:
        rows = repo.section_attendance_week(obs_db, section_id, week_no)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"section_id": section_id, "week_no": week_no, "records": rows}


@academic_user_router.put("/sections/{section_id}/attendance/{week_no}")
async def academic_put_attendance(
    section_id: str,
    week_no: int,
    body: AttendanceRecordsInput,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    # recorded_by → PostgreSQL FK `user.id` (Open WebUI kullanıcısı).
    # obs_academic_profiles.id ile karıştırma — FK ihlali ve HTTP 500 oluşur.
    try:
        n = repo.record_attendance(
            obs_db, section_id, week_no, body.records, str(user.id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"section_id": section_id, "week_no": week_no, "recorded": n}


@academic_user_router.put("/sections/{section_id}/attendance")
async def academic_put_attendance_legacy(
    section_id: str,
    body: AttendanceInput,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    try:
        n = repo.record_attendance(
            obs_db, section_id, body.week_no, body.records, str(user.id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"section_id": section_id, "week_no": body.week_no, "recorded": n}


@academic_user_router.get("/me/advisees")
async def academic_me_advisees(
    user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    return {
        "academic_user_id": user.id,
        "advisees": repo.academic_advisees(obs_db, user.id),
    }


class AcademicConsultingHoursBody(BaseModel):
    """Danışmanlık / görüşme saatleri — serbest metin (örn. Salı 14–16)."""

    consulting_hours: Optional[str] = None


@academic_user_router.get("/me/consulting-hours")
async def academic_me_consulting_hours_get(
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    return repo.get_academic_own_consulting_hours(obs_db, str(user.id))


@academic_user_router.put("/me/consulting-hours")
async def academic_me_consulting_hours_put(
    body: AcademicConsultingHoursBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    return repo.update_academic_own_consulting_hours(
        obs_db,
        str(user.id),
        (body.consulting_hours if body.consulting_hours is not None else "") or "",
    )


@academic_user_router.get("/me/approval-requests")
async def academic_me_approval_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    reqs = repo.list_approval_requests_for_academic(obs_db, user.id, status_filter)
    reqs = repo.enrich_approval_requests_add_drop(obs_db, user.id, reqs)
    return {"academic_user_id": user.id, "requests": reqs, "total": len(reqs)}


class ApprovalAction(BaseModel):
    action: str
    note: Optional[str] = None


@academic_user_router.patch("/approval-requests/{request_id}")
async def academic_approve_request(
    request_id: str,
    body: ApprovalAction,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok, err = repo.resolve_approval(
        obs_db, request_id, user.id, body.action == "approve", body.note
    )
    if not ok:
        raise HTTPException(
            status_code=400 if err else 404,
            detail=err or "Talep bulunamadı",
        )
    return {
        "id": request_id,
        "status": "approved" if body.action == "approve" else "rejected",
    }


@academic_user_router.get("/me/advisees/{student_user_id}/enrollments")
async def academic_advisee_enrollments(
    student_user_id: str,
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    spid, rows = repo.list_advisee_enrollments(
        obs_db, user.id, student_user_id, term_id
    )
    if spid is None:
        raise HTTPException(status_code=403, detail="Bu öğrencinin danışmanı değilsiniz.")
    return {
        "student_user_id": student_user_id,
        "term_id": term_id,
        "enrollments": rows,
    }


class AdviseeScheduleBody(BaseModel):
    student_user_id: str
    term_id: str


@academic_user_router.post("/me/advisees/finalize-schedule")
async def academic_finalize_advisee_schedule(
    body: AdviseeScheduleBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok, err = repo.finalize_advisee_schedule(
        obs_db, user.id, body.student_user_id, body.term_id
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err or "İşlem yapılamadı")
    return {"ok": True, "student_user_id": body.student_user_id, "term_id": body.term_id}


@academic_user_router.post("/me/advisees/reject-schedule")
async def academic_reject_advisee_schedule(
    body: AdviseeScheduleBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok, err = repo.reject_advisee_schedule(
        obs_db, user.id, body.student_user_id, body.term_id
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err or "İşlem yapılamadı")
    return {"ok": True, "student_user_id": body.student_user_id, "term_id": body.term_id}


class AdviseeAddEnrollmentBody(BaseModel):
    student_user_id: str
    section_id: str


@academic_user_router.post("/me/advisees/enrollments", status_code=status.HTTP_201_CREATED)
async def academic_advisee_add_enrollment(
    body: AdviseeAddEnrollmentBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    row, err = repo.advisor_add_enrollment_line(
        obs_db, user.id, body.student_user_id, body.section_id
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    return row


@academic_user_router.delete("/me/advisees/enrollments/{enrollment_id}")
async def academic_advisee_remove_enrollment(
    enrollment_id: str,
    student_user_id: str = Query(..., description="Öğrenci user id"),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok, err = repo.advisor_remove_enrollment_line(
        obs_db, user.id, student_user_id, enrollment_id
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err or "Silinemedi")
    return {"id": enrollment_id, "deleted": True}


class AcademicAnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=255)
    audience_type: str = Field(default="section", max_length=32)
    department_id: Optional[str] = None
    course_section_id: Optional[str] = None
    student_no: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _strip_text(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "title" in data and data["title"] is not None:
                data["title"] = str(data["title"]).strip()
            if "content" in data and data["content"] is not None:
                data["content"] = str(data["content"]).strip()
        return data


class AnnouncementUpdateBody(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = Field(None, max_length=255)
    audience_type: Optional[str] = Field(None, max_length=32)
    department_id: Optional[str] = None
    course_section_id: Optional[str] = None
    student_no: Optional[str] = None
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def _strip_optional(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for k in ("title", "content"):
                if k in data and data[k] is not None:
                    data[k] = str(data[k]).strip()
            if "student_no" in data and data["student_no"] is not None:
                data["student_no"] = str(data["student_no"]).strip() or None
        return data


@academic_user_router.get("/announcements")
async def academic_list_my_announcements(
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
    limit: int = Query(500, ge=1, le=2000),
):
    rows = repo.list_announcements_created_by(obs_db, user.id, limit=limit)
    return {"announcements": rows}


@academic_user_router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def academic_create_announcement(
    body: AcademicAnnouncementCreate,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    try:
        did, csid, sn = repo.resolve_academic_announcement_targets(
            obs_db,
            user.id,
            body.audience_type,
            body.department_id,
            body.course_section_id,
            body.student_no,
        )
        title = repo.clamp_announcement_varchar(body.title)
        content = repo.clamp_announcement_varchar(body.content)
        if not title or not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Başlık ve içerik boş olamaz.",
            )
        aid = repo.insert_announcement(
            obs_db,
            user.id,
            title,
            content,
            body.audience_type,
            did,
            csid,
            student_number=sn,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duyuru kaydedilemedi (veri veya veritabanı kısıtı).",
        )
    except DataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz alan formatı (ör. kimlik).",
        )
    return {
        "id": aid,
        "title": title,
        "content": content,
        "audience_type": body.audience_type,
    }


@academic_user_router.put("/announcements/{announcement_id}")
async def academic_update_announcement(
    announcement_id: str,
    body: AnnouncementUpdateBody,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Güncellenecek alan yok."
        )
    try:
        if "department_id" in raw:
            raw["department_id"] = repo.optional_uuid_param(
                raw.get("department_id"), "Bölüm kimliği"
            )
        if "course_section_id" in raw:
            raw["course_section_id"] = repo.optional_uuid_param(
                raw.get("course_section_id"), "Şube kimliği"
            )
        if "title" in raw and raw["title"] is not None:
            raw["title"] = repo.clamp_announcement_varchar(raw["title"])
        if "content" in raw and raw["content"] is not None:
            raw["content"] = repo.clamp_announcement_varchar(raw["content"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        ok, err = repo.update_announcement_owned(
            obs_db, announcement_id, user.id, raw, require_creator=True
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Güncelleme reddedildi (veri veya veritabanı kısıtı).",
        )
    except DataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz alan formatı.",
        )
    if not ok:
        if err == "not_found":
            raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
        if err == "forbidden":
            raise HTTPException(status_code=403, detail="Bu duyuruyu düzenleyemezsiniz.")
        if err == "no_fields":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Güncellenecek alan yok."
            )
        raise HTTPException(status_code=400, detail="Güncellenemedi.")
    row = repo.get_announcement_mgmt_by_id(obs_db, announcement_id)
    if not row:
        raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
    return row


@academic_user_router.delete("/announcements/{announcement_id}")
async def academic_delete_announcement(
    announcement_id: str,
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok, err = repo.delete_announcement_owned(
        obs_db, announcement_id, user.id, require_creator=True
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
    return {"id": announcement_id, "deleted": True}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


def _admin_delete_result(ok: bool, err: str) -> dict[str, bool]:
    if ok:
        return {"deleted": True}
    if err == "in_use":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kayıt ilişkili veriler nedeniyle silinemiyor.",
        )
    raise HTTPException(status_code=404, detail="Bulunamadı.")


@admin_router.get("/stats")
async def admin_stats(
    obs_db: Session = Depends(get_obs_session),
    db: Session = Depends(get_session),
    _u=Depends(get_obs_admin_user),
):
    c = repo.admin_counts(obs_db)
    ures = Users.get_users(filter=None, skip=0, limit=10_000, db=db)
    users = ures.get("users", [])
    return {
        **c,
        "users_total": len(users),
        "users_active": len(users),
    }


@admin_router.get("/departments")
async def admin_list_departments(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    return repo.list_departments(obs_db)


class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1)


@admin_router.post("/departments", status_code=status.HTTP_201_CREATED)
async def admin_create_department(
    body: DepartmentCreate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    return repo.admin_insert_department(obs_db, body.code, body.name)


class DepartmentUpdateBody(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    faculty_name: Optional[str] = None


@admin_router.put("/departments/{department_id}")
async def admin_put_department(
    department_id: str,
    body: DepartmentUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    row = repo.admin_update_department(obs_db, department_id, raw)
    if not row:
        raise HTTPException(status_code=404, detail="Bölüm bulunamadı.")
    return row


@admin_router.delete("/departments/{department_id}")
async def admin_delete_department_route(
    department_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_department(obs_db, department_id)
    return _admin_delete_result(ok, err)


@admin_router.get("/terms")
async def admin_list_terms(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    return repo.list_terms(obs_db)


class TermCreate(BaseModel):
    name: str
    academic_year: str = ""
    season: str = "fall"
    starts_at: str = ""
    ends_at: str = ""
    is_active: bool = False


@admin_router.post("/terms", status_code=status.HTTP_201_CREATED)
async def admin_create_term(
    body: TermCreate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    return repo.admin_insert_term(
        obs_db,
        body.name,
        body.academic_year,
        body.season,
        body.starts_at,
        body.ends_at,
        body.is_active,
    )


class TermUpdateBody(BaseModel):
    name: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: Optional[bool] = None


@admin_router.put("/terms/{term_id}")
async def admin_put_term(
    term_id: str,
    body: TermUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    row = repo.admin_update_term(obs_db, term_id, raw)
    if not row:
        raise HTTPException(status_code=404, detail="Dönem bulunamadı.")
    return row


@admin_router.delete("/terms/{term_id}")
async def admin_delete_term_route(
    term_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_term(obs_db, term_id)
    return _admin_delete_result(ok, err)


class TermRegistrationWindowsBody(BaseModel):
    registration_open: Optional[bool] = None
    registration_start: Optional[str] = None
    registration_end: Optional[str] = None
    add_drop_open: Optional[bool] = None
    add_drop_start: Optional[str] = None
    add_drop_end: Optional[str] = None


@admin_router.patch("/terms/{term_id}/registration-windows")
async def admin_patch_term_registration_windows(
    term_id: str,
    body: TermRegistrationWindowsBody,
    obs_db: Session = Depends(get_obs_session),
    user=Depends(get_obs_admin_user),
):
    row = repo.admin_update_term_registration_windows(
        obs_db,
        term_id,
        body.registration_open,
        body.registration_start,
        body.registration_end,
        body.add_drop_open,
        body.add_drop_start,
        body.add_drop_end,
        acting_user_id=str(user.id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Dönem bulunamadı")
    return row


@admin_router.get("/courses")
async def admin_list_courses(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    return repo.list_courses_raw(obs_db)


class CourseCreate(BaseModel):
    department_id: str
    code: str
    name: str
    credits: int = 3
    akts: int = 5
    class_year: int = 1
    course_type: str = "Z"
    theory_hours: str = "3+0"
    language: str = "Türkçe"


@admin_router.post("/courses", status_code=status.HTTP_201_CREATED)
async def admin_create_course(
    body: CourseCreate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    return repo.admin_insert_course(
        obs_db,
        body.department_id,
        body.code,
        body.name,
        body.credits,
        body.akts,
        body.class_year,
        body.course_type,
        body.theory_hours,
        body.language,
    )


class CourseUpdateBody(BaseModel):
    department_id: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    credits: Optional[int] = None
    akts: Optional[int] = None
    class_year: Optional[int] = None
    course_type: Optional[str] = None
    theory_hours: Optional[str] = None
    language: Optional[str] = None
    is_mandatory: Optional[bool] = None
    semester_no: Optional[int] = None
    curriculum_semester: Optional[int] = None


@admin_router.put("/courses/{course_id}")
async def admin_put_course(
    course_id: str,
    body: CourseUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    if "course_type" in raw:
        raw["type"] = raw.pop("course_type")
    row = repo.admin_update_course(obs_db, course_id, raw)
    if not row:
        raise HTTPException(status_code=404, detail="Ders bulunamadı.")
    return row


@admin_router.delete("/courses/{course_id}")
async def admin_delete_course_route(
    course_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_course(obs_db, course_id)
    return _admin_delete_result(ok, err)


@admin_router.get("/classrooms")
async def admin_list_classrooms(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    return repo.list_classrooms_raw(obs_db)


class ClassroomCreate(BaseModel):
    building: str = ""
    name: str
    capacity: int = 30
    is_online: bool = False


@admin_router.post("/classrooms", status_code=status.HTTP_201_CREATED)
async def admin_create_classroom(
    body: ClassroomCreate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    return repo.admin_insert_classroom(
        obs_db, body.building, body.name, body.capacity, body.is_online
    )


class ClassroomUpdateBody(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[int] = None
    capacity: Optional[int] = None
    is_online: Optional[bool] = None


@admin_router.put("/classrooms/{classroom_id}")
async def admin_put_classroom(
    classroom_id: str,
    body: ClassroomUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    row = repo.admin_update_classroom(obs_db, classroom_id, raw)
    if not row:
        raise HTTPException(status_code=404, detail="Derslik bulunamadı.")
    return row


@admin_router.delete("/classrooms/{classroom_id}")
async def admin_delete_classroom_route(
    classroom_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_classroom(obs_db, classroom_id)
    return _admin_delete_result(ok, err)


@admin_router.get("/instructors")
async def admin_instructors(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    return repo.list_instructors(obs_db)


class AcademicProfileUpdateBody(BaseModel):
    staff_number: Optional[str] = None
    title: Optional[str] = None
    department_id: Optional[str] = None
    office: Optional[str] = None
    phone: Optional[str] = None
    consulting_hours: Optional[str] = None


@admin_router.put("/academics/{user_id}")
async def admin_put_academic(
    user_id: str,
    body: AcademicProfileUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    row = repo.admin_update_academic_profile_by_user_id(obs_db, user_id, raw)
    if not row:
        raise HTTPException(
            status_code=404, detail="Akademisyen profili bulunamadı (user_id)."
        )
    return row


@admin_router.delete("/academics/{user_id}")
async def admin_delete_academic_route(
    user_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_academic_profile_by_user_id(obs_db, user_id)
    return _admin_delete_result(ok, err)


class StudentProfileAdminUpdateBody(BaseModel):
    student_number: Optional[str] = None
    department_id: Optional[str] = None
    enrollment_date: Optional[str] = None
    class_year: Optional[int] = None
    program: Optional[str] = None
    gpa: Optional[float] = None
    completed_akts: Optional[int] = None
    total_akts_required: Optional[int] = None
    status: Optional[str] = None
    is_financially_eligible: Optional[bool] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    program_semester_number: Optional[int] = None


@admin_router.put("/students/{user_id}")
async def admin_put_student_profile(
    user_id: str,
    body: StudentProfileAdminUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    row = repo.admin_update_student_profile_by_user_id(obs_db, user_id, raw)
    if not row:
        raise HTTPException(
            status_code=404, detail="Öğrenci profili bulunamadı (user_id)."
        )
    return row


@admin_router.delete("/students/{user_id}")
async def admin_delete_student_profile_route(
    user_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_student_profile_by_user_id(obs_db, user_id)
    return _admin_delete_result(ok, err)


@admin_router.get("/advisor-assignments/instructors")
async def admin_advisor_assignment_instructors(
    department_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    db: Session = Depends(get_session),
    _u=Depends(get_obs_admin_user),
):
    rows = repo.list_academic_instructors_dropdown(obs_db, db, department_id)
    rows = repo.augment_instructors_with_primary_academicians(rows, db, department_id)
    payload = _sanitize_for_json(jsonable_encoder({"instructors": rows}))
    return JSONResponse(content=payload)


# ---------------------------------------------------------------------------
# Admin — Danışman Atama (obs_student_advisors)
# ---------------------------------------------------------------------------


@admin_router.get("/student-advisors")
async def admin_list_student_advisors(
    search: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    advisor_user_id: Optional[str] = Query(None),
    only_unassigned: bool = Query(False),
    obs_db: Session = Depends(get_obs_session),
    db: Session = Depends(get_session),
    _u=Depends(get_obs_admin_user),
):
    rows = repo.list_students_with_advisor(
        obs_db,
        db,
        search=search,
        department_id=department_id,
        advisor_filter=advisor_user_id,
        only_unassigned=only_unassigned,
    )
    payload = _sanitize_for_json(jsonable_encoder({"students": rows, "total": len(rows)}))
    return JSONResponse(content=payload)


class StudentAdvisorAssignBody(BaseModel):
    """`advisor_user_id` boş/None = mevcut danışmanlığı kapat."""

    advisor_user_id: Optional[str] = None


@admin_router.put("/student-advisors/{student_user_id}")
async def admin_assign_student_advisor(
    student_user_id: str,
    body: StudentAdvisorAssignBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    adv = (body.advisor_user_id or "").strip() or None
    log.info(
        "[OBS-ADMIN] PUT /admin/student-advisors/%s body=%r -> resolved adv=%r",
        student_user_id,
        body.model_dump(),
        adv,
    )
    ok, err = repo.assign_student_advisor(obs_db, student_user_id, adv)
    log.info(
        "[OBS-ADMIN] PUT /admin/student-advisors/%s result ok=%s err=%s",
        student_user_id,
        ok,
        err,
    )
    if not ok:
        if err == "student_profile_not_found":
            raise HTTPException(status_code=404, detail="Öğrenci profili bulunamadı.")
        if err in ("advisor_profile_not_found", "advisor_no_department_for_stub"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Akademisyen profili oluşturulamadı (bölüm yok)."
                    if err == "advisor_no_department_for_stub"
                    else "Akademisyen profili bulunamadı."
                ),
            )
        if err == "missing_student":
            raise HTTPException(status_code=400, detail="Öğrenci kimliği zorunlu.")
        raise HTTPException(status_code=500, detail=f"Atama yapılamadı: {err}")
    return {"ok": True, "student_user_id": student_user_id, "advisor_user_id": adv}


@admin_router.delete("/student-advisors/{student_user_id}")
async def admin_clear_student_advisor(
    student_user_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    log.info(
        "[OBS-ADMIN] DELETE /admin/student-advisors/%s (kaldır)",
        student_user_id,
    )
    ok, err = repo.assign_student_advisor(obs_db, student_user_id, None)
    log.info(
        "[OBS-ADMIN] DELETE /admin/student-advisors/%s result ok=%s err=%s",
        student_user_id,
        ok,
        err,
    )
    if not ok:
        if err == "student_profile_not_found":
            raise HTTPException(status_code=404, detail="Öğrenci profili bulunamadı.")
        raise HTTPException(status_code=500, detail=f"Kaldırılamadı: {err}")
    return {"ok": True, "student_user_id": student_user_id, "advisor_user_id": None}


class StudentAdvisorBulkAssignBody(BaseModel):
    student_user_ids: list[str]
    advisor_user_id: Optional[str] = None


@admin_router.post("/student-advisors/bulk")
async def admin_bulk_assign_student_advisor(
    body: StudentAdvisorBulkAssignBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    if not body.student_user_ids:
        raise HTTPException(status_code=400, detail="Öğrenci listesi boş.")
    adv = (body.advisor_user_id or "").strip() or None
    result = repo.bulk_assign_student_advisor(obs_db, body.student_user_ids, adv)
    payload = _sanitize_for_json(jsonable_encoder(result))
    return JSONResponse(content=payload)


@admin_router.get("/course-sections")
async def admin_sections(
    term_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    rows = repo.list_sections_raw(obs_db, term_id)
    log.info(
        "[OBS-ADMIN] GET /admin/course-sections term_id=%s -> PostgreSQL count=%s | db=%s",
        term_id,
        len(rows),
        OBS_ENGINE_URL_SAFE,
    )
    return rows


class CourseSectionCreate(BaseModel):
    course_id: str
    course_code: str = ""
    course_name: str = ""
    term_id: str
    term_name: str = ""
    section_no: int = 1
    classroom_id: str = ""
    classroom_code: str = ""
    instructor_id: str = ""
    instructor_label: str = ""
    day_of_week: str = "Pazartesi"
    start_time: str = "09:00"
    end_time: str = "10:50"
    capacity: int = 40


@admin_router.post("/course-sections", status_code=status.HTTP_201_CREATED)
async def admin_create_section(
    body: CourseSectionCreate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    log.info(
        "[OBS-ADMIN] POST /admin/course-sections -> PostgreSQL obs_course_sections | course_id=%s term_id=%s section_no=%s instructor_user_id=%s classroom_id=%s | db=%s",
        body.course_id,
        body.term_id,
        body.section_no,
        body.instructor_id or "(yok)",
        body.classroom_id or "(yok)",
        OBS_ENGINE_URL_SAFE,
    )
    crid = body.classroom_id or None
    if not crid and body.classroom_code:
        crid = repo.resolve_classroom_id_by_code(obs_db, body.classroom_code)
    iuid = body.instructor_id or None
    try:
        sid = repo.admin_insert_section(
            obs_db,
            body.course_id,
            body.term_id,
            body.section_no,
            iuid,
            crid,
            body.day_of_week,
            body.start_time,
            body.end_time,
            body.capacity,
        )
    except ValueError as e:
        if str(e) == "no_department_for_stub_profile":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Akademik özlük için en az bir bölüm tanımlı olmalıdır.",
            ) from e
        raise
    except IntegrityError as e:
        obs_db.rollback()
        log.warning("[OBS-ADMIN] course-sections IntegrityError: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Veritabanı kısıtı: geçersiz ders/dönem/akademisyen/derslik veya aynı şube zaten var.",
        ) from e
    except SQLAlchemyError as e:
        obs_db.rollback()
        log.exception("[OBS-ADMIN] course-sections SQLAlchemyError: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OBS veritabanı hatası (sunucu loguna bakın).",
        ) from e
    log.info("[OBS-ADMIN] course-sections olusturuldu id=%s", sid.get("id"))
    return sid


class CourseSectionUpdateBody(BaseModel):
    course_id: Optional[str] = None
    term_id: Optional[str] = None
    section_no: Optional[int] = None
    classroom_id: Optional[str] = None
    instructor_user_id: Optional[str] = None
    day_of_week: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    capacity: Optional[int] = None


@admin_router.put("/sections/{section_id}")
async def admin_put_section(
    section_id: str,
    body: CourseSectionUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    if raw.get("classroom_id") == "":
        raw["classroom_id"] = None
    try:
        row = repo.admin_update_course_section(obs_db, section_id, raw)
    except ValueError as e:
        se = str(e)
        if se == "no_department_for_stub_profile":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Akademik özlük için en az bir bölüm tanımlı olmalıdır.",
            ) from e
        raise
    if not row:
        raise HTTPException(status_code=404, detail="Şube bulunamadı.")
    return row


@admin_router.delete("/sections/{section_id}")
async def admin_delete_section_route(
    section_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_course_section(obs_db, section_id)
    return _admin_delete_result(ok, err)


@admin_router.get("/calendar-events")
async def admin_calendar(
    term_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    return repo.list_calendar_raw(obs_db, term_id)


class CalendarEventCreate(BaseModel):
    term_id: str
    event_type: str
    title: str
    start_date: str
    end_date: str


@admin_router.post("/calendar-events", status_code=status.HTTP_201_CREATED)
async def admin_calendar_create(
    body: CalendarEventCreate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    return repo.admin_insert_calendar_event(
        obs_db,
        body.term_id,
        body.event_type,
        body.title,
        body.start_date,
        body.end_date,
    )


class CalendarEventUpdateBody(BaseModel):
    term_id: Optional[str] = None
    event_type: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@admin_router.put("/calendar/{event_id}")
async def admin_put_calendar_event(
    event_id: str,
    body: CalendarEventUpdateBody,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    row = repo.admin_update_calendar_event(obs_db, event_id, raw)
    if not row:
        raise HTTPException(status_code=404, detail="Takvim kaydı bulunamadı.")
    return row


@admin_router.delete("/calendar/{event_id}")
async def admin_delete_calendar_event_route(
    event_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok, err = repo.admin_delete_calendar_event(obs_db, event_id)
    return _admin_delete_result(ok, err)


@admin_router.get("/registration-settings")
async def admin_reg_settings(
    term_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    row = repo.registration_settings_row(obs_db, term_id)
    return row or {}


class RegistrationSettingsUpdate(BaseModel):
    akts_limit_default: Optional[int] = None
    akts_limit_high: Optional[int] = None
    akts_limit_top: Optional[int] = None
    akts_limit_prep: Optional[int] = None
    min_gpa_for_high_akts: Optional[float] = None
    min_gpa_for_top_akts: Optional[float] = None
    max_akts: Optional[int] = None
    bonus_akts: Optional[int] = None
    gpa_threshold: Optional[float] = None


@admin_router.post("/registration-settings")
async def admin_reg_settings_post(
    body: RegistrationSettingsUpdate,
    term_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    tid = term_id or repo.resolve_active_term_id(obs_db)
    if not tid:
        raise HTTPException(
            status_code=400, detail="Dönem belirtilmedi veya aktif dönem yok."
        )
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")
    return repo.upsert_registration_settings(obs_db, tid, payload)


class AdminAnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=255)
    audience_type: str = Field(default="all", max_length=32)
    department_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _strip_admin_ann(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "title" in data and data["title"] is not None:
                data["title"] = str(data["title"]).strip()
            if "content" in data and data["content"] is not None:
                data["content"] = str(data["content"]).strip()
        return data


@admin_router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def admin_ann_create(
    body: AdminAnnouncementCreate,
    user=Depends(get_obs_admin_user),
    obs_db: Session = Depends(get_obs_session),
):
    try:
        did = repo.optional_uuid_param(body.department_id, "Bölüm kimliği")
        title = repo.clamp_announcement_varchar(body.title)
        content = repo.clamp_announcement_varchar(body.content)
        if not title or not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Başlık ve içerik boş olamaz.",
            )
        aid = repo.insert_announcement(
            obs_db,
            user.id,
            title,
            content,
            body.audience_type,
            did,
            None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duyuru kaydedilemedi (veri veya veritabanı kısıtı).",
        )
    except DataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz alan formatı.",
        )
    return {"id": aid}


@admin_router.get("/announcements")
async def admin_list_announcements(
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
    limit: int = Query(500, ge=1, le=2000),
):
    rows = repo.list_announcements_all_admin(obs_db, limit=limit)
    return {"announcements": rows}


@admin_router.put("/announcements/{announcement_id}")
async def admin_update_announcement(
    announcement_id: str,
    body: AnnouncementUpdateBody,
    user=Depends(get_obs_admin_user),
    obs_db: Session = Depends(get_obs_session),
):
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Güncellenecek alan yok."
        )
    try:
        if "department_id" in raw:
            raw["department_id"] = repo.optional_uuid_param(
                raw.get("department_id"), "Bölüm kimliği"
            )
        if "course_section_id" in raw:
            raw["course_section_id"] = repo.optional_uuid_param(
                raw.get("course_section_id"), "Şube kimliği"
            )
        if "title" in raw and raw["title"] is not None:
            raw["title"] = repo.clamp_announcement_varchar(raw["title"])
        if "content" in raw and raw["content"] is not None:
            raw["content"] = repo.clamp_announcement_varchar(raw["content"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        ok, err = repo.update_announcement_owned(
            obs_db, announcement_id, user.id, raw, require_creator=False
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Güncelleme reddedildi (veri veya veritabanı kısıtı).",
        )
    except DataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz alan formatı.",
        )
    if not ok:
        if err == "not_found":
            raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
        if err == "no_fields":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Güncellenecek alan yok."
            )
        raise HTTPException(status_code=400, detail="Güncellenemedi.")
    row = repo.get_announcement_mgmt_by_id(obs_db, announcement_id)
    if not row:
        raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
    return row


@admin_router.delete("/announcements/{announcement_id}")
async def admin_delete_announcement(
    announcement_id: str,
    user=Depends(get_obs_admin_user),
    obs_db: Session = Depends(get_obs_session),
):
    ok, err = repo.delete_announcement_owned(
        obs_db, announcement_id, user.id, require_creator=False
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Duyuru bulunamadı.")
    return {"id": announcement_id, "deleted": True}


@admin_router.get("/document-requests")
async def admin_doc_list(
    status_filter: Optional[str] = Query(None, alias="status"),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    rows, total = repo.list_document_requests_admin(obs_db, status_filter)
    return {"requests": rows, "total": total}


@admin_router.patch("/document-requests/{request_id}")
async def admin_doc_patch(
    request_id: str,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok = repo.patch_document_request(obs_db, request_id, "tamamlandı")
    if not ok:
        raise HTTPException(status_code=404, detail="Bulunamadı")
    return {"id": request_id, "status": "tamamlandı"}


@admin_router.get("/audit-logs")
async def admin_audit(
    limit: int = 20,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    logs, total = repo.list_audit_logs(obs_db, limit)
    return {"logs": logs, "total": total}


# Admin kullanıcı oluşturma / güncelleme — Open WebUI user.role ile uyumlu (OBS obsAccess academician eşlemesi)
OBS_ADMIN_ASSIGNABLE_USER_ROLES = frozenset({"user", "admin", "academician", "pending"})


@admin_router.get("/users")
async def admin_list_users(
    role_filter: Optional[str] = Query(None, alias="role"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    _u=Depends(get_obs_admin_user),
):
    flt: dict[str, Any] = {}
    if search:
        flt["query"] = search
    if role_filter:
        if role_filter not in OBS_ADMIN_ASSIGNABLE_USER_ROLES:
            raise HTTPException(status_code=400, detail="Geçersiz rol filtresi")
        flt["roles"] = [role_filter]
    res = Users.get_users(filter=flt or None, skip=0, limit=5000, db=db)
    users_out = []
    for u in res["users"]:
        ts = u.created_at
        if isinstance(ts, int):
            cat = datetime.datetime.utcfromtimestamp(ts).date().isoformat()
        elif hasattr(ts, "isoformat"):
            cat = ts.isoformat()
        else:
            cat = str(ts)
        users_out.append(
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.name,
                "role": u.role,
                "is_active": True,
                "created_at": cat,
            }
        )
    return {"users": users_out, "total": len(users_out)}


class StudentProfileCreateBody(BaseModel):
    """Admin öğrenci oluştururken obs_student_profiles ile birlikte."""

    student_number: str = Field(..., min_length=1)
    department_id: str = Field(..., min_length=1)
    enrollment_date: Optional[str] = None
    class_year: int = 1
    program: str = "Lisans"
    gpa: float = 0.0
    completed_akts: int = 0
    total_akts_required: int = 240
    status: str = "active"
    is_financially_eligible: bool = True
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    tc_kimlik_no: Optional[str] = None
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    nationality: Optional[str] = None
    mother_name: Optional[str] = None
    father_name: Optional[str] = None
    high_school_name: Optional[str] = None
    high_school_graduation_year: Optional[int] = None
    program_semester_number: int = 1


class AcademicProfileCreateBody(BaseModel):
    """Admin akademisyen oluştururken obs_academic_profiles ile birlikte."""

    department_id: str = Field(..., min_length=1)
    staff_number: Optional[str] = None
    title: Optional[str] = None
    office: Optional[str] = None
    phone: Optional[str] = None
    consulting_hours: Optional[str] = None


class UserCreate(BaseModel):
    email: str
    full_name: str
    role: str = "user"
    password: str = "Abc123!"
    username: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None
    student_profile: Optional[StudentProfileCreateBody] = None
    academic_profile: Optional[AcademicProfileCreateBody] = None


def _rollback_webui_user_after_failed_obs_profile(webui_user_id: str, db: Session) -> None:
    """OBS tarafı yazılamazsa ana DB'deki yarım auth+user kaydını kaldırır."""
    try:
        if Auths.delete_auth_by_id(webui_user_id, db=db):
            log.warning(
                "OBS profil yazılamadı; WebUI kullanıcı geri alındı (user_id=%s)",
                webui_user_id,
            )
        else:
            log.error(
                "OBS profil yazılamadı; WebUI kullanıcı geri alınamadı (user_id=%s)",
                webui_user_id,
            )
    except Exception:
        log.exception(
            "OBS profil sonrası WebUI geri alma hatası (user_id=%s)",
            webui_user_id,
        )


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: UserCreate,
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    hashed = get_password_hash(body.password)
    role = body.role if body.role in OBS_ADMIN_ASSIGNABLE_USER_ROLES else "user"
    email = str(body.email).strip().lower()

    if role in ("user", "pending") and not body.student_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Öğrenci veya bekleyen kullanıcı için özlük bilgisi (student_profile) zorunludur.",
        )
    if role == "academician" and not body.academic_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Akademisyen için akademik profil (academic_profile) zorunludur.",
        )

    nu = Auths.insert_new_auth(
        email=email,
        password=hashed,
        name=body.full_name,
        profile_image_url="",
        role=role,
        db=db,
    )
    if not nu:
        raise HTTPException(status_code=400, detail="Oluşturulamadı")

    obs_profile_required = role in ("user", "pending", "academician")

    upd: dict[str, Any] = {}
    if body.username and str(body.username).strip():
        upd["username"] = str(body.username).strip()
    if body.gender and str(body.gender).strip():
        upd["gender"] = str(body.gender).strip()

    dob_done = False
    if body.date_of_birth and str(body.date_of_birth).strip():
        try:
            upd["date_of_birth"] = datetime.date.fromisoformat(
                str(body.date_of_birth).strip()[:10]
            )
            dob_done = True
        except ValueError:
            pass
    if (
        not dob_done
        and role in ("user", "pending")
        and body.student_profile
        and body.student_profile.birth_date
        and str(body.student_profile.birth_date).strip()
    ):
        try:
            upd["date_of_birth"] = datetime.date.fromisoformat(
                str(body.student_profile.birth_date).strip()[:10]
            )
        except ValueError:
            pass

    phone_line = None
    if body.phone and str(body.phone).strip():
        phone_line = str(body.phone).strip()
    elif (
        role in ("user", "pending")
        and body.student_profile
        and body.student_profile.phone
        and str(body.student_profile.phone).strip()
    ):
        phone_line = str(body.student_profile.phone).strip()
    if phone_line:
        info_u: dict[str, Any] = {}
        u0 = Users.get_user_by_id(nu.id, db=db)
        if u0 and getattr(u0, "info", None) and isinstance(u0.info, dict):
            info_u = dict(u0.info)
        info_u["phone"] = phone_line
        upd["info"] = info_u

    if upd:
        Users.update_user_by_id(nu.id, upd, db=db)

    uf = Users.get_user_by_id(nu.id, db=db)
    uref = uf or nu

    try:
        if role in ("user", "pending"):
            repo.ensure_mirror_openwebui_user_row(
                obs_db,
                user_id=str(nu.id),
                email=str(uref.email),
                name=str(uref.name),
                role=str(uref.role),
                profile_image_url=getattr(uref, "profile_image_url", None) or "",
            )
            repo.admin_insert_student_profile(
                obs_db, nu.id, body.student_profile.model_dump(exclude_none=True)
            )
            if not repo.resolve_student_profile_id(obs_db, nu.id):
                log.error(
                    "OBS obs_student_profiles doğrulanamadı (user_id=%s)",
                    nu.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Öğrenci profili veritabanında oluşturulamadı (doğrulama).",
                )
        elif role == "academician":
            repo.ensure_mirror_openwebui_user_row(
                obs_db,
                user_id=str(nu.id),
                email=str(uref.email),
                name=str(uref.name),
                role=str(uref.role),
                profile_image_url=getattr(uref, "profile_image_url", None) or "",
            )
            repo.admin_insert_academic_profile(
                obs_db, nu.id, body.academic_profile.model_dump(exclude_none=True)
            )
            if not repo.resolve_academic_profile_id(obs_db, nu.id):
                log.error(
                    "OBS obs_academic_profiles doğrulanamadı (user_id=%s)",
                    nu.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Akademik profil veritabanında oluşturulamadı (doğrulama).",
                )
    except HTTPException as hex_obj:
        if obs_profile_required:
            _rollback_webui_user_after_failed_obs_profile(nu.id, db)
        raise hex_obj
    except ValueError as e:
        if obs_profile_required:
            _rollback_webui_user_after_failed_obs_profile(nu.id, db)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except SQLAlchemyError:
        log.exception("OBS profil INSERT")
        if obs_profile_required:
            _rollback_webui_user_after_failed_obs_profile(nu.id, db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OBS veritabanında profil kaydı oluşturulamadı (şema veya zorunlu alan).",
        ) from None

    return {
        "id": nu.id,
        "email": nu.email,
        "full_name": nu.name,
        "role": nu.role,
        "is_active": True,
        "created_at": datetime.datetime.utcnow().date().isoformat(),
    }


@admin_router.post("/users/{user_id}/student-profile")
async def admin_create_student_profile_existing_user(
    user_id: str,
    body: StudentProfileCreateBody,
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    """
    `POST /api/v1/auths/add` veya benzeri yollarla yalnızca WebUI `user` tablosunda oluşmuş
    öğrenci için obs_student_profiles kaydı ekler (veya zaten varsa idempotent kalır).
    """
    u = Users.get_user_by_id(user_id, db=db)
    if not u:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    if u.role not in ("user", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Özlük yalnızca rolü 'user' veya 'pending' olan hesaplara eklenebilir.",
        )
    uf = Users.get_user_by_id(user_id, db=db)
    uref = uf or u
    try:
        repo.ensure_mirror_openwebui_user_row(
            obs_db,
            user_id=str(user_id),
            email=str(uref.email),
            name=str(uref.name),
            role=str(uref.role),
            profile_image_url=getattr(uref, "profile_image_url", None) or "",
        )
        repo.admin_insert_student_profile(
            obs_db, user_id, body.model_dump(exclude_none=True)
        )
        spid = repo.resolve_student_profile_id(obs_db, user_id)
        if not spid:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Öğrenci profili doğrulanamadı.",
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except SQLAlchemyError:
        log.exception("OBS öğrenci özlük INSERT (mevcut kullanıcı)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OBS veritabanında öğrenci kaydı oluşturulamadı.",
        ) from None
    return {"ok": True, "user_id": user_id, "student_profile_id": spid}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@admin_router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_session),
    _u=Depends(get_obs_admin_user),
):
    patch: dict[str, Any] = {}
    if body.full_name is not None:
        patch["name"] = body.full_name
    if body.role is not None:
        if body.role not in OBS_ADMIN_ASSIGNABLE_USER_ROLES:
            raise HTTPException(status_code=400, detail="Geçersiz rol")
        patch["role"] = body.role
    if patch:
        u = Users.update_user_by_id(user_id, patch, db=db)
        if not u:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
        return {
            "id": u.id,
            "email": u.email,
            "full_name": u.name,
            "role": u.role,
            "is_active": True,
            "created_at": str(u.created_at),
        }
    raise HTTPException(status_code=400, detail="Güncelleme yok")


@admin_router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str, db: Session = Depends(get_session), _u=Depends(get_obs_admin_user)
):
    temp = "Abc123!"
    Auths.update_user_password_by_id(user_id, get_password_hash(temp), db=db)
    return {"user_id": user_id, "temp_password": temp}


@admin_router.get("/roles")
async def admin_roles(
    obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    roles = repo.list_roles_with_permissions(obs_db)
    return {"roles": roles}


class RolePermissionsUpdate(BaseModel):
    permissions: list[str]


@admin_router.put("/roles/{role_id}/permissions")
async def admin_role_perm(
    role_id: str,
    body: RolePermissionsUpdate,
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    ok = repo.update_role_permissions(obs_db, role_id, body.permissions)
    if not ok:
        raise HTTPException(status_code=501, detail="Rol izinleri salt okunur")
    return {"id": role_id, "permissions": body.permissions}
