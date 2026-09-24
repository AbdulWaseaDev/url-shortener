"""Unit tests for Lambda handler with mocked boto3."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

# Set environment variables before importing app
os.environ['TABLE_NAME'] = 'test-table'
os.environ['BASE_URL'] = 'https://api.example.com'

from url_shortener.app import (
    lambda_handler,
    create_link,
    get_redirect,
    get_stats,
    error_response
)


class TestErrorResponse:
    """Test error response helper."""

    def test_creates_proper_format(self):
        """Should create properly formatted error response."""
        response = error_response(400, 'Test error')
        assert response['statusCode'] == 400
        assert 'error' in json.loads(response['body'])
        assert json.loads(response['body'])['error'] == 'Test error'

    def test_includes_cors_header(self):
        """Should include CORS header."""
        response = error_response(404, 'Not found')
        assert response['headers']['Access-Control-Allow-Origin'] == '*'


class TestLambdaHandler:
    """Test main Lambda handler routing."""

    @patch('url_shortener.app.dynamodb')
    def test_routes_post_links(self, mock_dynamodb):
        """Should route POST /links to create_link."""
        mock_dynamodb.put_item.return_value = {}

        event = {
            'httpMethod': 'POST',
            'path': '/links',
            'body': json.dumps({'url': 'https://example.com'})
        }

        response = lambda_handler(event, None)
        assert response['statusCode'] in (201, 200)

    @patch('url_shortener.app.dynamodb')
    def test_routes_get_redirect(self, mock_dynamodb):
        """Should route GET /{code} to get_redirect."""
        mock_dynamodb.update_item.return_value = {
            'Attributes': {
                'original_url': {'S': 'https://example.com'},
                'click_count': {'N': '1'}
            }
        }

        event = {
            'httpMethod': 'GET',
            'path': '/abc123',
            'pathParameters': {'code': 'abc123'}
        }

        response = lambda_handler(event, None)
        assert response['statusCode'] == 302

    @patch('url_shortener.app.dynamodb')
    def test_routes_get_stats(self, mock_dynamodb):
        """Should route GET /links/{code}/stats to get_stats."""
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'short_code': {'S': 'abc123'},
                'original_url': {'S': 'https://example.com'},
                'click_count': {'N': '5'},
                'created_at': {'S': '2024-01-01T00:00:00'}
            }
        }

        event = {
            'httpMethod': 'GET',
            'path': '/links/abc123/stats',
            'pathParameters': {'code': 'abc123'}
        }

        response = lambda_handler(event, None)
        assert response['statusCode'] == 200

    def test_returns_404_for_unknown_route(self):
        """Should return 404 for unknown routes."""
        event = {
            'httpMethod': 'DELETE',
            'path': '/unknown',
            'pathParameters': {}
        }

        response = lambda_handler(event, None)
        assert response['statusCode'] == 404


class TestCreateLink:
    """Test POST /links endpoint."""

    @patch('url_shortener.app.dynamodb')
    @patch('url_shortener.app.generate_short_code')
    def test_creates_link_successfully(self, mock_generate, mock_dynamodb):
        """Should create link and return short URL."""
        mock_generate.return_value = 'abc123'
        mock_dynamodb.put_item.return_value = {}

        event = {
            'body': json.dumps({'url': 'https://example.com/long-url'})
        }

        response = create_link(event)

        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['short_code'] == 'abc123'
        assert body['original_url'] == 'https://example.com/long-url'
        assert 'short_url' in body

        # Verify DynamoDB was called correctly
        mock_dynamodb.put_item.assert_called_once()
        call_args = mock_dynamodb.put_item.call_args
        assert call_args[1]['TableName'] == 'test-table'
        assert call_args[1]['Item']['short_code']['S'] == 'abc123'

    @patch('url_shortener.app.dynamodb')
    def test_rejects_invalid_json(self, mock_dynamodb):
        """Should return 400 for invalid JSON."""
        event = {'body': 'not valid json'}
        response = create_link(event)
        assert response['statusCode'] == 400
        assert 'json' in json.loads(response['body'])['error'].lower()

    @patch('url_shortener.app.dynamodb')
    def test_rejects_missing_url(self, mock_dynamodb):
        """Should return 400 for missing URL."""
        event = {'body': json.dumps({})}
        response = create_link(event)
        assert response['statusCode'] == 400
        assert 'url' in json.loads(response['body'])['error'].lower()

    @patch('url_shortener.app.dynamodb')
    def test_rejects_invalid_url(self, mock_dynamodb):
        """Should return 400 for invalid URL."""
        event = {'body': json.dumps({'url': 'not-a-url'})}
        response = create_link(event)
        assert response['statusCode'] == 400
        assert 'invalid' in json.loads(response['body'])['error'].lower()

    @patch('url_shortener.app.dynamodb')
    @patch('url_shortener.app.generate_short_code')
    def test_retries_on_collision(self, mock_generate, mock_dynamodb):
        """Should retry with new code on collision."""
        # First two codes collide, third succeeds
        mock_generate.side_effect = ['collision1', 'collision2', 'success3']

        # Simulate collision then success
        def put_side_effect(*args, **kwargs):
            code = kwargs['Item']['short_code']['S']
            if code in ('collision1', 'collision2'):
                from botocore.exceptions import ClientError
                raise ClientError(
                    {'Error': {'Code': 'ConditionalCheckFailedException'}},
                    'PutItem'
                )
            return {}

        mock_dynamodb.put_item.side_effect = put_side_effect

        event = {'body': json.dumps({'url': 'https://example.com'})}
        response = create_link(event)

        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['short_code'] == 'success3'
        assert mock_dynamodb.put_item.call_count == 3


class TestGetRedirect:
    """Test GET /{code} endpoint."""

    @patch('url_shortener.app.dynamodb')
    def test_redirects_successfully(self, mock_dynamodb):
        """Should return 302 redirect with original URL."""
        mock_dynamodb.update_item.return_value = {
            'Attributes': {
                'original_url': {'S': 'https://example.com/original'},
                'click_count': {'N': '1'}
            }
        }

        response = get_redirect('abc123')

        assert response['statusCode'] == 302
        assert response['headers']['Location'] == 'https://example.com/original'

        # Verify atomic increment was called
        call_args = mock_dynamodb.update_item.call_args
        assert 'ADD click_count' in call_args[1]['UpdateExpression']

    @patch('url_shortener.app.dynamodb')
    def test_returns_404_for_nonexistent_code(self, mock_dynamodb):
        """Should return 404 if code doesn't exist."""
        mock_dynamodb.update_item.return_value = {}  # No Attributes

        response = get_redirect('nonexistent')

        assert response['statusCode'] == 404
        assert 'not found' in json.loads(response['body'])['error'].lower()

    def test_rejects_empty_code(self):
        """Should return 400 for empty code."""
        response = get_redirect('')
        assert response['statusCode'] == 400

    @patch('url_shortener.app.dynamodb')
    def test_increments_click_count_atomically(self, mock_dynamodb):
        """Should use atomic ADD operation for click count."""
        mock_dynamodb.update_item.return_value = {
            'Attributes': {
                'original_url': {'S': 'https://example.com'},
                'click_count': {'N': '5'}
            }
        }

        get_redirect('abc123')

        call_args = mock_dynamodb.update_item.call_args[1]
        assert call_args['UpdateExpression'] == 'ADD click_count :inc'
        assert call_args['ExpressionAttributeValues'][':inc']['N'] == '1'


class TestGetStats:
    """Test GET /links/{code}/stats endpoint."""

    @patch('url_shortener.app.dynamodb')
    def test_returns_stats_successfully(self, mock_dynamodb):
        """Should return link statistics."""
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'short_code': {'S': 'abc123'},
                'original_url': {'S': 'https://example.com'},
                'click_count': {'N': '42'},
                'created_at': {'S': '2024-01-01T12:00:00'}
            }
        }

        response = get_stats('abc123')

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['short_code'] == 'abc123'
        assert body['click_count'] == 42
        assert body['created_at'] == '2024-01-01T12:00:00'

    @patch('url_shortener.app.dynamodb')
    def test_returns_404_for_nonexistent_code(self, mock_dynamodb):
        """Should return 404 if code doesn't exist."""
        mock_dynamodb.get_item.return_value = {}  # No Item

        response = get_stats('nonexistent')

        assert response['statusCode'] == 404

    def test_rejects_empty_code(self):
        """Should return 400 for empty code."""
        response = get_stats('')
        assert response['statusCode'] == 400
