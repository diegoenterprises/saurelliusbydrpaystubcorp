# AWS Elastic Beanstalk Deployment Using Boto3 SDK

Complete guide for deploying to AWS Elastic Beanstalk using the boto3 Python SDK instead of AWS CLI.

---

## Prerequisites

```bash
pip install boto3
```

---

## Complete Deployment Script

Save this as `deploy_to_beanstalk.py`:

```python
#!/usr/bin/env python3

import boto3
import zipfile
import os
import time
from datetime import datetime
from botocore.exceptions import ClientError

class BeanstalkDeployer:
    def __init__(self, 
                 application_name='saurellius-platform',
                 environment_name='saurellius-prod-env2',
                 region='us-east-1'):
        """Initialize AWS clients and configuration"""
        self.application_name = application_name
        self.environment_name = environment_name
        self.region = region
        
        # Initialize AWS clients
        self.s3_client = boto3.client('s3', region_name=region)
        self.eb_client = boto3.client('elasticbeanstalk', region_name=region)
        self.sts_client = boto3.client('sts', region_name=region)
        
        # Get account ID for S3 bucket name
        self.account_id = self.sts_client.get_caller_identity()['Account']
        self.s3_bucket = f'elasticbeanstalk-{region}-{self.account_id}'
        
        print(f"✅ Initialized deployer for account: {self.account_id}")
        print(f"✅ S3 Bucket: {self.s3_bucket}")
    
    def create_deployment_package(self, source_dir='/home/ubuntu/saurelliusbydrpaystubcorp'):
        """Create a ZIP file of the application"""
        print(f"\n📦 Creating deployment package from: {source_dir}")
        
        zip_path = '/tmp/saurellius-app.zip'
        
        # Directories and files to exclude
        exclude_patterns = [
            '__pycache__',
            '*.pyc',
            '.git',
            '.gitignore',
            'venv',
            'env',
            '.env',
            '.DS_Store',
            '*.log',
            'node_modules',
            '.pytest_cache',
            '.coverage',
            'htmlcov',
            '*.sqlite3'
        ]
        
        def should_exclude(path):
            """Check if path should be excluded"""
            for pattern in exclude_patterns:
                if pattern in path:
                    return True
            return False
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            file_count = 0
            for root, dirs, files in os.walk(source_dir):
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if not should_exclude(d)]
                
                for file in files:
                    if should_exclude(file):
                        continue
                    
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
                    file_count += 1
        
        zip_size = os.path.getsize(zip_path) / (1024 * 1024)  # Size in MB
        print(f"✅ Created deployment package: {zip_path}")
        print(f"✅ Package size: {zip_size:.2f} MB")
        print(f"✅ Files included: {file_count}")
        
        return zip_path
    
    def ensure_s3_bucket_exists(self):
        """Create S3 bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.s3_bucket)
            print(f"✅ S3 bucket exists: {self.s3_bucket}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                print(f"📦 Creating S3 bucket: {self.s3_bucket}")
                if self.region == 'us-east-1':
                    self.s3_client.create_bucket(Bucket=self.s3_bucket)
                else:
                    self.s3_client.create_bucket(
                        Bucket=self.s3_bucket,
                        CreateBucketConfiguration={'LocationConstraint': self.region}
                    )
                print(f"✅ Created S3 bucket: {self.s3_bucket}")
            else:
                raise
    
    def upload_to_s3(self, zip_path):
        """Upload deployment package to S3"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        s3_key = f'deployments/{self.application_name}-{timestamp}.zip'
        
        print(f"\n☁️  Uploading to S3...")
        print(f"   Bucket: {self.s3_bucket}")
        print(f"   Key: {s3_key}")
        
        try:
            self.s3_client.upload_file(
                zip_path, 
                self.s3_bucket, 
                s3_key,
                ExtraArgs={'ServerSideEncryption': 'AES256'}
            )
            print(f"✅ Uploaded to S3: s3://{self.s3_bucket}/{s3_key}")
            return s3_key
        except Exception as e:
            print(f"❌ Failed to upload to S3: {str(e)}")
            raise
    
    def create_application_version(self, s3_key):
        """Create a new application version in Elastic Beanstalk"""
        version_label = f"v{int(time.time())}"
        
        print(f"\n🏷️  Creating application version: {version_label}")
        
        try:
            self.eb_client.create_application_version(
                ApplicationName=self.application_name,
                VersionLabel=version_label,
                Description=f"Deployed via boto3 at {datetime.now().isoformat()}",
                SourceBundle={
                    'S3Bucket': self.s3_bucket,
                    'S3Key': s3_key
                },
                AutoCreateApplication=False,
                Process=True
            )
            print(f"✅ Created application version: {version_label}")
            return version_label
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterValue':
                print(f"⚠️  Application '{self.application_name}' doesn't exist. Creating it...")
                self.eb_client.create_application(
                    ApplicationName=self.application_name,
                    Description='Saurellius Paystub Platform'
                )
                # Retry version creation
                return self.create_application_version(s3_key)
            else:
                raise
    
    def deploy_to_environment(self, version_label):
        """Deploy the application version to the environment"""
        print(f"\n🚀 Deploying to environment: {self.environment_name}")
        
        try:
            response = self.eb_client.update_environment(
                ApplicationName=self.application_name,
                EnvironmentName=self.environment_name,
                VersionLabel=version_label
            )
            
            print(f"✅ Deployment initiated!")
            print(f"   Environment ID: {response['EnvironmentId']}")
            print(f"   Status: {response['Status']}")
            print(f"   Health: {response.get('Health', 'Unknown')}")
            
            return response
        except ClientError as e:
            print(f"❌ Deployment failed: {str(e)}")
            raise
    
    def wait_for_deployment(self, timeout=600):
        """Wait for the deployment to complete"""
        print(f"\n⏳ Waiting for deployment to complete (timeout: {timeout}s)...")
        
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < timeout:
            try:
                response = self.eb_client.describe_environments(
                    ApplicationName=self.application_name,
                    EnvironmentNames=[self.environment_name]
                )
                
                if not response['Environments']:
                    print(f"❌ Environment not found: {self.environment_name}")
                    return False
                
                env = response['Environments'][0]
                status = env['Status']
                health = env.get('Health', 'Unknown')
                
                if status != last_status:
                    print(f"   Status: {status} | Health: {health}")
                    last_status = status
                
                if status == 'Ready':
                    if health in ['Green', 'Yellow']:
                        print(f"\n✅ Deployment completed successfully!")
                        print(f"   Environment URL: {env.get('CNAME', 'N/A')}")
                        print(f"   Health: {health}")
                        return True
                    else:
                        print(f"\n⚠️  Deployment completed but health is: {health}")
                        return False
                
                if status in ['Terminated', 'Terminating']:
                    print(f"\n❌ Environment is terminating/terminated")
                    return False
                
                time.sleep(10)
                
            except Exception as e:
                print(f"⚠️  Error checking status: {str(e)}")
                time.sleep(10)
        
        print(f"\n⏰ Deployment timeout reached ({timeout}s)")
        return False
    
    def get_environment_status(self):
        """Get current environment status"""
        try:
            response = self.eb_client.describe_environments(
                ApplicationName=self.application_name,
                EnvironmentNames=[self.environment_name]
            )
            
            if response['Environments']:
                env = response['Environments'][0]
                print(f"\n📊 Current Environment Status:")
                print(f"   Name: {env['EnvironmentName']}")
                print(f"   Status: {env['Status']}")
                print(f"   Health: {env.get('Health', 'Unknown')}")
                print(f"   URL: {env.get('CNAME', 'N/A')}")
                print(f"   Version: {env.get('VersionLabel', 'Unknown')}")
                return env
            else:
                print(f"❌ Environment not found: {self.environment_name}")
                return None
        except Exception as e:
            print(f"❌ Error getting environment status: {str(e)}")
            return None
    
    def update_environment_variables(self, env_vars):
        """Update environment variables"""
        print(f"\n🔧 Updating environment variables...")
        
        option_settings = [
            {
                'Namespace': 'aws:elasticbeanstalk:application:environment',
                'OptionName': key,
                'Value': value
            }
            for key, value in env_vars.items()
        ]
        
        try:
            self.eb_client.update_environment(
                ApplicationName=self.application_name,
                EnvironmentName=self.environment_name,
                OptionSettings=option_settings
            )
            print(f"✅ Updated {len(env_vars)} environment variables")
        except Exception as e:
            print(f"❌ Failed to update environment variables: {str(e)}")
            raise
    
    def full_deploy(self, source_dir='/home/ubuntu/saurelliusbydrpaystubcorp', 
                    wait=True, env_vars=None):
        """Complete deployment process"""
        print("=" * 70)
        print("🚀 ELASTIC BEANSTALK DEPLOYMENT")
        print("=" * 70)
        
        try:
            # Step 1: Create deployment package
            zip_path = self.create_deployment_package(source_dir)
            
            # Step 2: Ensure S3 bucket exists
            self.ensure_s3_bucket_exists()
            
            # Step 3: Upload to S3
            s3_key = self.upload_to_s3(zip_path)
            
            # Step 4: Create application version
            version_label = self.create_application_version(s3_key)
            
            # Step 5: Update environment variables if provided
            if env_vars:
                self.update_environment_variables(env_vars)
            
            # Step 6: Deploy to environment
            self.deploy_to_environment(version_label)
            
            # Step 7: Wait for deployment
            if wait:
                success = self.wait_for_deployment()
                if success:
                    self.get_environment_status()
                    return True
                else:
                    return False
            else:
                print("\n⚠️  Deployment initiated but not waiting for completion")
                return True
                
        except Exception as e:
            print(f"\n❌ Deployment failed: {str(e)}")
            return False
        finally:
            # Cleanup
            if os.path.exists('/tmp/saurellius-app.zip'):
                os.remove('/tmp/saurellius-app.zip')
                print("\n🧹 Cleaned up temporary files")


def main():
    """Main deployment function"""
    
    # Configuration
    APPLICATION_NAME = 'saurellius-platform'
    ENVIRONMENT_NAME = 'saurellius-prod-env2'
    REGION = 'us-east-1'
    SOURCE_DIR = '/home/ubuntu/saurelliusbydrpaystubcorp'
    
    # Environment variables to set (optional)
    ENV_VARS = {
        'DEBUG': 'False',
        'ALLOWED_HOSTS': 'your-domain.com,elasticbeanstalk.com',
        # AWS Credentials
        'AWS_ACCESS_KEY_ID': '[YOUR_AWS_ACCESS_KEY_ID]',
        'AWS_SECRET_ACCESS_KEY': '[YOUR_AWS_SECRET_ACCESS_KEY]',
        # Stripe API Keys
        'STRIPE_PUBLISHABLE_KEY': '[YOUR_STRIPE_PUBLISHABLE_KEY]',
        'STRIPE_SECRET_KEY': '[YOUR_STRIPE_SECRET_KEY]',
        # Weather API Key
        'OPENWEATHER_API_KEY': '[YOUR_OPENWEATHER_API_KEY]',
        # IP Intelligence API Key
        'IP_INTELLIGENCE_API_KEY': '[YOUR_IP_INTELLIGENCE_API_KEY]',
    }
    
    # Initialize deployer
    deployer = BeanstalkDeployer(
        application_name=APPLICATION_NAME,
        environment_name=ENVIRONMENT_NAME,
        region=REGION
    )
    
    # Check current status
    deployer.get_environment_status()
    
    # Perform deployment
    success = deployer.full_deploy(
        source_dir=SOURCE_DIR,
        wait=True,  # Wait for deployment to complete
        env_vars=ENV_VARS  # Set to None if you don't want to update env vars
    )
    
    if success:
        print("\n" + "=" * 70)
        print("✅ DEPLOYMENT SUCCESSFUL!")
        print("=" * 70)
        exit(0)
    else:
        print("\n" + "=" * 70)
        print("❌ DEPLOYMENT FAILED!")
        print("=" * 70)
        exit(1)


if __name__ == "__main__":
    main()
```

