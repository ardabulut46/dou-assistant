"""Mevcut PostgreSQL obs_* şeması için SIS sorguları (UUID FK'lar, user_id varchar)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

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


LETTER_POINTS: dict[str, float] = {
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


def letter_to_point(lg: Optional[str]) -> Optional[float]:
    if not lg:
        return None
    return LETTER_POINTS.get(lg.upper().strip())


def resolve_student_profile_id(db: Session, webui_user_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT id FROM obs_student_profiles WHERE user_id = :u LIMIT 1"),
        {"u": webui_user_id},
    ).first()
    return _str_id(row[0]) if row else None


def resolve_academic_profile_id(db: Session, webui_user_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT id FROM obs_academic_profiles WHERE user_id = :u LIMIT 1"),
        {"u": webui_user_id},
    ).first()
    return _str_id(row[0]) if row else None


def get_student_profile_api(db: Session, webui_user_id: str) -> Optional[dict[str, Any]]:
    row = db.execute(
        text(
            f"""
        SELECT sp.id, sp.user_id, sp.student_number, sp.department_id,
               d.name AS department_name, d.faculty_name, d.code AS department_code,
               sp.program, sp.class_year, sp.gpa, sp.completed_akts, sp.total_akts_required,
               sp.status, sp.enrollment_date, sp.is_financially_eligible,
               sp.phone, sp.address, sp.emergency_contact, sp.emergency_phone,
               u.name AS full_name, u.email AS email
        FROM obs_student_profiles sp
        LEFT JOIN obs_departments d ON sp.department_id = d.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        WHERE sp.user_id = :uid
        """
        ),
        {"uid": webui_user_id},
    ).mappings().first()
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
    row = db.execute(
        text(
            "SELECT program, class_year FROM obs_student_profiles WHERE id = :id"
        ),
        {"id": spid},
    ).mappings().first()
    if not row:
        return False
    p = (row.get("program") or "").lower()
    return "hazırlık" in p or "hazirlik" in p or row.get("class_year") == 0


def get_advisor_api(db: Session, webui_user_id: str) -> dict[str, Any]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return {"student_user_id": webui_user_id, "advisor": None, "valid_from": None, "valid_to": None}
    row = db.execute(
        text(
            f"""
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
        """
        ),
        {"sid": spid},
    ).mappings().first()
    if not row:
        return {"student_user_id": webui_user_id, "advisor": None, "valid_from": None, "valid_to": None}
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
    rows = db.execute(
        text(
            """
        SELECT id, name, start_date, end_date, is_active FROM obs_terms
        ORDER BY start_date NULLS LAST, name
        """
        )
    ).mappings().all()
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
            }
        )
    return out


def list_departments(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text("SELECT id, code, name FROM obs_departments ORDER BY name")
    ).mappings().all()
    return [
        {"id": _str_id(r["id"]), "code": r.get("code") or "", "name": r.get("name") or ""}
        for r in rows
    ]


def term_calendar(db: Session, term_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
        SELECT id, term_id, event_type, title, start_date, end_date
        FROM obs_calendar_events WHERE term_id = :tid ORDER BY start_date
        """
        ),
        {"tid": term_id},
    ).mappings().all()
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
    db: Session, department_id: Optional[str]
) -> list[dict[str, Any]]:
    if department_id:
        q = """
            SELECT id, title, content, audience_type, department_id, is_active, published_at, created_by_user_id
            FROM obs_announcements
            WHERE is_active = true
              AND (
                audience_type = 'all'
                OR (audience_type = 'department' AND department_id::text = :did)
              )
            ORDER BY published_at DESC NULLS LAST
            """
        rows = db.execute(text(q), {"did": department_id}).mappings().all()
    else:
        q = """
            SELECT id, title, content, audience_type, department_id, is_active, published_at, created_by_user_id
            FROM obs_announcements
            WHERE is_active = true AND audience_type = 'all'
            ORDER BY published_at DESC NULLS LAST
            """
        rows = db.execute(text(q)).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "title": r.get("title") or "",
            "content": r.get("content") or "",
            "audience_type": r.get("audience_type") or "",
            "department_id": _str_id(r.get("department_id")),
            "is_active": bool(r.get("is_active")),
            "published_at": r.get("published_at").isoformat() if r.get("published_at") else None,
            "created_by": r.get("created_by_user_id"),
        }
        for r in rows
    ]


