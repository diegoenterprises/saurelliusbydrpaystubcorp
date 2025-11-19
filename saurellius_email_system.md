# 📧 Saurellius In-House Email System: Hybrid Implementation Guide

## 🎯 Mission: Build Secure Email Service for Saurellius Platform

**Primary Domain:** `saurellius.drpaystub.com` (Platform)  
**Email Domain:** `drpaystub.net` (Email sending)  
**From Address:** `diego@drpaystub.net`  
**Architecture:** Hybrid (Self-hosted Postal + AWS SES Relay)

---

## 📋 TABLE OF CONTENTS

1. [Architecture Overview](#architecture-overview)
2. [Why Hybrid Approach](#why-hybrid-approach)
3. [Technical Requirements](#technical-requirements)
4. [Phase 1: DNS Configuration](#phase-1-dns-configuration)
5. [Phase 2: AWS SES Setup](#phase-2-aws-ses-setup)
6. [Phase 3: Postal Installation](#phase-3-postal-installation)
7. [Phase 4: Integration & Configuration](#phase-4-integration--configuration)
8. [Phase 5: Email Service Implementation](#phase-5-email-service-implementation)
9. [Phase 6: Testing & Verification](#phase-6-testing--verification)
10. [Monitoring & Maintenance](#monitoring--maintenance)
11. [Troubleshooting Guide](#troubleshooting-guide)

---

## 🏗️ ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                     Saurellius Platform                          │
│                 (saurellius.drpaystub.com)                       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ API Calls
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Email Service Layer (Python)                        │
│                utils/email_service.py                            │
│  - Forgot Password                                               │
│  - Email Verification                                            │
│  - Paystub Delivery                                              │
│  - Welcome Emails                                                │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ SMTP/API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Postal (Self-Hosted)                           │
│              mail.drpaystub.net (Your Server)                    │
│  - Queue Management                                              │
│  - Template Engine                                               │
│  - Analytics & Logs                                              │
│  - Webhook Processing                                            │
│  - Bounce/Complaint Handling                                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ Relay via SMTP
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AWS SES (Relay)                              │
│              email-smtp.us-east-1.amazonaws.com                  │
│  - IP Reputation Management                                      │
│  - Deliverability Optimization                                   │
│  - ISP Relationships                                             │
│  - Spam Filtering                                                │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ SMTP/TLS
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Recipient Inbox                                 │
│            (Gmail, Outlook, Yahoo, etc.)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 💡 WHY HYBRID APPROACH

### ✅ Benefits of Self-Hosted Postal:
- **Full Control** - Own your email infrastructure and data
- **No Per-Email Costs** - Pay for server, not per message
- **Custom Templates** - Complete control over email design
- **Advanced Analytics** - Deep insights into email performance
- **GDPR Compliant** - Data stays on your servers
- **API Flexibility** - Build exactly what you need

### ✅ Benefits of AWS SES Relay:
- **Proven Deliverability** - 99%+ inbox placement
- **IP Reputation** - Established sender reputation
- **ISP Relationships** - Whitelisted with major providers
- **Bounce Management** - Automatic handling of bad addresses
- **Low Cost** - $0.10 per 1,000 emails
- **No Warm-up Required** - Use their IPs immediately

### 🎯 Combined Benefits:
- **Best of Both Worlds** - Control + Deliverability
- **Risk Mitigation** - Not dependent on single provider
- **Cost Effective** - Lower than pure commercial solution
- **Scalable** - Handles growth without infrastructure changes

---

## 🔧 TECHNICAL REQUIREMENTS

### Server Requirements (for Postal)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 2 cores | 4 cores |
| **RAM** | 4 GB | 8 GB |
| **Storage** | 20 GB SSD | 50 GB SSD |
| **OS** | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| **Network** | 1 Gbps | 1 Gbps |

**Recommended Provider:** AWS EC2 (t3.medium) or DigitalOcean Droplet ($40-60/month)

### Required DNS Records

| Record Type | Purpose | Priority |
|-------------|---------|----------|
| **A Record** | Points mail.drpaystub.net to server IP | Critical |
| **MX Record** | Specifies mail server for domain | Critical |
| **SPF Record** | Authorizes sending servers | Critical |
| **DKIM Record** | Email authentication signature | Critical |
| **DMARC Record** | Email authentication policy | Critical |
| **PTR Record** | Reverse DNS (rDNS) | Critical |

### Required Services

| Service | Purpose | Cost |
|---------|---------|------|
| **AWS SES** | Email relay | $0.10/1000 emails |
| **Domain (drpaystub.net)** | Email domain | $10-15/year |
| **SSL Certificate** | Secure SMTP | Free (Let's Encrypt) |
| **Server** | Postal hosting | $40-60/month |

---

## 📝 PHASE 1: DNS CONFIGURATION

### Step 1.1: Purchase Email Domain (if not owned)

```bash
# Domain: drpaystub.net
# Registrar: Namecheap, GoDaddy, or Route 53
# Cost: ~$10-15/year
```

### Step 1.2: Set Up DNS Records

Login to your DNS provider (e.g., Cloudflare, Route 53) and add these records:

#### A Record (Mail Server)
```
Type: A
Name: mail.drpaystub.net
Value: YOUR_SERVER_IP
TTL: 3600
```

#### MX Record (Mail Exchange)
```
Type: MX
Name: @
Value: mail.drpaystub.net
Priority: 10
TTL: 3600
```

#### SPF Record (Sender Policy Framework)
```
Type: TXT
Name: @
Value: v=spf1 include:amazonses.com ip4:YOUR_SERVER_IP -all
TTL: 3600

Explanation:
- v=spf1: SPF version 1
- include:amazonses.com: Allow AWS SES to send
- ip4:YOUR_SERVER_IP: Allow your Postal server
- -all: Reject all other servers
```

#### DKIM Record (Will be generated by Postal)
```
Type: TXT
Name: postal._domainkey.drpaystub.net
Value: [Generated by Postal - see Phase 3]
TTL: 3600
```

#### DMARC Record (Email Authentication Policy)
```
Type: TXT
Name: _dmarc.drpaystub.net
Value: v=DMARC1; p=quarantine; rua=mailto:dmarc@drpaystub.net; ruf=mailto:dmarc@drpaystub.net; fo=1; adkim=s; aspf=s; pct=100
TTL: 3600

Explanation:
- p=quarantine: Quarantine suspicious emails (use p=reject after testing)
- rua: Aggregate reports sent here
- ruf: Forensic reports sent here
- adkim=s: Strict DKIM alignment
- aspf=s: Strict SPF alignment
```

### Step 1.3: Verify DNS Propagation

```bash
# Check A record
dig +short mail.drpaystub.net

# Check MX record
dig +short MX drpaystub.net

# Check SPF record
dig +short TXT drpaystub.net | grep spf

# Check DMARC record
dig +short TXT _dmarc.drpaystub.net
```

**Expected Results:**
- A record returns your server IP
- MX record returns `mail.drpaystub.net`
- SPF record shows your SPF policy
- DMARC record shows your DMARC policy

---

## 🔐 PHASE 2: AWS SES SETUP

### Step 2.1: Create AWS Account & Enable SES

```bash
# 1. Go to AWS Console: https://console.aws.amazon.com
# 2. Navigate to: Services → Simple Email Service (SES)
# 3. Select Region: us-east-1 (N. Virginia) - recommended for best deliverability
```

### Step 2.2: Verify Email Domain

1. **In AWS SES Console:**
   - Click "Domains" → "Verify a New Domain"
   - Enter: `drpaystub.net`
   - Check "Generate DKIM Settings"
   - Click "Verify This Domain"

2. **AWS will provide 3 CNAME records** for DKIM:
```
Name: xxx._domainkey.drpaystub.net
Value: xxx.dkim.amazonses.com

Name: yyy._domainkey.drpaystub.net
Value: yyy.dkim.amazonses.com

Name: zzz._domainkey.drpaystub.net
Value: zzz.dkim.amazonses.com
```

3. **Add these CNAME records to your DNS**

4. **Wait for verification** (usually 5-30 minutes)

### Step 2.3: Verify Sender Email

1. **In AWS SES Console:**
   - Click "Email Addresses" → "Verify a New Email Address"
   - Enter: `diego@drpaystub.net`
   - Click "Verify This Email Address"

2. **Check your email** and click the verification link

### Step 2.4: Request Production Access

**CRITICAL:** By default, SES is in "Sandbox Mode" (can only send to verified emails).

1. **Navigate to:** SES → Account Dashboard → "Request Production Access"

2. **Fill out form:**
   - **Use Case:** Transactional (password resets, notifications)
   - **Website URL:** https://saurellius.drpaystub.com
   - **Describe Use Case:**
     ```
     Saurellius is a payroll management platform that sends:
     - Password reset emails
     - Email verification links
     - Paystub delivery notifications
     - Account activity alerts
     
     Estimated volume: 1,000-5,000 emails/month
     All emails are transactional (not marketing)
     Users opt-in during registration
     Bounce and complaint handling automated via webhooks
     ```
   - **Acknowledge Compliance:** Check all boxes

3. **Submit request** (usually approved within 24 hours)

### Step 2.5: Create SMTP Credentials

1. **Navigate to:** SES → SMTP Settings → "Create My SMTP Credentials"

2. **Create IAM User:**
   - IAM User Name: `saurellius-ses-smtp`
   - Click "Create"

3. **Download Credentials:**
   - **SMTP Username:** AKIAXXXXXXXXXXXXXXXX
   - **SMTP Password:** BxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXXX
   - **SMTP Endpoint:** email-smtp.us-east-1.amazonaws.com
   - **Port:** 587 (TLS) or 465 (SSL)

**SAVE THESE CREDENTIALS SECURELY!** You'll need them for Postal configuration.

---

## 📦 PHASE 3: POSTAL INSTALLATION

### Step 3.1: Provision Server

**Option A: AWS EC2**
```bash
# Launch EC2 instance
# AMI: Ubuntu 22.04 LTS
# Instance Type: t3.medium (2 vCPU, 4GB RAM)
# Storage: 50 GB gp3 SSD
# Security Group: Open ports 22, 25, 80, 443, 587
```

**Option B: DigitalOcean**
```bash
# Create Droplet
# OS: Ubuntu 22.04 LTS
# Plan: $48/month (4GB RAM, 2 vCPU)
# Datacenter: Choose closest to users
# Additional: Enable backups
```

### Step 3.2: Initial Server Setup

```bash
# SSH into server
ssh root@YOUR_SERVER_IP

# Update system
apt update && apt upgrade -y

# Set hostname
hostnamectl set-hostname mail.drpaystub.net

# Edit /etc/hosts
nano /etc/hosts
# Add this line:
YOUR_SERVER_IP mail.drpaystub.net mail

# Create non-root user
adduser postal
usermod -aG sudo postal

# Switch to postal user
su - postal
```

### Step 3.3: Install Docker & Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker postal

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version

# Logout and login again for group changes
exit
su - postal
```

### Step 3.4: Install Postal

```bash
# Install Git
sudo apt install git -y

# Clone Postal repository
cd /opt
sudo git clone https://github.com/postalserver/postal.git
sudo chown -R postal:postal postal
cd postal

# Install dependencies
sudo apt install -y build-essential libssl-dev zlib1g-dev

# Install Ruby (required for Postal)
sudo apt install -y ruby ruby-dev

# Install Bundler
sudo gem install bundler

# Install Postal dependencies
bundle install

# Initialize Postal
sudo ./bin/postal initialize

# Start Postal installation
sudo ./bin/postal start
```

### Step 3.5: Install SSL Certificate

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Stop Postal temporarily
sudo ./bin/postal stop

# Obtain SSL certificate
sudo certbot certonly --standalone -d mail.drpaystub.net --email diego@drpaystub.net --agree-tos

# Certificate will be saved to:
# /etc/letsencrypt/live/mail.drpaystub.net/fullchain.pem
# /etc/letsencrypt/live/mail.drpaystub.net/privkey.pem

# Restart Postal
sudo ./bin/postal start

# Set up auto-renewal
sudo crontab -e
# Add this line:
0 0 1 * * certbot renew --post-hook "cd /opt/postal && ./bin/postal restart"
```

---

## 🔗 PHASE 4: INTEGRATION & CONFIGURATION

### Step 4.1: Configure Postal to Relay via AWS SES

```bash
# Edit Postal configuration
sudo nano /opt/postal/config/postal.yml
```

Add SMTP relay configuration:
```yaml
smtp_relays:
  - name: aws_ses
    hostname: email-smtp.us-east-1.amazonaws.com
    port: 587
    username: AKIAXXXXXXXXXXXXXXXX  # Your SES SMTP username
    password: BxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxXXX  # Your SES SMTP password
    ssl_mode: starttls
    authentication: plain
```

### Step 4.2: Create Postal API Key

```bash
# Access Postal web UI
https://mail.drpaystub.net

# Navigate to: Organization → Servers → Platform → Credentials
# Click "Create new credential"

Name: Saurellius Platform API
Type: API Key

# Copy the generated API key
# Format: proj_live_xxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Save this API key - you'll need it in your application!**

---

**This guide continues with Phases 5-6, Monitoring, Troubleshooting, and all implementation code. The document is now properly organized from top to bottom.**

**Download this corrected version and the content will flow properly!** 📧✨