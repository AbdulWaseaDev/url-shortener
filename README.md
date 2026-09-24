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
                                           CloudWatch logs, alarms
                                               + X-Ray tracing
```

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
- **Scalability:** Fully serverless, auto-scales from 0 to millions of requests
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

**Deploying your own copy on a custom domain?**
- See [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md) for step-by-step instructions

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
KEY_ID=$(aws cloudformation describe-stacks --stack-name url-shortener-dev \
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

The alarms have no notification targets, so their state shows only in the CloudWatch console. To get emailed, add an SNS topic and set it as each alarm's `AlarmActions`. Lambda also has X-Ray tracing enabled.

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
5. **An issued ACM certificate** for your custom domain, in the same region as the stack. The template's `DomainName` and `CertificateArn` parameters default to this project's domain; override them to deploy your own copy (see [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md)):
   ```bash
   sam deploy --parameter-overrides Environment=dev \
     DomainName=go.yourdomain.com \
     CertificateArn=arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID
   ```
   After deploying, point a DNS-only CNAME for the domain at the custom domain's target (`aws apigateway get-domain-name --domain-name go.yourdomain.com --query regionalDomainName`).

### Deploy to AWS

```bash
# 1. Build the application
sam build

# 2. Deploy (first time - guided)
sam deploy --guided

# Follow prompts:
#   - Stack Name: url-shortener-dev
#   - AWS Region: us-east-1 (or your preferred region)
#   - Parameter Environment: dev
#   - Confirm changes: Y
#   - Allow SAM CLI IAM role creation: Y
#   - Disable rollback: N
#   - Save arguments to config: Y

# 3. Subsequent deploys (uses saved config)
sam deploy

# 4. Get API endpoint
sam list stack-outputs --stack-name url-shortener-dev
```

**Alternative: Deploy to production environment**
```bash
sam deploy --config-env prod
```

### What Gets Created

The deployment creates:
- 1 DynamoDB table (on-demand billing)
- 1 Lambda function (Python 3.13, 256MB memory)
- 1 API Gateway REST API (3 routes) with a regional custom domain
- 1 API key and usage plan (for `POST /links`)
- 4 CloudWatch alarms
- 1 CloudWatch Log Group (7-day retention)
- 1 IAM role (Lambda execution role with DynamoDB permissions)

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

Integration tests hit the **real deployed API**:

```bash
# Set API endpoint and key (see Security & Rate Limiting for getting the key)
export API_ENDPOINT=https://url-shortener.berlintechs.com
export API_KEY=YOUR_API_KEY
export RUN_INTEGRATION_TESTS=true

# Run integration tests
pytest tests/integration/ -v
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

The project includes **automated deployment** on every push to `main` branch.

### Workflow Behavior

On every push to `main`:
1. ✅ Checkout code
2. ✅ Set up Python 3.13
3. ✅ Install dependencies
4. ✅ Run unit tests (must pass)
5. ✅ Build with SAM
6. ✅ Deploy to AWS (creates/updates CloudFormation stack)
7. ✅ Read the stack's API key and run the integration tests against the deployed API
8. ✅ Print deployed API endpoint

**Deployment stops if unit tests fail, and the run fails if the deployed API doesn't pass the integration tests.**

### OIDC Authentication

GitHub Actions uses **OIDC** (OpenID Connect) for secure authentication to AWS without long-lived credentials. The workflow automatically assumes the IAM role configured in the repository secrets.

**Required Secret:**
- `AWS_ROLE_ARN`: ARN of the IAM role with deployment permissions

The role also needs `apigateway:GET` on the API key (`arn:aws:apigateway:us-east-1::/apikeys/*`) so the workflow can read the key for the integration tests.

For detailed OIDC setup instructions, see the CI/CD section in the original documentation.

---

## Cleanup

Delete all AWS resources:

```bash
sam delete --stack-name url-shortener-dev
```

This removes:
- Lambda function
- API Gateway, including the custom domain mapping, API key and usage plan
- DynamoDB table (⚠️ **deletes all data**)
- CloudWatch logs and alarms
- IAM role

The ACM certificate and the Cloudflare DNS records live outside the stack; delete them separately if you no longer need them.

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
│   └── integration/                        # Integration tests (real API, run in CI)
│       ├── __init__.py
│       └── test_api.py                     # End-to-end tests incl. API key checks
├── events/                                 # Sample API Gateway events for local testing
│   ├── create_link.json
│   ├── get_redirect.json
│   └── get_stats.json
├── .github/workflows/
│   └── deploy.yml                          # CI/CD: unit tests, deploy, integration tests
├── URL-Shortener.postman_collection.json   # Postman collection (base_url, api_key vars)
├── POSTMAN_GUIDE.md                        # Postman usage guide
├── CUSTOM_DOMAIN_SETUP.md                  # Custom domain setup guide
├── DEPLOYMENT.md                           # Deployment guide
├── template.yaml                           # SAM infra: API, domain, API key, alarms
├── samconfig.toml                          # SAM deployment configuration
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
sam logs --stack-name url-shortener-dev --tail
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

**Fix:** Export API endpoint before running tests:
```bash
export API_ENDPOINT=https://url-shortener.berlintechs.com
export API_KEY=YOUR_API_KEY
export RUN_INTEGRATION_TESTS=true
pytest tests/integration/
```

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
