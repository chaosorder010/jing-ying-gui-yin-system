"""Seed system configs. Sample CSV/JSON live under data/samples."""

from app.database import SessionLocal
from app.services.config_service import ensure_default_configs


def main() -> None:
    db = SessionLocal()
    try:
        ensure_default_configs(db)
        print("seed ok")
    finally:
        db.close()


if __name__ == "__main__":
    main()
