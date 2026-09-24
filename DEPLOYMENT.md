# URL Shortener - Deployment Guide

How to deploy your own copy of the URL shortener from scratch: a **staging** and a **production** stack, each on its own custom domain, with email alerts and a GitHub Actions pipeline that tests on staging before promoting to production.

Examples use this project's names (`berlintechs.com`, `us-east-1`). Replace them with your own.

---

## 1. Prerequisites

```bash
aws --version              # AWS CLI v2
aws sts get-caller-identity  # credentials configured
sam --version              # SAM CLI
python --version           # Python 3.13+
docker --version           # for sam build --use-container (CI uses it)
```

You also need a domain whose DNS you control (this project uses Cloudflare).

---

## 2. One-time setup

### 2.1 Alert email

Alarm notifications go to an address stored in SSM Parameter Store, so it never appears in the repo. The deploy fails if this parameter is missing.

```bash
aws ssm put-parameter --name /url-shortener/alert-email --type String \
  --value you@example.com --region us-east-1
```

> **Git Bash on Windows:** prefix the command with `MSYS_NO_PATHCONV=1`, otherwise the `/url-shortener/...` name is rewritten into a Windows path.

### 2.2 Certificates for both domains

Request one certificate per environment (see [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md) for the DNS records, including the CAA record many domains need):

```bash
aws acm request-certificate --domain-name url-shortener-staging.yourdomain.com \
  --validation-method DNS --region us-east-1
aws acm request-certificate --domain-name url-shortener.yourdomain.com \
  --validation-method DNS --region us-east-1
```

Wait until both show `ISSUED`:
```bash
aws acm list-certificates --region us-east-1 \
  --query 'CertificateSummaryList[].[DomainName,Status]' --output table
```

### 2.3 Point samconfig.toml at your domains

In `samconfig.toml`, set `DomainName` and `CertificateArn` in the `[default]`/`[staging]` and `[prod]` sections to your domains and the certificate ARNs from 2.2. Set `DomainName=""` to deploy an environment without a custom domain.

---

## 3. Deploy

```bash
# Build once
sam build

# Staging (default config) - review the changeset, then confirm
sam deploy

# Production
sam deploy --config-env prod
```

Each stack creates:

| Resource | Notes |
|---|---|
| DynamoDB table `url-shortener-links-<env>` | On-demand, point-in-time recovery, **retained and deletion-protected** |
| Lambda `url-shortener-api-<env>` | Python 3.13, X-Ray tracing, logs kept 30 days in prod and 7 in staging |
| API Gateway REST API | 3 routes, stage throttling, X-Ray tracing, API key + usage plan on `POST /links` |
| Custom domain + base path mapping | Only when `DomainName` is set |
| 4 CloudWatch alarms | 5xx, errors, throttles, p99 latency |
| SNS topic `url-shortener-<env>-alerts` | Emails the SSM alert address |

### 3.1 After the first deploy of each stack

1. **DNS:** create a CNAME for the domain pointing at the stack's `CustomDomainTarget` output, **DNS only** (not proxied):
   ```bash
   sam list stack-outputs --stack-name url-shortener-prod
   ```
2. **Alerts:** click the link in the "AWS Notification - Subscription Confirmation" email. Alerts only arrive after confirming.
3. **API key:** read the key for creating links:
   ```bash
   KEY_ID=$(aws cloudformation describe-stacks --stack-name url-shortener-prod \
     --query 'Stacks[0].Outputs[?OutputKey==`ApiKeyId`].OutputValue' --output text)
   aws apigateway get-api-key --api-key "$KEY_ID" --include-value --query value --output text
   ```
   A brand-new key can return `403` for about a minute while API Gateway propagates it.

### 3.2 Test it

```bash
BASE=https://url-shortener.yourdomain.com
KEY=your-api-key

curl -X POST $BASE/links -H 'Content-Type: application/json' -H "x-api-key: $KEY" \
  -d '{"url": "https://github.com/AbdulWaseaDev"}'
# {"short_code": "a3X9mK", "short_url": "https://url-shortener.yourdomain.com/a3X9mK", ...}

curl -i $BASE/a3X9mK                 # 302 with Location header
curl $BASE/links/a3X9mK/stats        # click_count: 1
```

---

## 4. CI/CD with GitHub Actions

The workflow (`.github/workflows/deploy.yml`) runs on every push to `main`:

1. **Build** - unit tests, `sam build`, upload the build artifact
2. **Staging** - deploy `url-shortener-staging`, run integration tests (test links are deleted afterwards)
3. **Production** - only if staging passed: deploy `url-shortener-prod`, run read-only smoke tests

### 4.1 OIDC provider and role

