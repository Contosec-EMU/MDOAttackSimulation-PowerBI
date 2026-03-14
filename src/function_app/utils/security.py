"""Security utilities for input sanitization and response hardening."""

import logging
from typing import Optional
from urllib.parse import urlparse

import azure.functions as func

from config import MAX_STRING_LENGTH

logger = logging.getLogger(__name__)


def sanitize_string(value: object, max_length: int = MAX_STRING_LENGTH) -> Optional[str]:
    """Sanitize string input from API responses.

    Args:
        value: Input value to sanitize
        max_length: Maximum allowed string length

    Returns:
        Sanitized string or None if input is None
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if len(value) > max_length:
        logger.warning(f"String truncated from {len(value)} to {max_length} chars")
        value = value[:max_length]
    return value


def add_security_headers(response: func.HttpResponse) -> func.HttpResponse:
    """Add security headers to HTTP response.

    Adds standard security headers including:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000
    - Content-Security-Policy: default-src 'none'
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


def sanitize_url_for_logging(url: str, max_length: int = 100) -> str:
    """Remove query params and truncate URL for safe logging.

    Args:
        url: Full URL that may contain sensitive query parameters
        max_length: Maximum length of returned string

    Returns:
        Sanitized URL safe for logging
    """
    parsed = urlparse(url)
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return safe_url[:max_length]
