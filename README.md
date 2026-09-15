# URL Shortener - Serverless REST API

A production-ready, serverless URL shortener built with AWS Lambda, API Gateway, and DynamoDB. Create short links, track click statistics, and redirect users—all with zero server management.

## What It Does

This application provides a REST API for:
- **Creating short links** from long URLs
- **Redirecting** users from short codes to original URLs
- **Tracking statistics** including click counts and creation timestamps

## API Contract

Base URL: `https://{api-id}.execute-api.{region}.amazonaws.com/Prod`

### 1. Create Short Link

**Endpoint:** `POST /links`

**Request:**
```bash
curl -X POST https://your-api.com/links \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com/very/long/url"}'
```

**Response:** `201 Created`
```json
{
  "short_code": "a3X9mK",
  "short_url": "https://your-api.com/a3X9mK",
  "original_url": "https://example.com/very/long/url"
}
```

**Validation:**
- URL must be valid HTTP/HTTPS format
- URL cannot be empty
- URL max length: 2048 characters

**Error Responses:**
- `400 Bad Request` - Invalid URL format or missing required fields
- `500 Internal Server Error` - Failed to create link (rare)

---

### 2. Redirect to Original URL

**Endpoint:** `GET /{code}`

**Request:**
```bash
curl -L https://your-api.com/a3X9mK
```

**Response:** `301 Moved Permanently`
```
Location: https://example.com/very/long/url
```

The redirect is permanent (301), and each access atomically increments the click counter.

**Error Responses:**
- `404 Not Found` - Short code does not exist

---

### 3. Get Link Statistics

**Endpoint:** `GET /links/{code}/stats`

**Request:**
```bash
curl https://your-api.com/links/a3X9mK/stats
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

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌──────────────┐
│   Client    │─────▶│ API Gateway  │─────▶│   Lambda    │─────▶│  DynamoDB    │
│ (Browser/   │◀─────│   (REST)     │◀─────│  (Python)   │◀─────│  (NoSQL)     │
│   curl)     │      └──────────────┘      └─────────────┘      └──────────────┘
└─────────────┘
```

**Flow:**

1. **Client** sends HTTP request to API Gateway
2. **API Gateway** validates request structure and routes to Lambda
3. **Lambda** (Python 3.12) executes business logic:
   - POST /links: Validates URL, generates 6-char short code, stores in DynamoDB
   - GET /{code}: Looks up code, atomically increments counter, returns 301 redirect
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
- **Scalability:** Fully serverless, auto-scales from 0 to millions of requests
- **Cost-efficiency:** On-demand billing for DynamoDB and Lambda (pay only for what you use)

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
3. **Python 3.12+** installed
4. **Docker** (for `sam build --use-container`)

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
- 1 Lambda function (Python 3.12, 256MB memory)
- 1 API Gateway REST API (3 routes)
- 2 CloudWatch Log Groups (7-day retention)
- 1 IAM role (Lambda execution role with DynamoDB permissions)

**Estimated monthly cost:** $0-5 for low traffic (first 1M Lambda requests free, first 25GB DynamoDB storage free)

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
# Set API endpoint (get from sam deploy output)
export API_ENDPOINT=https://abc123.execute-api.us-east-1.amazonaws.com/Prod
export RUN_INTEGRATION_TESTS=true

# Run integration tests
pytest tests/integration/ -v
```

### Local API Testing with SAM

Start API Gateway locally:

```bash
# Start local API
sam local start-api

# In another terminal, test endpoints
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

The project includes automated deployment on push to `main` via GitHub Actions.

### Setup OIDC Authentication (One-Time)

GitHub Actions uses **OIDC** (OpenID Connect) instead of long-lived access keys for security.

#### 1. Create IAM OIDC Identity Provider (AWS Console)

1. Go to **IAM → Identity Providers → Add Provider**
2. Provider Type: `OpenID Connect`
3. Provider URL: `https://token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. Click **Add Provider**

#### 2. Create IAM Role for GitHub Actions

1. Go to **IAM → Roles → Create Role**
2. Trusted Entity Type: `Web Identity`
3. Identity Provider: `token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. Click **Next**
6. Attach policies:
   - `AWSCloudFormationFullAccess`
   - `IAMFullAccess`
   - `AmazonS3FullAccess`
   - `AWSLambda_FullAccess`
   - `AmazonDynamoDBFullAccess`
   - `AmazonAPIGatewayAdministrator`
   - `CloudWatchLogsFullAccess`
7. Role name: `GitHubActionsDeployRole`
8. Click **Create Role**

#### 3. Edit Trust Policy

