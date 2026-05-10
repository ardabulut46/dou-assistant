"""
Hangi veritabaninin OBS icin kullanildigini gosterir (.env, open_webui import etmez).

Calistir:  cd backend && python _obs_db_check.py
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR / "data")).resolve()


def _load_env_file(path: Path) -> None:
    """python-dotenv yoksa bile proje kökündeki .env'i okur (KEY=value)."""
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


def main() -> None:
    env_path = REPO_ROOT / ".env"
    if load_dotenv:
        load_dotenv(env_path)
    else:
        _load_env_file(env_path)

    primary = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR.as_posix()}/webui.db"
    obs_raw = (os.getenv("OBS_DATABASE_URL") or "").strip()
    tek_db = (not obs_raw) or (obs_raw == primary.strip())
    obs_url = primary if tek_db else obs_raw

    print("=== OBS / Dou veritabani kontrolu ===\n")
    print(".env:", REPO_ROOT / ".env", "| var mi:", (REPO_ROOT / ".env").exists())
    print("\nPRIMARY DATABASE_URL:")
    print(" ", primary)
    print("\nOBS_DATABASE_URL:")
    print(" ", obs_raw if obs_raw else "(bos -> Open WebUI ile TEK DB: DATABASE_URL)")
    print(
        "\nOBS motoru (uygulama ile ayni mi):",
        "EVET (tek havuz)" if tek_db else "HAYIR (ayri URL)",
    )
    print("\nOBS icin efektif URL:")
    print(" ", obs_url)

    if obs_url.startswith("sqlite"):
        db_path = obs_url.replace("sqlite:///", "").split("?")[0]
        p = Path(db_path)
        print("\nSQLite dosyasi:", p.resolve())
        print("Dosya boyutu (byte):", p.stat().st_size if p.exists() else "YOK")

    eng = create_engine(obs_url, pool_pre_ping="sqlite" not in obs_url.lower())
    insp = inspect(eng)
    all_tabs = insp.get_table_names()
    obs_tabs = sorted(t for t in all_tabs if t.startswith("obs_"))

    print("\nToplam tablo sayisi:", len(all_tabs))
    if all_tabs:
        print("Ilk 40 tablo:", ", ".join(all_tabs[:40]))
    print("\nobs_* tablo sayisi:", len(obs_tabs))
    if obs_tabs:
        print("obs tablolari:", ", ".join(obs_tabs))

    is_sqlite = "sqlite" in obs_url.lower()
    print("\n--- Kritik tablo satir sayilari ---")
    with eng.connect() as conn:
        for tbl in [
            "obs_course_enrollments",
            "obs_student_profiles",
            "obs_courses",
            "obs_course_sections",
        ]:
            if tbl not in all_tabs:
                print(f"  {tbl}: TABLO YOK")
                continue
            qtext = (
                f"SELECT COUNT(*) FROM {tbl}"
                if is_sqlite
                else f'SELECT COUNT(*) FROM "{tbl}"'
            )
            n = conn.execute(text(qtext)).scalar()
            print(f"  {tbl}: {int(n or 0)} satir")

    if "obs_announcements" in all_tabs and not is_sqlite:
        with eng.connect() as conn:
            cols = conn.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = ANY (current_schemas(false))
                      AND table_name = 'obs_announcements'
                      AND column_name IN ('student_number', 'student_no', 'course_section_id', 'audience_type')
                    ORDER BY column_name
                    """
                )
            ).fetchall()
            print("\n--- obs_announcements (secili kolonlar) ---")
            for (cn,) in cols:
                print(f"  - {cn}")

    print(
        "\nNOT: Ekranda ders gorup burada obs_* yoksa, backend'i calistirdigin ortamda\n"
        "      DATABASE_URL / OBS_DATABASE_URL farkli olabilir (PyCharm Run, Docker, vb.).\n"
        "      Bu script sadece proje kokundaki .env'i yukler."
    )


if __name__ == "__main__":
    main()