1. **IAM → Identity providers → Add provider**: OpenID Connect, URL `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.
2. **IAM → Roles → Create role** (Web identity, the provider above), named `GitHubActionsDeployRole`, with these managed policies:
   - `AWSCloudFormationFullAccess`, `IAMFullAccess`, `AmazonS3FullAccess`
   - `AWSLambda_FullAccess`, `AmazonDynamoDBFullAccess`, `AmazonAPIGatewayAdministrator`, `CloudWatchLogsFullAccess`
3. Add an inline policy for alerts, alarms and the alert-email parameter (replace `ACCOUNT_ID`):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": ["sns:CreateTopic", "sns:DeleteTopic", "sns:GetTopicAttributes", "sns:SetTopicAttributes", "sns:Subscribe", "sns:Unsubscribe", "sns:GetSubscriptionAttributes", "sns:ListSubscriptionsByTopic", "sns:TagResource", "sns:UntagResource", "sns:ListTagsForResource"],
         "Resource": "arn:aws:sns:us-east-1:ACCOUNT_ID:url-shortener-*" },
       { "Effect": "Allow", "Action": ["sns:Unsubscribe", "sns:GetSubscriptionAttributes", "cloudwatch:DescribeAlarms"], "Resource": "*" },
       { "Effect": "Allow", "Action": ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource", "cloudwatch:UntagResource", "cloudwatch:ListTagsForResource"],
         "Resource": "arn:aws:cloudwatch:us-east-1:ACCOUNT_ID:alarm:url-shortener-*" },
       { "Effect": "Allow", "Action": ["ssm:GetParameter", "ssm:GetParameters"],
         "Resource": "arn:aws:ssm:us-east-1:ACCOUNT_ID:parameter/url-shortener/*" }
     ]
   }
   ```
4. **Trust policy:** the pipeline's jobs run in the `staging` and `production` GitHub environments, so the subject must allow more than the `main` branch. Use a wildcard for the repo:
   ```json
   "Condition": {
     "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
     "StringLike": { "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/url-shortener:*" }
   }
   ```

### 4.2 GitHub secret

Repo → **Settings → Secrets and variables → Actions → New repository secret**:
- `AWS_ROLE_ARN` = `arn:aws:iam::ACCOUNT_ID:role/GitHubActionsDeployRole`

Push to `main` and watch the **Actions** tab. If staging fails, production is skipped.

---

## 5. Day-to-day

- **Ship a change:** push to `main`. CI handles staging, tests and production.
- **Deploy by hand:** `sam build && sam deploy` (staging), then `sam deploy --config-env prod`.
- **Logs:** `sam logs --stack-name url-shortener-prod --tail`
- **Stack events:** `aws cloudformation describe-stack-events --stack-name url-shortener-prod`
- **Look at a link:**
  ```bash
  aws dynamodb get-item --table-name url-shortener-links-prod \
    --key '{"short_code": {"S": "a3X9mK"}}'
  ```

---

## 6. Cleanup

```bash
sam delete --stack-name url-shortener-staging
sam delete --stack-name url-shortener-prod
```

The **tables are kept** (retained and deletion-protected). To delete one:
```bash
aws dynamodb update-table --table-name url-shortener-links-prod --no-deletion-protection-enabled
aws dynamodb delete-table --table-name url-shortener-links-prod
```

Also remove, if no longer needed: the ACM certificates, the `/url-shortener/alert-email` parameter, and the DNS records.

---

## 7. Cost

Per environment, at low traffic, this is roughly **$0/month**:

| Service | Free allowance |
|---|---|
| Lambda | 1M requests/month (always free) |
| DynamoDB on-demand | 25 GB storage; requests cost fractions of a cent at this volume |
| API Gateway | 1M requests/month for the first 12 months, then $3.50 per million |
| CloudWatch alarms | 10 alarms free (4 per stack), then $0.10/alarm/month |
| SNS email | 1,000 emails/month |
| ACM certificates, custom domains, SSM standard parameters | Free |

---

## 8. Troubleshooting

### Certificate status `FAILED` with `CAA_ERROR`
Your domain has CAA records that don't allow Amazon. Add a CAA record for the subdomain (`0 issue "amazon.com"`), delete the failed certificate and request a new one. See [CUSTOM_DOMAIN_SETUP.md](CUSTOM_DOMAIN_SETUP.md).

### Deploy fails: "Parameter /url-shortener/alert-email not found"
Create the parameter (step 2.1).

### `POST /links` returns 403 right after a deploy
A new API key takes about a minute to become active. If it persists, check you're using the key for the right stack.

### "Unable to upload artifact"
```bash
sam deploy --resolve-s3
```

### `--parameter-overrides` with empty values on PowerShell
PowerShell mangles quotes, so `DomainName=""` may not arrive as empty. Put the parameters in a YAML file and pass `--parameter-overrides file://params.yaml`.

### Stack events show `CREATE_FAILED`
```bash
aws cloudformation describe-stack-events --stack-name url-shortener-prod \
  --query "StackEvents[?contains(ResourceStatus,'FAILED')].[LogicalResourceId,ResourceStatusReason]"
```
A common cause is a custom domain that already exists in another stack; a domain name can only be attached to one API Gateway custom domain per region.
