"""
OBS akademik HTTP istekleri için obs_audit_logs kaydı (admin / öğrenci / akademisyen).
İstek gövdesi okunmaz; yalnızca method, path, query, HTTP durumu ve kullanıcı bilgisi yazılır.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text
from starlette.requests import Request

from open_webui.models.users import Users
from open_webui.routers import obs_sis_repository as repo
from open_webui.utils.auth import decode_token

log = logging.getLogger(__name__)

# request.state.obs_audit_actor — check_url sonrası dolu
OBS_AUDIT_ACTOR_STATE_KEY = "obs_audit_actor"

# /api/v1 altında chats, models vb. ile karışmaması için dar whitelist
_OBS_PUBLIC_API_PREFIXES = (
    "/api/v1/terms",
    "/api/v1/departments",
    "/api/v1/announcements",
    "/api/v1/messages",
    "/api/v1/dev/",
)


def obs_http_path_matches_audit(path: str) -> bool:
    """Middleware ve konsol logu için: bu yol OBS akademik API kapsamında mı?"""
    if path == "/api/v1/audit/event":
        return False
    if path.startswith("/api/v1/admin"):
        return True
    if path.startswith("/api/v1/student"):
        return True
    if path.startswith("/api/v1/academic"):
        return True
    if path.startswith("/api/v1/obs"):
        return True
    for p in _OBS_PUBLIC_API_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return True
    return False


def _token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    c = request.cookies.get("token")
    if c:
        return c
    st = getattr(request.state, "token", None)
    if st is not None and getattr(st, "credentials", None):
        return str(st.credentials)
    return None


def _student_no_for_webui_user(user_id: str) -> str:
    if not user_id:
        return ""
    try:
        from open_webui.internal.obs_db import ObsSessionLocal

        session = ObsSessionLocal()
        try:
            row = session.execute(
                text(
                    """
                    SELECT student_no FROM obs_student_profiles
                    WHERE user_id = :uid LIMIT 1
                    """
                ),
                {"uid": str(user_id)},
            ).first()
            if row and row[0] is not None:
                return str(row[0]).strip()
        finally:
            session.close()
    except Exception:
        log.debug("obs_audit student_no okunamadı", exc_info=True)
    return ""


def _audit_display_label(
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


def resolve_obs_audit_actor_dict(request: Request) -> dict[str, Any]:
    """JWT/cookie ile kullanıcı; e-posta, ad, öğrenci no dahil."""
    token = _token_from_request(request)
    empty = {
        "user_id": None,
        "name": "",
        "email": "",
        "student_no": "",
        "display": "Bilinmeyen kullanıcı",
        "webui_role": "",
        "obs_role": "",
    }
    if not token:
        return empty
    try:
        user = None
        if token.startswith("sk-"):
            user = Users.get_user_by_api_key(token)
        else:
            data = decode_token(token)
            if data and data.get("id") is not None:
                user = Users.get_user_by_id(str(data["id"]))
        if not user:
            return {**empty, "display": "Geçersiz oturum"}
        uid = str(user.id)
        name = str(getattr(user, "name", "") or "").strip()
        email = str(getattr(user, "email", "") or "").strip()
        student_no = _student_no_for_webui_user(uid)
        return {
            "user_id": uid,
            "name": name,
            "email": email,
            "student_no": student_no,
            "display": _audit_display_label(name, email, student_no, uid),
            "webui_role": str(getattr(user, "role", "") or ""),
            "obs_role": _obs_role_from_user(user),
        }
    except Exception:
        log.debug("resolve_obs_audit_actor_dict başarısız", exc_info=True)
        return {**empty, "display": "Kimlik okunamadı"}


def resolve_obs_audit_actor(
    request: Request,
) -> tuple[Optional[str], str, str, str]:
    """Geriye uyumluluk: (user_id, display, webui_role, obs_role)."""
    a = resolve_obs_audit_actor_dict(request)
    return (
        a.get("user_id"),
        str(a.get("display") or ""),
        str(a.get("webui_role") or ""),
        str(a.get("obs_role") or ""),
    )


def get_obs_audit_actor_from_request(request: Request) -> dict[str, Any]:
    """check_url doldurduysa state; yoksa anlık çözümleme."""
    cached = getattr(request.state, OBS_AUDIT_ACTOR_STATE_KEY, None)
    if isinstance(cached, dict) and cached.get("user_id"):
        return cached
    return resolve_obs_audit_actor_dict(request)


def build_http_audit_plain_message(
    *,
    actor: dict[str, Any],
    method: str,
    path: str,
    api_label: str,
    status_code: int,
    query: str = "",
) -> str:
    """Tek satır — DB'de message kolonuna yazılır; liste ekranı bunu okur."""
    m = (method or "").upper()
    email = str(actor.get("email") or "").strip()
    name = str(actor.get("name") or "").strip()
    student_no = str(actor.get("student_no") or "").strip()
    who = _audit_display_label(name, email, student_no, str(actor.get("user_id") or ""))
    line = f"{who} | {m} {path}"
    if api_label and api_label != path:
        line += f" | {api_label}"
    if query:
        line += f" | ?{query[:120]}"
    line += f" | HTTP {status_code}"
    return line[:4000]


def _obs_role_from_user(user) -> str:
    info = getattr(user, "info", None) or {}
    if isinstance(info, dict):
        r = repo.user_info_obs_role(info)
        if r:
            return str(r)
    return ""


