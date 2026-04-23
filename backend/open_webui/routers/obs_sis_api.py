"""OBS akademik API — mevcut PostgreSQL obs_* tabloları (UUID, academic/student profiller)."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
    {"email": "ogrenci@dou.edu.tr", "name": "Ramazan Öğrenci", "password": "Obs1234!", "role": "user"},
    {"email": "akademisyen@dou.edu.tr", "name": "Dr. Ayşe Yılmaz", "password": "Obs1234!", "role": "user"},
    {"email": "admin@dou.edu.tr", "name": "Sistem Yöneticisi", "password": "Obs1234!", "role": "admin"},
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
async def list_terms(obs_db: Session = Depends(get_obs_session), _u=Depends(get_verified_user)):
    return repo.list_terms(obs_db)


@public_router.get("/terms/{term_id}/calendar")
async def term_calendar(term_id: str, obs_db: Session = Depends(get_obs_session), _u=Depends(get_verified_user)):
    return {"term_id": term_id, "events": repo.term_calendar(obs_db, term_id)}


@public_router.get("/departments")
async def list_departments(obs_db: Session = Depends(get_obs_session), _u=Depends(get_verified_user)):
    return repo.list_departments(obs_db)


@public_router.get("/announcements")
async def list_announcements(
    audience_type: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_verified_user),
):
    return {"announcements": repo.list_announcements_filtered(obs_db, audience_type, department_id)}


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
async def send_message(body: MessageCreate, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    rid = body.receiver_user_id or ""
    if not rid:
        raise HTTPException(status_code=400, detail="receiver_user_id gerekli")
    return repo.insert_message(obs_db, user.id, rid, body.subject, body.body)


@public_router.patch("/messages/{message_id}/read")
async def mark_read(message_id: str, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    ok = repo.mark_message_read(obs_db, message_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    return {"id": message_id, "is_read": True}


@public_router.delete("/messages/{message_id}")
async def delete_message(message_id: str, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    ok = repo.soft_delete_message(obs_db, message_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    return {"id": message_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Öğrenci
# ---------------------------------------------------------------------------


@student_router.get("/me/profile")
async def student_me_profile(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    row = repo.get_student_profile_api(obs_db, user.id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Öğrenci profili bulunamadı")
    return row


@student_router.get("/me/advisor")
async def student_me_advisor(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    return repo.get_advisor_api(obs_db, user.id)


@student_router.get("/me/enrollments")
async def student_me_enrollments(
    term_id: Optional[str] = Query(None),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    spid, rows = repo.list_enrollments(obs_db, user.id, term_id)
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
    spid, rows = repo.list_enrollments(obs_db, user.id, term_id)
    if spid is None:
        return {"student_user_id": user.id, "term_id": term_id or "", "schedule": []}
    tid = term_id or (rows[0]["term_id"] if rows else "")
    sched = repo.schedule_from_enrollments(rows, tid) if tid else []
    return {"student_user_id": user.id, "term_id": tid, "schedule": sched}


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
async def student_me_transcript(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
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
async def student_doc_req(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    rows = repo.list_document_requests(obs_db, user.id)
    return {"student_user_id": user.id, "requests": rows}


class DocReqCreate(BaseModel):
    requesting_institution: str
    request_reason: str
    document_type: str
    document_subtype: str


@student_router.post("/me/document-requests", status_code=status.HTTP_201_CREATED)
async def student_doc_create(body: DocReqCreate, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
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
async def student_me_announcements(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    prof = repo.get_student_profile_api(obs_db, user.id)
    dept = prof.get("department_id") if prof else None
    anns = repo.list_student_feed_announcements(obs_db, dept or None)
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
async def student_enrollment_request(body: EnrollmentRequest, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    adv = repo.get_advisor_api(obs_db, user.id)
    appr = (adv.get("advisor") or {}).get("academic_user_id")
    reqs = repo.create_enrollment_requests(
        obs_db, user.id, getattr(user, "name", "") or "", body.section_ids, body.note, appr
    )
    if not reqs and not repo.resolve_student_profile_id(obs_db, user.id):
        raise HTTPException(status_code=404, detail="Öğrenci profili bulunamadı")
    return {"requests": reqs, "count": len(reqs)}


class DropRequest(BaseModel):
    enrollment_id: str
    reason: Optional[str] = None


@student_router.post("/me/drop-requests", status_code=status.HTTP_201_CREATED)
async def student_drop_request(body: DropRequest, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    adv = repo.get_advisor_api(obs_db, user.id)
    appr = (adv.get("advisor") or {}).get("academic_user_id")
    row = repo.create_drop_request(
        obs_db, user.id, getattr(user, "name", "") or "", body.enrollment_id, body.reason, appr
    )
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
async def student_graduation(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    prof = repo.get_student_profile_api(obs_db, user.id)
    return _empty_graduation(user.id, prof)


@student_router.get("/me/financial")
async def student_financial(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
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
async def student_curriculum(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
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
async def student_applications_create(body: ApplicationCreate, user=Depends(get_verified_user)):
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
    _, rows = repo.list_enrollments(obs_db, user.id, term_id)
    tid = term_id or (rows[0]["term_id"] if rows else "")
    sched = repo.schedule_from_enrollments(rows, tid) if tid else []
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
async def prep_grades(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
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
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    sections = repo.academic_sections(obs_db, user.id, term_id)
    return {"academic_user_id": user.id, "term_id_filter": term_id, "sections": sections}


@academic_user_router.get("/me/sections/{section_id}/students")
async def academic_section_students(section_id: str, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    sec, students = repo.section_students(obs_db, section_id)
    if not sec:
        raise HTTPException(status_code=404, detail="Şube bulunamadı")
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return {"section_id": section_id, "section": sec, "students": students}


@academic_user_router.get("/sections/{section_id}/exams")
async def academic_section_exams(section_id: str, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return {"section_id": section_id, "exams": repo.section_exams(obs_db, section_id)}


class ExamCreate(BaseModel):
    exam_type: str = "midterm"
    exam_date: str
    exam_time: str = "09:00"
    classroom: Optional[str] = None
    weight_percent: float = 40.0


@academic_user_router.post("/sections/{section_id}/exams", status_code=status.HTTP_201_CREATED)
async def academic_create_exam(
    section_id: str, body: ExamCreate, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return repo.insert_exam(
        obs_db, section_id, body.exam_type, body.exam_date, body.exam_time, body.classroom, body.weight_percent
    )


@academic_user_router.get("/sections/{section_id}/grades")
async def academic_section_grades(section_id: str, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    return {"section_id": section_id, "students": repo.section_grade_rows(obs_db, section_id)}


class GradeInput(BaseModel):
    grades: list[dict[str, Any]]


@academic_user_router.put("/sections/{section_id}/grades")
async def academic_put_grades(
    section_id: str, body: GradeInput, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    n = repo.upsert_grades(obs_db, section_id, body.grades)
    return {"section_id": section_id, "updated": n}


@academic_user_router.post("/sections/{section_id}/grades/finalize")
async def academic_finalize_grades(section_id: str, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    repo.finalize_section_grades(obs_db, section_id)
    return {"section_id": section_id, "finalized": True}


class AttendanceInput(BaseModel):
    week_no: int
    records: list[dict[str, Any]]


@academic_user_router.put("/sections/{section_id}/attendance")
async def academic_put_attendance(
    section_id: str, body: AttendanceInput, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    if not repo.section_owned_by_instructor(obs_db, section_id, user.id):
        raise HTTPException(status_code=403, detail="Bu şube size ait değil")
    n = repo.record_attendance(obs_db, section_id, body.week_no, body.records, user.id)
    return {"section_id": section_id, "week_no": body.week_no, "recorded": n}


@academic_user_router.get("/me/advisees")
async def academic_me_advisees(user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)):
    return {"academic_user_id": user.id, "advisees": repo.academic_advisees(obs_db, user.id)}


@academic_user_router.get("/me/approval-requests")
async def academic_me_approval_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    user=Depends(get_verified_user),
    obs_db: Session = Depends(get_obs_session),
):
    reqs = repo.list_approval_requests_for_academic(obs_db, user.id, status_filter)
    return {"academic_user_id": user.id, "requests": reqs, "total": len(reqs)}


class ApprovalAction(BaseModel):
    action: str
    note: Optional[str] = None


@academic_user_router.patch("/approval-requests/{request_id}")
async def academic_approve_request(
    request_id: str, body: ApprovalAction, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    ok = repo.resolve_approval(obs_db, request_id, user.id, body.action == "approve", body.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Talep bulunamadı")
    return {"id": request_id, "status": "approved" if body.action == "approve" else "rejected"}


class AcademicAnnouncementCreate(BaseModel):
    title: str
    content: str
    audience_type: str = "section"
    department_id: Optional[str] = None
    course_section_id: Optional[str] = None
    student_no: Optional[str] = None


@academic_user_router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def academic_create_announcement(
    body: AcademicAnnouncementCreate, user=Depends(get_verified_user), obs_db: Session = Depends(get_obs_session)
):
    aid = repo.insert_announcement(
        obs_db,
        user.id,
        body.title,
        body.content,
        body.audience_type,
        body.department_id,
        body.course_section_id,
    )
    return {"id": aid, "title": body.title, "content": body.content, "audience_type": body.audience_type}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@admin_router.get("/stats")
async def admin_stats(obs_db: Session = Depends(get_obs_session), db: Session = Depends(get_session), _u=Depends(get_obs_admin_user)):
    c = repo.admin_counts(obs_db)
    ures = Users.get_users(filter=None, skip=0, limit=10_000, db=db)
    users = ures.get("users", [])
    return {
        **c,
        "users_total": len(users),
        "users_active": len(users),
    }


@admin_router.get("/departments")
async def admin_list_departments(obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.list_departments(obs_db)


class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1)


@admin_router.post("/departments", status_code=status.HTTP_201_CREATED)
async def admin_create_department(body: DepartmentCreate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.admin_insert_department(obs_db, body.code, body.name)


@admin_router.get("/terms")
async def admin_list_terms(obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.list_terms(obs_db)


class TermCreate(BaseModel):
    name: str
    academic_year: str = ""
    season: str = "fall"
    starts_at: str = ""
    ends_at: str = ""
    is_active: bool = False


@admin_router.post("/terms", status_code=status.HTTP_201_CREATED)
async def admin_create_term(body: TermCreate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.admin_insert_term(
        obs_db, body.name, body.academic_year, body.season, body.starts_at, body.ends_at, body.is_active
    )


@admin_router.get("/courses")
async def admin_list_courses(obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
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
async def admin_create_course(body: CourseCreate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
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


@admin_router.get("/classrooms")
async def admin_list_classrooms(obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.list_classrooms_raw(obs_db)


class ClassroomCreate(BaseModel):
    building: str = ""
    name: str
    capacity: int = 30
    is_online: bool = False


@admin_router.post("/classrooms", status_code=status.HTTP_201_CREATED)
async def admin_create_classroom(body: ClassroomCreate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.admin_insert_classroom(obs_db, body.building, body.name, body.capacity, body.is_online)


@admin_router.get("/instructors")
async def admin_instructors(obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.list_instructors(obs_db)


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
async def admin_create_section(body: CourseSectionCreate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
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
    if iuid:
        apid = repo.resolve_academic_profile_id(obs_db, iuid)
        if not apid:
            log.warning(
                "[OBS-ADMIN] instructor user_id=%s icin obs_academic_profiles yok",
                iuid,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu kullanıcı için obs_academic_profiles kaydı yok; önce akademisyen profili oluşturun.",
            )
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
async def admin_calendar_create(body: CalendarEventCreate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    return repo.admin_insert_calendar_event(
        obs_db, body.term_id, body.event_type, body.title, body.start_date, body.end_date
    )


@admin_router.get("/registration-settings")
async def admin_reg_settings(
    term_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    row = repo.registration_settings_row(obs_db, term_id)
    return row or {}


class RegistrationSettingsUpdate(BaseModel):
    max_akts: int = 30
    bonus_akts: int = 6
    gpa_threshold: float = 2.50
    enrollment_deadline: str = ""
    add_drop_deadline: str = ""


@admin_router.post("/registration-settings")
async def admin_reg_settings_post(
    body: RegistrationSettingsUpdate,
    term_id: Optional[str] = Query(None),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    tid = term_id or repo.resolve_active_term_id(obs_db)
    if not tid:
        raise HTTPException(status_code=400, detail="Dönem belirtilmedi veya aktif dönem yok.")
    return repo.upsert_registration_settings(obs_db, tid, body.model_dump())


class AdminAnnouncementCreate(BaseModel):
    title: str
    content: str
    audience_type: str = "all"
    department_id: Optional[str] = None


@admin_router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def admin_ann_create(
    body: AdminAnnouncementCreate, user=Depends(get_obs_admin_user), obs_db: Session = Depends(get_obs_session)
):
    aid = repo.insert_announcement(
        obs_db, user.id, body.title, body.content, body.audience_type, body.department_id, None
    )
    return {"id": aid}


@admin_router.get("/document-requests")
async def admin_doc_list(
    status_filter: Optional[str] = Query(None, alias="status"),
    obs_db: Session = Depends(get_obs_session),
    _u=Depends(get_obs_admin_user),
):
    rows, total = repo.list_document_requests_admin(obs_db, status_filter)
    return {"requests": rows, "total": total}


@admin_router.patch("/document-requests/{request_id}")
async def admin_doc_patch(request_id: str, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    ok = repo.patch_document_request(obs_db, request_id, "tamamlandı")
    if not ok:
        raise HTTPException(status_code=404, detail="Bulunamadı")
    return {"id": request_id, "status": "tamamlandı"}


@admin_router.get("/audit-logs")
async def admin_audit(limit: int = 20, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    logs, total = repo.list_audit_logs(obs_db, limit)
    return {"logs": logs, "total": total}


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


class UserCreate(BaseModel):
    email: str
    full_name: str
    role: str = "user"
    password: str = "Abc123!"


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(body: UserCreate, db: Session = Depends(get_session), _u=Depends(get_obs_admin_user)):
    hashed = get_password_hash(body.password)
    nu = Auths.insert_new_auth(
        email=body.email,
        password=hashed,
        name=body.full_name,
        profile_image_url="",
        role=body.role if body.role in ("admin", "user", "pending") else "user",
        db=db,
    )
    if not nu:
        raise HTTPException(status_code=400, detail="Oluşturulamadı")
    return {
        "id": nu.id,
        "email": nu.email,
        "full_name": nu.name,
        "role": nu.role,
        "is_active": True,
        "created_at": datetime.datetime.utcnow().date().isoformat(),
    }


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@admin_router.patch("/users/{user_id}")
async def admin_update_user(user_id: str, body: UserUpdate, db: Session = Depends(get_session), _u=Depends(get_obs_admin_user)):
    patch: dict[str, Any] = {}
    if body.full_name is not None:
        patch["name"] = body.full_name
    if body.role is not None:
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
async def admin_reset_password(user_id: str, db: Session = Depends(get_session), _u=Depends(get_obs_admin_user)):
    temp = "Abc123!"
    Auths.update_user_password_by_id(user_id, get_password_hash(temp), db=db)
    return {"user_id": user_id, "temp_password": temp}


@admin_router.get("/roles")
async def admin_roles(obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)):
    roles = repo.list_roles_with_permissions(obs_db)
    return {"roles": roles}


class RolePermissionsUpdate(BaseModel):
    permissions: list[str]


@admin_router.put("/roles/{role_id}/permissions")
async def admin_role_perm(
    role_id: str, body: RolePermissionsUpdate, obs_db: Session = Depends(get_obs_session), _u=Depends(get_obs_admin_user)
):
    ok = repo.update_role_permissions(obs_db, role_id, body.permissions)
    if not ok:
        raise HTTPException(status_code=501, detail="Rol izinleri salt okunur")
    return {"id": role_id, "permissions": body.permissions}
