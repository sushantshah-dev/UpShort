from __future__ import annotations

import datetime as dt

from peewee import CharField, DateTimeField, ForeignKeyField

from app.database import BaseModel
from app.models.url import Url


class Visitor(BaseModel):
    short_url = ForeignKeyField(Url, backref="visitors", on_delete="CASCADE")
    fingerprint = CharField(max_length=64)
    first_seen_at = DateTimeField(default=dt.datetime.utcnow)
    last_seen_at = DateTimeField(default=dt.datetime.utcnow)

    class Meta:
        table_name = "short_url_visitors"
        indexes = ((("short_url", "fingerprint"), True),)