def list_announcements_filtered(
    db: Session, audience_type: Optional[str], department_id: Optional[str]
) -> list[dict[str, Any]]:
    q = """
        SELECT id, title, content, audience_type, department_id, is_active, published_at, created_by_user_id
        FROM obs_announcements WHERE is_active = true
        """
    params: dict[str, Any] = {}
    if audience_type:
        q += " AND (audience_type = :at OR audience_type = 'all')"
        params["at"] = audience_type
    if department_id:
        q += " AND (department_id::text = :did OR department_id IS NULL)"
        params["did"] = department_id
    q += " ORDER BY published_at DESC NULLS LAST"
    rows = db.execute(text(q), params).mappings().all()
    return [
        {
            "id": _str_id(r["id"]),
            "title": r.get("title") or "",
            "content": r.get("content") or "",
            "audience_type": r.get("audience_type") or "",
            "department_id": _str_id(r.get("department_id")),
            "is_active": bool(r.get("is_active")),
            "published_at": r.get("published_at").isoformat() if r.get("published_at") else None,
            "created_by": r.get("created_by_user_id"),
        }
        for r in rows
    ]


def messages_inbox(db: Session, user_id: str, sender_type: Optional[str]) -> list[dict[str, Any]]:
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


def messages_sent(db: Session, user_id: str, receiver_type: Optional[str]) -> list[dict[str, Any]]:
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
        text(
            """
        INSERT INTO obs_messages (id, sender_user_id, receiver_user_id, subject, body, is_read, status, sent_at)
        VALUES (:id, :su, :ru, :sub, :body, false, 'active', NOW())
        """
        ),
        {
            "id": mid,
            "su": sender_user_id,
            "ru": receiver_user_id,
            "sub": subject,
            "body": body,
        },
    )
    db.commit()
    row = db.execute(
        text(
            """
        SELECT m.id, m.sender_user_id, m.receiver_user_id, m.subject, m.body,
               m.is_read, m.status, m.sent_at,
               su.name AS sender_name, ru.name AS receiver_name
        FROM obs_messages m
        LEFT JOIN "user" su ON su.id = m.sender_user_id
        LEFT JOIN "user" ru ON ru.id = m.receiver_user_id
        WHERE m.id = :mid
        """
        ),
        {"mid": mid},
    ).mappings().first()
    return _message_row(row) if row else {"id": mid, "subject": subject, "body": body}


def mark_message_read(db: Session, message_id: str, reader_user_id: str) -> bool:
    res = db.execute(
        text(
            """
        UPDATE obs_messages SET is_read = true, read_at = NOW(), status = 'read'
        WHERE id = :mid AND receiver_user_id = :uid
        """
        ),
        {"mid": message_id, "uid": reader_user_id},
    )
    db.commit()
    return res.rowcount > 0


def soft_delete_message(db: Session, message_id: str, user_id: str) -> bool:
    res = db.execute(
        text(
            """
        UPDATE obs_messages SET status = 'deleted'
        WHERE id = :mid AND (sender_user_id = :uid OR receiver_user_id = :uid)
        """
        ),
        {"mid": message_id, "uid": user_id},
    )
    db.commit()
    return res.rowcount > 0


