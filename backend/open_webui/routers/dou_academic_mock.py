"""
OBS akademik API uyumluluk katmanı.

Gerçek uçlar `obs_sis_api` içinde; veri mevcut PostgreSQL obs_* tablolarından gelir.
"""

from open_webui.routers.obs_sis_api import (
    academic_user_router,
    admin_router,
    public_router,
    student_router,
)

__all__ = [
    "public_router",
    "student_router",
    "academic_user_router",
    "admin_router",
]
