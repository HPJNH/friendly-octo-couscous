from __future__ import annotations

from urllib.parse import SplitResult, urlsplit

from flask import current_app, request


ALLOWED_PUBLIC_SCHEMES = {"http", "https"}


def _origin_from_parts(parts: SplitResult) -> str | None:
    scheme = (parts.scheme or "").strip().lower()
    netloc = (parts.netloc or "").strip().lower()
    if scheme not in ALLOWED_PUBLIC_SCHEMES or not netloc:
        return None
    return f"{scheme}://{netloc}"


def normalize_public_base_url(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    origin = _origin_from_parts(parts)
    if not origin:
        raise ValueError("PUBLIC_BASE_URL 必须是完整的 http(s) 地址，例如 https://intel.example.com")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("PUBLIC_BASE_URL 只能填写基础地址，不要包含 path、query 或 fragment")
    return origin


def allowed_redirect_origins() -> set[str]:
    origins: set[str] = set()
    try:
        request_origin = _origin_from_parts(urlsplit(request.host_url))
    except RuntimeError:
        request_origin = None
    if request_origin:
        origins.add(request_origin)
    public_base_url = str(current_app.config.get("PUBLIC_BASE_URL", "") or "").strip()
    if public_base_url:
        origins.add(public_base_url)
    return origins


def _relative_target_from_parts(parts: SplitResult) -> str | None:
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path.lstrip("/")
    if path.startswith("//"):
        return None
    query = f"?{parts.query}" if parts.query else ""
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return f"{path}{query}{fragment}"


def sanitize_optional_redirect_target(target: str | None) -> str | None:
    value = str(target or "").strip()
    if not value:
        return None
    if value.startswith("/") and not value.startswith("//"):
        return value

    parts = urlsplit(value)
    origin = _origin_from_parts(parts)
    if not origin or origin not in allowed_redirect_origins():
        return None
    return _relative_target_from_parts(parts)


def sanitize_redirect_target(target: str | None, fallback: str) -> str:
    return sanitize_optional_redirect_target(target) or fallback
