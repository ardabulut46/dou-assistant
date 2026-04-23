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


def main() -> None:
    if load_dotenv:
        load_dotenv(REPO_ROOT / ".env")

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

    print(
        "\nNOT: Ekranda ders gorup burada obs_* yoksa, backend'i calistirdigin ortamda\n"
        "      DATABASE_URL / OBS_DATABASE_URL farkli olabilir (PyCharm Run, Docker, vb.).\n"
        "      Bu script sadece proje kokundaki .env'i yukler."
    )


if __name__ == "__main__":
    main()
