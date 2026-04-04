from __future__ import annotations

import datetime as dt

from peewee import CharField, DateTimeField, ForeignKeyField, IntegerField, TextField

from app.database import BaseModel
from app.models.user import User


class Url(BaseModel):
    user = ForeignKeyField(User, backref="urls", on_delete="CASCADE")
    slug = CharField(max_length=64, unique=True, index=True)
    target_url = TextField()
    metadata_title = CharField(max_length=255, null=True)
    metadata_description = TextField(null=True)
    metadata_tags = CharField(max_length=255, null=True)
    click_count = IntegerField(default=0)
    unique_visitor_count = IntegerField(default=0)
    desktop_click_count = IntegerField(default=0)
    mobile_click_count = IntegerField(default=0)
    other_device_click_count = IntegerField(default=0)
    first_clicked_at = DateTimeField(null=True)
    last_clicked_at = DateTimeField(null=True)
    last_referrer = CharField(max_length=512, null=True)
    last_visitor_ip = CharField(max_length=64, null=True)
    last_user_agent = TextField(null=True)
    created_at = DateTimeField(default=dt.datetime.utcnow)
    updated_at = DateTimeField(default=dt.datetime.utcnow)

    class Meta:
        table_name = "short_urls"
