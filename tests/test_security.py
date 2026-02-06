"""Tests for utils/security.py — sanitize_string, add_security_headers, sanitize_url_for_logging."""

import logging
from unittest.mock import MagicMock

import pytest

from config import MAX_STRING_LENGTH
from utils.security import add_security_headers, sanitize_string, sanitize_url_for_logging


# ===================================================================
# sanitize_string
# ===================================================================

class TestSanitizeString:

    def test_none_returns_none(self):
        assert sanitize_string(None) is None

    def test_strips_whitespace(self):
        assert sanitize_string("  hello  ") == "hello"

    def test_normal_string_unchanged(self):
        assert sanitize_string("clean") == "clean"

    def test_empty_string(self):
        assert sanitize_string("") == ""

    def test_truncates_long_string(self, caplog):
        long_str = "x" * (MAX_STRING_LENGTH + 500)
        with caplog.at_level(logging.WARNING):
            result = sanitize_string(long_str)
        assert len(result) == MAX_STRING_LENGTH
        assert "truncated" in caplog.text.lower()

    def test_exactly_max_length_not_truncated(self):
        exact = "a" * MAX_STRING_LENGTH
        assert sanitize_string(exact) == exact

    def test_converts_non_string_int(self):
        assert sanitize_string(123) == "123"

    def test_converts_non_string_float(self):
        assert sanitize_string(3.14) == "3.14"

    def test_converts_non_string_bool(self):
        assert sanitize_string(True) == "True"

    def test_custom_max_length(self):
        result = sanitize_string("abcdefgh", max_length=5)
        assert result == "abcde"

    def test_strips_then_checks_length(self):
        # Leading/trailing spaces stripped before length check
        padded = "  " + "a" * 10 + "  "
        assert sanitize_string(padded, max_length=20) == "a" * 10


# ===================================================================
# sanitize_url_for_logging
# ===================================================================

class TestSanitizeUrlForLogging:

    def test_strips_query_params(self):
        url = "https://graph.microsoft.com/v1.0/users?$filter=id eq '123'&$top=10"
        result = sanitize_url_for_logging(url)
        assert "?" not in result
        assert "$filter" not in result
        assert result.startswith("https://graph.microsoft.com")

    def test_preserves_path(self):
        url = "https://graph.microsoft.com/v1.0/security/attackSimulation/simulations"
        result = sanitize_url_for_logging(url)
        assert "/security/attackSimulation/simulations" in result

    def test_truncates_to_max_length(self):
        long_path = "/a" * 200
        url = f"https://example.com{long_path}"
        result = sanitize_url_for_logging(url, max_length=50)
        assert len(result) <= 50

    def test_no_query_params_unchanged(self):
        url = "https://graph.microsoft.com/v1.0/users"
        result = sanitize_url_for_logging(url)
        assert result == url

    def test_strips_fragment(self):
        url = "https://example.com/page#section"
        result = sanitize_url_for_logging(url)
        # Fragment is part of urlparse path or excluded; no query params
        assert "?" not in result


# ===================================================================
# add_security_headers
# ===================================================================

class TestAddSecurityHeaders:

    def _make_mock_response(self):
        resp = MagicMock()
        resp.headers = {}
        return resp

    def test_adds_all_five_headers(self):
        resp = self._make_mock_response()
        result = add_security_headers(resp)
        assert result is resp  # mutates in place and returns same object

        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Content-Security-Policy",
        ]
        for header in expected_headers:
            assert header in resp.headers, f"Missing header: {header}"

    def test_x_content_type_options_nosniff(self):
        resp = self._make_mock_response()
        add_security_headers(resp)
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_deny(self):
        resp = self._make_mock_response()
        add_security_headers(resp)
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_hsts_includes_max_age(self):
        resp = self._make_mock_response()
        add_security_headers(resp)
        assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]

    def test_csp_default_src_none(self):
        resp = self._make_mock_response()
        add_security_headers(resp)
        assert "default-src 'none'" in resp.headers["Content-Security-Policy"]
