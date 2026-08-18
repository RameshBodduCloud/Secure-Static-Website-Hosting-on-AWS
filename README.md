
# Secure Static Website Hosting on AWS

Production-style static website hosted on AWS using a **private S3 bucket**, **CloudFront (OAC)**, **Route 53**, **ACM (HTTPS)**, and a **Lambda function** that automatically invalidates the CloudFront cache when `index.html` is updated.

**Live demo:** [https://sudharam.online](https://sudharam.online)

---

## Features

- Private S3 origin (Block Public Access enabled)
- CloudFront CDN for global, low-latency delivery
- Origin Access Control (OAC) so only CloudFront can read S3 objects
- Custom domain + HTTPS via Route 53 and ACM
- Automatic CloudFront cache invalidation using S3 → Lambda
- Fully static site (no servers to manage)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME FLOW (User Request) │
│ │
│ [User/Browser] │
│ │ │
│ │ 1) DNS lookup: sudharam.online │
│ v │
│ [Route 53 Hosted Zone] │
│ │ │
│ │ 2) Alias A/AAAA → CloudFront │
│ v │
│ [CloudFront Distribution] <── [ACM Certificate us-east-1] │
│ │ │
│ │ 3) Origin fetch via OAC (cache miss) │
│ v │
│ [S3 Bucket (Private, Block Public Access ON)] │
│ │
├─────────────────────────────────────────────────────────────┤
│ (Cache Invalidation) │
│ │
│ [You upload index.html to S3 via Console] │
│ │ │
│ │ 4) S3 Event: ObjectCreated (suffix: index.html) │
│ v │
│ [Lambda Function (auto-cloudfront-invalidation)] │
│ │ │
│ │ 5) cloudfront:CreateInvalidation API │
│ v │
│ [CloudFront Cache Cleared ✅] │
│ │ │
│ │ 6) Next user request gets fresh content │
│ v │
│ [User sees updated website instantly] ✅ │
│ │
└─────────────────────────────────────────────────────────────┘