def list_enrollments(
    db: Session, webui_user_id: str, term_id: Optional[str]
) -> tuple[Optional[str], list[dict[str, Any]]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None, []
    q = """
        SELECT ce.id AS enrollment_id, ce.status,
               c.code AS course_code, c.name AS course_name, c.credits, c.akts,
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
        WHERE ce.student_id = :spid AND ce.status = 'active'
        """
    params: dict[str, Any] = {"spid": spid}
    if term_id:
        q += " AND cs.term_id = :tid"
        params["tid"] = term_id
    rows = db.execute(text(q), params).mappings().all()
    out = []
    for r in rows:
        room = r.get("classroom_code") or r.get("classroom_name") or ""
        out.append(
            {
                "id": _str_id(r["enrollment_id"]),
                "student_id": webui_user_id,
                "section_id": _str_id(r["section_id"]),
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "instructor_name": r.get("instructor_name") or "",
                "credits": int(r.get("credits") or 0),
                "akts": int(r.get("akts") or 0),
                "term_id": _str_id(r["term_id"]),
                "classroom": room,
                "day_of_week": r.get("day_of_week") or "",
                "start_time": _fmt_time(r.get("start_time")),
                "end_time": _fmt_time(r.get("end_time")),
                "section_no": int(r.get("section_no") or 0),
                "theory_hours": r.get("theory_hours") or "",
                "language": r.get("language") or "",
                "class_year": int(r.get("class_year") or 0),
                "type": r.get("type") or "",
                "status": r.get("status") or "",
            }
        )
    total_akts = sum(x["akts"] for x in out if x["status"] == "active")
    for x in out:
        x["_total_akts_computed"] = total_akts
    return spid, out


def schedule_from_enrollments(rows: list[dict[str, Any]], term_id: str) -> list[dict[str, Any]]:
    sched = []
    for r in rows:
        if r.get("term_id") != term_id and term_id:
            continue
        sched.append(
            {
                "day": r.get("day_of_week") or "",
                "start": r.get("start_time") or "",
                "end": r.get("end_time") or "",
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "classroom": r.get("classroom") or "",
                "instructor": r.get("instructor_name") or "",
            }
        )
    return sched


def list_student_exams(db: Session, webui_user_id: str, term_id: Optional[str]) -> list[dict[str, Any]]:
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
        WHERE ce.status = 'active'
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


def list_student_grades(db: Session, webui_user_id: str, term_id: Optional[str]) -> list[dict[str, Any]]:
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
        WHERE ce.student_id = :spid
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


def gpa_summary(db: Session, webui_user_id: str, term_id: Optional[str]) -> dict[str, Any]:
    prof = get_student_profile_api(db, webui_user_id) or {}
    grades = list_student_grades(db, webui_user_id, term_id)
    terms_gpa: dict[str, dict[str, Any]] = {}
    for g in grades:
        if not g.get("letter_grade"):
            continue
        pt = letter_to_point(g["letter_grade"])
        if pt is None:
            continue
        tid = g["term_id"]
        if tid not in terms_gpa:
            terms_gpa[tid] = {"pts": 0.0, "akts": 0, "name": tid}
        ak = 0
        row = db.execute(
            text(
                "SELECT c.akts FROM obs_course_enrollments ce JOIN obs_course_sections cs ON ce.course_section_id = cs.id JOIN obs_courses c ON cs.course_id = c.id WHERE ce.id = :eid"
            ),
            {"eid": g["enrollment_id"]},
        ).first()
        if row:
            ak = int(row[0] or 0)
        terms_gpa[tid]["pts"] += pt * ak
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
    cum = prof.get("gpa")
    return {
        "student_user_id": webui_user_id,
        "cumulative_gpa": cum,
        "total_akts_completed": int(prof.get("completed_akts") or 0),
        "class_level": int(prof.get("class_level") or 0),
        "terms": term_list,
    }


def transcript(db: Session, webui_user_id: str) -> dict[str, Any]:
    grades = list_student_grades(db, webui_user_id, None)
    by_term: dict[str, list[dict[str, Any]]] = {}
    for g in grades:
        if not g.get("is_finalized") and not g.get("letter_grade"):
            continue
        tid = g["term_id"]
        by_term.setdefault(tid, []).append(g)
    transcript_terms = []
    total_akts = 0
    weighted = 0.0
    akts_sum = 0
    for tid, tgrades in by_term.items():
        tname = (
            db.execute(text("SELECT name FROM obs_terms WHERE id = :id"), {"id": tid}).scalar()
            or tid
        )
        courses = []
        term_akts = 0
        term_pts = 0.0
        for g in tgrades:
            ak_row = db.execute(
                text(
                    """
                SELECT c.akts, c.credits FROM obs_course_enrollments ce
                JOIN obs_course_sections cs ON ce.course_section_id = cs.id
                JOIN obs_courses c ON cs.course_id = c.id WHERE ce.id = :eid
                """
                ),
                {"eid": g["enrollment_id"]},
            ).mappings().first()
            akts = int(ak_row["akts"] or 0) if ak_row else 0
            credits = int(ak_row["credits"] or 0) if ak_row else 0
            lg = g.get("letter_grade") or ""
            gp = letter_to_point(lg) or 0.0
            courses.append(
                {
                    "code": g["course_code"],
                    "name": g["course_name"],
                    "credits": credits,
                    "akts": akts,
                    "letter": lg,
                    "grade_point": gp,
                }
            )
            term_akts += akts
            term_pts += gp * akts
            total_akts += akts
            weighted += gp * akts
            akts_sum += akts
        term_gpa = round(term_pts / term_akts, 2) if term_akts else 0.0
        transcript_terms.append(
            {
                "term_name": tname,
                "courses": courses,
                "term_gpa": term_gpa,
                "term_akts": term_akts,
            }
        )
    cgpa = round(weighted / akts_sum, 2) if akts_sum else 0.0
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
        WHERE ce.student_id = :spid
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
        cat_name = type_to_cat.get(raw_type) or ("Diğer" if raw_type else "Program Dersleri")
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


def clear_student_enrollments_and_related(db: Session, webui_user_id: str) -> dict[str, Any]:
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
        db.execute(text("DELETE FROM obs_grade_entries WHERE enrollment_id = :eid"), {"eid": eid})
        db.execute(
            text("DELETE FROM obs_approval_requests WHERE related_enrollment_id = :eid"),
            {"eid": eid},
        )
    db.execute(text("DELETE FROM obs_attendance_records WHERE student_id = :spid"), {"spid": spid})
    res = db.execute(
        text("DELETE FROM obs_course_enrollments WHERE student_id = :spid"),
        {"spid": spid},
    )
    deleted = int(res.rowcount or 0)
    db.commit()
    return {"ok": True, "deleted_enrollments": deleted, "detail": "Kayıtlar silindi"}


def attendance_summary(db: Session, webui_user_id: str, term_id: Optional[str]) -> list[dict[str, Any]]:
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
    rows = db.execute(
        text(
            """
        SELECT id, requesting_institution, request_reason, document_type, document_subtype,
               status, created_at
        FROM obs_document_requests WHERE student_id = :sid ORDER BY created_at DESC
        """
        ),
        {"sid": spid},
    ).mappings().all()
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
    db: Session, webui_user_id: str, institution: str, reason: str, dtype: str, subtype: str
) -> Optional[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None
    rid = str(uuid.uuid4())
    db.execute(
        text(
            """
        INSERT INTO obs_document_requests
        (id, student_id, requesting_institution, request_reason, document_type, document_subtype, status, created_at, updated_at)
        VALUES (:id, :sid, :inst, :reason, :dtype, :subtype, 'bekliyor', NOW(), NOW())
        """
        ),
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
    allowed = {k: patch[k] for k in ("phone", "address", "emergency_contact", "emergency_phone") if k in patch and patch[k] is not None}
    if not allowed:
        return True
    sets = ", ".join(f"{k} = :{k}" for k in allowed)
    params = {**allowed, "uid": webui_user_id}
    db.execute(
        text(f"UPDATE obs_student_profiles SET {sets}, updated_at = NOW() WHERE user_id = :uid"),
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
            text("SELECT id FROM obs_terms WHERE is_active = true ORDER BY start_date DESC LIMIT 1")
        ).first()
        tid = _str_id(row[0]) if row else None
    q = """
        SELECT cs.id, c.code AS course_code, c.name AS course_name, c.credits, c.akts,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity,
               cr.code AS classroom_code, ins_u.name AS instructor_name,
               (SELECT COUNT(*) FROM obs_course_enrollments ce2 WHERE ce2.course_section_id = cs.id AND ce2.status = 'active') AS enrolled
        FROM obs_course_sections cs
        JOIN obs_courses c ON cs.course_id = c.id
        LEFT JOIN obs_classrooms cr ON cs.classroom_id = cr.id
        LEFT JOIN obs_academic_profiles ap ON cs.instructor_id = ap.id
        LEFT JOIN "user" ins_u ON ins_u.id = ap.user_id
        WHERE NOT EXISTS (
            SELECT 1 FROM obs_course_enrollments ce
            WHERE ce.course_section_id = cs.id AND ce.student_id = :spid AND ce.status = 'active'
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
        out.append(
            {
                "id": _str_id(r["id"]),
                "course_code": r.get("course_code") or "",
                "course_name": r.get("course_name") or "",
                "credits": int(r.get("credits") or 0),
                "akts": int(r.get("akts") or 0),
                "instructor_name": r.get("instructor_name") or "",
                "day_of_week": r.get("day_of_week") or "",
                "start_time": _fmt_time(r.get("start_time")),
                "end_time": _fmt_time(r.get("end_time")),
                "classroom": r.get("classroom_code") or "",
                "capacity": cap,
                "enrolled": enr,
            }
        )
    return tid, out


def academic_sections(db: Session, webui_user_id: str, term_id: Optional[str]) -> list[dict[str, Any]]:
    apid = resolve_academic_profile_id(db, webui_user_id)
    if not apid:
        return []
    q = """
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
            "day_of_week": r.get("day_of_week") or "",
            "start_time": _fmt_time(r.get("start_time")),
            "end_time": _fmt_time(r.get("end_time")),
            "enrollment_count": int(r.get("enrollment_count") or 0),
            "capacity": int(r.get("capacity") or 0),
        }
        for r in rows
    ]


