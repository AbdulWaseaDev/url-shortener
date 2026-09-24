"""Read-only smoke tests for production.

Run after a production deploy to confirm the API is up and wired correctly.
They never create links, so they leave no data in the production table.

Usage:
    export SMOKE_API_ENDPOINT=https://url-shortener.berlintechs.com
    pytest tests/smoke/
"""

import os

import pytest
import requests


pytestmark = pytest.mark.skipif(
    not os.getenv('SMOKE_API_ENDPOINT'),
    reason="Smoke tests disabled. Set SMOKE_API_ENDPOINT to run"
)


@pytest.fixture(scope='module')
def api_endpoint():
    return os.environ['SMOKE_API_ENDPOINT'].rstrip('/')


def test_unknown_code_returns_404(api_endpoint):
    """Redirect route reaches Lambda and DynamoDB, and doesn't create an item."""
    response = requests.get(f'{api_endpoint}/zzzzzz', allow_redirects=False, timeout=10)
    assert response.status_code == 404


def test_stats_for_unknown_code_returns_404(api_endpoint):
    """Stats route reaches Lambda and DynamoDB."""
    response = requests.get(f'{api_endpoint}/links/zzzzzz/stats', timeout=10)
    assert response.status_code == 404


def test_create_link_requires_api_key(api_endpoint):
    """API key enforcement is active on POST /links."""
    response = requests.post(
        f'{api_endpoint}/links',
        json={'url': 'https://example.com'},
        timeout=10
    )
    assert response.status_code == 403
