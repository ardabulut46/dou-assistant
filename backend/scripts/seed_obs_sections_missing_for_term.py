"""
Katalogda (obs_courses) görünen ancak seçilen obs_terms için henüz şubesi olmayan
derslere varsayılan obs_course_sections (section_no=1) INSERT eder.

.env ten DATABASE_URL okur (python-dotenv gerekmez).

Örnek (önizleme):
  cd backend && python scripts/seed_obs_sections_missing_for_term.py --term-id <UUID>

Uygula:
  cd backend && python scripts/seed_obs_sections_missing_for_term.py --term-id <UUID> --apply
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        os.environ[key] = val


def _db_url() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        _load_env_file(REPO_ROOT / ".env")
    primary = os.getenv("DATABASE_URL") or ""
    obs = (os.getenv("OBS_DATABASE_URL") or "").strip()
    if obs and obs != primary.strip():
        return obs
    return primary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--term-id", required=True, help="obs_terms.id (UUID)")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Gerçekten INSERT yap; olmadan sadece sayım",
    )
    args = p.parse_args()
    tid = args.term_id.strip()
    uuid.UUID(tid)

    url = _db_url()
    if not url.startswith("postgresql"):
        print("Bu script PostgreSQL DATABASE_URL gerektirir.", file=sys.stderr)
        return 1

    eng = create_engine(url, pool_pre_ping=True)

    preview_codes = text(
        """
SELECT c.code, c.name
FROM obs_courses c
JOIN obs_departments dep ON dep.id = c.department_id
WHERE NOT EXISTS (
    SELECT 1 FROM obs_course_sections cs
    WHERE cs.course_id = c.id AND cs.term_id = CAST(:tid AS uuid)
)
ORDER BY dep.name, c.class_year, c.semester_no, c.is_mandatory DESC NULLS LAST, c.name
LIMIT 80
"""
    )
    cnt_q = text(
        """
SELECT COUNT(*)::int
FROM obs_courses c
JOIN obs_departments dep ON dep.id = c.department_id
WHERE NOT EXISTS (
    SELECT 1 FROM obs_course_sections cs
    WHERE cs.course_id = c.id AND cs.term_id = CAST(:tid AS uuid)
)
"""
    )
    ins = text(
        """
INSERT INTO obs_course_sections (
    id, course_id, term_id, instructor_id, section_no, classroom_id,
    day_of_week, start_time, end_time, capacity, created_at
)
SELECT
    gen_random_uuid(),
    c.id,
    CAST(:tid AS uuid),
    NULL,
    1,
    NULL,
    'Pazartesi',
    TIME '09:00',
    TIME '10:30',
    50,
    NOW()
FROM obs_courses c
JOIN obs_departments dep ON dep.id = c.department_id
WHERE NOT EXISTS (
    SELECT 1 FROM obs_course_sections cs
    WHERE cs.course_id = c.id AND cs.term_id = CAST(:tid AS uuid)
)
"""
    )

    with eng.connect() as conn:
        n = int(conn.execute(cnt_q, {"tid": tid}).scalar() or 0)
        print(f"Bu dönem için şubesi olmayan ders sayısı: {n}")
        rows = conn.execute(preview_codes, {"tid": tid}).fetchall()
        if rows:
            print("Örnek (ilk 80 kod):")
            for code, name in rows:
                print(f"  {code}\t{name}")
        else:
            print("Eklenecek satır yok.")
        if not args.apply:
            print("\nGerçek ekleme için: --apply")
            return 0

    try:
        with eng.begin() as conn:
            r = conn.execute(ins, {"tid": tid})
            print(f"\nINSERT tamamlandi. Bildirilen etkilenen satır: {r.rowcount}")
    except Exception as e:
        print(f"\nINSERT hatası (kolon NOT NULL / FK olabilir): {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
