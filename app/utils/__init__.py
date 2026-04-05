from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets
from urllib.parse import urlparse

from flask import jsonify, request
from peewee import OperationalError
from werkzeug.exceptions import BadRequest

from app.cache import short_url_cache
from app.metrics import record_cache_lookup
from app.models.url import Url
from app.models.visitor import Visitor

_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RESERVED_SLUGS = {
    "api",
    "dashboard",
    "health",
    "login",
    "logout",
    "metrics",
    "register",
    "urls",
    "static",
}


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _is_valid_url(candidate: str) -> bool:
    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.fullmatch(slug)) and slug not in _RESERVED_SLUGS


def _is_valid_email(candidate: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(candidate)) and len(candidate) <= 255


def _prefers_json_response() -> bool:
    if request.is_json:
        return True

    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    if best != "application/json":
        return False

    return (
        request.accept_mimetypes["application/json"]
        >= request.accept_mimetypes["text/html"]
    )


def json_error(message: str, status_code: int, *, error_type: str = "invalid_request"):
    response = jsonify(
        {
            "error": {
                "type": error_type,
                "message": message,
                "status": status_code,
            }
        }
    )
    response.status_code = status_code
    return response


def load_json_object() -> tuple[dict, None] | tuple[None, tuple]:
    if request.mimetype != "application/json" and not request.mimetype.endswith("+json"):
        return None, (
            json_error(
                "Request body must use Content-Type: application/json.",
                415,
                error_type="unsupported_media_type",
            ),
            415,
        )

    try:
        payload = request.get_json(silent=False)
    except BadRequest:
        return None, (
            json_error("Malformed JSON request body.", 400, error_type="malformed_json"),
            400,
        )

    if not isinstance(payload, dict):
        return None, (
            json_error(
                "JSON request body must be an object.",
                400,
                error_type="invalid_request",
            ),
            400,
        )

    return payload, None


def generate_slug(length: int = 8) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    slug = "".join(secrets.choice(alphabet) for _ in range(length))
    if _is_valid_slug(slug):
        return slug
    return generate_slug(length)


def _extract_client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64] or None
    return (request.remote_addr or "")[:64] or None


def _parse_optional_expires_at(raw_value: str) -> dt.datetime | None:
    if not raw_value:
        return None

    normalized = raw_value.strip()
    if not normalized:
        return None

    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(normalized, fmt)
        except ValueError:
            continue

    raise ValueError("Invalid expiration timestamp format.")


def _isoformat_or_none(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def _is_resource_inactive(resource) -> tuple[bool, int]:
    if not resource.get("is_active", True):
        return True, 404

    expires_at_raw = resource.get("expires_at")
    if not expires_at_raw:
        return False, 200

    expires_at = expires_at_raw
    if isinstance(expires_at_raw, str):
        normalized = expires_at_raw.removesuffix("Z")
        expires_at = dt.datetime.fromisoformat(normalized)

    if expires_at <= _utcnow():
        return True, 410

    return False, 200


def _detect_device_type(user_agent: str) -> str:
    user_agent_lower = user_agent.lower()
    mobile_tokens = ["mobile", "android", "iphone", "ipad", "ipod"]
    desktop_tokens = ["windows", "macintosh", "linux", "x11"]

    if any(token in user_agent_lower for token in mobile_tokens):
        return "mobile"
    if any(token in user_agent_lower for token in desktop_tokens):
        return "desktop"
    return "other"


def cache_url(url_obj: Url) -> None:
    short_url_cache.set(
        slug=url_obj.slug,
        target_url=url_obj.target_url,
        click_count=url_obj.click_count,
        created_at=url_obj.created_at,
        is_active=url_obj.is_active,
        expires_at=url_obj.expires_at,
        metadata_title=url_obj.metadata_title,
        metadata_description=url_obj.metadata_description,
        metadata_tags=url_obj.metadata_tags,
    )


def build_url_payload(url_obj: Url) -> dict:
    return {
        "slug": url_obj.slug,
        "target_url": url_obj.target_url,
        "click_count": url_obj.click_count,
        "created_at": _isoformat_or_none(url_obj.created_at),
        "is_active": url_obj.is_active,
        "expires_at": _isoformat_or_none(url_obj.expires_at),
        "metadata_title": url_obj.metadata_title,
        "metadata_description": url_obj.metadata_description,
        "metadata_tags": url_obj.metadata_tags,
    }


def _hydrate_cache_from_db(slug: str) -> tuple[dict, str] | tuple[None, None]:
    cached, source = short_url_cache.get(slug)
    if cached is not None:
        return cached, source

    try:
        url_obj = Url.get_or_none(Url.slug == slug)
    except OperationalError:
        return None, None

    if url_obj is None:
        return None, None

    cache_url(url_obj)
    record_cache_lookup("database", "hit")
    return build_url_payload(url_obj), "database"


def cache_tier_header_value(source: str | None) -> str:
    if source == "memory":
        return "local"
    if source == "redis":
        return "shared"
    return "fresh"


def _upsert_visitor_visit(
    url_obj: Url,
    fingerprint: str,
    now: dt.datetime,
) -> bool:
    database = Visitor._meta.database
    cursor = database.execute_sql(
        """
        INSERT INTO short_url_visitors (short_url_id, fingerprint, first_seen_at, last_seen_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (short_url_id, fingerprint)
        DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at
        RETURNING (xmax = 0) AS inserted
        """,
        (url_obj.id, fingerprint, now, now),
    )
    row = cursor.fetchone()
    return bool(row[0]) if row else False


def record_redirect_visit(url_obj: Url) -> None:
    now = _utcnow()
    client_ip = _extract_client_ip()
    user_agent = (request.headers.get("User-Agent") or "")[:512]
    referrer = (request.referrer or "")[:512] or None
    device_type = _detect_device_type(user_agent)

    fingerprint_source = f"{client_ip or 'unknown'}|{user_agent}"
    visitor_fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()

    new_visitor = _upsert_visitor_visit(url_obj, visitor_fingerprint, now)

    url_obj.click_count += 1
    if new_visitor:
        url_obj.unique_visitor_count += 1
    if url_obj.first_clicked_at is None:
        url_obj.first_clicked_at = now
    url_obj.last_clicked_at = now
    url_obj.last_referrer = referrer
    url_obj.last_visitor_ip = client_ip
    url_obj.last_user_agent = user_agent or None
    if device_type == "mobile":
        url_obj.mobile_click_count += 1
    elif device_type == "desktop":
        url_obj.desktop_click_count += 1
    else:
        url_obj.other_device_click_count += 1
    url_obj.updated_at = now
    url_obj.save()

    cache_url(url_obj)
