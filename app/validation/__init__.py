from __future__ import annotations

from flask import request

from app.utils import (
    _is_valid_email,
    _is_valid_slug,
    _is_valid_url,
    _parse_optional_expires_at,
)

_ALLOWED_FORM_MIME_TYPES = {
    "application/x-www-form-urlencoded",
    "multipart/form-data",
}
_MAX_EMAIL_LENGTH = 255
_MAX_PASSWORD_LENGTH = 255
_MAX_URL_LENGTH = 2048
_MAX_METADATA_TITLE_LENGTH = 255
_MAX_METADATA_DESCRIPTION_LENGTH = 2000
_MAX_METADATA_TAGS_LENGTH = 255


def _validate_form_content_type() -> str | None:
    if request.mimetype in _ALLOWED_FORM_MIME_TYPES:
        return None
    return "Form submissions must use form encoding."


def _get_form_value(
    field_name: str,
    *,
    required: bool = False,
    strip: bool = True,
    lower: bool = False,
    max_length: int | None = None,
    label: str | None = None,
) -> tuple[str, str | None]:
    values = request.form.getlist(field_name)
    field_label = label or field_name.replace("_", " ").title()

    if len(values) > 1:
        return "", f"{field_label} must be provided only once."

    value = values[0] if values else ""
    if not isinstance(value, str):
        return "", f"{field_label} must be text."

    if strip:
        value = value.strip()
    if lower:
        value = value.lower()

    if required and not value:
        return "", f"{field_label} is required."

    if max_length is not None and len(value) > max_length:
        return "", f"{field_label} must be at most {max_length} characters."

    return value, None


def _get_checkbox_value(
    field_name: str, *, label: str | None = None
) -> tuple[bool, str | None]:
    values = request.form.getlist(field_name)
    field_label = label or field_name.replace("_", " ").title()

    if len(values) > 1:
        return False, f"{field_label} must be provided only once."
    if not values:
        return False, None
    if values[0] != "on":
        return False, f"{field_label} must be a valid checkbox value."

    return True, None


def _validate_registration_form() -> tuple[dict[str, str], str | None]:
    content_type_error = _validate_form_content_type()
    if content_type_error:
        return {}, content_type_error

    email, email_error = _get_form_value(
        "email", required=True, lower=True, max_length=_MAX_EMAIL_LENGTH, label="Email"
    )
    if email_error:
        return {"email": email}, email_error
    if not _is_valid_email(email):
        return {"email": email}, "Email must be valid."

    password, password_error = _get_form_value(
        "password",
        required=True,
        strip=False,
        max_length=_MAX_PASSWORD_LENGTH,
        label="Password",
    )
    if password_error:
        return {"email": email}, password_error

    confirm_password, confirm_password_error = _get_form_value(
        "confirm_password",
        required=True,
        strip=False,
        max_length=_MAX_PASSWORD_LENGTH,
        label="Confirm password",
    )
    if confirm_password_error:
        return {"email": email}, confirm_password_error

    if password != confirm_password:
        return {"email": email}, "Passwords do not match."

    return {
        "email": email,
        "password": password,
        "confirm_password": confirm_password,
    }, None


def _validate_login_form() -> tuple[dict[str, str], str | None]:
    content_type_error = _validate_form_content_type()
    if content_type_error:
        return {}, content_type_error

    email, email_error = _get_form_value(
        "email", required=True, lower=True, max_length=_MAX_EMAIL_LENGTH, label="Email"
    )
    if email_error:
        return {"email": email}, email_error
    if not _is_valid_email(email):
        return {"email": email}, "Email must be valid."

    password, password_error = _get_form_value(
        "password",
        required=True,
        strip=False,
        max_length=_MAX_PASSWORD_LENGTH,
        label="Password",
    )
    if password_error:
        return {"email": email}, password_error

    return {"email": email, "password": password}, None


def _validate_url_form() -> tuple[dict[str, str | bool], str | None]:
    content_type_error = _validate_form_content_type()
    if content_type_error:
        return {}, content_type_error

    target_url, target_url_error = _get_form_value(
        "target_url", required=True, max_length=_MAX_URL_LENGTH, label="Target URL"
    )
    slug, slug_error = _get_form_value(
        "slug", required=True, max_length=64, label="Slug"
    )
    is_active, is_active_error = _get_checkbox_value("is_active", label="Link status")
    expires_at_raw, expires_at_error = _get_form_value(
        "expires_at", max_length=32, label="Expires At"
    )
    metadata_title, metadata_title_error = _get_form_value(
        "metadata_title", max_length=_MAX_METADATA_TITLE_LENGTH, label="Metadata Title"
    )
    metadata_description, metadata_description_error = _get_form_value(
        "metadata_description",
        max_length=_MAX_METADATA_DESCRIPTION_LENGTH,
        label="Metadata Description",
    )
    metadata_tags, metadata_tags_error = _get_form_value(
        "metadata_tags", max_length=_MAX_METADATA_TAGS_LENGTH, label="Metadata Tags"
    )

    form = {
        "target_url": target_url,
        "slug": slug,
        "is_active": is_active,
        "expires_at": expires_at_raw,
        "metadata_title": metadata_title,
        "metadata_description": metadata_description,
        "metadata_tags": metadata_tags,
    }

    for error in (
        target_url_error,
        slug_error,
        is_active_error,
        expires_at_error,
        metadata_title_error,
        metadata_description_error,
        metadata_tags_error,
    ):
        if error:
            return form, error

    if not _is_valid_url(target_url):
        return form, "Target URL must be an absolute http/https URL."

    if not _is_valid_slug(slug):
        return (
            form,
            "Slug must be 3-64 characters and use letters, numbers, '_' or '-'.",
        )

    try:
        expires_at = _parse_optional_expires_at(expires_at_raw)
    except ValueError:
        return form, "Expiration must be a valid date and time."

    return {**form, "expires_at": expires_at}, None