---

## AWS Credentials Setup

### Option 1: Environment Variables (Recommended)

```bash
export AWS_ACCESS_KEY_ID="[YOUR_AWS_ACCESS_KEY_ID]"
export AWS_SECRET_ACCESS_KEY="[YOUR_AWS_SECRET_ACCESS_KEY]"
export AWS_DEFAULT_REGION="us-east-1"
```

### Option 2: AWS Credentials File

Create `~/.aws/credentials`:

```ini
[default]
aws_access_key_id = [YOUR_AWS_ACCESS_KEY_ID]
aws_secret_access_key = [YOUR_AWS_SECRET_ACCESS_KEY]
```

Create `~/.aws/config`:

```ini
[default]
region = us-east-1
output = json
```

### Option 3: IAM Role (for EC2 instances)

If running on EC2, attach an IAM role with these permissions:
- `AWSElasticBeanstalkFullAccess`
- `AmazonS3FullAccess`

---

## Usage Examples

### Basic Deployment

```bash
# Set credentials
export AWS_ACCESS_KEY_ID="[YOUR_AWS_ACCESS_KEY_ID]"
export AWS_SECRET_ACCESS_KEY="[YOUR_AWS_SECRET_ACCESS_KEY]"
export AWS_DEFAULT_REGION="us-east-1"

# Run deployment
python deploy_to_beanstalk.py
```