In the newly created role, go to **Trust Relationships → Edit Trust Policy**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::{YOUR_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:{YOUR_GITHUB_USERNAME}/url-shortener:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

**Replace:**
- `{YOUR_ACCOUNT_ID}` with your AWS account ID (12 digits)
- `{YOUR_GITHUB_USERNAME}` with your GitHub username

#### 4. Add GitHub Repository Secret

1. Go to your GitHub repository → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `AWS_ROLE_ARN`
4. Value: `arn:aws:iam::{YOUR_ACCOUNT_ID}:role/GitHubActionsDeployRole`
5. Click **Add secret**

### Workflow Behavior

On every push to `main`:
1. ✅ Checkout code
2. ✅ Set up Python 3.12
3. ✅ Install dependencies
4. ✅ Run unit tests (must pass)
5. ✅ Build with SAM
6. ✅ Deploy to AWS (creates/updates CloudFormation stack)
7. ✅ Print deployed API endpoint

**Deployment fails if tests fail** (safe deployment pattern).

---

## Cleanup

Delete all AWS resources:

```bash
sam delete --stack-name url-shortener-dev
```

This removes:
- Lambda function
- API Gateway
- DynamoDB table (⚠️ **deletes all data**)
- CloudWatch logs
- IAM role

---

## Project Structure

```
url-shortener/
├── url_shortener/              # Lambda function code
│   ├── app.py                  # Main handler (routes requests)
│   ├── shortener.py            # Core logic (validation, code generation)
│   └── requirements.txt        # Python dependencies (boto3)
├── tests/
│   ├── unit/                   # Unit tests (mocked, no AWS)
│   │   ├── test_shortener.py   # Test validation & code gen
│   │   └── test_handler.py     # Test Lambda handler logic
│   └── integration/            # Integration tests (real API)
│       └── test_api.py         # End-to-end API tests
├── events/                     # Sample API Gateway events for local testing
│   ├── create_link.json
│   ├── get_redirect.json
│   └── get_stats.json
├── .github/workflows/
│   └── deploy.yml              # CI/CD pipeline
├── template.yaml               # SAM/CloudFormation infrastructure
├── samconfig.toml              # SAM deployment configuration
├── pytest.ini                  # Pytest configuration
└── README.md                   # This file
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

### Unit tests fail with "ModuleNotFoundError"

**Fix:** Install Lambda dependencies:
```bash
pip install -r url_shortener/requirements.txt
```

### Integration tests skip with "API_ENDPOINT not set"

**Fix:** Export API endpoint before running tests:
```bash
export API_ENDPOINT=$(sam list stack-outputs --stack-name url-shortener-dev --output json | jq -r '.[] | select(.OutputKey=="ApiEndpoint") | .OutputValue')
export RUN_INTEGRATION_TESTS=true
pytest tests/integration/
```

---

## Technical Interview Talking Points

If asked to explain this project:

1. **Architecture:** "It's a serverless three-tier app: API Gateway handles HTTP, Lambda processes business logic in Python, DynamoDB stores data. Fully managed, auto-scaling, pay-per-use."

2. **DynamoDB Design:** "Short code is the partition key. I chose DynamoDB over RDS because (a) simple key-value access pattern, (b) millisecond latency at any scale, (c) no server management."

3. **Atomic Counter:** "Click count uses DynamoDB's `ADD` operation in `UpdateItem`—it's atomic, no race conditions even under high concurrency. Alternative would be read-modify-write with optimistic locking, but that's slower and more complex."

4. **Collision Handling:** "Short codes are random, so collisions are possible. I use `ConditionExpression: attribute_not_exists(short_code)` to atomically check-and-insert, then retry with a new code if it fails. 62^6 combinations means collisions are rare until millions of links."

5. **IAM Least Privilege:** "Lambda role has DynamoDBCrudPolicy scoped to only this table. If compromised, attacker can't access S3, other DynamoDB tables, or escalate privileges."

6. **Testing Strategy:** "Unit tests mock boto3 with Python's `unittest.mock`—fast, no AWS credentials needed. Integration tests hit real API and validate end-to-end flow. CI runs both before deploy."

7. **CI/CD Security:** "GitHub Actions uses OIDC, not long-lived access keys. Each deploy gets a temporary token scoped to this repo. Mitigates risk of leaked credentials."

8. **Observability:** "Lambda logs to CloudWatch, X-Ray tracing enabled for distributed debugging. API Gateway access logs capture HTTP metadata. 7-day retention balances cost and debuggability."

---

## License

MIT License - feel free to use this code for learning, interviews, or production projects.

---

## Credits

Built with:
- [AWS Lambda](https://aws.amazon.com/lambda/) - Serverless compute
- [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) - NoSQL database
- [AWS SAM](https://aws.amazon.com/serverless/sam/) - Infrastructure as Code
- [pytest](https://pytest.org/) - Testing framework
- [GitHub Actions](https://github.com/features/actions) - CI/CD
