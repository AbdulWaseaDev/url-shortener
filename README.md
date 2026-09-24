# URL Shortener - Serverless REST API

A production-ready, serverless URL shortener built with AWS Lambda, API Gateway, and DynamoDB. Create short links, track click statistics, and redirect users—all with zero server management.

## What It Does

This application provides a REST API for:
- **Creating short links** from long URLs
- **Redirecting** users from short codes to original URLs
- **Tracking statistics** including click counts and creation timestamps

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────┐      ┌──────────────┐
│   Client    │─────▶│   API Gateway    │─────▶│   Lambda    │─────▶│  DynamoDB    │
│ (Browser/   │◀─────│ (REST, custom    │◀─────│  (Python)   │◀─────│  (NoSQL)     │
│   curl)     │      │  domain + keys)  │      └─────────────┘      └──────────────┘
└─────────────┘      └──────────────────┘             │
                                                      ▼
                                   CloudWatch logs + X-Ray tracing
                                   CloudWatch alarms ──▶ SNS ──▶ Email
```

The same stack runs twice: **staging** (`url-shortener-staging.berlintechs.com`) and **production** (`url-shortener.berlintechs.com`), each with its own table, API key and alarms.

**Flow:**

1. **Client** sends HTTP request to `url-shortener.berlintechs.com` (Cloudflare DNS → API Gateway regional custom domain)
2. **API Gateway** checks the API key on `POST /links`, applies rate limits, and routes to Lambda
3. **Lambda** (Python 3.13) executes business logic:
   - POST /links: Validates URL, generates 6-char short code, stores in DynamoDB
   - GET /{code}: Looks up code, atomically increments counter, returns 302 redirect
   - GET /links/{code}/stats: Retrieves and returns link metadata
4. **DynamoDB** stores link mappings with structure:
   ```
   {
     "short_code": "a3X9mK",           // Partition key
     "original_url": "https://...",
     "click_count": 42,
     "created_at": "2024-01-15T10:30:00"
   }
   ```

**Key Design Choices:**

- **Short code generation:** Random 6-character alphanumeric codes (62^6 = ~56B combinations)
- **Collision handling:** Atomic `PutItem` with `ConditionExpression` ensures uniqueness; retries up to 5 times on collision
- **Click tracking:** Uses DynamoDB `UpdateExpression` with `ADD` for atomic counter increments (no race conditions)
- **Custom domain:** Served from `url-shortener.berlintechs.com` (API Gateway regional custom domain with an ACM certificate, DNS in Cloudflare), mapped at the root so short links have no `/Prod` stage prefix
- **Temporary redirects:** Returns `302 Found` rather than `301`, because browsers cache 301s permanently and would skip the Lambda (and the click counter) on repeat visits
- **No accidental writes on lookups:** The redirect's `UpdateItem` uses `attribute_exists(short_code)`, so unknown codes return 404 instead of upserting an empty item
- **Data protection:** The table has `DeletionPolicy: Retain`, `UpdateReplacePolicy: Retain`, deletion protection and point-in-time recovery, so links survive a deleted or replaced stack
- **Staging before production:** Every change is deployed to a separate staging stack and must pass integration tests there before it reaches production
- **Scalability:** Fully serverless and scales automatically. API Gateway throttling (50 req/s, 5 req/s for link creation) caps traffic and cost.
- **Cost-efficiency:** On-demand billing for DynamoDB and Lambda (pay only for what you use)

## Quick Start

**Live API:** `https://url-shortener.berlintechs.com`

