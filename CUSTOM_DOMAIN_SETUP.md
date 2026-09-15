# Setting Up a Custom Domain for Your URL Shortener

## Why You Need a Custom Domain

Currently, your short URLs look like this:
```
https://pktmrol6o8.execute-api.us-east-1.amazonaws.com/Prod/a3X9mK
```

With a custom domain, they can be much shorter:
```
https://go.yourdomain.com/a3X9mK
or
https://s.yourdomain.com/a3X9mK
```

---

## Prerequisites

1. **Own a domain** (e.g., purchased from Route 53, GoDaddy, Namecheap, etc.)
2. **AWS Certificate Manager (ACM)** certificate for your domain
3. **Route 53 hosted zone** (if using Route 53 for DNS)

---

## Step 1: Request SSL Certificate in ACM

1. Go to **AWS Certificate Manager** in `us-east-1` region (important!)
2. Click **Request Certificate**
3. Choose **Request a public certificate**
4. Enter domain names:
   - `go.yourdomain.com` (or your preferred subdomain)
5. Validation method: **DNS validation** (recommended)
6. Click **Request**
7. Click **Create records in Route 53** (if using Route 53)
8. Wait for status to become **Issued** (~5-10 minutes)

---

## Step 2: Create Custom Domain in API Gateway

### Via AWS Console:

1. Go to **API Gateway** → **Custom domain names**
2. Click **Create**
3. Configure:
   - **Domain name:** `go.yourdomain.com`
   - **ACM certificate:** Select the certificate from Step 1
   - **Endpoint type:** Regional
4. Click **Create domain name**
5. **Note the API Gateway domain name** (e.g., `d-abc123.execute-api.us-east-1.amazonaws.com`)

### Via AWS CLI:

```bash
aws apigateway create-domain-name \
  --domain-name go.yourdomain.com \
  --regional-certificate-arn arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID \
  --endpoint-configuration types=REGIONAL \
  --region us-east-1
```

---

## Step 3: Add Base Path Mapping

Map your custom domain to the API Gateway stage.

### Via AWS Console:

1. In the custom domain, go to **API mappings** tab
2. Click **Configure API mappings**
3. Click **Add new mapping**
4. Configure:
   - **API:** Select `url-shortener-dev` (or your stack name)
   - **Stage:** `Prod`
   - **Path:** Leave empty (so short codes work directly: `go.yourdomain.com/abc123`)
5. Click **Save**

### Via AWS CLI:

```bash
# Get API ID
API_ID=$(aws cloudformation describe-stacks \
  --stack-name url-shortener-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text | cut -d'/' -f3 | cut -d'.' -f1)

# Create base path mapping
aws apigateway create-base-path-mapping \
  --domain-name go.yourdomain.com \
  --rest-api-id $API_ID \
  --stage Prod \
  --region us-east-1
```

---

## Step 4: Configure DNS (Route 53)

Point your custom domain to API Gateway.

### Via AWS Console:

1. Go to **Route 53** → **Hosted zones**
2. Select your domain's hosted zone
3. Click **Create record**
4. Configure:
   - **Record name:** `go` (for `go.yourdomain.com`)
   - **Record type:** `A`
   - **Alias:** Toggle ON
   - **Route traffic to:**
     - Choose **Alias to API Gateway API**
     - Region: `us-east-1`
     - Select your custom domain
5. Click **Create records**

### Via AWS CLI:

```bash
# Get API Gateway domain name
APIGW_DOMAIN=$(aws apigateway get-domain-name \
  --domain-name go.yourdomain.com \
  --query 'regionalDomainName' \
  --output text)

# Get hosted zone ID
APIGW_ZONE_ID=$(aws apigateway get-domain-name \
  --domain-name go.yourdomain.com \
  --query 'regionalHostedZoneId' \
  --output text)

# Create Route 53 record
aws route53 change-resource-record-sets \
  --hosted-zone-id YOUR_HOSTED_ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "go.yourdomain.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "'$APIGW_ZONE_ID'",
          "DNSName": "'$APIGW_DOMAIN'",
          "EvaluateTargetHealth": false
        }
      }
    }]
  }'
```

### Using External DNS Provider (GoDaddy, Namecheap, etc.):

If your domain is not in Route 53, create a CNAME record:
- **Type:** CNAME
- **Name:** go
- **Value:** The API Gateway domain name from Step 2 (e.g., `d-abc123.execute-api.us-east-1.amazonaws.com`)

