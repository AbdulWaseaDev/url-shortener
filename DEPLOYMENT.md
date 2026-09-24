# URL Shortener - Complete Deployment Guide

This guide walks you through deploying the URL shortener to AWS from scratch.

## Prerequisites Check

Before starting, verify you have:

```bash
# Check AWS CLI
aws --version
# Should show: aws-cli/2.x.x or higher

# Check AWS credentials are configured
aws sts get-caller-identity
# Should show your AWS account ID and user ARN

# Check SAM CLI
sam --version
# Should show: SAM CLI, version 1.x.x or higher

# Check Python
python --version
# Should show: Python 3.12.x or higher

# Check Docker (required for sam build --use-container)
docker --version
# Should show: Docker version 20.x.x or higher
```

If any command fails, install the missing tool first.

---

## Step 1: Deploy to AWS (First Time)

Navigate to the project directory:

```bash
cd C:/git-repos/url-shortener
```

### 1.1 Build the Application

```bash
sam build
```

**What this does:**
- Downloads Python dependencies (boto3)
- Packages Lambda function code
- Validates template.yaml syntax

**Expected output:**
```
Build Succeeded

Built Artifacts  : .aws-sam/build
Built Template   : .aws-sam/build/template.yaml
```

### 1.2 Deploy with Guided Setup

```bash
sam deploy --guided
```

**You'll be prompted for:**

1. **Stack Name:** `url-shortener-staging` (recommended)
2. **AWS Region:** `us-east-1` (or your preferred region)
3. **Parameter Environment:** `staging`
4. **Confirm changes before deploy:** `Y`
5. **Allow SAM CLI IAM role creation:** `Y`
6. **Disable rollback:** `N`
7. **UrlShortenerFunction may not have authorization defined, Is this okay?** `Y`
8. **Save arguments to configuration file:** `Y`
9. **SAM configuration file:** `samconfig.toml` (default)
10. **SAM configuration environment:** `default`

**Deployment takes ~2-3 minutes.** You'll see:
- Creating CloudFormation stack
- Creating DynamoDB table
- Creating Lambda function
- Creating API Gateway
- Creating IAM roles and log groups

**Expected output:**
```
Successfully created/updated stack - url-shortener-prod in us-east-1

CloudFormation outputs from deployed stack
-----------------------------------------------------------
Outputs
-----------------------------------------------------------
Key                 ApiEndpoint
Description         API Gateway endpoint URL for URL shortener
Value               https://abc123xyz.execute-api.us-east-1.amazonaws.com/Prod

Key                 TableName
Description         DynamoDB table storing link mappings
Value               url-shortener-links-dev

Key                 FunctionArn
Description         Lambda function ARN
Value               arn:aws:lambda:us-east-1:123456789012:function:url-shortener-api-dev
-----------------------------------------------------------
```

**🎉 Your API is now live!** Copy the `ApiEndpoint` value.

---

## Step 2: Test the Deployed API

### 2.1 Create a Short Link

```bash
# Replace with your actual API endpoint
export API_ENDPOINT="https://abc123xyz.execute-api.us-east-1.amazonaws.com/Prod"

# Create a short link
curl -X POST $API_ENDPOINT/links \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.github.com/AbdulWaseaDev"}'
```

**Expected response:**
```json
{
  "short_code": "a3X9mK",
  "short_url": "https://abc123xyz.execute-api.us-east-1.amazonaws.com/Prod/a3X9mK",
  "original_url": "https://www.github.com/AbdulWaseaDev"
}
```

### 2.2 Test the Redirect

```bash
# Use the short_code from previous response
curl -L $API_ENDPOINT/a3X9mK
```

You should be redirected to the original URL.

### 2.3 Check Statistics

```bash
curl $API_ENDPOINT/links/a3X9mK/stats
```

**Expected response:**
```json
{
  "short_code": "a3X9mK",
  "original_url": "https://www.github.com/AbdulWaseaDev",
  "click_count": 1,
  "created_at": "2024-01-15T10:30:00.123456"
}
```

---

## Step 3: Run Tests Locally

### 3.1 Install Test Dependencies

```bash
pip install pytest boto3 requests
```

### 3.2 Run Unit Tests

```bash
# Unit tests don't require AWS credentials
pytest tests/unit/ -v
```

**Expected output:**
```
tests/unit/test_shortener.py::TestGenerateShortCode::test_default_length PASSED
tests/unit/test_shortener.py::TestGenerateShortCode::test_alphanumeric_only PASSED
tests/unit/test_shortener.py::TestIsValidUrl::test_valid_http_url PASSED
...
======================== 15 passed in 0.45s ========================
```

### 3.3 Run Integration Tests (Optional)

```bash
# Set environment variables
export API_ENDPOINT="https://abc123xyz.execute-api.us-east-1.amazonaws.com/Prod"
export RUN_INTEGRATION_TESTS=true

# Run integration tests
pytest tests/integration/ -v
```

These tests create real links in your deployed API and verify the complete flow.

---

## Step 4: Set Up GitHub Actions CI/CD (Optional)

If you want automatic deployment on push to GitHub:

### 4.1 Create IAM OIDC Provider

**In AWS Console:**

