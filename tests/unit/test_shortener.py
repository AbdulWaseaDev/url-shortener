"""Unit tests for core shortener logic."""

import string

import pytest
from url_shortener.shortener import (
    generate_short_code,
    is_valid_url,
    validate_create_link_request
)


class TestGenerateShortCode:
    """Test short code generation."""

    def test_default_length(self):
        """Short code should be 6 characters by default."""
        code = generate_short_code()
        assert len(code) == 6

    def test_custom_length(self):
        """Should support custom lengths."""
        code = generate_short_code(length=10)
        assert len(code) == 10

    def test_alphanumeric_only(self):
        """Code should contain only alphanumeric characters."""
        code = generate_short_code()
        assert code.isalnum()

    def test_default_code_is_six_ascii_alphanumerics(self):
        """Default code is 6 characters, each from the a-z, A-Z, 0-9 alphabet."""
        alphabet = set(string.ascii_letters + string.digits)
        for _ in range(50):
            code = generate_short_code()
            assert len(code) == 6
            assert set(code) <= alphabet

    def test_uniqueness(self):
        """Multiple calls should produce different codes (statistically)."""
        codes = [generate_short_code() for _ in range(100)]
        # Should have high uniqueness (allow small collision chance)
        assert len(set(codes)) > 95


class TestIsValidUrl:
    """Test URL validation."""

    def test_valid_http_url(self):
        """Should accept valid HTTP URLs."""
        assert is_valid_url('http://example.com') is True

    def test_valid_https_url(self):
        """Should accept valid HTTPS URLs."""
        assert is_valid_url('https://example.com') is True

    def test_valid_url_with_path(self):
        """Should accept URLs with paths."""
        assert is_valid_url('https://example.com/path/to/page') is True

    def test_valid_url_with_query(self):
        """Should accept URLs with query parameters."""
        assert is_valid_url('https://example.com/page?param=value') is True

    def test_valid_url_with_fragment(self):
        """Should accept URLs with fragments."""
        assert is_valid_url('https://example.com/page#section') is True

    def test_invalid_empty_string(self):
        """Should reject empty strings."""
        assert is_valid_url('') is False

    def test_invalid_none(self):
        """Should reject None."""
        assert is_valid_url(None) is False

    def test_invalid_not_string(self):
        """Should reject non-string types."""
        assert is_valid_url(123) is False
        assert is_valid_url(['http://example.com']) is False

    def test_invalid_no_scheme(self):
        """Should reject URLs without scheme."""
        assert is_valid_url('example.com') is False

    def test_invalid_no_domain(self):
        """Should reject URLs without domain."""
        assert is_valid_url('http://') is False

    def test_invalid_ftp_scheme(self):
        """Should reject non-HTTP(S) schemes."""
        assert is_valid_url('ftp://example.com') is False

    def test_invalid_javascript_scheme(self):
        """Should reject javascript: URLs."""
        assert is_valid_url('javascript:alert(1)') is False

    def test_invalid_malformed(self):
        """Should reject malformed URLs."""
        assert is_valid_url('not a url at all') is False


class TestValidateCreateLinkRequest:
    """Test request validation for creating links."""

    def test_valid_request(self):
        """Should accept valid request with URL."""
        body = {'url': 'https://example.com'}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is True
        assert error is None

    def test_empty_body(self):
        """Should reject empty body."""
        is_valid, error = validate_create_link_request({})
        assert is_valid is False
        assert 'url' in error.lower()

    def test_none_body(self):
        """Should reject None body."""
        is_valid, error = validate_create_link_request(None)
        assert is_valid is False
        assert 'required' in error.lower()

    def test_missing_url_field(self):
        """Should reject body without 'url' field."""
        body = {'other_field': 'value'}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is False
        assert 'url' in error.lower()

    def test_empty_url(self):
        """Should reject empty URL."""
        body = {'url': ''}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is False
        assert 'empty' in error.lower()

    def test_url_not_string(self):
        """Should reject non-string URL."""
        body = {'url': 123}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is False
        assert 'string' in error.lower()

    def test_invalid_url_format(self):
        """Should reject invalid URL format."""
        body = {'url': 'not-a-url'}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is False
        assert 'invalid' in error.lower()

    def test_url_too_long(self):
        """Should reject URLs longer than 2048 characters."""
        long_url = 'https://example.com/' + 'a' * 2100
        body = {'url': long_url}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is False
        assert 'too long' in error.lower()

    def test_url_max_length_accepted(self):
        """Should accept URLs at max length (2048 chars)."""
        # Create URL exactly at limit
        max_url = 'https://example.com/' + 'a' * (2048 - len('https://example.com/'))
        body = {'url': max_url}
        is_valid, error = validate_create_link_request(body)
        assert is_valid is True
        assert error is None