def section_owned_by_instructor(db: Session, section_id: str, webui_user_id: str) -> bool:
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
    sec = db.execute(
        text(
            """
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
        """
        ),
        {"sid": section_id},
    ).mappings().first()
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
        "day_of_week": sec.get("day_of_week") or "",
        "start_time": _fmt_time(sec.get("start_time")),
        "end_time": _fmt_time(sec.get("end_time")),
        "enrollment_count": int(sec.get("enrollment_count") or 0),
        "capacity": int(sec.get("capacity") or 0),
    }
    rows = db.execute(
        text(
            f"""
        SELECT ce.id AS enrollment_id, ce.status, sp.student_number, u.name, sp.gpa
        FROM obs_course_enrollments ce
        JOIN obs_student_profiles sp ON ce.student_id = sp.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        WHERE ce.course_section_id = :sid AND ce.status = 'active'
        """
        ),
        {"sid": section_id},
    ).mappings().all()
    students = [
        {
            "student_no": r.get("student_number") or "",
            "name": r.get("name") or "",
            "enrollment_id": _str_id(r["enrollment_id"]),
            "enrollment_status": r.get("status") or "",
            "gpa": float(r["gpa"]) if r.get("gpa") is not None else 0.0,
        }
        for r in rows
    ]
    return section_dict, students


