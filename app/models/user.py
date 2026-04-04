from __future__ import annotations

import datetime as dt

from peewee import CharField, DateTimeField

from app.database import BaseModel


class User(BaseModel):
    email = CharField(max_length=255, unique=True, index=True)
    password_hash = CharField(max_length=255)
    created_at = DateTimeField(default=dt.datetime.utcnow)

    class Meta:
        table_name = "users"