# OBS arayüz rotaları (Svelte /obs/...)
_OBS_UI_PATH_LABELS: dict[str, str] = {
    "/obs/ogrenci": "Öğrenci paneli",
    "/obs/ogrenci/ders-kayit": "Ders kayıt",
    "/obs/ogrenci/ders-ekle-birak": "Ders ekle / bırak",
    "/obs/ogrenci/not-listesi": "Not listesi",
    "/obs/ogrenci/mesajlar-gelen": "Gelen mesajlar",
    "/obs/ogrenci/mesajlar-gonderilen": "Gönderilen mesajlar",
    "/obs/akademisyen": "Akademisyen paneli",
    "/obs/akademisyen/not-girisi": "Not girişi",
    "/obs/akademisyen/yoklama-girisi": "Yoklama girişi",
    "/obs/akademisyen/onay-talepleri": "Onay talepleri",
    "/obs/admin": "Admin paneli",
    "/obs/admin/audit-kayitlari": "Audit kayıtları",
    "/obs/admin/kullanici-yonetimi": "Kullanıcı yönetimi",
    "/obs/admin/ders-katalogu": "Ders kataloğu",
    "/obs/admin/donem-yonetimi": "Dönem yönetimi",
}

# API yolları (en spesifik eşleşme önce)
_OBS_API_PATH_LABELS: list[tuple[str, str]] = [
    ("/api/v1/student/me/submit-schedule", "Öğrenci — Programı danışmana gönder"),
    ("/api/v1/student/me/draft-enrollments", "Öğrenci — Taslak ders kayıtları"),
    ("/api/v1/student/me/enrollments", "Öğrenci — Kayıtlı dersler"),
    ("/api/v1/student/me/profile", "Öğrenci — Profil"),
    ("/api/v1/student/me/drop-requests", "Öğrenci — Ders bırakma talebi"),
    ("/api/v1/academic/sections", "Akademisyen — Şube / not / yoklama"),
    ("/api/v1/academic/me/approval-requests", "Akademisyen — Onay talepleri"),
    ("/api/v1/academic/me/advisees", "Akademisyen — Danışmanlık öğrencileri"),
    ("/api/v1/admin/audit-logs", "Admin — Audit listesi"),
    ("/api/v1/admin/users", "Admin — Kullanıcılar"),
    ("/api/v1/admin/departments", "Admin — Bölümler"),
    ("/api/v1/admin/terms", "Admin — Dönemler"),
    ("/api/v1/admin/courses", "Admin — Ders kataloğu"),
    ("/api/v1/messages", "Mesajlaşma"),
    ("/api/v1/terms", "Dönem listesi"),
    ("/api/v1/departments", "Bölüm listesi"),
]


def obs_ui_path_label(path: str) -> str:
    p = (path or "").rstrip("/") or "/"
    if p in _OBS_UI_PATH_LABELS:
        return _OBS_UI_PATH_LABELS[p]
    best = ""
    best_lbl = ""
    for prefix, lbl in _OBS_UI_PATH_LABELS.items():
        if p == prefix or p.startswith(prefix + "/"):
            if len(prefix) > len(best):
                best = prefix
                best_lbl = lbl
    return best_lbl or p


def obs_api_path_label(path: str) -> str:
    p = path or ""
    for prefix, lbl in _OBS_API_PATH_LABELS:
        if p == prefix or p.startswith(prefix + "/"):
            return lbl
    if p.startswith("/api/v1/student"):
        return "Öğrenci API"
    if p.startswith("/api/v1/academic"):
        return "Akademisyen API"
    if p.startswith("/api/v1/admin"):
        return "Admin API"
    return p


def _obs_crud_action_from_http_method(method: str) -> tuple[str, str]:
    """(action_anahtari, crud_turu) — admin arayüzünde CRUD satırları seçilebilir."""
    m = (method or "").upper()
    if m == "GET":
        return "obs.crud.read", "read"
    if m == "POST":
        return "obs.crud.create", "create"
    if m in ("PUT", "PATCH"):
        return "obs.crud.update", "update"
    if m == "DELETE":
        return "obs.crud.delete", "delete"
    return f"obs.http.{m.lower()}", m.lower()


def record_obs_audit_http_row_sync(
    *,
    actor: dict[str, Any],
    method: str,
    path: str,
    query: str,
    status_code: int,
    duration_ms: int,
) -> None:
    try:
        m = (method or "").upper()
        action, crud_kind = _obs_crud_action_from_http_method(m)
        api_label = obs_api_path_label(path)
        plain = build_http_audit_plain_message(
            actor=actor,
            method=m,
            path=path,
            api_label=api_label,
            status_code=status_code,
            query=query,
        )
        repo.record_obs_audit_event_isolated(
            actor_user_id=actor.get("user_id"),
            actor_label=str(actor.get("display") or ""),
            action=action,
            entity_type=api_label[:255] if api_label else "obs_api",
            entity_id=path[:128],
            details={
                "crud": crud_kind,
                "http_method": m,
                "path": path,
                "api_label": api_label,
                "query": (query or "")[:2048],
                "status_code": status_code,
                "duration_ms": duration_ms,
                "webui_role": actor.get("webui_role"),
                "obs_role": actor.get("obs_role"),
                "email": actor.get("email"),
                "name": actor.get("name"),
                "student_no": actor.get("student_no"),
            },
            source="http",
            plain_message=plain,
        )
    except Exception:
        log.debug("OBS HTTP audit satırı yazılamadı", exc_info=True)