### Custom Configuration

```python
from deploy_to_beanstalk import BeanstalkDeployer

# Initialize with custom settings
deployer = BeanstalkDeployer(
    application_name='my-app',
    environment_name='my-env',
    region='us-west-2'
)

# Deploy with custom environment variables
deployer.full_deploy(
    source_dir='/path/to/your/app',
    wait=True,
    env_vars={
        'DATABASE_URL': 'postgresql://localhost/mydb',
        'SECRET_KEY': 'super-secret-key',
        'DEBUG': 'False'
    }
)
```

### Deploy Without Waiting

```python
deployer = BeanstalkDeployer()
deployer.full_deploy(wait=False)  # Returns immediately after initiating deployment
```

### Check Status Only

```python
deployer = BeanstalkDeployer()
deployer.get_environment_status()
```

### Update Environment Variables Only

```python
deployer = BeanstalkDeployer()
deployer.update_environment_variables({
    'NEW_VAR': 'new-value',
    'ANOTHER_VAR': 'another-value'
})
```

---

## Required IAM Permissions

Your AWS credentials must have these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "elasticbeanstalk:*",
                "s3:*",
                "sts:GetCallerIdentity"
            ],
            "Resource": "*"
        }
    ]
}
```

---

## Troubleshooting

### "NoSuchBucket" Error

The script automatically creates the S3 bucket if it doesn't exist. If you still see this error:

```python
# Manually create bucket
deployer = BeanstalkDeployer()
deployer.ensure_s3_bucket_exists()
```

### "Application does not exist" Error

The script will auto-create the application. If manual creation is needed:

```python
import boto3

