"""Lambda handler for URL shortener API."""

import json
import os
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shortener import generate_short_code, validate_create_link_request

# Initialize DynamoDB client (not resource - we want low-level control)
dynamodb = boto3.client('dynamodb')

# Environment variables
TABLE_NAME = os.environ.get('TABLE_NAME')
BASE_URL = os.environ.get('BASE_URL', '')


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Main Lambda handler - routes requests to appropriate handlers.

    Routes:
    - POST /links -> create_link
    - GET /{code} -> get_redirect
    - GET /links/{code}/stats -> get_stats

    Args:
        event: API Gateway event
        context: Lambda context (unused)

    Returns:
        API Gateway response dict with statusCode, headers, body
    """
    try:
        http_method = event.get('httpMethod')
        path = event.get('path', '')
        path_params = event.get('pathParameters') or {}

        # Route to appropriate handler
        if http_method == 'POST' and path == '/links':
            return create_link(event)
        elif http_method == 'GET' and path.endswith('/stats'):
            # GET /links/{code}/stats
            code = path_params.get('code')
            return get_stats(code)
        elif http_method == 'GET' and 'code' in path_params:
            # GET /{code}
            code = path_params.get('code')
            return get_redirect(code)
        else:
            return error_response(404, 'Not Found')

    except Exception as e:
        # Log the error but don't expose internal details to client
        print(f"Unhandled error: {str(e)}")
        return error_response(500, 'Internal server error')


def create_link(event: dict) -> dict:
    """
    Create a new short link.

    POST /links
    Body: { "url": "https://example.com/long-url" }

    Returns:
        201 Created with { "short_code": "abc123", "short_url": "https://..." }
        400 Bad Request if validation fails
        500 Internal Server Error on DynamoDB errors
    """
    try:
        # Parse and validate request body
        body = json.loads(event.get('body', '{}'))
        is_valid, error_msg = validate_create_link_request(body)

        if not is_valid:
            return error_response(400, error_msg)

        original_url = body['url']

        # Generate short code with collision retry logic
        max_retries = 5
        for attempt in range(max_retries):
            short_code = generate_short_code()

            try:
                # Atomic write - only succeed if code doesn't exist
                dynamodb.put_item(
                    TableName=TABLE_NAME,
                    Item={
                        'short_code': {'S': short_code},
                        'original_url': {'S': original_url},
                        'created_at': {'S': datetime.utcnow().isoformat()},
                        'click_count': {'N': '0'}
                    },
                    ConditionExpression='attribute_not_exists(short_code)'
                )

                # Success - return the short link
                short_url = f"{BASE_URL}/{short_code}"
                return {
                    'statusCode': 201,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'short_code': short_code,
                        'short_url': short_url,
                        'original_url': original_url
                    })
                }

            except ClientError as e:
                # If ConditionalCheckFailedException, code already exists - retry
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    if attempt == max_retries - 1:
                        return error_response(500, 'Failed to generate unique short code')
                    continue  # Retry with new code
                else:
                    # Other DynamoDB error
                    print(f"DynamoDB error: {e}")
                    return error_response(500, 'Failed to create short link')

    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON in request body')
    except Exception as e:
        print(f"Error creating link: {str(e)}")
        return error_response(500, 'Internal server error')


def get_redirect(short_code: str) -> dict:
    """
    Look up short code and redirect to original URL.

    GET /{code}

    Atomically increments click_count before returning redirect.

    Returns:
        301 Moved Permanently with Location header
        404 Not Found if code doesn't exist
        500 Internal Server Error on DynamoDB errors
    """
    if not short_code:
        return error_response(400, 'Short code is required')

    try:
        # Atomic increment of click count
        response = dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={'short_code': {'S': short_code}},
            UpdateExpression='ADD click_count :inc',
            ExpressionAttributeValues={':inc': {'N': '1'}},
            ReturnValues='ALL_NEW'
        )

        # Check if item exists
        if 'Attributes' not in response:
            return error_response(404, 'Short link not found')

        # Extract original URL from response
        original_url = response['Attributes'].get('original_url', {}).get('S')

        if not original_url:
            return error_response(404, 'Short link not found')

        # Return 301 redirect
        return {
            'statusCode': 301,
            'headers': {
                'Location': original_url,
                'Access-Control-Allow-Origin': '*'
            },
            'body': ''
        }

    except ClientError as e:
        print(f"DynamoDB error: {e}")
        return error_response(500, 'Failed to retrieve link')
    except Exception as e:
        print(f"Error getting redirect: {str(e)}")
        return error_response(500, 'Internal server error')


def get_stats(short_code: str) -> dict:
    """
    Get statistics for a short link.

    GET /links/{code}/stats

    Returns:
        200 OK with { "short_code": "...", "click_count": 42, "created_at": "..." }
        404 Not Found if code doesn't exist
        500 Internal Server Error on DynamoDB errors
    """
    if not short_code:
        return error_response(400, 'Short code is required')

    try:
        # Get item from DynamoDB
        response = dynamodb.get_item(
            TableName=TABLE_NAME,
            Key={'short_code': {'S': short_code}}
        )

        # Check if item exists
        if 'Item' not in response:
            return error_response(404, 'Short link not found')

        item = response['Item']

        # Parse DynamoDB item format to simple dict
        stats = {
            'short_code': short_code,
            'original_url': item.get('original_url', {}).get('S', ''),
            'click_count': int(item.get('click_count', {}).get('N', 0)),
            'created_at': item.get('created_at', {}).get('S', '')
        }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(stats)
        }

    except ClientError as e:
        print(f"DynamoDB error: {e}")
        return error_response(500, 'Failed to retrieve stats')
    except Exception as e:
        print(f"Error getting stats: {str(e)}")
        return error_response(500, 'Internal server error')


def error_response(status_code: int, message: str) -> dict:
    """
    Create a standardized error response.

    Args:
        status_code: HTTP status code
        message: Error message to return to client

    Returns:
        API Gateway response dict
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({'error': message})
    }
