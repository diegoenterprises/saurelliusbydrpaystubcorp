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
        try:
            self.account_id = self.sts_client.get_caller_identity()['Account']
            self.s3_bucket = f'elasticbeanstalk-{region}-{self.account_id}'
            print(f"✅ Initialized deployer for account: {self.account_id}")
            print(f"✅ S3 Bucket: {self.s3_bucket}")
        except ClientError as e:
            print(f"❌ Failed to get AWS account ID: {e}")
            raise
    
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
            '*.sqlite3',
            '*.docx', # Exclude all docx files
            '*.rtf', # Exclude all rtf files
            '*.csv', # Exclude all csv files
            '*.pages', # Exclude all pages files
            '*.txt', # Exclude all txt files
            '*.png', # Exclude all png files
            'deploy_to_beanstalk.py', # Exclude the deploy script itself
            'BundleLogs-1763314569622.zip', # Exclude the log bundle
            'CompleteImplementationStrategy&DocumentOrchestration(1).md', # Exclude the strategy document
            'AWSElasticBeanstalkDeploymentUsingBoto3SDK.md', # Exclude the guide
            'weasyprint-aws-deps.md', # Exclude the dependency guide
            'ultimate_paystub_complete.py' # Exclude the file that is likely a duplicate or older version
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
    
    def wait_for_version_processing(self, version_label, timeout=300):
        """Wait for the application version to finish processing"""
        print(f"\n⏳ Waiting for application version '{version_label}' to process (timeout: {timeout}s)...")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = self.eb_client.describe_application_versions(
                    ApplicationName=self.application_name,
                    VersionLabels=[version_label]
                )
                
                version = response['ApplicationVersions'][0]
                status = version['Status']
                
                if status == 'Processed':
                    print(f"✅ Application version '{version_label}' processed successfully.")
                    return True
                elif status == 'Failed':
                    print(f"❌ Application version '{version_label}' failed processing.")
                    return False
                
                print(f"   Current status: {status}. Waiting...")
                time.sleep(10)
                
            except Exception as e:
                print(f"⚠️  Error checking version status: {str(e)}")
                time.sleep(10)
        
        print(f"\n⏰ Application version processing timeout reached ({timeout}s)")
        return False

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
    
    def wait_for_deployment(self, timeout=660):
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
    
    def deploy(self):
        """Main deployment workflow"""
        try:
            zip_path = self.create_deployment_package()
            self.ensure_s3_bucket_exists()
            s3_key = self.upload_to_s3(zip_path)
            version_label = self.create_application_version(s3_key)
            
            # CRITICAL FIX: Wait for version to process before deploying
            if not self.wait_for_version_processing(version_label, timeout=600):
                print("\n❌ Deployment failed because application version did not process successfully.")
                return
                
            self.deploy_to_environment(version_label)
            self.wait_for_deployment()
            print("\n✨ Deployment process finished.")
        except Exception as e:
            print(f"\n❌ CRITICAL DEPLOYMENT FAILURE: {str(e)}")
            
if __name__ == '__main__':
    # Default parameters for Saurellius Platform
    deployer = BeanstalkDeployer(
        application_name='saurellius-platform',
        environment_name='saurellius-prod-env2',
        region='us-east-1' # Change to your region
    )
    deployer.deploy()
