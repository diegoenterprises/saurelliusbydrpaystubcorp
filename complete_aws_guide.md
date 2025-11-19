# Saurellius Platform - Complete AWS Production Deployment Guide

## 🎯 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CloudFront CDN                          │
│              (Global Edge Locations + SSL/TLS)                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                              │
┌───────▼────────┐            ┌───────▼────────┐
│   Static S3    │            │  Elastic       │
│   (Frontend)   │            │  Beanstalk     │
│   HTML/CSS/JS  │            │  (Flask API)   │
└────────────────┘            └───────┬────────┘
                                      │
                       ┌──────────────┼──────────────┐
                       │              │              │
                ┌──────▼─────┐  ┌────▼────┐  ┌─────▼─────┐
                │ RDS        │  │ Lambda  │  │ S3 Bucket │
                │ PostgreSQL │  │ (PDF)   │  │ (PDFs)    │
                └────────────┘  └─────────┘  └───────────┘
                       │
                ┌──────▼──────┐
                │   Secrets   │
                │   Manager   │
                └─────────────┘
```

---

## 📋 Prerequisites

### Required AWS Services
- ✅ **AWS Account** with billing enabled
- ✅ **IAM User** with administrator access
- ✅ **AWS CLI** installed and configured
- ✅ **EB CLI** installed
- ✅ **Domain** registered (or use Route 53)

### Local Development Tools
```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install EB CLI
pip install awsebcli

# Verify installations
aws --version
eb --version
```

---

## 🗄️ Part 1: Database Setup (RDS PostgreSQL)

### 1. Create RDS Instance via Console

```bash
# Or use CLI
aws rds create-db-instance \
    --db-instance-identifier saurellius-db-prod \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --engine-version 15.4 \
    --master-username saurellius_admin \
    --master-user-password YOUR_SECURE_PASSWORD \
    --allocated-storage 20 \
    --storage-type gp3 \
    --vpc-security-group-ids sg-XXXXXXXXX \
    --db-name saurellius_production \
    --backup-retention-period 7 \
    --preferred-backup-window "03:00-04:00" \
    --preferred-maintenance-window "mon:04:00-mon:05:00" \
    --publicly-accessible \
    --tags Key=Environment,Value=Production Key=Application,Value=Saurellius
```

### 2. Configure Security Group

```bash
# Allow Elastic Beanstalk instances to connect
aws ec2 authorize-security-group-ingress \
    --group-id sg-XXXXXXXXX \
    --protocol tcp \
    --port 5432 \
    --source-group sg-EB-INSTANCE-GROUP-ID
```

### 3. Create Database Schema

```bash
# Connect to RDS
psql -h saurellius-db-prod.xxxxx.us-east-1.rds.amazonaws.com \
     -U saurellius_admin \
     -d saurellius_production

# Run schema from your repo
psql -h YOUR_RDS_ENDPOINT \
     -U saurellius_admin \
     -d saurellius_production \
     -f schema.sql
```

---

## 🔐 Part 2: Secrets Manager Setup

### Create Secrets

```bash
# Database credentials
aws secretsmanager create-secret \
    --name saurellius/database \
    --description "RDS PostgreSQL credentials" \
    --secret-string '{
        "username": "saurellius_admin",
        "password": "YOUR_SECURE_PASSWORD",
        "host": "saurellius-db-prod.xxxxx.us-east-1.rds.amazonaws.com",
        "port": 5432,
        "database": "saurellius_production"
    }'

# JWT Secret
aws secretsmanager create-secret \
    --name saurellius/jwt-secret \
    --secret-string "$(openssl rand -base64 64)"

# Encryption Key (Fernet)
aws secretsmanager create-secret \
    --name saurellius/encryption-key \
    --secret-string "$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Stripe Keys
aws secretsmanager create-secret \
    --name saurellius/stripe \
    --secret-string '{
        "secret_key": "sk_live_YOUR_STRIPE_KEY",
        "publishable_key": "pk_live_YOUR_STRIPE_KEY",
        "webhook_secret": "whsec_YOUR_WEBHOOK_SECRET"
    }'
```

---

## 📦 Part 3: S3 Buckets Setup

### 1. Create PDF Storage Bucket

```bash
aws s3 mb s3://saurellius-paystubs-prod --region us-east-1

# Configure CORS
aws s3api put-bucket-cors --bucket saurellius-paystubs-prod --cors-configuration '{
    "CORSRules": [{
        "AllowedOrigins": ["https://saurellius.drpaystub.com"],
        "AllowedMethods": ["GET", "PUT", "POST"],
        "AllowedHeaders": ["*"],
        "MaxAgeSeconds": 3000
    }]
}'

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket saurellius-paystubs-prod \
    --versioning-configuration Status=Enabled

# Lifecycle policy (delete after 90 days)
aws s3api put-bucket-lifecycle-configuration \
    --bucket saurellius-paystubs-prod \
    --lifecycle-configuration '{
        "Rules": [{
            "Id": "DeleteOldPaystubs",
            "Status": "Enabled",
            "ExpirationInDays": 90
        }]
    }'
```

### 2. Create Static Website Bucket

```bash
aws s3 mb s3://saurellius-frontend-prod --region us-east-1

# Enable static website hosting
aws s3 website s3://saurellius-frontend-prod \
    --index-document index.html \
    --error-document error.html

