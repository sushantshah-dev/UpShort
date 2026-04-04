from __future__ import annotations

from peewee import CharField, DateTimeField, ForeignKeyField, TextField

from app.database import BaseModel
from app.models.url import Url
from app.models.user import User


class Event(BaseModel):
    short_url = ForeignKeyField(Url, backref="events", on_delete="CASCADE")
    user = ForeignKeyField(User, backref="url_events", on_delete="CASCADE")
    event_type = CharField(max_length=32, index=True)
    occurred_at = DateTimeField(index=True)
    details = TextField(null=True)

    class Meta:
        table_name = "short_url_events"