1. Go to **IAM → Identity Providers → Add Provider**
2. Provider Type: `OpenID Connect`
3. Provider URL: `https://token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. Click **Add Provider**

### 4.2 Create IAM Role

1. Go to **IAM → Roles → Create Role**
2. Trusted Entity Type: `Web Identity`
3. Identity Provider: `token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. Attach policies:
   - `AWSCloudFormationFullAccess`
   - `IAMFullAccess`
   - `AmazonS3FullAccess`
   - `AWSLambda_FullAccess`
   - `AmazonDynamoDBFullAccess`
   - `AmazonAPIGatewayAdministrator`
   - `CloudWatchLogsFullAccess`
6. Role name: `GitHubActionsDeployRole`
7. Click **Create Role**

### 4.3 Update Trust Policy

Click on the role → **Trust Relationships → Edit Trust Policy**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/url-shortener:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

Replace:
- `YOUR_ACCOUNT_ID` - Your 12-digit AWS account ID
- `YOUR_GITHUB_USERNAME` - Your GitHub username

### 4.4 Add GitHub Secret

1. Push code to GitHub:
   ```bash
   cd C:/git-repos/url-shortener
   git init
   git add .
   git commit -m "Initial commit: URL shortener serverless app"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/url-shortener.git
   git push -u origin main
   ```

2. In GitHub repo → **Settings → Secrets and variables → Actions**
3. Click **New repository secret**
4. Name: `AWS_ROLE_ARN`
5. Value: `arn:aws:iam::YOUR_ACCOUNT_ID:role/GitHubActionsDeployRole`
6. Click **Add secret**

### 4.5 Test GitHub Actions

Push to main branch - the workflow will automatically:
1. Run unit tests
2. Build with SAM
3. Deploy to AWS

Check **Actions** tab in GitHub to see the workflow run.

---

## Step 5: Subsequent Deployments

After the first deployment, you can deploy changes quickly:

```bash
# Make code changes...

# Build
sam build

# Deploy (uses saved config from samconfig.toml)
sam deploy
```

---

## Monitoring & Debugging

### View Lambda Logs

```bash
# Tail logs in real-time
sam logs --stack-name url-shortener-prod --tail

# View recent logs
sam logs --stack-name url-shortener-prod --start-time '10min ago'
```

### View CloudFormation Stack

```bash
# List all stack outputs
sam list stack-outputs --stack-name url-shortener-prod

# View stack events
aws cloudformation describe-stack-events --stack-name url-shortener-prod
```

### View DynamoDB Table

```bash
# Get table name
TABLE_NAME=$(aws cloudformation describe-stacks \
  --stack-name url-shortener-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`TableName`].OutputValue' \
  --output text)

# Scan table (shows all items)
aws dynamodb scan --table-name $TABLE_NAME

# Get specific item
aws dynamodb get-item \
  --table-name $TABLE_NAME \
  --key '{"short_code": {"S": "a3X9mK"}}'
```

---

## Cleanup

To delete all AWS resources:

```bash
sam delete --stack-name url-shortener-prod
```

**⚠️ This deletes:**
- Lambda function
- API Gateway
- DynamoDB table (all data is lost!)
- CloudWatch logs
- IAM role

Confirm with `y` when prompted.

---

## Cost Estimate

For **low traffic** (< 1,000 requests/day):

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | First 1M requests free | $0.00 |
| DynamoDB | First 25GB storage free | $0.00 |
| API Gateway | First 1M calls free (12 months) | $0.00 |
| CloudWatch Logs | 5GB free | $0.00 |
| **Total** | | **~$0-2/month** |

For **moderate traffic** (10,000 requests/day):

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 300,000 requests/month | ~$0.06 |
| DynamoDB | On-demand, ~1M reads/writes | ~$1.25 |
| API Gateway | 300,000 calls | ~$1.05 |
| CloudWatch Logs | 1GB/month | ~$0.50 |
| **Total** | | **~$3/month** |

---

## Troubleshooting

### "Unable to upload artifact"

**Solution:** SAM couldn't create S3 bucket. Use:
```bash
sam deploy --guided --resolve-s3
```

### "AccessDeniedException"

**Solution:** AWS credentials don't have sufficient permissions. Verify:
```bash
aws sts get-caller-identity
```

Ensure your IAM user/role has CloudFormation, Lambda, DynamoDB, and API Gateway permissions.

### "CREATE_FAILED" during deployment

**Check error:**
```bash
aws cloudformation describe-stack-events --stack-name url-shortener-prod
```

Common issues:
- DynamoDB table name already exists (delete old stack first)
- Region quota limits reached

### Unit tests fail

**Solution:** Install dependencies:
```bash
pip install -r url_shortener/requirements.txt
pip install pytest
```

---

## What You've Built

✅ **Fully serverless URL shortener**
✅ **Production-ready with error handling**
✅ **Comprehensive test suite (unit + integration)**
✅ **CI/CD pipeline with GitHub Actions**
✅ **Infrastructure as Code (SAM/CloudFormation)**
✅ **Least-privilege IAM permissions**
✅ **Atomic click counter (no race conditions)**
✅ **Observability (CloudWatch Logs + X-Ray)**

**You can now:**
- Use this in production
- Showcase it in interviews
- Extend it with custom domains, rate limiting, analytics, etc.

**Next Steps:**
- Add custom domain with Route 53 + ACM
- Implement TTL (Time-To-Live) for auto-expiring links
- Add Redis caching for hot links
- Build a frontend UI
- Add authentication with API keys
- Implement rate limiting with API Gateway usage plans

---

**Questions?** Check the main README.md or AWS documentation.
