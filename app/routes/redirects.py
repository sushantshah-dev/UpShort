from flask import Blueprint, abort, current_app, make_response, render_template
from peewee import OperationalError

from app.cache import short_url_cache
from app.metrics import record_fallback_usage
from app.models.url import Url
from app.utils import (
    _hydrate_cache_from_db,
    _is_resource_inactive,
    _isoformat_or_none,
    cache_tier_header_value,
    cache_url,
    record_redirect_visit,
)

redirects_bp = Blueprint("redirects", __name__)


@redirects_bp.get("/<string:slug>")
def resolve_short_url(slug: str):
    url_payload, _source = _hydrate_cache_from_db(slug)
    if url_payload is None:
        abort(404)

    is_inactive, status_code = _is_resource_inactive(url_payload)
    if is_inactive:
        abort(status_code)

    try:
        url_obj = Url.get_or_none(Url.slug == slug)
        if url_obj is not None:
            resource_payload = {
                "is_active": url_obj.is_active,
                "expires_at": _isoformat_or_none(url_obj.expires_at),
            }
            is_inactive, status_code = _is_resource_inactive(resource_payload)
            if is_inactive:
                cache_url(url_obj)
                abort(status_code)

            record_redirect_visit(url_obj)
        else:
            short_url_cache.increment_click_count(slug)
    except OperationalError:
        record_fallback_usage("redirect_click_count_cache_only")
        short_url_cache.increment_click_count(slug)

    html = render_template(
        "resolve_redirect.html",
        target_url=url_payload["target_url"],
        metadata_title=url_payload.get("metadata_title"),
        metadata_description=url_payload.get("metadata_description"),
        metadata_tags=url_payload.get("metadata_tags"),
    )
    response = make_response(html, 302)
    response.headers["Location"] = url_payload["target_url"]
    response.headers["X-Cache-Tier"] = cache_tier_header_value(_source)
    current_app.logger.info(
        "redirect served",
        extra={
            "location": url_payload["target_url"],
        },
    )
    return response
