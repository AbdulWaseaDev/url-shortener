"""Core URL shortener logic - validation and code generation."""

import random
import string
from urllib.parse import urlparse


def generate_short_code(length: int = 6) -> str:
    """
    Generate a random alphanumeric short code.

    Uses uppercase, lowercase letters and digits (62 possible characters).
    With 6 characters: 62^6 = ~56 billion possible combinations.

    Args:
        length: Length of the short code (default: 6)

    Returns:
        Random alphanumeric string of specified length
    """
    characters = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    return ''.join(random.choices(characters, k=length))


def is_valid_url(url: str) -> bool:
    """
    Validate that a string is a properly formatted URL.

    Checks for:
    - Non-empty string
    - Valid URL structure (scheme + netloc)
    - HTTP or HTTPS scheme only

    Args:
        url: The URL string to validate

    Returns:
        True if valid URL, False otherwise
    """
    if not url or not isinstance(url, str):
        return False

    try:
        result = urlparse(url)
        # Must have both scheme and netloc (domain)
        # Scheme must be http or https
        return all([
            result.scheme in ('http', 'https'),
            result.netloc
        ])
    except Exception:
        return False


def validate_create_link_request(body: dict) -> tuple[bool, str | None]:
    """
    Validate the request body for creating a new short link.

    Args:
        body: Request body dictionary

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if invalid
    """
    if body is None:
        return False, "Request body is required"

    if 'url' not in body:
        return False, "Missing required field: 'url'"

    url = body['url']

    if not url:
        return False, "URL cannot be empty"

    if not isinstance(url, str):
        return False, "URL must be a string"

    if not is_valid_url(url):
        return False, "Invalid URL format. Must be a valid HTTP or HTTPS URL"

    # Optional: Check URL length (DynamoDB has a 400KB item size limit)
    if len(url) > 2048:
        return False, "URL is too long (max 2048 characters)"

    return True, None