# Upload frontend files
aws s3 sync ./frontend s3://saurellius-frontend-prod --delete
```

---

## ⚡ Part 4: Lambda Function Setup (PDF Generation)

### 1. Create Lambda Function

**lambda_function.py:**
```python
import json
import boto3
import os
from SAURELLIUS2026 import generate_snappt_compliant_paystub

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Lambda function for PDF generation
    Triggered by API Gateway or direct invoke
    """
    try:
        # Parse input
        paystub_data = json.loads(event['body']) if 'body' in event else event
        user_id = paystub_data['user_id']
        paystub_id = paystub_data['paystub_id']
        
        # Generate PDF
        pdf_bytes = generate_snappt_compliant_paystub(
            paystub_data=paystub_data['data'],
            template_id="eusotrip_original"
        )
        
        # Upload to S3
        s3_bucket = os.environ['S3_BUCKET']
        s3_key = f"paystubs/{user_id}/{paystub_id}.pdf"
        
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType='application/pdf'
        )
        
        # Generate presigned URL
        pdf_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': s3_bucket, 'Key': s3_key},
            ExpiresIn=604800  # 7 days
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'pdf_url': pdf_url,
                's3_key': s3_key
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
```

### 2. Create Lambda Deployment Package

```bash
cd lambda
pip install -r requirements.txt -t .
zip -r lambda_function.zip .

# Create Lambda function
aws lambda create-function \
    --function-name saurellius-pdf-generator \
    --runtime python3.11 \
    --role arn:aws:iam::ACCOUNT_ID:role/lambda-execution-role \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://lambda_function.zip \
    --timeout 60 \
    --memory-size 512 \
    --environment Variables="{S3_BUCKET=saurellius-paystubs-prod}"
```

---

## 🚀 Part 5: Elastic Beanstalk Deployment

### 1. Prepare Application

**requirements.txt:**
```txt
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-JWT-Extended==4.5.3
Flask-CORS==4.0.0
psycopg2-binary==2.9.9
boto3==1.34.0
cryptography==41.0.7
stripe==7.8.0
WeasyPrint==60.1
qrcode==7.4.2
Pillow==10.1.0
python-dotenv==1.0.0
gunicorn==21.2.0
```

**Procfile:**
```
web: gunicorn --bind :8000 --workers 3 --timeout 60 application:app
```

**.ebextensions/01_python.config:**
```yaml
option_settings:
  aws:elasticbeanstalk:container:python:
    WSGIPath: application:app
  aws:elasticbeanstalk:application:environment:
    PYTHONPATH: "/var/app/current:$PYTHONPATH"
  aws:elasticbeanstalk:environment:proxy:
    ProxyServer: nginx
```

**.ebextensions/02_environment.config:**
```yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    FLASK_ENV: "production"
    DATABASE_URL: "postgresql://user:pass@host:5432/db"
    JWT_SECRET_KEY: "from-secrets-manager"
    ENCRYPTION_KEY: "from-secrets-manager"
    STRIPE_SECRET_KEY: "from-secrets-manager"
    S3_BUCKET: "saurellius-paystubs-prod"
```

### 2. Initialize Elastic Beanstalk

```bash
cd saurellius-platform

# Initialize EB
eb init -p python-3.11 saurellius-platform --region us-east-1

# Create environment
eb create saurellius-prod-env \
    --instance-type t3.small \
    --min-instances 2 \
    --max-instances 10 \
    --envvars \
        DATABASE_URL="postgresql://user:pass@host:5432/db",\
        JWT_SECRET_KEY="from-secrets-manager",\
        ENCRYPTION_KEY="from-secrets-manager",\
        STRIPE_SECRET_KEY="from-secrets-manager",\
        S3_BUCKET="saurellius-paystubs-prod"

# Deploy
eb deploy

# Check status
eb status
eb health
eb logs
```

### 3. Configure Auto-Scaling

```bash
# Update auto-scaling settings
eb config

# Add these settings:
# aws:autoscaling:asg:
#   MinSize: 2
#   MaxSize: 10
# aws:autoscaling:trigger:
#   MeasureName: CPUUtilization
#   Statistic: Average
#   Unit: Percent
#   UpperThreshold: 70
#   LowerThreshold: 20
```

---

## 🌐 Part 6: CloudFront + Custom Domain

### 1. Request SSL Certificate

```bash
# Request certificate in us-east-1 (required for CloudFront)
aws acm request-certificate \
    --domain-name saurellius.drpaystub.com \
    --validation-method DNS \
    --region us-east-1

# Note the CertificateArn from output
# Add CNAME records to Route 53 for validation
```

### 2. Create CloudFront Distribution

```bash
aws cloudfront create-distribution --distribution-config '{
    "CallerReference": "saurellius-'$(date +%s)'",
    "Comment": "Saurellius Platform CDN",
    "DefaultRootObject": "index.html",
    "Origins": {
        "Quantity": 2,
        "Items": [
            {
                "Id": "S3-saurellius-frontend",
                "DomainName": "saurellius-frontend-prod.s3.amazonaws.com",
                "S3OriginConfig": {
                    "OriginAccessIdentity": ""
                }
            },
            {
                "Id": "EB-saurellius-api",
                "DomainName": "saurellius-prod-env.xxxxx.us-east-1.elasticbeanstalk.com",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "https-only"
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "S3-saurellius-frontend",
        "ViewerProtocolPolicy": "redirect-to-https",
        "Compress": true,
        "ForwardedValues": {
            "QueryString": false,
            "Cookies": {"Forward": "none"}
        }
    },
    "CacheBehaviors": {
        "Quantity": 1,
        "Items": [{
            "PathPattern": "/api/*",
            "TargetOriginId": "EB-saurellius-api",
            "ViewerProtocolPolicy": "https-only",
            "ForwardedValues": {
                "QueryString": true,
                "Headers": {"Quantity": 1, "Items": ["Authorization"]},
                "Cookies": {"Forward": "all"}
            }
        }]
    },
    "Enabled": true,
    "ViewerCertificate": {
        "CloudFrontDefaultCertificate": false,
        "ACMCertificateArn": "arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID",
        "SSLSupportMethod": "sni-only",
        "MinimumProtocolVersion": "TLSv1.2_2021"
    },
    "Aliases": {
        "Quantity": 1,
        "Items": ["saurellius.drpaystub.com"]
    }
}'
```

### 3. Update Route 53

```bash
# Create A record pointing to CloudFront
aws route53 change-resource-record-sets \
    --hosted-zone-id HOSTED_ZONE_ID \
    --change-batch '{
        "Changes": [{
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "saurellius.drpaystub.com",
                "Type": "A",
                "AliasTarget": {
                    "HostedZoneId": "Z2FDTNDATAQYW2",
                    "DNSName": "d1234567890.cloudfront.net",
                    "EvaluateTargetHealth": false
                }
            }
        }]
    }'
```

---

## 💳 Part 7: Stripe Integration

### 1. Create Products & Prices

```bash
# Starter Plan
stripe products create \
  --name "Saurellius Starter" \
  --description "10 paystubs per month" \
  --metadata tier=starter

stripe prices create \
  --product prod_STARTER_ID \
  --unit-amount 5000 \
  --currency usd \
  --recurring interval=month

# Professional Plan
stripe products create \
  --name "Saurellius Professional" \
  --description "30 paystubs per month" \
  --metadata tier=professional

stripe prices create \
  --product prod_PROFESSIONAL_ID \
  --unit-amount 10000 \
  --currency usd \
  --recurring interval=month

# Business Plan
stripe products create \
  --name "Saurellius Business" \
  --description "Unlimited paystubs" \
  --metadata tier=business

stripe prices create \
  --product prod_BUSINESS_ID \
  --unit-amount 15000 \
  --currency usd \
  --recurring interval=month
```

### 2. Configure Webhook

```bash
# Create webhook endpoint
stripe webhook_endpoints create \
  --url https://saurellius.drpaystub.com/api/webhooks/stripe \
  --enabled-events customer.subscription.created \
  --enabled-events customer.subscription.updated \
  --enabled-events customer.subscription.deleted \
  --enabled-events payment_intent.succeeded \
  --enabled-events payment_intent.payment_failed
```

---

## 🔍 Part 8: Monitoring & Logging

### 1. CloudWatch Alarms

```bash
# High CPU Alert
aws cloudwatch put-metric-alarm \
    --alarm-name saurellius-high-cpu \
    --alarm-description "Alert when CPU exceeds 80%" \
    --metric-name CPUUtilization \
    --namespace AWS/ElasticBeanstalk \
    --statistic Average \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:saurellius-alerts

# Database Connections
aws cloudwatch put-metric-alarm \
    --alarm-name saurellius-db-connections \
    --metric-name DatabaseConnections \
    --namespace AWS/RDS \
    --statistic Average \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:saurellius-alerts

# Lambda Errors
aws cloudwatch put-metric-alarm \
    --alarm-name saurellius-lambda-errors \
    --metric-name Errors \
    --namespace AWS/Lambda \
    --dimensions Name=FunctionName,Value=saurellius-pdf-generator \
    --statistic Sum \
    --period 60 \
    --evaluation-periods 1 \
    --threshold 10 \
    --comparison-operator GreaterThanThreshold \
    --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:saurellius-alerts
```

### 2. Application Logs

```bash
# View EB logs
eb logs

# Stream logs
eb logs --stream

# CloudWatch Logs
aws logs tail /aws/elasticbeanstalk/saurellius-prod-env/var/log/web.stdout.log --follow

# Lambda logs
aws logs tail /aws/lambda/saurellius-pdf-generator --follow
```

### 3. CloudWatch Dashboard

```bash
# Create dashboard
aws cloudwatch put-dashboard \
    --dashboard-name Saurellius-Production \
    --dashboard-body '{
        "widgets": [
            {
                "type": "metric",
                "properties": {
                    "metrics": [
                        ["AWS/ElasticBeanstalk", "CPUUtilization", {"stat": "Average"}],
                        ["AWS/RDS", "CPUUtilization", {"stat": "Average"}],
                        ["AWS/Lambda", "Invocations", {"stat": "Sum"}]
                    ],
                    "period": 300,
                    "stat": "Average",
                    "region": "us-east-1",
                    "title": "System Performance"
                }
            }
        ]
    }'
```

---

## ✅ Part 9: Post-Deployment Checklist

### Security
- [ ] Enable AWS WAF on CloudFront
- [ ] Configure Security Groups (only allow necessary ports)
- [ ] Enable RDS encryption at rest
- [ ] Enable S3 bucket encryption
- [ ] Rotate Secrets Manager secrets
- [ ] Enable MFA for AWS root account
- [ ] Set up IAM roles with least privilege
- [ ] Enable AWS GuardDuty
- [ ] Configure AWS Config rules
- [ ] Enable AWS CloudTrail

### Performance
- [ ] Enable CloudFront compression
- [ ] Configure CloudFront cache policies
- [ ] Set up RDS read replicas (if needed)
- [ ] Enable ElastiCache for session storage
- [ ] Optimize database queries with indexes
- [ ] Configure Lambda reserved concurrency
- [ ] Enable EB enhanced health reporting
- [ ] Set up auto-scaling policies

### Backup & Recovery
- [ ] Enable RDS automated backups (7 days)
- [ ] Configure S3 versioning
- [ ] Set up disaster recovery plan
- [ ] Test backup restoration
- [ ] Create RDS snapshots
- [ ] Document recovery procedures
- [ ] Set up cross-region replication (optional)

### Monitoring
- [ ] Set up CloudWatch dashboards
- [ ] Configure SNS alerts for critical metrics
- [ ] Enable AWS X-Ray for distributed tracing
- [ ] Set up custom metrics for business KPIs
- [ ] Configure log retention policies
- [ ] Enable Lambda Insights
- [ ] Set up Synthetics canaries

### Testing
- [ ] Test all API endpoints
- [ ] Verify PDF generation works
- [ ] Test Stripe payment flow
- [ ] Verify email notifications
- [ ] Test mobile responsiveness
- [ ] Run load tests
- [ ] Test failover scenarios

---

## 🧪 Part 10: Testing & Verification

### 1. Health Check

```bash
# Check Elastic Beanstalk health
curl https://saurellius.drpaystub.com/health

# Expected response:
# {"status": "healthy", "database": "connected", "timestamp": "2025-01-15T12:00:00Z"}
```

### 2. Test Authentication

```bash
# Register new user
curl -X POST https://saurellius.drpaystub.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "phone": "+1234567890",
    "password": "SecurePassword123!",
    "subscription_tier": "starter"
  }'

# Login
curl -X POST https://saurellius.drpaystub.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePassword123!"
  }'
```

### 3. Test Paystub Generation

```bash
# Get JWT token from login response
TOKEN="your_jwt_token_here"

# Generate paystub
curl -X POST https://saurellius.drpaystub.com/api/paystubs/generate-complete \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": 1,
    "pay_info": {
      "period_start": "2025-01-01",
      "period_end": "2025-01-15",
      "pay_date": "2025-01-20"
    },
    "earnings": {
      "regular_hours": 80,
      "hourly_rate": 45.00,
      "overtime_hours": 5,
      "bonus": 500
    },
    "deductions": {
      "contribution_401k": 200,
      "health_insurance": 150
    }
  }'
```

### 4. Load Testing

```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Run load test (1000 requests, 10 concurrent)
ab -n 1000 -c 10 -H "Authorization: Bearer $TOKEN" \
   https://saurellius.drpaystub.com/api/dashboard/summary

# Expected: 
# - Requests per second: > 50
# - Mean response time: < 200ms
# - Failed requests: 0
```

---

## 🔄 Part 11: CI/CD Pipeline (GitHub Actions)

### 1. Create GitHub Actions Workflow

**.github/workflows/deploy.yml:**
```yaml
name: Deploy to AWS Elastic Beanstalk

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install awsebcli
    
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v2
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1
    
    - name: Deploy to Elastic Beanstalk
      run: |
        eb init -p python-3.11 saurellius-platform --region us-east-1
        eb deploy saurellius-prod-env --timeout 20
    
    - name: Invalidate CloudFront cache
      run: |
        aws cloudfront create-invalidation \
          --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
          --paths "/*"
```

### 2. Add GitHub Secrets

```bash
# In GitHub repository settings, add:
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
CLOUDFRONT_DISTRIBUTION_ID
```

---

## 📊 Part 12: Cost Optimization

### Monthly Cost Estimate

```
Service                  Configuration              Monthly Cost
------------------------------------------------------------------------
Elastic Beanstalk        t3.small (2 instances)     ~$60
RDS PostgreSQL           db.t3.micro                ~$15
S3 Storage               50GB storage               ~$1.15
CloudFront               10GB transfer              ~$0.85
Lambda                   10K invocations            ~$0.20
Secrets Manager          4 secrets                  ~$1.60
Route 53                 1 hosted zone              ~$0.50
CloudWatch               Custom metrics             ~$3.00
------------------------------------------------------------------------
TOTAL                                               ~$82.30/month
```

### Cost Reduction Strategies

1. **Reserved Instances**: Save 40-60% on RDS
2. **Spot Instances**: Use for non-critical workloads
3. **S3 Lifecycle**: Auto-delete old PDFs after 90 days
4. **CloudFront**: Use edge caching effectively
5. **Lambda**: Optimize memory and timeout settings
6. **RDS**: Use Aurora Serverless for variable workloads

---

## 🚨 Part 13: Disaster Recovery

### Backup Strategy

```bash
# Automated RDS snapshots (daily)
aws rds modify-db-instance \
    --db-instance-identifier saurellius-db-prod \
    --backup-retention-period 7 \
    --preferred-backup-window "03:00-04:00"

# Manual snapshot before major changes
aws rds create-db-snapshot \
    --db-instance-identifier saurellius-db-prod \
    --db-snapshot-identifier saurellius-pre-deploy-$(date +%Y%m%d)

# S3 cross-region replication
aws s3api put-bucket-replication \
    --bucket saurellius-paystubs-prod \
    --replication-configuration file://replication.json
```

### Recovery Procedures

**RDS Restore:**
```bash
# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier saurellius-db-restored \
    --db-snapshot-identifier saurellius-snapshot-name
```

**Application Rollback:**
```bash
# Rollback EB environment
eb deploy --version previous-version-label
```

---

## 📈 Part 14: Scaling Strategy

### Auto-Scaling Configuration

```yaml
# .ebextensions/03_autoscaling.config
option_settings:
  aws:autoscaling:asg:
    MinSize: 2
    MaxSize: 10
  aws:autoscaling:trigger:
    MeasureName: CPUUtilization
    Statistic: Average
    Unit: Percent
    UpperThreshold: 70
    UpperBreachScaleIncrement: 2
    LowerThreshold: 20
    LowerBreachScaleIncrement: -1
    BreachDuration: 5
```

### Database Scaling

```bash
# Read replica for scaling reads
aws rds create-db-instance-read-replica \
    --db-instance-identifier saurellius-db-read-replica \
    --source-db-instance-identifier saurellius-db-prod \
    --db-instance-class db.t3.small
```

---

## 🎓 Part 15: Best Practices

### Security Best Practices
1. ✅ Use IAM roles instead of access keys
2. ✅ Enable MFA on all AWS accounts
3. ✅ Rotate secrets regularly
4. ✅ Use VPC for network isolation
5. ✅ Enable AWS CloudTrail for auditing
6. ✅ Implement least privilege access
7. ✅ Use AWS WAF to protect against attacks
8. ✅ Enable encryption at rest and in transit

### Performance Best Practices
1. ✅ Use CloudFront for static assets
2. ✅ Enable database query caching
3. ✅ Optimize Lambda cold starts
4. ✅ Use connection pooling for databases
5. ✅ Implement API rate limiting
6. ✅ Use async processing for heavy tasks
7. ✅ Monitor and optimize database indexes

### Operational Best Practices
1. ✅ Use infrastructure as code (CloudFormation/Terraform)
2. ✅ Implement comprehensive monitoring
3. ✅ Set up automated testing
4. ✅ Document all deployment procedures
5. ✅ Use blue-green deployments
6. ✅ Maintain runbooks for common issues
7. ✅ Regular security audits

---

## 🔧 Part 16: Troubleshooting Guide

### Common Issues and Solutions

#### Issue 1: 502 Bad Gateway
```bash
# Check EB environment health
eb health

# Check application logs
eb logs

# Common causes:
# - Application not binding to correct port
# - Application crash on startup
# - Timeout issues

# Solution: Verify Procfile
web: gunicorn --bind :8000 --workers 3 --timeout 60 application:app
```

#### Issue 2: Database Connection Errors
```bash
# Test database connectivity
psql -h RDS_ENDPOINT -U username -d database_name

# Check security group rules
aws ec2 describe-security-groups --group-ids sg-XXXXXXXXX

# Verify environment variables
eb printenv

# Solution: Update security group to allow EB instances
aws ec2 authorize-security-group-ingress \
    --group-id sg-RDS-SG \
    --protocol tcp \
    --port 5432 \
    --source-group sg-EB-SG
```

#### Issue 3: S3 Upload Failures
```bash
# Check IAM role permissions
aws iam get-role-policy --role-name aws-elasticbeanstalk-ec2-role --policy-name S3Access

# Test S3 access
aws s3 ls s3://saurellius-paystubs-prod

# Solution: Add S3 permissions to EB instance role
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GetObject",
    "s3:DeleteObject"
  ],
  "Resource": "arn:aws:s3:::saurellius-paystubs-prod/*"
}
```

#### Issue 4: Lambda Timeout
```bash
# Check Lambda logs
aws logs tail /aws/lambda/saurellius-pdf-generator --follow

# Increase timeout
aws lambda update-function-configuration \
    --function-name saurellius-pdf-generator \
    --timeout 120 \
    --memory-size 1024
```

#### Issue 5: High CPU Usage
```bash
# Check current instances
eb status

# Scale up immediately
aws autoscaling set-desired-capacity \
    --auto-scaling-group-name asg-name \
    --desired-capacity 5

# Identify bottleneck
eb ssh
top -c
```

---

## 🔐 Part 17: Security Hardening

### 1. Enable AWS WAF

```bash
# Create WAF Web ACL
aws wafv2 create-web-acl \
    --name saurellius-waf \
    --scope CLOUDFRONT \
    --default-action Allow={} \
    --rules file://waf-rules.json \
    --visibility-config \
        SampledRequestsEnabled=true,\
        CloudWatchMetricsEnabled=true,\
        MetricName=SaurelliusWAF

# Associate with CloudFront
aws wafv2 associate-web-acl \
    --web-acl-arn arn:aws:wafv2:us-east-1:ACCOUNT_ID:global/webacl/saurellius-waf/ID \
    --resource-arn arn:aws:cloudfront::ACCOUNT_ID:distribution/DISTRIBUTION_ID
```

**waf-rules.json:**
```json
[
  {
    "Name": "RateLimitRule",
    "Priority": 1,
    "Statement": {
      "RateBasedStatement": {
        "Limit": 2000,
        "AggregateKeyType": "IP"
      }
    },
    "Action": {
      "Block": {}
    },
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "RateLimit"
    }
  },
  {
    "Name": "SQLInjectionRule",
    "Priority": 2,
    "Statement": {
      "SqliMatchStatement": {
        "FieldToMatch": {
          "AllQueryArguments": {}
        },
        "TextTransformations": [
          {
            "Priority": 0,
            "Type": "URL_DECODE"
          }
        ]
      }
    },
    "Action": {
      "Block": {}
    },
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "SQLInjection"
    }
  }
]
```

### 2. Enable AWS GuardDuty

```bash
# Enable GuardDuty
aws guardduty create-detector --enable

# Get detector ID
DETECTOR_ID=$(aws guardduty list-detectors --query 'DetectorIds[0]' --output text)

# Configure threat intelligence
aws guardduty update-detector \
    --detector-id $DETECTOR_ID \
    --finding-publishing-frequency FIFTEEN_MINUTES
```

### 3. Configure AWS Config

```bash
# Enable Config
aws configservice put-configuration-recorder \
    --configuration-recorder name=default,roleARN=arn:aws:iam::ACCOUNT_ID:role/config-role \
    --recording-group allSupported=true,includeGlobalResourceTypes=true

# Start recording
aws configservice start-configuration-recorder --configuration-recorder-name default

# Add compliance rules
aws configservice put-config-rule --config-rule file://config-rules.json
```

### 4. Enable VPC Flow Logs

```bash
# Create CloudWatch log group
aws logs create-log-group --log-group-name /aws/vpc/flowlogs

# Enable VPC flow logs
aws ec2 create-flow-logs \
    --resource-type VPC \
    --resource-ids vpc-XXXXXXXX \
    --traffic-type ALL \
    --log-destination-type cloud-watch-logs \
    --log-group-name /aws/vpc/flowlogs \
    --deliver-logs-permission-arn arn:aws:iam::ACCOUNT_ID:role/vpc-flow-logs-role
```

---

## 📱 Part 18: Frontend Deployment

### 1. Prepare Frontend Files

```bash
cd saurellius-platform

# Copy auth pages
cp auth-pages.html static/auth.html

# Copy dashboard
cp saurellius-dashboard-2025.html static/dashboard.html

# Copy landing page
cp landing.html static/index.html

# Update API endpoints in all files
sed -i 's|const API_BASE_URL = .*|const API_BASE_URL = "https://saurellius.drpaystub.com";|g' static/*.html
```

### 2. Upload to S3

```bash
# Sync static files
aws s3 sync static/ s3://saurellius-frontend-prod/ \
    --delete \
    --cache-control max-age=31536000 \
    --exclude "*.html"

# Upload HTML with no-cache
aws s3 sync static/ s3://saurellius-frontend-prod/ \
    --exclude "*" \
    --include "*.html" \
    --cache-control no-cache

# Make bucket public (for CloudFront only)
aws s3api put-bucket-policy --bucket saurellius-frontend-prod --policy file://bucket-policy.json
```

**bucket-policy.json:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFrontReadAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity XXXXXXXX"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::saurellius-frontend-prod/*"
    }
  ]
}
```

### 3. Invalidate CloudFront Cache

```bash
# Invalidate all files
aws cloudfront create-invalidation \
    --distribution-id DISTRIBUTION_ID \
    --paths "/*"

# Invalidate specific paths
aws cloudfront create-invalidation \
    --distribution-id DISTRIBUTION_ID \
    --paths "/index.html" "/dashboard.html" "/auth.html"
```

---

## 🧪 Part 19: Integration Testing

### 1. End-to-End Testing Script

**test_e2e.sh:**
```bash
#!/bin/bash

API_URL="https://saurellius.drpaystub.com"
EMAIL="test_$(date +%s)@example.com"
PASSWORD="TestPassword123!"

echo "🧪 Starting End-to-End Tests..."

# Test 1: Health Check
echo "Test 1: Health Check"
HEALTH=$(curl -s $API_URL/health)
if echo $HEALTH | grep -q "healthy"; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed"
    exit 1
fi

# Test 2: User Registration
echo "Test 2: User Registration"
REGISTER=$(curl -s -X POST $API_URL/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Test User\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"phone\":\"+1234567890\"}")

if echo $REGISTER | grep -q "token"; then
    TOKEN=$(echo $REGISTER | jq -r '.token')
    echo "✅ Registration passed - Token: ${TOKEN:0:20}..."
else
    echo "❌ Registration failed"
    exit 1
fi

# Test 3: User Login
echo "Test 3: User Login"
LOGIN=$(curl -s -X POST $API_URL/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

if echo $LOGIN | grep -q "token"; then
    echo "✅ Login passed"
else
    echo "❌ Login failed"
    exit 1
fi

# Test 4: Dashboard Summary
echo "Test 4: Dashboard Summary"
DASHBOARD=$(curl -s $API_URL/api/dashboard/summary \
  -H "Authorization: Bearer $TOKEN")

if echo $DASHBOARD | grep -q "total_paystubs"; then
    echo "✅ Dashboard passed"
else
    echo "❌ Dashboard failed"
    exit 1
fi

# Test 5: Add Employee
echo "Test 5: Add Employee"
EMPLOYEE=$(curl -s -X POST $API_URL/api/employees \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name":"John",
    "last_name":"Doe",
    "ssn":"123-45-6789",
    "email":"john.doe@example.com",
    "date_of_birth":"1990-01-01",
    "address":{"street":"123 Main St","city":"Los Angeles","state":"CA","zip":"90001"},
    "employment":{"job_title":"Developer","hire_date":"2025-01-01","pay_rate":45.00,"pay_frequency":"biweekly","employment_type":"full-time"},
    "tax_info":{"filing_status":"single","allowances":1,"additional_withholding":0}
  }')

if echo $EMPLOYEE | grep -q "employee_id"; then
    EMPLOYEE_ID=$(echo $EMPLOYEE | jq -r '.employee_id')
    echo "✅ Add employee passed - ID: $EMPLOYEE_ID"
else
    echo "❌ Add employee failed"
    exit 1
fi

# Test 6: Generate Paystub
echo "Test 6: Generate Paystub"
PAYSTUB=$(curl -s -X POST $API_URL/api/paystubs/generate-complete \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"employee_id\":$EMPLOYEE_ID,
    \"pay_info\":{\"period_start\":\"2025-01-01\",\"period_end\":\"2025-01-15\",\"pay_date\":\"2025-01-20\"},
    \"earnings\":{\"regular_hours\":80,\"hourly_rate\":45.00,\"overtime_hours\":0,\"bonus\":0},
    \"deductions\":{\"contribution_401k\":100,\"health_insurance\":150}
  }")

if echo $PAYSTUB | grep -q "pdf_url"; then
    echo "✅ Paystub generation passed"
else
    echo "❌ Paystub generation failed"
    exit 1
fi

echo ""
echo "🎉 All tests passed!"
```

### 2. Run Tests

```bash
chmod +x test_e2e.sh
./test_e2e.sh
```

---

## 📊 Part 20: Performance Optimization

### 1. Database Query Optimization

```sql
-- Create indexes for common queries
CREATE INDEX CONCURRENTLY idx_paystubs_user_pay_date 
ON paystubs(user_id, pay_date DESC);

CREATE INDEX CONCURRENTLY idx_paystubs_employee_pay_date 
ON paystubs(employee_id, pay_date DESC);

CREATE INDEX CONCURRENTLY idx_employees_user_status 
ON employees(user_id, status) WHERE status = 'active';

-- Analyze query performance
EXPLAIN ANALYZE 
SELECT * FROM paystubs 
WHERE user_id = 1 
ORDER BY pay_date DESC 
LIMIT 10;
```

### 2. Enable Database Connection Pooling

**application.py:**
```python
from sqlalchemy.pool import QueuePool

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'poolclass': QueuePool,
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
    'max_overflow': 20
}
```

### 3. Implement Redis Caching

```bash
# Create ElastiCache Redis cluster
aws elasticache create-cache-cluster \
    --cache-cluster-id saurellius-redis \
    --cache-node-type cache.t3.micro \
    --engine redis \
    --num-cache-nodes 1

# Update application to use Redis
pip install redis flask-caching
```

**cache_config.py:**
```python
from flask_caching import Cache

cache = Cache(config={
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_HOST': 'saurellius-redis.xxxxx.cache.amazonaws.com',
    'CACHE_REDIS_PORT': 6379,
    'CACHE_REDIS_DB': 0,
    'CACHE_DEFAULT_TIMEOUT': 300
})

# Cache dashboard data
@cache.memoize(timeout=300)
def get_dashboard_summary(user_id):
    # Query database
    return data
```

### 4. CloudFront Cache Optimization

```bash
# Create cache policy
aws cloudfront create-cache-policy \
    --cache-policy-config file://cache-policy.json
```

**cache-policy.json:**
```json
{
  "Name": "SaurelliusOptimized",
  "MinTTL": 1,
  "MaxTTL": 31536000,
  "DefaultTTL": 86400,
  "ParametersInCacheKeyAndForwardedToOrigin": {
    "EnableAcceptEncodingGzip": true,
    "EnableAcceptEncodingBrotli": true,
    "HeadersConfig": {
      "HeaderBehavior": "whitelist",
      "Headers": {
        "Quantity": 1,
        "Items": ["Authorization"]
      }
    },
    "QueryStringsConfig": {
      "QueryStringBehavior": "none"
    },
    "CookiesConfig": {
      "CookieBehavior": "none"
    }
  }
}
```

---

## 🔔 Part 21: Notifications Setup

### 1. Configure SNS Topics

```bash
# Create SNS topic for alerts
aws sns create-topic --name saurellius-alerts

# Get topic ARN
TOPIC_ARN=$(aws sns list-topics --query "Topics[?contains(TopicArn,'saurellius-alerts')].TopicArn" --output text)

# Subscribe email
aws sns subscribe \
    --topic-arn $TOPIC_ARN \
    --protocol email \
    --notification-endpoint admin@saurellius.com

# Subscribe SMS
aws sns subscribe \
    --topic-arn $TOPIC_ARN \
    --protocol sms \
    --notification-endpoint +1234567890
```

### 2. Configure SES for Email

```bash
# Verify domain
aws ses verify-domain-identity --domain saurellius.com

# Add DNS records (from verification output)
# TXT: _amazonses.saurellius.com
# CNAME: amazonses verification token

# Create email template
aws ses create-template --cli-input-json file://email-template.json
```

**email-template.json:**
```json
{
  "Template": {
    "TemplateName": "PaystubGenerated",
    "SubjectPart": "Your Paystub is Ready - {{payDate}}",
    "HtmlPart": "<html><body><h1>Paystub Generated</h1><p>Your paystub for {{employeeName}} is ready.</p><p>Net Pay: ${{netPay}}</p><a href='{{downloadUrl}}'>Download PDF</a></body></html>",
    "TextPart": "Your paystub for {{employeeName}} is ready. Net Pay: ${{netPay}}. Download: {{downloadUrl}}"
  }
}
```

### 3. Implement Lambda for Notifications

**notification_lambda.py:**
```python
import boto3
import json

ses_client = boto3.client('ses')
sns_client = boto3.client('sns')

def lambda_handler(event, context):
    """
    Send notification when paystub is generated
    """
    record = event['Records'][0]
    
    if record['eventName'] == 'INSERT':
        paystub = record['dynamodb']['NewImage']
        
        # Send email
        ses_client.send_templated_email(
            Source='noreply@saurellius.com',
            Destination={'ToAddresses': [paystub['employee_email']['S']]},
            Template='PaystubGenerated',
            TemplateData=json.dumps({
                'employeeName': paystub['employee_name']['S'],
                'netPay': paystub['net_pay']['N'],
                'payDate': paystub['pay_date']['S'],
                'downloadUrl': paystub['pdf_url']['S']
            })
        )
        
        # Send SMS (optional)
        if paystub.get('phone'):
            sns_client.publish(
                PhoneNumber=paystub['phone']['S'],
                Message=f"Your paystub is ready. Net pay: ${paystub['net_pay']['N']}"
            )
    
    return {'statusCode': 200}
```

---

## 📈 Part 22: Analytics and Reporting

### 1. Enable CloudWatch Insights

```bash
# Create log insights query
aws logs put-query-definition \
    --name "Paystub Generation Rate" \
    --log-group-names "/aws/elasticbeanstalk/saurellius-prod-env/var/log/web.stdout.log" \
    --query-string 'fields @timestamp, @message | filter @message like /paystub generated/ | stats count() by bin(5m)'
```

### 2. Create Custom Metrics

**metrics.py:**
```python
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

def track_paystub_generation(user_id, amount):
    """Track business metrics"""
    cloudwatch.put_metric_data(
        Namespace='Saurellius/Business',
        MetricData=[
            {
                'MetricName': 'PaystubsGenerated',
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': datetime.now(),
                'Dimensions': [
                    {'Name': 'UserId', 'Value': str(user_id)}
                ]
            },
            {
                'MetricName': 'PaystubValue',
                'Value': float(amount),
                'Unit': 'None',
                'Timestamp': datetime.now()
            }
        ]
    )
```

### 3. Setup QuickSight Dashboard

```bash
# Create QuickSight data source
aws quicksight create-data-source \
    --aws-account-id ACCOUNT_ID \
    --data-source-id saurellius-rds \
    --name "Saurellius Production DB" \
    --type "RDS" \
    --data-source-parameters file://datasource-params.json
```

---

## 🎯 Part 23: Final Verification Checklist

### Pre-Launch Checklist

```markdown
## Infrastructure
- [ ] RDS database created and accessible
- [ ] Elastic Beanstalk environment healthy (GREEN)
- [ ] S3 buckets created and configured
- [ ] Lambda function deployed and tested
- [ ] CloudFront distribution active
- [ ] Route 53 DNS configured
- [ ] SSL certificate issued and attached

## Security
- [ ] Secrets Manager configured
- [ ] IAM roles have least privilege
- [ ] Security groups properly configured
- [ ] AWS WAF enabled on CloudFront
- [ ] GuardDuty enabled
- [ ] CloudTrail logging enabled
- [ ] VPC Flow Logs enabled

## Application
- [ ] All API endpoints tested
- [ ] PDF generation working
- [ ] Email notifications working
- [ ] Stripe payments integrated
- [ ] Authentication working (JWT)
- [ ] Frontend deployed to S3
- [ ] Database migrations run

## Monitoring
- [ ] CloudWatch alarms configured
- [ ] SNS notifications setup
- [ ] Custom metrics tracking
- [ ] Log aggregation working
- [ ] Performance monitoring active

## Performance
- [ ] Load testing completed
- [ ] Database indexes created
- [ ] Caching implemented
- [ ] CDN configured properly
- [ ] Auto-scaling tested

## Backup & Recovery
- [ ] Automated backups enabled
- [ ] Disaster recovery plan documented
- [ ] Backup restoration tested
- [ ] RTO/RPO defined

## Documentation
- [ ] API documentation complete
- [ ] Deployment runbook created
- [ ] Troubleshooting guide written
- [ ] Architecture diagrams updated
```

---

## 🚀 Part 24: Go-Live Procedure

### Day Before Launch

```bash
# 1. Final backup
aws rds create-db-snapshot \
    --db-instance-identifier saurellius-db-prod \
    --db-snapshot-identifier pre-launch-$(date +%Y%m%d)

# 2. Verify all systems
./test_e2e.sh

# 3. Check monitoring
aws cloudwatch get-dashboard --dashboard-name Saurellius-Production

# 4. Review logs
eb logs --all

# 5. Warm up CloudFront
curl -I https://saurellius.drpaystub.com
```

### Launch Day

```bash
# 1. Final deployment
eb deploy saurellius-prod-env

# 2. Invalidate CloudFront
aws cloudfront create-invalidation --distribution-id DIST_ID --paths "/*"

# 3. Verify health
curl https://saurellius.drpaystub.com/health

# 4. Monitor logs in real-time
eb logs --stream

# 5. Watch CloudWatch metrics
# Open CloudWatch dashboard
```

### Post-Launch

```bash
# Monitor for 24 hours
# Check these every hour:
- CloudWatch alarms
- Error rates
- Response times
- Database connections
- Lambda invocations
- User signups
- Paystub generations
```

---

## 📚 Part 25: Additional Resources

### Documentation Links
- [AWS Elastic Beanstalk](https://docs.aws.amazon.com/elasticbeanstalk/)
- [Amazon RDS PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/)
- [AWS Lambda](https://docs.aws.amazon.com/lambda/)
- [Amazon CloudFront](https://docs.aws.amazon.com/cloudfront/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)

### Support Contacts
- **AWS Support**: https://console.aws.amazon.com/support/
- **Stripe Support**: https://support.stripe.com/
- **Emergency Hotline**: [Your on-call number]

---

## ✅ Deployment Complete!

**Congratulations!** Your Saurellius platform is now deployed to AWS production infrastructure.

**Live URL**: https://saurellius.drpaystub.com

### Next Steps:
1. Monitor metrics for first 48 hours
2. Gather user feedback
3. Optimize based on real usage patterns
4. Plan feature releases
5. Schedule regular security audits

---

**Platform Status**: 🟢 DEPLOYED & OPERATIONAL  
**Date**: January 2025  
**Version**: 1.0.0-production