def section_exams(db: Session, section_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
        SELECT id, course_section_id, exam_type, exam_date, exam_time, weight_percent, cr.code AS classroom_code
        FROM obs_exams ex
        LEFT JOIN obs_classrooms cr ON ex.classroom_id = cr.id
        WHERE ex.course_section_id = :sid
        """
        ),
        {"sid": section_id},
    ).mappings().all()
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
    db: Session, section_id: str, exam_type: str, exam_date: str, exam_time: str, classroom: Optional[str], weight: float
) -> dict[str, Any]:
    eid = str(uuid.uuid4())
    cr_id = None
    if classroom:
        row = db.execute(
            text("SELECT id FROM obs_classrooms WHERE code = :c LIMIT 1"), {"c": classroom}
        ).first()
        if row:
            cr_id = str(row[0])
    db.execute(
        text(
            """
        INSERT INTO obs_exams (id, course_section_id, exam_type, exam_date, exam_time, classroom_id, weight_percent, is_published, created_at)
        VALUES (:id, :csid, :et, :ed, :etm, :crid, :wp, false, NOW())
        """
        ),
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


def section_grade_rows(db: Session, section_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            f"""
        SELECT ce.id AS enrollment_id, sp.student_number, u.name,
               g.midterm, g.final, g.letter_grade, g.is_finalized
        FROM obs_course_enrollments ce
        JOIN obs_student_profiles sp ON ce.student_id = sp.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        LEFT JOIN obs_grade_entries g ON g.enrollment_id = ce.id
        WHERE ce.course_section_id = :sid AND ce.status = 'active'
        """
        ),
        {"sid": section_id},
    ).mappings().all()
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


def upsert_grades(
    db: Session, section_id: str, grades: list[dict[str, Any]]
) -> int:
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
            text("SELECT id FROM obs_grade_entries WHERE enrollment_id = :eid"),
            {"eid": eid},
        ).first()
        if exists:
            db.execute(
                text(
                    """
                UPDATE obs_grade_entries SET midterm = COALESCE(:m, midterm), final = COALESCE(:f, final), updated_at = NOW()
                WHERE enrollment_id = :eid
                """
                ),
                {"eid": eid, "m": mid, "f": fin},
            )
        else:
            gid = str(uuid.uuid4())
            db.execute(
                text(
                    """
                INSERT INTO obs_grade_entries (id, enrollment_id, midterm, final, is_finalized, is_published, created_at, updated_at)
                VALUES (:gid, :eid, :m, :f, false, false, NOW(), NOW())
                """
                ),
                {"gid": gid, "eid": eid, "m": mid, "f": fin},
            )
        n += 1
    db.commit()
    return n


def finalize_section_grades(db: Session, section_id: str) -> None:
    db.execute(
        text(
            """
        UPDATE obs_grade_entries g SET is_finalized = true, finalized_at = NOW()
        FROM obs_course_enrollments ce
        WHERE g.enrollment_id = ce.id AND ce.course_section_id = :sid
        """
        ),
        {"sid": section_id},
    )
    db.commit()


def record_attendance(
    db: Session, section_id: str, week_no: int, records: list[dict[str, Any]], recorded_by: str
) -> int:
    for rec in records:
        eid = rec.get("enrollment_id")
        st = rec.get("status") or "present"
        row = db.execute(
            text("SELECT student_id FROM obs_course_enrollments WHERE id = :eid AND course_section_id = :sid"),
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
            text(
                """
            INSERT INTO obs_attendance_records (id, student_id, course_section_id, week_no, status, recorded_at, recorded_by)
            VALUES (:id, :spid, :sid, :w, :st, NOW(), :rb)
            """
            ),
            {"id": rid, "spid": spid, "sid": section_id, "w": week_no, "st": st, "rb": recorded_by},
        )
    db.commit()
    return len(records)


def academic_advisees(db: Session, webui_user_id: str) -> list[dict[str, Any]]:
    apid = resolve_academic_profile_id(db, webui_user_id)
    if not apid:
        return []
    rows = db.execute(
        text(
            f"""
        SELECT sp.student_number, u.name, d.code AS dept_code, sp.class_year, sp.gpa, sp.status
        FROM obs_student_advisors sa
        JOIN obs_student_profiles sp ON sa.student_id = sp.id
        LEFT JOIN {USER_TBL} u ON u.id = sp.user_id
        LEFT JOIN obs_departments d ON sp.department_id = d.id
        WHERE sa.advisor_id = :apid
          AND (sa.valid_to IS NULL OR sa.valid_to >= CURRENT_DATE)
        """
        ),
        {"apid": apid},
    ).mappings().all()
    return [
        {
            "student_no": r.get("student_number") or "",
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
               sp.student_number, u.name AS student_name,
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


def resolve_approval(
    db: Session, request_id: str, approver_user_id: str, approve: bool, note: Optional[str]
) -> bool:
    st = "approved" if approve else "rejected"
    res = db.execute(
        text(
            """
        UPDATE obs_approval_requests SET status = :st, note = COALESCE(:note, note), resolved_at = NOW()
        WHERE id = :rid AND approver_id = :aid
        """
        ),
        {"st": st, "note": note, "rid": request_id, "aid": approver_user_id},
    )
    db.commit()
    return res.rowcount > 0


def insert_announcement(
    db: Session,
    created_by: str,
    title: str,
    content: str,
    audience_type: str,
    department_id: Optional[str],
    course_section_id: Optional[str],
) -> str:
    aid = str(uuid.uuid4())
    db.execute(
        text(
            """
        INSERT INTO obs_announcements
        (id, created_by_user_id, title, content, audience_type, department_id, course_section_id, is_active, published_at, created_at)
        VALUES (:id, :cb, :t, :c, :at, :did, :csid, true, NOW(), NOW())
        """
        ),
        {
            "id": aid,
            "cb": created_by,
            "t": title,
            "c": content,
            "at": audience_type,
            "did": department_id,
            "csid": course_section_id,
        },
    )
    db.commit()
    return aid


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
        row = db.execute(
            text("SELECT * FROM obs_registration_settings WHERE term_id = :t LIMIT 1"),
            {"t": term_id},
        ).mappings().first()
    else:
        row = db.execute(
            text(
                """
            SELECT rs.* FROM obs_registration_settings rs
            INNER JOIN obs_terms tm ON rs.term_id = tm.id
            WHERE tm.is_active = true
            LIMIT 1
            """
            )
        ).mappings().first()
    return dict(row) if row else None


def resolve_active_term_id(db: Session) -> Optional[str]:
    row = db.execute(
        text("SELECT id FROM obs_terms WHERE is_active = true ORDER BY start_date DESC LIMIT 1")
    ).first()
    return _str_id(row[0]) if row else None


def upsert_registration_settings(db: Session, term_id: str, body: dict[str, Any]) -> dict[str, Any]:
    max_akts = int(body.get("max_akts", 30))
    bonus_akts = int(body.get("bonus_akts", 0))
    gpa_threshold = float(body.get("gpa_threshold", 2.50))
    existing = db.execute(
        text("SELECT id FROM obs_registration_settings WHERE term_id = :tid LIMIT 1"),
        {"tid": term_id},
    ).first()
    params = {
        "tid": term_id,
        "ma": max_akts,
        "ba": bonus_akts,
        "gt": gpa_threshold,
    }
    if existing:
        db.execute(
            text(
                """
                UPDATE obs_registration_settings
                SET max_akts = :ma, bonus_akts = :ba, gpa_threshold = :gt, updated_at = NOW()
                WHERE term_id = :tid
                """
            ),
            params,
        )
    else:
        rid = str(uuid.uuid4())
        db.execute(
            text(
                """
                INSERT INTO obs_registration_settings
                    (id, term_id, max_akts, bonus_akts, gpa_threshold, created_at, updated_at)
                VALUES (:id, :tid, :ma, :ba, :gt, NOW(), NOW())
                """
            ),
            {**params, "id": rid},
        )
    db.commit()
    return registration_settings_row(db, term_id) or {}


def list_audit_logs(db: Session, limit: int) -> tuple[list, int]:
    rows = db.execute(
        text("SELECT * FROM obs_audit_logs ORDER BY created_at DESC NULLS LAST LIMIT :lim"),
        {"lim": limit},
    ).mappings().all()
    return [dict(r) for r in rows], len(rows)


def list_document_requests_admin(db: Session, status_filter: Optional[str]) -> tuple[list, int]:
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
    rows = db.execute(
        text(
            f"""
        SELECT ap.user_id, u.email, u.name, u.role
        FROM obs_academic_profiles ap
        LEFT JOIN {USER_TBL} u ON u.id = ap.user_id
        """
        ),
    ).mappings().all()
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
        row = db.execute(
            text(
                """
            SELECT c.code, c.name FROM obs_course_sections cs
            JOIN obs_courses c ON cs.course_id = c.id WHERE cs.id = :csid
            """
            ),
            {"csid": sid},
        ).mappings().first()
        cc = row.get("course_code") if row else ""
        cn = row.get("course_name") if row else ""
        rid = str(uuid.uuid4())
        db.execute(
            text(
                """
            INSERT INTO obs_approval_requests
            (id, student_id, approver_id, request_type, related_enrollment_id, status, note, created_at)
            VALUES (:id, :spid, :appr, 'enrollment_request', NULL, 'pending', :note, NOW())
            """
            ),
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
) -> Optional[dict[str, Any]]:
    spid = resolve_student_profile_id(db, webui_user_id)
    if not spid:
        return None
    row = db.execute(
        text(
            "SELECT id FROM obs_course_enrollments WHERE id = :eid AND student_id = :spid"
        ),
        {"eid": enrollment_id, "spid": spid},
    ).first()
    if not row:
        return None
    sp_row = db.execute(
        text("SELECT student_number FROM obs_student_profiles WHERE id = :id"),
        {"id": spid},
    ).first()
    student_no = sp_row[0] if sp_row else ""
    rid = str(uuid.uuid4())
    db.execute(
        text(
            """
        INSERT INTO obs_approval_requests
        (id, student_id, approver_id, request_type, related_enrollment_id, status, note, created_at)
        VALUES (:id, :spid, :appr, 'drop_request', :eid, 'pending', :reason, NOW())
        """
        ),
        {
            "id": rid,
            "spid": spid,
            "appr": approver_user_id,
            "eid": enrollment_id,
            "reason": reason,
        },
    )
    db.commit()
    return {
        "id": rid,
        "student_user_id": webui_user_id,
        "enrollment_id": enrollment_id,
        "request_type": "drop_request",
        "status": "pending",
        "reason": reason,
        "student_name": student_display_name,
        "student_no": student_no,
        "created_at": datetime.utcnow().isoformat(),
    }


def list_roles_with_permissions(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
        SELECT rp.role_name, p.code
        FROM obs_role_permissions rp
        JOIN obs_permissions p ON p.id = rp.permission_id
        ORDER BY rp.role_name, p.code
        """
        )
    ).mappings().all()
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
    db: Session, name: str, academic_year: str, season: str, starts_at: str, ends_at: str, is_active: bool
) -> dict[str, Any]:
    _ = academic_year
    _ = season
    tid = str(uuid.uuid4())
    sd = starts_at if starts_at else None
    ed = ends_at if ends_at else None
    db.execute(
        text(
            """
        INSERT INTO obs_terms (id, name, start_date, end_date, is_active, created_at)
        VALUES (:id, :name, CAST(:sd AS date), CAST(:ed AS date), :ia, NOW())
        """
        ),
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
        text(
            """
        INSERT INTO obs_courses (id, department_id, code, name, credits, akts, class_year, type, theory_hours, language, created_at)
        VALUES (:id, :did, :code, :name, :cr, :ak, :cy, :typ, :th, :lang, NOW())
        """
        ),
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
        text(
            """
        INSERT INTO obs_classrooms (id, code, name, building, capacity, is_online)
        VALUES (:id, :code, :name, :b, :cap, :io)
        """
        ),
        {"id": rid, "code": code, "name": name, "b": building, "cap": capacity, "io": is_online},
    )
    db.commit()
    return {"id": rid, "building": building, "name": name, "capacity": capacity, "is_online": is_online}


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
        apid = resolve_academic_profile_id(db, instructor_user_id)
    sid = str(uuid.uuid4())
    db.execute(
        text(
            """
        INSERT INTO obs_course_sections
        (id, course_id, term_id, instructor_id, section_no, classroom_id, day_of_week, start_time, end_time, capacity, created_at)
        VALUES (:id, :cid, :tid, :iid, :sn, :crid, :dow, CAST(:st AS time), CAST(:et AS time), :cap, NOW())
        """
        ),
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
    db: Session, term_id: str, event_type: str, title: str, start_date: str, end_date: str
) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    db.execute(
        text(
            """
        INSERT INTO obs_calendar_events (id, term_id, event_type, title, start_date, end_date, created_at)
        VALUES (:id, :tid, :et, :ti, CAST(:sd AS date), CAST(:ed AS date), NOW())
        """
        ),
        {"id": cid, "tid": term_id, "et": event_type, "ti": title, "sd": start_date, "ed": end_date},
    )
    db.commit()
    return {"id": cid, "term_id": term_id, "event_type": event_type, "title": title, "start_date": start_date, "end_date": end_date}


def list_courses_raw(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("SELECT * FROM obs_courses ORDER BY code")).mappings().all()
    return [dict(r) for r in rows]


def list_classrooms_raw(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("SELECT * FROM obs_classrooms ORDER BY code")).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = _str_id(d.get("id"))
        out.append(d)
    return out


def list_sections_raw(db: Session, term_id: Optional[str]) -> list[dict[str, Any]]:
    q = """
        SELECT cs.id, cs.course_id, cs.term_id, cs.section_no, cs.instructor_id, cs.classroom_id,
               cs.day_of_week, cs.start_time, cs.end_time, cs.capacity, cs.created_at,
               c.code AS course_code, c.name AS course_name,
               cr.code AS classroom_code,
               ins_u.name AS instructor_label
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
        d["classroom_id"] = _str_id(d.get("classroom_id"))
        d["start_time"] = _fmt_time(d.get("start_time"))
        d["end_time"] = _fmt_time(d.get("end_time"))
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else str(d["created_at"])
        out.append(d)
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
