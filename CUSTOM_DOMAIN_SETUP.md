# Custom Domain Setup

Without a custom domain, short links use the API Gateway URL:
```
https://abc123xyz.execute-api.us-east-1.amazonaws.com/Prod/a3X9mK
```

With one, they look like this project's production links:
```
https://url-shortener.berlintechs.com/a3X9mK
```

The custom domain is part of `template.yaml`. You request a certificate, set two parameters, deploy, and add a DNS record. The Lambda builds short URLs from whatever domain the request came in on, so no code or environment variable changes are needed.

The steps below use Cloudflare for DNS, as this project does. Any DNS provider that supports CNAME records works the same way.

---

## Step 1: Request a certificate

The certificate must be in the **same region as the stack** (regional endpoint), for example `us-east-1`:

```bash
aws acm request-certificate \
  --domain-name url-shortener.yourdomain.com \
  --validation-method DNS \
  --region us-east-1
```

Get the validation record:
```bash
aws acm describe-certificate --region us-east-1 --certificate-arn CERT_ARN \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord'
```

## Step 2: Add the DNS records for validation

In Cloudflare, add:

| Type | Name | Value | Proxy |
|---|---|---|---|
| CNAME | the validation name, without `.yourdomain.com` | the validation value | **DNS only** |

**Check for CAA records first.** If your domain has CAA records (Cloudflare adds them for its own certificates), Amazon must be allowed or validation fails with `CAA_ERROR`. Add a CAA record for just this subdomain:

| Type | Name | Flags | Tag | CA domain name |
|---|---|---|---|---|
| CAA | `url-shortener` | `0` | Only allow specific hostnames (`issue`) | `amazon.com` |

Check whether the domain has CAA records:
```bash
curl -s -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=yourdomain.com&type=CAA'
```

Wait for the certificate to be issued (usually a few minutes):
```bash
aws acm wait certificate-validated --region us-east-1 --certificate-arn CERT_ARN
```

A certificate that failed validation can't be retried. Fix the DNS, delete it, and request a new one; the new request normally reuses the same validation record.

## Step 3: Set the domain in samconfig.toml

In the environment's section of `samconfig.toml`:

```toml
parameter_overrides = "Environment=\"prod\" DomainName=\"url-shortener.yourdomain.com\" CertificateArn=\"arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID\""
```

This creates an `AWS::ApiGateway::DomainName` (regional, TLS 1.2) and a base path mapping to the `Prod` stage at the root, so links have no `/Prod` prefix.

## Step 4: Deploy and point DNS at it

```bash
sam build && sam deploy --config-env prod
sam list stack-outputs --stack-name url-shortener-prod   # CustomDomainTarget
```

In Cloudflare, add:

| Type | Name | Target | Proxy |
|---|---|---|---|
| CNAME | `url-shortener` | `CustomDomainTarget` output, e.g. `d-abc123.execute-api.us-east-1.amazonaws.com` | **DNS only** |

Keep it **DNS only**. If you turn on Cloudflare's proxy, set SSL/TLS mode to **Full (strict)**, otherwise you can get redirect loops or certificate errors.

## Step 5: Test

```bash
curl -X POST https://url-shortener.yourdomain.com/links \
  -H 'Content-Type: application/json' -H 'x-api-key: YOUR_API_KEY' \
  -d '{"url": "https://github.com/AbdulWaseaDev/url-shortener"}'
# "short_url": "https://url-shortener.yourdomain.com/a3X9mK"

curl -i https://url-shortener.yourdomain.com/a3X9mK   # 302
```

---

## Moving a domain to another stack

A domain name can belong to only one API Gateway custom domain in a region. To move it (for example from an old stack to a new one):

1. Deploy the old stack with `DomainName=""` to release the domain.
2. Deploy the new stack with the domain.
3. Update the CNAME to the new stack's `CustomDomainTarget`.

Links are unreachable between steps 1 and 3, so have the DNS change ready. Create both changesets first (`sam deploy --no-execute-changeset`) and execute them back to back.

---

## Troubleshooting

### Certificate `FAILED` with `CAA_ERROR`
Add the CAA record from Step 2, then request a new certificate.

### Domain doesn't resolve
Check the record is live:
```bash
curl -s -H 'accept: application/dns-json' \
  'https://cloudflare-dns.com/dns-query?name=url-shortener.yourdomain.com&type=CNAME'
```

### 403 Forbidden on every route
The base path mapping is missing or points at the wrong API. Check the stack has `CustomDomainMapping` and the CNAME targets this stack's `CustomDomainTarget`.

### Short URLs contain `/Prod/`
The request came in through the `execute-api` URL instead of the custom domain. Use the custom domain.

---

## Cost

ACM certificates and API Gateway custom domains are free. You only pay for the domain registration itself.