---

## Step 5: Update Lambda Function

Update the Lambda function to return the custom domain in short URLs.

### Option 1: Add BASE_URL Environment Variable

```bash
aws lambda update-function-configuration \
  --function-name url-shortener-api-dev \
  --environment "Variables={TABLE_NAME=url-shortener-links-dev,BASE_URL=https://go.yourdomain.com}"
```

### Option 2: Update SAM Template

Edit `template.yaml`:

```yaml
Environment:
  Variables:
    TABLE_NAME: !Ref LinksTable
    BASE_URL: https://go.yourdomain.com  # Add this line
```

Then deploy:
```bash
sam build && sam deploy
```

### Option 3: Update Python Code

Edit `url_shortener/shortener.py`:

```python
# Change this
base_url = os.environ.get('BASE_URL', '')

# To this
base_url = 'https://go.yourdomain.com'
```

---

## Step 6: Test Your Custom Domain

```bash
# Create a short link
curl -X POST https://go.yourdomain.com/links \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://github.com/AbdulWaseaDev/url-shortener"}'

# Response should include custom domain
{
  "short_code": "a3X9mK",
  "short_url": "https://go.yourdomain.com/a3X9mK",
  "original_url": "https://github.com/AbdulWaseaDev/url-shortener"
}

# Test redirect
curl -L https://go.yourdomain.com/a3X9mK
```

---

## Troubleshooting

### DNS not resolving

Wait 5-15 minutes for DNS propagation, then check:
```bash
nslookup go.yourdomain.com
dig go.yourdomain.com
```

### Certificate validation stuck

If using DNS validation:
1. Ensure CNAME records are created in your DNS
2. Wait up to 30 minutes for validation
3. Check ACM console for validation status

### API Gateway returns 403 Forbidden

- Ensure base path mapping is created
- Verify API stage is `Prod` not `prod`
- Check custom domain is mapped to correct API

### Short URLs still show old domain

Update Lambda environment variable or redeploy code with new BASE_URL.

---

## Cost Considerations

- **ACM Certificate:** Free
- **Custom Domain Name:** $0 (no additional charge)
- **Route 53 Hosted Zone:** ~$0.50/month
- **Route 53 Queries:** $0.40 per million queries

**Total additional cost:** ~$0.50-1.00/month

---

## Popular Short Domain Providers

If you don't own a domain, consider these short domain providers:

1. **Short.io** - Provides short domains like `short.link`
2. **Rebrandly** - Custom short domains
3. **TinyURL** - Classic short domain service
4. **is.gd** - Free short domain

Or purchase a short domain (2-5 characters):
- Check availability: [Namecheap](https://www.namecheap.com), [GoDaddy](https://www.godaddy.com)
- Examples: `go.link`, `s.link`, `u.to`, `myco.de`

---

## Example Complete Setup

```bash
# 1. Request certificate (wait for validation)
aws acm request-certificate \
  --domain-name go.yourdomain.com \
  --validation-method DNS \
  --region us-east-1

# 2. Create custom domain
aws apigateway create-domain-name \
  --domain-name go.yourdomain.com \
  --regional-certificate-arn arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID \
  --endpoint-configuration types=REGIONAL \
  --region us-east-1

# 3. Create base path mapping
aws apigateway create-base-path-mapping \
  --domain-name go.yourdomain.com \
  --rest-api-id YOUR_API_ID \
  --stage Prod

# 4. Update Lambda environment
aws lambda update-function-configuration \
  --function-name url-shortener-api-dev \
  --environment "Variables={TABLE_NAME=url-shortener-links-dev,BASE_URL=https://go.yourdomain.com}"

# 5. Create Route 53 record (done via console or CLI as shown above)
```

---

## Benefits of Custom Domain

✅ **Shorter URLs:** `go.yourdomain.com/abc123` vs `pktmrol6o8.execute-api.us-east-1.amazonaws.com/Prod/abc123`

✅ **Branding:** Use your company/personal brand

✅ **Trust:** Users trust branded domains more than random API Gateway URLs

✅ **Flexibility:** Can change backend without changing URLs

✅ **Professional:** Better for production use

---

## Without a Custom Domain

If you don't want to set up a custom domain, the current API still works perfectly fine for:
- Testing and development
- Internal tools
- Technical audiences who don't mind longer URLs
- Learning and portfolio projects

The functionality is identical—only the URL length differs!