Update / automation path (not in request path):
S3 ObjectCreated (suffix: index.html)
  → Lambda
  → CloudFront CreateInvalidation (/*)
```

---

## Tech Stack

| Layer | Service / Tech |
|---|---|
| Website | HTML, CSS, JavaScript |
| Storage | Amazon S3 |
| CDN | Amazon CloudFront |
| Origin security | CloudFront OAC + S3 bucket policy |
| DNS | Amazon Route 53 |
| TLS | AWS Certificate Manager (ACM) |
| Automation | AWS Lambda + S3 Event Notification |

---
## Repository Structure
```
.
├── index.html                 # Static website
├── screenshots/               # Console / architecture screenshots
│   ├── architecture.png
│   ├── s3-bucket.png
│   ├── cloudfront-oac.png
│   ├── route53-alias.png
│   ├── acm-cert.png
│   ├── lambda-trigger.png
│   └── live-site.png
├── lambda/
│   └── invalidate_cloudfront.py
└── README.md
```

---

## Prerequisites

- AWS account
- A registered domain (this project uses Route 53)
- IAM permissions for S3, CloudFront, Route 53, ACM, Lambda, and IAM

---

## Setup Guide

### 1. Create a private S3 bucket

1. Create a bucket (example: `your-static-site-bucket`).
2. Keep **Block all public access = ON**.
3. Do **not** enable S3 Static Website Hosting (not needed for CloudFront + OAC).
4. Upload `index.html` to the **root** of the bucket.
<img width="1918" height="574" alt="image" src="https://github.com/user-attachments/assets/35fb06d0-fa93-47e8-b0dc-4bf00b8354de" />


---

### 2. Create a CloudFront distribution

1. Origin domain: your S3 bucket REST endpoint  
   Example: `your-bucket.s3.<region>.amazonaws.com`
2. Origin access: **Origin Access Control (recommended)**
3. Create / select an OAC with **Sign requests**.
4. Default root object: `index.html`
5. Allowed HTTP methods: **GET, HEAD** (static site)

<img width="940" height="440" alt="image" src="https://github.com/user-attachments/assets/8e1938ce-040c-4b7b-a6df-7b55c24d8a8c" />


---

### 3. Update the S3 bucket policy (OAC read-only)

CloudFront can generate this automatically. The policy should allow **only** `s3:GetObject` from your distribution.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontReadOnly",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudfront.amazonaws.com"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::YOUR_ACCOUNT_ID:distribution/YOUR_DISTRIBUTION_ID"
        }
      }
    }
  ]
}
```

> CloudFront should **not** have `s3:PutObject` or `s3:DeleteObject`. Uploads are done by your IAM user/role, not by CloudFront.

---

### 4. Request an ACM certificate (must be `us-east-1`)

1. Open ACM in **US East (N. Virginia)**.
2. Request a public certificate for:
   - `example.com`
   - optionally `www.example.com`
3. Use DNS validation and create the CNAME records in Route 53.
4. Wait until status is **Issued**.
5. Attach the certificate to the CloudFront distribution.
6. Add the domain(s) under **Alternate domain names (CNAMEs)**.

<img width="940" height="393" alt="image" src="https://github.com/user-attachments/assets/58e933d6-c27b-4394-ad79-5228aecf004f" />


---

### 5. Point Route 53 to CloudFront

In the hosted zone:

| Record name | Type | Alias | Target |
|---|---|---|---|
| `@` (apex) | A | Yes | CloudFront distribution |
| `@` (apex) | AAAA | Yes | CloudFront distribution (optional IPv6) |
| `www` | A | Yes | CloudFront distribution (optional) |

<img width="1919" height="769" alt="image" src="https://github.com/user-attachments/assets/efce5faa-5144-4784-bf8d-5879bbc5e585" />


If the domain is registered outside AWS, update the registrar nameservers to the Route 53 hosted-zone NS records.

---

### 6. Lambda: automatic CloudFront invalidation

When `index.html` is uploaded/overwritten in S3, Lambda calls `cloudfront:CreateInvalidation`.
<img width="940" height="246" alt="image" src="https://github.com/user-attachments/assets/d23ecfe7-3038-451d-9523-99af82977955" />


#### Lambda code (`lambda/invalidate_cloudfront.py`)

```python
import boto3
import time
import json

DISTRIBUTION_ID = "YOUR_DISTRIBUTION_ID"
client = boto3.client("cloudfront")

def lambda_handler(event, context):
    try:
        response = client.create_invalidation(
            DistributionId=DISTRIBUTION_ID,
            InvalidationBatch={
                "Paths": {
                    "Quantity": 1,
                    "Items": ["/*"]
                },
                "CallerReference": str(time.time())
            }
        )

        invalidation_id = response["Invalidation"]["Id"]
        print(f"Successfully cleared cache. Invalidation ID: {invalidation_id}")

        return {
            "statusCode": 200,
            "body": json.dumps("Success! Website updated.")
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps("Failed to clear cache.")
        }
```

#### IAM permission for the Lambda role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "cloudfront:CreateInvalidation",
      "Resource": "arn:aws:cloudfront::YOUR_ACCOUNT_ID:distribution/YOUR_DISTRIBUTION_ID"
    }
  ]
}
```

#### S3 trigger

- Event: `s3:ObjectCreated:*`
- Bucket: your website bucket
- Suffix: `index.html`  
  (avoids one invalidation per CSS/JS/image upload)
<img width="1919" height="838" alt="image" src="https://github.com/user-attachments/assets/3c4096da-b1a7-4103-ae05-e5ef051b3bef" />


---

## How to update the website

1. Edit `index.html` locally.
2. Upload it to the S3 bucket (overwrite).
3. S3 invokes Lambda.
4. Lambda creates a CloudFront invalidation.
5. Hard-refresh the browser (`Ctrl + F5` / `Cmd + Shift + R`).

---

## Screenshots

Add your console screenshots under `screenshots/` and they will render here.

| Screenshot | Description |
|---|---|
| `architecture.png` | End-to-end architecture diagram |
| `s3-bucket.png` | Private S3 bucket with `index.html` |
| `cloudfront-oac.png` | CloudFront origin + OAC |
| `acm-cert.png` | ACM certificate in us-east-1 |
| `route53-alias.png` | Route 53 alias to CloudFront |
| `lambda-trigger.png` | S3 event trigger on Lambda |
| `live-site.png` | Live site on custom domain |

<img width="1911" height="782" alt="image" src="https://github.com/user-attachments/assets/56235bf3-24f5-4d85-a962-bc1e50c8d915" />


---

## Troubleshooting

### `AccessDenied` on the CloudFront URL
- Confirm `index.html` exists at the **bucket root** (not inside a folder).
- Set CloudFront **Default root object** to `index.html`.
- Confirm the bucket policy allows `s3:GetObject` for your distribution ARN.
- Test: `https://YOUR_DISTRIBUTION.cloudfront.net/index.html`

### Custom domain shows `NXDOMAIN`
- Confirm the Route 53 **A (Alias)** record exists.
- Confirm the domain registrar uses the Route 53 nameservers.
- DNS changes can take time to propagate.

### Uploaded a new file but the old site still appears
- CloudFront is caching the previous version.
- Check CloudFront → **Invalidations**.
- Create a manual invalidation for `/*` if Lambda did not run.
- Hard-refresh the browser.

### Lambda did not create an invalidation
- Confirm the S3 trigger suffix is exactly `index.html`.
- Confirm the Lambda role has `cloudfront:CreateInvalidation`.
- Check CloudWatch Logs for the function.
- Confirm `DISTRIBUTION_ID` in the code is correct.
- Click **Deploy** after changing Lambda code.

---

## Security Notes

- Keep the S3 bucket private.
- Give CloudFront **read-only** access (`s3:GetObject` only).
- Scope the bucket policy with `AWS:SourceArn` to your distribution.
- Do not allow public `s3:PutObject` / `s3:DeleteObject`.
- Prefer hashed asset filenames + long cache TTL in production; invalidate mainly HTML.

---
