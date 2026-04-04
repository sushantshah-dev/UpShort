from __future__ import annotations

import csv
import datetime as dt
import os
from pathlib import Path

from peewee import chunked
from werkzeug.security import generate_password_hash

from app.database import db
from app.models.url import Url
from app.models.event import Event
from app.models.user import User

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
USERS_CSV = SEED_DIR / "users.csv"
URLS_CSV = SEED_DIR / "urls.csv"
EVENTS_CSV = SEED_DIR / "events.csv"
DEFAULT_SEED_PASSWORD = os.environ.get("SEED_DEFAULT_PASSWORD", "seed-password")


def _parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _load_users_rows() -> list[dict]:
    rows: list[dict] = []
    with USERS_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        password_hash = generate_password_hash(DEFAULT_SEED_PASSWORD)
        for row in reader:
            rows.append(
                {
                    "id": int(row["id"]),
                    "email": row["email"].strip().lower(),
                    "password_hash": password_hash,
                    "created_at": _parse_timestamp(row["created_at"]),
                }
            )
    return rows


def _load_urls_rows() -> list[dict]:
    rows: list[dict] = []
    with URLS_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "id": int(row["id"]),
                    "user_id": int(row["user_id"]),
                    "slug": row["short_code"].strip(),
                    "target_url": row["original_url"].strip(),
                    "metadata_title": (row.get("title") or "").strip() or None,
                    "created_at": _parse_timestamp(row["created_at"]),
                    "updated_at": _parse_timestamp(row["updated_at"]),
                }
            )
    return rows


def _load_events_rows() -> list[dict]:
    rows: list[dict] = []
    with EVENTS_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "id": int(row["id"]),
                    "short_url_id": int(row["url_id"]),
                    "user_id": int(row["user_id"]),
                    "event_type": row["event_type"].strip(),
                    "occurred_at": _parse_timestamp(row["timestamp"]),
                    "details": (row.get("details") or "").strip() or None,
                }
            )
    return rows


def _insert_in_batches(model, rows: list[dict], batch_size: int = 500) -> None:
    for batch in chunked(rows, batch_size):
        model.insert_many(batch).execute()


def _sync_pk_sequence(table_name: str) -> None:
    db.execute_sql(f"""
        SELECT setval(
            pg_get_serial_sequence('{table_name}', 'id'),
            COALESCE((SELECT MAX(id) FROM "{table_name}"), 1),
            (SELECT COUNT(*) > 0 FROM "{table_name}")
        )
        """)


def _sync_all_sequences() -> None:
    _sync_pk_sequence("users")
    _sync_pk_sequence("short_urls")
    _sync_pk_sequence("short_url_events")
    _sync_pk_sequence("short_url_visitors")


def seed_database_if_empty() -> bool:
    seeded_any = False

    if USERS_CSV.exists() and User.select().count() == 0:
        user_rows = _load_users_rows()
        with db.atomic():
            _insert_in_batches(User, user_rows)
        seeded_any = True

    if URLS_CSV.exists() and Url.select().count() == 0:
        url_rows = _load_urls_rows()
        with db.atomic():
            _insert_in_batches(Url, url_rows)
        seeded_any = True

    if EVENTS_CSV.exists() and Event.select().count() == 0:
        # Events require users and urls to be present first.
        if User.select().count() > 0 and Url.select().count() > 0:
            event_rows = _load_events_rows()
            with db.atomic():
                _insert_in_batches(Event, event_rows)
            seeded_any = True

    # Always run sequence sync so existing DBs recover from sequence drift.
    _sync_all_sequences()

    return seeded_any