**Create your first short link** (requires an API key, see [Security & Rate Limiting](#security--rate-limiting)):
```bash
curl -X POST https://url-shortener.berlintechs.com/links \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: YOUR_API_KEY' \
  -d '{"url": "https://github.com/AbdulWaseaDev/url-shortener"}'
```

Redirects and stats are public, so anyone can open a short link.

**Using Postman?**
- Import the ready-to-use collection: `URL-Shortener.postman_collection.json`
- See [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md) for detailed instructions

**Deploying your own copy?**
- [DEPLOYMENT.md](DEPLOYMENT.md) covers the full setup: staging and prod stacks, alerts and CI
- [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md) covers certificates and DNS for the custom domains

## API Contract

**Base URL:** `https://url-shortener.berlintechs.com`

### 1. Create Short Link

**Endpoint:** `POST /links` (requires `x-api-key` header)

**Request:**
```bash
curl -X POST https://url-shortener.berlintechs.com/links \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: YOUR_API_KEY' \
  -d '{"url": "https://example.com/very/long/url"}'
```

**Response:** `201 Created`
```json
{
  "short_code": "a3X9mK",
  "short_url": "https://url-shortener.berlintechs.com/a3X9mK",
  "original_url": "https://example.com/very/long/url"
}
```

**Validation:**
- URL must be valid HTTP/HTTPS format
- URL cannot be empty
- URL max length: 2048 characters

**Error Responses:**
- `400 Bad Request` - Invalid URL format or missing required fields
- `403 Forbidden` - Missing or invalid API key
- `429 Too Many Requests` - Rate limit or daily quota exceeded
- `500 Internal Server Error` - Failed to create link (rare)

---

### 2. Redirect to Original URL

**Endpoint:** `GET /{code}`

**Request:**
```bash
curl -L https://url-shortener.berlintechs.com/a3X9mK
```

**Response:** `302 Found`
```
Location: https://example.com/very/long/url
```

The redirect is temporary (302) so browsers don't cache it, which means every visit reaches the API and atomically increments the click counter.

**Error Responses:**
- `404 Not Found` - Short code does not exist

---

### 3. Get Link Statistics

**Endpoint:** `GET /links/{code}/stats`

**Request:**
```bash
curl https://url-shortener.berlintechs.com/links/a3X9mK/stats
```

**Response:** `200 OK`
```json
{
  "short_code": "a3X9mK",
  "original_url": "https://example.com/very/long/url",
  "click_count": 42,
  "created_at": "2024-01-15T10:30:00.123456"
}
```

**Error Responses:**
- `404 Not Found` - Short code does not exist

---

## Security & Rate Limiting

| Route | Access | Limits |
|---|---|---|
| `POST /links` | API key (`x-api-key` header) | 5 req/s, burst 10, 1,000 links/day per key |
| `GET /{code}` | Public | 50 req/s, burst 100 (stage-wide) |
| `GET /links/{code}/stats` | Public | 50 req/s, burst 100 (stage-wide) |

Link creation is keyed so strangers can't fill the table, run up the bill, or use the domain to disguise phishing links. The API key, usage plan and throttles are all defined in `template.yaml`.

**Get the API key** (after deploying):
```bash
KEY_ID=$(aws cloudformation describe-stacks --stack-name url-shortener-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiKeyId`].OutputValue' --output text)
aws apigateway get-api-key --api-key "$KEY_ID" --include-value --query value --output text
```

---

## Monitoring

CloudWatch alarms are defined in the template:

| Alarm | Fires when |
|---|---|
| `url-shortener-<env>-api-5xx` | 5+ API 5xx responses in 5 minutes |
| `url-shortener-<env>-lambda-errors` | Any Lambda invocation error in 5 minutes |
| `url-shortener-<env>-lambda-throttles` | Any Lambda throttling in 5 minutes |
| `url-shortener-<env>-lambda-latency` | p99 duration above 3 seconds for 15 minutes |

Each alarm notifies an SNS topic (`url-shortener-<env>-alerts`) when it fires and again when it recovers, and the topic emails the address stored in SSM Parameter Store at `/url-shortener/alert-email`. Keeping the address in SSM keeps it out of the repo. AWS sends a confirmation email the first time a stack is deployed; alerts only arrive after you click it.

Set or change the address:
```bash
aws ssm put-parameter --name /url-shortener/alert-email --type String \
  --value you@example.com --overwrite
```

Lambda also has X-Ray tracing enabled.

---

## IAM Permissions

The Lambda function has **least-privilege** access via the `DynamoDBCrudPolicy`:

```yaml
Policies:
  - DynamoDBCrudPolicy:
      TableName: !Ref LinksTable
```

This grants only:
- `dynamodb:GetItem` - Read link data for redirects and stats
- `dynamodb:PutItem` - Create new short links
- `dynamodb:UpdateItem` - Atomically increment click counter
- `dynamodb:DeleteItem` - (Not used, but included in policy)

The policy is scoped to **only** the specific DynamoDB table created by this stack—no other tables or AWS resources are accessible.

**Why least privilege matters:** If the Lambda function were compromised, the attacker could only interact with this single table, not your entire AWS account.

---

## Deployment

### Prerequisites

1. **AWS CLI** configured with credentials ([setup guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html))
2. **SAM CLI** installed ([installation guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
3. **Python 3.13+** installed
4. **Docker** (for `sam build --use-container`)
5. **An alert email in SSM** at `/url-shortener/alert-email` (see [Monitoring](#monitoring)). The deploy fails if it's missing.
6. **An issued ACM certificate** for each environment's domain, in the same region as the stack (see [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md)). Domains and certificate ARNs are set per environment in `samconfig.toml`. Leave `DomainName` empty to deploy without a custom domain. After deploying, point a DNS-only CNAME at the stack's `CustomDomainTarget` output.

### Environments

| Environment | Stack | URL | Deployed by |
|---|---|---|---|
| Staging | `url-shortener-staging` | `https://url-shortener-staging.berlintechs.com` | CI on every push to `main`; integration tests run here |
| Production | `url-shortener-prod` | `https://url-shortener.berlintechs.com` | CI, only after staging passes |

Each environment has its own table, API key, alarms and alert topic.

### Deploy to AWS

Normally CI deploys (see [CI/CD](#cicd-with-github-actions)). To deploy by hand:

```bash
# 1. Build the application
sam build

# 2. Deploy to staging (the default config) and review the changeset
sam deploy

# 3. Deploy to production
sam deploy --config-env prod

# 4. Show stack outputs (BaseUrl, ApiKeyId, CustomDomainTarget, ...)
sam list stack-outputs --stack-name url-shortener-prod
```

### What Gets Created

The deployment creates:
- 1 DynamoDB table (on-demand billing, retained and deletion-protected)
- 1 Lambda function (Python 3.13, 256MB memory)
- 1 API Gateway REST API (3 routes) with a regional custom domain
- 1 API key and usage plan (for `POST /links`)
- 4 CloudWatch alarms and an SNS alert topic with an email subscription
- 1 CloudWatch Log Group (7-day retention)
- 1 IAM role (Lambda execution role with DynamoDB permissions)

This is per environment (staging and production).

**Estimated monthly cost:** $0-5 for low traffic (first 1M Lambda requests free, first 25GB DynamoDB storage free)

---

## Using the API with Postman

### Import Collection (Recommended)

1. Open Postman
2. Click **Import** → **File** tab
3. Select `URL-Shortener.postman_collection.json` from this repository
4. All 3 endpoints will be pre-configured and ready to test!

### Manual Testing

See [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md) for:
- Detailed endpoint descriptions
- Request/response examples
- Testing workflow
- Tips for using environment variables
- Sample Postman tests

---

## Local Development & Testing

### Run Unit Tests

Unit tests use mocked boto3 calls and run **without AWS credentials**:

```bash
# Install test dependencies
pip install pytest boto3 requests

# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_shortener.py -v

# Run with coverage
pytest tests/unit/ --cov=url_shortener --cov-report=term-missing
```

### Run Integration Tests

Integration tests create real links, so run them against **staging**. With `TABLE_NAME` set, they delete the links they created when they finish:

```bash
export API_ENDPOINT=https://url-shortener-staging.berlintechs.com
export API_KEY=YOUR_STAGING_API_KEY   # from the url-shortener-staging stack
export TABLE_NAME=url-shortener-links-staging
export RUN_INTEGRATION_TESTS=true

pytest tests/integration/ -v
```

### Run Smoke Tests

Read-only checks that are safe against production (no links are created):

```bash
export SMOKE_API_ENDPOINT=https://url-shortener.berlintechs.com
pytest tests/smoke/ -v
```

### Local API Testing with SAM

Start API Gateway locally:

```bash
# Start local API
sam local start-api

# In another terminal, test endpoints (SAM local does not enforce API keys)
curl -X POST http://127.0.0.1:3000/links \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'
```

**Note:** Local testing requires Docker and AWS credentials (to access real DynamoDB).

### Invoke Lambda Directly

```bash
# Test POST /links
sam local invoke UrlShortenerFunction -e events/create_link.json

# Test GET /{code} (requires existing short code)
sam local invoke UrlShortenerFunction -e events/get_redirect.json

# Test GET /links/{code}/stats
sam local invoke UrlShortenerFunction -e events/get_stats.json
```

---

## CI/CD with GitHub Actions

Every push to `main` runs a three-stage pipeline:

```
Unit tests + build ──▶ Deploy staging ──▶ Integration tests ──▶ Deploy production ──▶ Smoke tests
                       (staging stack)    (staging, cleaned up)  (prod stack)          (read-only)
```

1. **Build:** run unit tests, then `sam build`. The build artifact is reused by both deploys, so production gets exactly what staging tested.
2. **Staging:** deploy `url-shortener-staging`, read its API key, and run the integration tests. Test links are deleted afterwards.
3. **Production:** runs only if staging passed. Deploys `url-shortener-prod`, then runs read-only smoke tests against `url-shortener.berlintechs.com`.

A failure at any stage stops the pipeline, so a change that breaks staging never reaches production. CloudFormation rolls back a deploy that fails partway through. Deploys never run concurrently.

### OIDC Authentication

GitHub Actions uses **OIDC** (OpenID Connect) for secure authentication to AWS without long-lived credentials. The workflow automatically assumes the IAM role configured in the repository secrets.

**Required Secret:**
- `AWS_ROLE_ARN`: ARN of the IAM role with deployment permissions

Besides CloudFormation, Lambda, API Gateway, DynamoDB, IAM, S3 and CloudWatch Logs, the role needs:
- `sns:*Topic*`, `sns:Subscribe`/`Unsubscribe` on `url-shortener-*` topics (alert topics)
- `cloudwatch:PutMetricAlarm`/`DeleteAlarms`/`DescribeAlarms` on `url-shortener-*` alarms
- `ssm:GetParameter(s)` on `/url-shortener/*` (alert email)
- `apigateway:GET` on API keys (to read the staging key for integration tests)

For detailed OIDC setup instructions, see the CI/CD section in the original documentation.

---

## Cleanup

Delete all AWS resources:

```bash
sam delete --stack-name url-shortener-staging
sam delete --stack-name url-shortener-prod
```

This removes:
- Lambda function
- API Gateway, including the custom domain, API key and usage plan
- CloudWatch logs, alarms and the SNS alert topic
- IAM role

The **DynamoDB table is kept** (it's retained and deletion-protected). To delete it too, turn protection off first:
```bash
aws dynamodb update-table --table-name url-shortener-links-prod --no-deletion-protection-enabled
aws dynamodb delete-table --table-name url-shortener-links-prod
```

The ACM certificates, the SSM alert-email parameter and the Cloudflare DNS records live outside the stacks; delete them separately if you no longer need them.

---

## Project Structure

```
url-shortener/
├── url_shortener/                          # Lambda function code
│   ├── __init__.py
│   ├── app.py                              # Handler: routing, redirects, stats, short URL building
│   ├── shortener.py                        # Core logic (validation, code generation)
│   └── requirements.txt                    # Python dependencies (boto3)
├── tests/
│   ├── __init__.py
│   ├── unit/                               # Unit tests (mocked, no AWS)
│   │   ├── __init__.py
│   │   ├── test_shortener.py               # Test validation & code gen
│   │   └── test_handler.py                 # Test handler logic, 404s, short URLs
│   ├── integration/                        # Integration tests (staging, run in CI)
│   │   ├── __init__.py
│   │   └── test_api.py                     # End-to-end tests, cleans up test links
│   └── smoke/                              # Read-only production checks (run in CI)
│       ├── __init__.py
│       └── test_smoke.py                   # 404s and API key enforcement
├── events/                                 # Sample API Gateway events for local testing
│   ├── create_link.json
│   ├── get_redirect.json
│   └── get_stats.json
├── .github/workflows/
│   └── deploy.yml                          # CI/CD: build, staging + tests, prod + smoke
├── URL-Shortener.postman_collection.json   # Postman collection (base_url, api_key vars)
├── POSTMAN_GUIDE.md                        # Postman usage guide
├── CUSTOM_DOMAIN_SETUP.md                  # Certificates, CAA and DNS for custom domains
├── DEPLOYMENT.md                           # Full setup: stacks, alerts, CI role, cleanup
├── template.yaml                           # SAM infra: API, domain, API key, alarms, alerts
├── samconfig.toml                          # Staging and prod deploy configuration
├── pytest.ini                              # Pytest configuration
├── .gitignore                              # Git ignore rules
└── README.md                               # This file
```

---

## Troubleshooting

### Deployment fails with "Unable to upload artifact"

**Cause:** SAM couldn't create S3 bucket for deployment artifacts.

**Fix:**
```bash
sam deploy --guided --resolve-s3
```

### Lambda returns 500 errors

**Check logs:**
```bash
sam logs --stack-name url-shortener-prod --tail
```

**Common issues:**
- Missing `TABLE_NAME` environment variable
- DynamoDB table doesn't exist (check `sam deploy` completed)
- Lambda doesn't have IAM permissions (check execution role)

### Creating a link returns 403 Forbidden

The `x-api-key` header is missing or wrong. Get the current key with the commands under [Security & Rate Limiting](#security--rate-limiting).

### Requests return 429 Too Many Requests

A rate limit or the 1,000/day link quota was hit. The quota resets daily; the limits are set in `template.yaml` under `Globals.Api`.

### Unit tests fail with "ModuleNotFoundError"

**Fix:** Install Lambda dependencies:
```bash
pip install -r url_shortener/requirements.txt
```

### Integration tests skip with "API_ENDPOINT not set"

**Fix:** Export the staging endpoint and key before running tests (see [Run Integration Tests](#run-integration-tests)).

### Deploy fails with "Parameter /url-shortener/alert-email not found"

**Fix:** Store the alert email in SSM (see [Monitoring](#monitoring)), then deploy again.

### Not receiving alert emails

Check your inbox (and spam) for "AWS Notification - Subscription Confirmation" and click the link. Each stack's topic needs its own confirmation.

---

## Author

**Abdul Wasea** · [GitHub @AbdulWaseaDev](https://github.com/AbdulWaseaDev)

---

## License

MIT License

---

## Credits

Built with:
- [AWS Lambda](https://aws.amazon.com/lambda/) - Serverless compute
- [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) - NoSQL database
- [AWS SAM](https://aws.amazon.com/serverless/sam/) - Infrastructure as Code
- [pytest](https://pytest.org/) - Testing framework
- [GitHub Actions](https://github.com/features/actions) - CI/CD