eb = boto3.client('elasticbeanstalk')
eb.create_application(
    ApplicationName='saurellius-platform',
    Description='Saurellius Paystub Platform'
)
```

### Environment Not Found

List all environments:

```python
import boto3

eb = boto3.client('elasticbeanstalk')
response = eb.describe_environments(ApplicationName='saurellius-platform')

for env in response['Environments']:
    print(f"Environment: {env['EnvironmentName']}")
    print(f"Status: {env['Status']}")
    print(f"Health: {env.get('Health', 'Unknown')}")
    print("---")
```

### Deployment Stuck

Check events for debugging:

```python
import boto3

eb = boto3.client('elasticbeanstalk')
events = eb.describe_events(
    ApplicationName='saurellius-platform',
    EnvironmentName='saurellius-prod-env2',
    MaxRecords=20
)

for event in events['Events']:
    print(f"{event['EventDate']}: {event['Message']}")
```

---

## Advantages Over AWS CLI

1. **Programmatic Control** - Full Python control over deployment logic
2. **Better Error Handling** - Catch and handle specific errors
3. **Custom Workflows** - Add pre/post deployment steps
4. **No CLI Installation** - Just needs boto3
5. **Credential Flexibility** - Multiple ways to authenticate
6. **Status Monitoring** - Built-in deployment progress tracking
7. **Automated Packaging** - Intelligent file exclusion
8. **Reusable** - Import as module in other scripts

---

## Integration with CI/CD

### GitHub Actions

```yaml
name: Deploy to Elastic Beanstalk

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install boto3
      
      - name: Deploy to Beanstalk
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: python deploy_to_beanstalk.py
```

### GitLab CI

```yaml
deploy:
  stage: deploy
  image: python:3.11
  before_script:
    - pip install boto3
  script:
    - python deploy_to_beanstalk.py
  only:
    - main
  variables:
    AWS_ACCESS_KEY_ID: $AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY: $AWS_SECRET_ACCESS_KEY
```

---

## Next Steps

1. Save the script as `deploy_to_beanstalk.py`
2. Update the configuration variables in `main()`
3. Set your AWS credentials
4. Run: `python deploy_to_beanstalk.py`
5. Monitor the deployment progress in terminal

---

**Last Updated**: November 2025