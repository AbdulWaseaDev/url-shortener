"""Integration tests against real deployed API.

These tests hit the actual API Gateway endpoint and interact with
real DynamoDB tables. They are gated behind the RUN_INTEGRATION_TESTS
environment variable to avoid running accidentally.

Usage:
    export API_ENDPOINT=https://xyz.execute-api.us-east-1.amazonaws.com/Prod
    export RUN_INTEGRATION_TESTS=true
    pytest tests/integration/
"""

import os
import time

import pytest
import requests


# Skip all tests in this module if integration tests not enabled
pytestmark = pytest.mark.skipif(
    not os.getenv('RUN_INTEGRATION_TESTS'),
    reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true to run"
)


@pytest.fixture(scope='module')
def api_endpoint():
    """Get API endpoint from environment variable."""
    endpoint = os.getenv('API_ENDPOINT')
    if not endpoint:
        pytest.skip("API_ENDPOINT environment variable not set")
    return endpoint.rstrip('/')


class TestCreateLinkIntegration:
    """Integration tests for POST /links."""

    def test_create_link_full_flow(self, api_endpoint):
        """Test creating a link and verifying it exists."""
        # Create a link
        test_url = f'https://example.com/test/{int(time.time())}'
        response = requests.post(
            f'{api_endpoint}/links',
            json={'url': test_url},
            timeout=10
        )

        assert response.status_code == 201
        data = response.json()

        assert 'short_code' in data
        assert 'short_url' in data
        assert data['original_url'] == test_url

        short_code = data['short_code']
        assert len(short_code) == 6

        # Verify the link works by checking stats
        stats_response = requests.get(
            f'{api_endpoint}/links/{short_code}/stats',
            timeout=10
        )

        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert stats['original_url'] == test_url
        assert stats['click_count'] == 0  # Not clicked yet

    def test_create_link_validation(self, api_endpoint):
        """Test that invalid URLs are rejected."""
        response = requests.post(
            f'{api_endpoint}/links',
            json={'url': 'not-a-valid-url'},
            timeout=10
        )

        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'invalid' in data['error'].lower()

    def test_create_link_missing_url(self, api_endpoint):
        """Test that missing URL field is rejected."""
        response = requests.post(
            f'{api_endpoint}/links',
            json={},
            timeout=10
        )

        assert response.status_code == 400
        data = response.json()
        assert 'error' in data


class TestRedirectIntegration:
    """Integration tests for GET /{code}."""

    def test_redirect_increments_counter(self, api_endpoint):
        """Test that redirect increments click count."""
        # Create a link
        test_url = f'https://example.com/redirect-test/{int(time.time())}'
        create_response = requests.post(
            f'{api_endpoint}/links',
            json={'url': test_url},
            timeout=10
        )

        assert create_response.status_code == 201
        short_code = create_response.json()['short_code']

        # Check initial stats (0 clicks)
        stats_response = requests.get(
            f'{api_endpoint}/links/{short_code}/stats',
            timeout=10
        )
        initial_stats = stats_response.json()
        assert initial_stats['click_count'] == 0

        # Follow redirect (don't allow redirects so we can check response)
        redirect_response = requests.get(
            f'{api_endpoint}/{short_code}',
            allow_redirects=False,
            timeout=10
        )

        assert redirect_response.status_code == 301
        assert redirect_response.headers['Location'] == test_url

        # Check stats again (should be 1 click)
        stats_response = requests.get(
            f'{api_endpoint}/links/{short_code}/stats',
            timeout=10
        )
        final_stats = stats_response.json()
        assert final_stats['click_count'] == 1

    def test_redirect_nonexistent_code(self, api_endpoint):
        """Test that nonexistent codes return 404."""
        response = requests.get(
            f'{api_endpoint}/XXXXXX',
            allow_redirects=False,
            timeout=10
        )

        assert response.status_code == 404
        data = response.json()
        assert 'error' in data


class TestStatsIntegration:
    """Integration tests for GET /links/{code}/stats."""

    def test_stats_for_new_link(self, api_endpoint):
        """Test stats endpoint returns correct data."""
        # Create a link
        test_url = f'https://example.com/stats-test/{int(time.time())}'
        create_response = requests.post(
            f'{api_endpoint}/links',
            json={'url': test_url},
            timeout=10
        )

        short_code = create_response.json()['short_code']

        # Get stats
        stats_response = requests.get(
            f'{api_endpoint}/links/{short_code}/stats',
            timeout=10
        )

        assert stats_response.status_code == 200
        stats = stats_response.json()

        assert stats['short_code'] == short_code
        assert stats['original_url'] == test_url
        assert stats['click_count'] == 0
        assert 'created_at' in stats

    def test_stats_nonexistent_code(self, api_endpoint):
        """Test stats for nonexistent code returns 404."""
        response = requests.get(
            f'{api_endpoint}/links/XXXXXX/stats',
            timeout=10
        )

        assert response.status_code == 404


class TestEndToEndFlow:
    """Full end-to-end flow test."""

    def test_complete_workflow(self, api_endpoint):
        """Test complete workflow: create, redirect multiple times, check stats."""
        # 1. Create a link
        test_url = f'https://example.com/e2e-test/{int(time.time())}'
        create_response = requests.post(
            f'{api_endpoint}/links',
            json={'url': test_url},
            timeout=10
        )

        assert create_response.status_code == 201
        short_code = create_response.json()['short_code']

        # 2. Click the link 3 times
        for i in range(3):
            redirect_response = requests.get(
                f'{api_endpoint}/{short_code}',
                allow_redirects=False,
                timeout=10
            )
            assert redirect_response.status_code == 301

        # 3. Verify stats show 3 clicks
        stats_response = requests.get(
            f'{api_endpoint}/links/{short_code}/stats',
            timeout=10
        )

        stats = stats_response.json()
        assert stats['click_count'] == 3
        assert stats['original_url'] == test_url
