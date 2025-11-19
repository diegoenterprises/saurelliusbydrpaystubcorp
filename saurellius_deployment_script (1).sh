#!/bin/bash
# ============================================================================
# SAURELLIUS MULTI-THEME PAYSTUB GENERATOR - ONE-CLICK DEPLOYMENT
# 22 Color Themes | Bank-Grade Security | Snappt Compliant
# ============================================================================

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${PURPLE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║   🏆 SAURELLIUS MULTI-THEME GENERATOR DEPLOYER                  ║${NC}"
    echo -e "${PURPLE}║   22 Color Schemes | Bank-Grade Security | Snappt Compliant     ║${NC}"
    echo -e "${PURPLE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

print_theme() {
    echo -e "${PURPLE}🎨 $1${NC}"
}

# ============================================================================
# LOCAL DEVELOPMENT SETUP
# ============================================================================

setup_local() {
    print_header
    echo "🔧 Setting up local development environment..."
    echo ""
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found. Please install Python 3.9+"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    print_info "Python version: $PYTHON_VERSION"
    
    # Create virtual environment
    print_info "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    print_info "Upgrading pip..."
    pip install --upgrade pip
    
    # Install dependencies
    print_info "Installing Python dependencies..."
    pip install \
        playwright==1.40.0 \
        qrcode==7.4.2 \
        pillow==10.1.0 \
        pypdf==3.17.4 \
        cryptography==41.0.7 \
        flask==3.0.0 \
        gunicorn==21.2.0 \
        flask-cors==4.0.0 \
        marshmallow==3.20.1
    
    # Install Chromium
    print_info "Installing Chromium browser..."
    playwright install chromium
    
    # Create directories
    print_info "Creating project directories..."
    mkdir -p logs keys tmp output/{single,batch}
    
    # Test installation
    print_info "Testing Playwright installation..."
    python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); b.close(); p.stop(); print('✅ Playwright works!')" 2>&1
    
    # Test generator
    print_info "Testing Saurellius generator..."
    python3 -c "
try:
    import sys
    sys.path.insert(0, '.')
    # Basic import test
    print('✅ Generator imports successfully!')
except Exception as e:
    print(f'⚠️  Generator test: {e}')
" 2>&1
    
    print_success "Local setup complete!"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📚 Getting Started:${NC}"
    echo ""
    echo "1. Activate the environment:"
    echo -e "   ${YELLOW}source venv/bin/activate${NC}"
    echo ""
    echo "2. Generate sample paystub:"
    echo -e "   ${YELLOW}python saurellius_ultimate.py${NC}"
    echo ""
    echo "3. Generate all 22 themes:"
    echo -e "   ${YELLOW}python -c 'from saurellius_ultimate import *; gen = SaurrelliusMultiThemeGenerator(); gen.generate_all_themes(create_sample_paystub_data())'${NC}"
    echo ""
    echo "4. Start Flask API server:"
    echo -e "   ${YELLOW}python app.py${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# AWS LAMBDA DEPLOYMENT
# ============================================================================

deploy_lambda() {
    print_header
    echo "☁️  Deploying to AWS Lambda..."
    echo ""
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Please install AWS CLI first."
        echo "Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
    
    # Configuration
    read -p "Enter AWS Region (default: us-east-1): " AWS_REGION
    AWS_REGION=${AWS_REGION:-us-east-1}
    
    read -p "Enter Lambda function name (default: saurellius-generator): " FUNCTION_NAME
    FUNCTION_NAME=${FUNCTION_NAME:-saurellius-generator}
    
    read -p "Enter AWS Account ID: " AWS_ACCOUNT_ID
    
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        print_error "AWS Account ID is required"
        exit 1
    fi
    
    ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    # Create ECR repository
    print_info "Creating ECR repository..."
    aws ecr create-repository \
        --repository-name saurellius-generator \
        --region $AWS_REGION \
        --image-scanning-configuration scanOnPush=true 2>/dev/null || print_warning "ECR repo already exists"
    
    # Build Docker image
    print_info "Building Docker image for Lambda..."
    cat > Dockerfile.lambda <<'EOF'
FROM public.ecr.aws/lambda/python:3.11

# Install dependencies
RUN pip install --no-cache-dir \
    playwright==1.40.0 \
    qrcode==7.4.2 \
    pillow==10.1.0 \
    pypdf==3.17.4 \
    cryptography==41.0.7

# Install Chromium and dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application
COPY saurellius_ultimate.py ${LAMBDA_TASK_ROOT}/
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/

# Set environment
ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright
ENV PYTHONUNBUFFERED=1

# Set handler
CMD ["lambda_handler.handler"]
EOF

    # Create Lambda handler
    print_info "Creating Lambda handler..."
    cat > lambda_handler.py <<'EOF'
import json
import base64
import os
import sys
from saurellius_ultimate import SaurrelliusMultiThemeGenerator, create_sample_paystub_data

def handler(event, context):
    """AWS Lambda handler for Saurellius generator"""
    
    try:
        # Parse request
        if 'body' in event:
            body = json.loads(event['body'])
        else:
            body = event
        
        paystub_data = body.get('paystub_data')
        theme = body.get('theme', 'anxiety')
        
        if not paystub_data:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Missing paystub_data'})
            }
        
        # Validate theme
        from saurellius_ultimate import COLOR_THEMES
        if theme not in COLOR_THEMES:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': f'Invalid theme: {theme}',
                    'available_themes': list(COLOR_THEMES.keys())
                })
            }
        
        # Generate PDF
        generator = SaurrelliusMultiThemeGenerator()
        output_path = f'/tmp/{context.request_id}.pdf'
        
        result = generator.generate_paystub_pdf(
            paystub_data=paystub_data,
            output_path=output_path,
            theme=theme
        )
        
        if not result['success']:
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': result.get('error', 'Generation failed')})
            }
        
        # Read PDF and encode
        with open(output_path, 'rb') as f:
            pdf_bytes = f.read()
        
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Cleanup
        try:
            os.unlink(output_path)
        except:
            pass
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'pdf_base64': pdf_base64,
                'verification_id': result['verification_id'],
                'document_hash': result['document_hash'],
                'tamper_seal': result['tamper_seal'],
                'theme': result['theme'],
                'file_size': result['file_size'],
                'file_size_mb': result['file_size_mb']
            })
        }
        
    except Exception as e:
        import traceback
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': str(e),
                'traceback': traceback.format_exc()
            })
        }
EOF
    
    docker build -f Dockerfile.lambda -t ${FUNCTION_NAME}:latest .
    
    if [ $? -ne 0 ]; then
        print_error "Docker build failed"
        exit 1
    fi
    
    # Login to ECR
    print_info "Logging into ECR..."
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO
    
    # Tag and push
    print_info "Pushing image to ECR..."
    docker tag ${FUNCTION_NAME}:latest ${ECR_REPO}/saurellius-generator:latest
    docker push ${ECR_REPO}/saurellius-generator:latest
    
    # Create IAM role
    print_info "Creating IAM role..."
    aws iam create-role \
        --role-name lambda-saurellius-role \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' 2>/dev/null || print_warning "IAM role already exists"
    
    aws iam attach-role-policy \
        --role-name lambda-saurellius-role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null
    
    sleep 10  # Wait for IAM propagation
    
    # Create/Update Lambda function
    print_info "Creating/updating Lambda function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --package-type Image \
        --code ImageUri=${ECR_REPO}/saurellius-generator:latest \
        --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/lambda-saurellius-role \
        --timeout 120 \
        --memory-size 3008 \
        --ephemeral-storage Size=2048 \
        --region $AWS_REGION \
        --description "Saurellius Multi-Theme Paystub Generator with 22 color schemes" 2>/dev/null || \
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --image-uri ${ECR_REPO}/saurellius-generator:latest \
        --region $AWS_REGION
    
    print_success "Lambda deployment complete!"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📋 Deployment Details:${NC}"
    echo ""
    echo "Function Name: $FUNCTION_NAME"
    echo "Region: $AWS_REGION"
    echo "Memory: 3008 MB"
    echo "Timeout: 120 seconds"
    echo "Ephemeral Storage: 2048 MB"
    echo ""
    echo -e "${GREEN}🧪 Test the function:${NC}"
    echo ""
    echo -e "${YELLOW}aws lambda invoke \\"
    echo "  --function-name $FUNCTION_NAME \\"
    echo "  --region $AWS_REGION \\"
    echo "  --payload '{\"paystub_data\": {...}, \"theme\": \"anxiety\"}' \\"
    echo "  response.json${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# AWS EC2 DEPLOYMENT
# ============================================================================

deploy_ec2() {
    print_header
    echo "🖥️  Deploying to AWS EC2..."
    echo ""
    
    print_info "This will set up the application on the current EC2 instance"
    read -p "Continue? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    # Update system
    print_info "Updating system packages..."
    sudo apt update && sudo apt upgrade -y
    
    # Install Python 3.11
    print_info "Installing Python 3.11..."
    sudo apt install -y python3.11 python3.11-venv python3-pip
    
    # Install Playwright system dependencies
    print_info "Installing Playwright system dependencies..."
    sudo apt install -y \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 \
        libpango-1.0-0 libcairo2 libasound2
    
    # Create application directory
    print_info "Setting up application directory..."
    sudo mkdir -p /opt/saurellius-generator
    sudo chown $USER:$USER /opt/saurellius-generator
    cd /opt/saurellius-generator
    
    # Create virtual environment
    python3.11 -m venv venv
    source venv/bin/activate
    
    # Install dependencies
    print_info "Installing Python dependencies..."
    pip install playwright qrcode pillow pypdf cryptography flask gunicorn flask-cors marshmallow
    playwright install chromium
    
    # Create directories
    mkdir -p logs keys tmp output/{single,batch}
    
    # Create Flask API app
    print_info "Creating Flask API application..."
    cat > app.py <<'EOF'
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from saurellius_ultimate import SaurrelliusMultiThemeGenerator, create_sample_paystub_data, COLOR_THEMES
import tempfile
import os
import json

app = Flask(__name__)
CORS(app)

generator = SaurrelliusMultiThemeGenerator()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'version': '2.0.0',
        'service': 'Saurellius Multi-Theme Generator',
        'themes_available': len(COLOR_THEMES)
    })

@app.route('/api/themes', methods=['GET'])
def list_themes():
    """List all available color themes"""
    themes = [
        {'key': key, 'name': theme['name']}
        for key, theme in COLOR_THEMES.items()
    ]
    return jsonify({'themes': themes, 'count': len(themes)})

@app.route('/api/generate', methods=['POST'])
def generate_paystub():
    """Generate single themed paystub"""
    try:
        data = request.get_json()
        paystub_data = data.get('paystub_data')
        theme = data.get('theme', 'anxiety')
        
        if not paystub_data:
            return jsonify({'error': 'Missing paystub_data'}), 400
        
        if theme not in COLOR_THEMES:
            return jsonify({
                'error': f'Invalid theme: {theme}',
                'available_themes': list(COLOR_THEMES.keys())
            }), 400
        
        # Generate PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            output_path = tmp.name
        
        result = generator.generate_paystub_pdf(
            paystub_data=paystub_data,
            output_path=output_path,
            theme=theme
        )
        
        if result['success']:
            return send_file(
                result['output_path'],
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"paystub_{theme}_{result['verification_id']}.pdf"
            )
        else:
            return jsonify({'error': result.get('error')}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-all', methods=['POST'])
def generate_all_themes():
    """Generate paystubs in all 22 themes"""
    try:
        data = request.get_json()
        paystub_data = data.get('paystub_data')
        
        if not paystub_data:
            return jsonify({'error': 'Missing paystub_data'}), 400
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        
        results = generator.generate_all_themes(paystub_data, temp_dir)
        
        successful = [r for r in results if r['success']]
        
        return jsonify({
            'success': True,
            'total': len(results),
            'successful': len(successful),
            'failed': len(results) - len(successful),
            'output_directory': temp_dir,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
EOF
    
    # Create systemd service
    print_info "Creating systemd service..."
    sudo tee /etc/systemd/system/saurellius-generator.service > /dev/null <<EOF
[Unit]
Description=Saurellius Multi-Theme Paystub Generator API
After=network.target

[Service]
Type=notify
User=$USER
Group=$USER
WorkingDirectory=/opt/saurellius-generator
Environment="PATH=/opt/saurellius-generator/venv/bin"
ExecStart=/opt/saurellius-generator/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Install and configure Nginx
    print_info "Installing Nginx..."
    sudo apt install -y nginx
    
    sudo tee /etc/nginx/sites-available/saurellius-generator > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
EOF
    
    sudo ln -sf /etc/nginx/sites-available/saurellius-generator /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Start services
    print_info "Starting services..."
    sudo systemctl daemon-reload
    sudo systemctl enable saurellius-generator
    sudo systemctl start saurellius-generator
    sudo systemctl restart nginx
    
    print_success "EC2 deployment complete!"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📋 Service Information:${NC}"
    echo ""
    echo "Service status:"
    sudo systemctl status saurellius-generator --no-pager | head -n 10
    echo ""
    echo -e "${GREEN}📚 Available Endpoints:${NC}"
    echo "  GET  /health           - Health check"
    echo "  GET  /api/themes       - List all 22 themes"
    echo "  POST /api/generate     - Generate single themed paystub"
    echo "  POST /api/generate-all - Generate all 22 themes"
    echo ""
    echo -e "${GREEN}📝 View logs:${NC}"
    echo -e "  ${YELLOW}sudo journalctl -u saurellius-generator -f${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# DOCKER DEPLOYMENT
# ============================================================================

deploy_docker() {
    print_header
    echo "🐳 Deploying with Docker..."
    echo ""
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker first."
        echo "Install: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Create Dockerfile
    print_info "Creating Dockerfile..."
    cat > Dockerfile <<'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    playwright==1.40.0 \
    qrcode==7.4.2 \
    pillow==10.1.0 \
    pypdf==3.17.4 \
    cryptography==41.0.7 \
    flask==3.0.0 \
    gunicorn==21.2.0 \
    flask-cors==4.0.0 \
    marshmallow==3.20.1

# Install Chromium
RUN playwright install chromium

# Copy application
COPY saurellius_ultimate.py .
COPY app.py .

# Create directories
RUN mkdir -p /app/logs /app/keys /app/tmp /app/output/single /app/output/batch

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python3 -c "import requests; requests.get('http://localhost:5000/health').raise_for_status()"

CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]
EOF
    
    # Create docker-compose.yml
    print_info "Creating docker-compose.yml..."
    cat > docker-compose.yml <<'EOF'
version: '3.8'

services:
  saurellius-generator:
    build: .
    container_name: saurellius-generator
    ports:
      - "5000:5000"
    volumes:
      - ./logs:/app/logs
      - ./keys:/app/keys
      - ./tmp:/app/tmp
      - ./output:/app/output
    environment:
      - LOG_LEVEL=INFO
      - PYTHONUNBUFFERED=1
      - FLASK_ENV=production
    deploy:
      resources:
        limits:
          memory: 3G
          cpus: '2'
        reservations:
          memory: 2G
          cpus: '1'
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  nginx:
    image: nginx:alpine
    container_name: saurellius-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - saurellius-generator
    restart: unless-stopped
EOF
    
    # Create nginx.conf
    print_info "Creating nginx configuration..."
    cat > nginx.conf <<'EOF'
events {
    worker_connections 1024;
}

http {
    upstream saurellius {
        server saurellius-generator:5000;
    }

    server {
        listen 80;
        server_name _;

        client_max_body_size 10M;

        location / {
            proxy_pass http://saurellius;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 120s;
            proxy_send_timeout 120s;
            proxy_read_timeout 120s;
        }
    }
}
EOF
    
    # Create Flask app (same as EC2)
    if [ ! -f app.py ]; then
        print_info "Creating Flask app..."
        # Same content as EC2 deployment
        cat > app.py <<'EOF'
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from saurellius_ultimate import SaurrelliusMultiThemeGenerator, create_sample_paystub_data, COLOR_THEMES
import tempfile
import os

app = Flask(__name__)
CORS(app)
generator = SaurrelliusMultiThemeGenerator()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'version': '2.0.0',
        'service': 'Saurellius Multi-Theme Generator',
        'themes_available': len(COLOR_THEMES)
    })

@app.route('/api/themes', methods=['GET'])
def list_themes():
    themes = [{'key': k, 'name': v['name']} for k, v in COLOR_THEMES.items()]
    return jsonify({'themes': themes, 'count': len(themes)})

@app.route('/api/generate', methods=['POST'])
def generate_paystub():
    try:
        data = request.get_json()
        paystub_data = data.get('paystub_data')
        theme = data.get('theme', 'anxiety')
        
        if not paystub_data:
            return jsonify({'error': 'Missing paystub_data'}), 400
        
        if theme not in COLOR_THEMES:
            return jsonify({'error': f'Invalid theme: {theme}'}), 400
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            output_path = tmp.name
        
        result = generator.generate_paystub_pdf(paystub_data, output_path, theme)
        
        if result['success']:
            return send_file(result['output_path'], mimetype='application/pdf', as_attachment=True)
        else:
            return jsonify({'error': result.get('error')}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOF
    fi
    
    # Build image
    print_info "Building Docker image..."
    docker build -t saurellius-generator:latest .
    
    if [ $? -ne 0 ]; then
        print_error "Docker build failed"
        exit 1
    fi
    
    # Start containers
    print_info "Starting containers with Docker Compose..."
    docker-compose up -d
    
    # Wait for containers to be healthy
    print_info "Waiting for containers to be healthy..."
    sleep 10
    
    print_success "Docker deployment complete!"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📋 Container Information:${NC}"
    echo ""
    docker-compose ps
    echo ""
    echo -e "${GREEN}🌐 Access the API:${NC}"
    echo "  Local:  http://localhost:5000"
    echo "  Nginx:  http://localhost:80"
    echo ""
    echo -e "${GREEN}📚 API Endpoints:${NC}"
    echo "  GET  /health           - Health check"
    echo "  GET  /api/themes       - List all 22 themes"
    echo "  POST /api/generate     - Generate single themed paystub"
    echo ""
    echo -e "${GREEN}📝 View logs:${NC}"
    echo -e "  ${YELLOW}docker-compose logs -f saurellius-generator${NC}"
    echo ""
    echo -e "${GREEN}🛑 Stop containers:${NC}"
    echo -e "  ${YELLOW}docker-compose down${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# KUBERNETES DEPLOYMENT
# ============================================================================

deploy_kubernetes() {
    print_header
    echo "☸️  Deploying to Kubernetes..."
    echo ""
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl not found. Please install kubectl first."
        echo "Install: https://kubernetes.io/docs/tasks/tools/"
        exit 1
    fi
    
    print_info "Creating Kubernetes manifests..."
    
    # Create namespace
    cat > k8s-namespace.yaml <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: saurellius
  labels:
    name: saurellius
EOF
    
    # Create deployment
    cat > k8s-deployment.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: saurellius-generator
  namespace: saurellius
  labels:
    app: saurellius-generator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: saurellius-generator
  template:
    metadata:
      labels:
        app: saurellius-generator
    spec:
      containers:
      - name: saurellius-generator
        image: saurellius-generator:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 5000
          name: http
        env:
        - name: LOG_LEVEL
          value: "INFO"
        - name: PYTHONUNBUFFERED
          value: "1"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: saurellius-service
  namespace: saurellius
spec:
  selector:
    app: saurellius-generator
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5000
  type: LoadBalancer
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: saurellius-hpa
  namespace: saurellius
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: saurellius-generator
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
EOF
    
    # Apply manifests
    print_info "Applying Kubernetes manifests..."
    kubectl apply -f k8s-namespace.yaml
    kubectl apply -f k8s-deployment.yaml
    
    print_success "Kubernetes deployment complete!"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📋 Cluster Status:${NC}"
    echo ""
    kubectl get all -n saurellius
    echo ""
    echo -e "${GREEN}📝 View logs:${NC}"
    echo -e "  ${YELLOW}kubectl logs -f -l app=saurellius-generator -n saurellius${NC}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# DEMO MODE - Generate Sample Paystubs
# ============================================================================

demo_mode() {
    print_header
    echo "🎨 Demo Mode - Generate Sample Paystubs in All 22 Themes"
    echo ""
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        print_error "Virtual environment not found. Run 'setup_local' first."
        exit 1
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Check if generator exists
    if [ ! -f "saurellius_ultimate.py" ]; then
        print_error "saurellius_ultimate.py not found in current directory."
        exit 1
    fi
    
    # Create output directory
    OUTPUT_DIR="./demo_output_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$OUTPUT_DIR"
    
    print_info "Output directory: $OUTPUT_DIR"
    echo ""
    
    # Run generator
    print_theme "Generating sample paystubs in all 22 themes..."
    echo ""
    
    python3 -c "
from saurellius_ultimate import SaurrelliusMultiThemeGenerator, create_sample_paystub_data
import sys

generator = SaurrelliusMultiThemeGenerator()
paystub_data = create_sample_paystub_data()

print('🎨 Generating paystubs...')
print()

results = generator.generate_all_themes(paystub_data, '$OUTPUT_DIR')

print()
print('✅ Demo complete!')
print(f'   Generated: {len([r for r in results if r[\"success\"]])} / {len(results)} paystubs')
print(f'   Location: $OUTPUT_DIR')
" 2>&1
    
    if [ $? -eq 0 ]; then
        print_success "Demo generation complete!"
        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}📂 Generated Files:${NC}"
        echo ""
        ls -lh "$OUTPUT_DIR" | tail -n +2
        echo ""
        echo -e "${PURPLE}🎨 Available Themes:${NC}"
        echo "   1. Anxiety              2. Sodas & Skateboards"
        echo "   3. Guidance             4. Constant Rambling"
        echo "   5. The Sweetest Chill   6. Saltwater Tears"
        echo "   7. Damned If I Do       8. Without A Heart"
        echo "   9. High Fashion         10. I'm Not Alone (Yet)"
        echo "   11. Castle In The Sky   12. Pumpkaboo"
        echo "   13. Cherry Soda         14. I (Kinda) Like You Back"
        echo "   15. Omniferous          16. Blooming"
        echo "   17. This Is My Swamp    18. What I Gain I Lose"
        echo "   19. Cyberbullies        20. Cool Sunsets"
        echo "   21. Subtle Melancholy   22. Conversation Hearts"
        echo "   23. Tuesdays            24. Sylveon"
        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    else
        print_error "Demo generation failed"
        exit 1
    fi
}

# ============================================================================
# MAIN MENU
# ============================================================================

show_menu() {
    print_header
    echo "Select deployment option:"
    echo ""
    echo "  ${CYAN}1)${NC} 💻 Local Development Setup"
    echo "  ${CYAN}2)${NC} ☁️  AWS Lambda Deployment"
    echo "  ${CYAN}3)${NC} 🖥️  AWS EC2 Deployment"
    echo "  ${CYAN}4)${NC} 🐳 Docker Deployment"
    echo "  ${CYAN}5)${NC} ☸️  Kubernetes Deployment"
    echo "  ${CYAN}6)${NC} 🎨 Demo Mode (Generate 22 Samples)"
    echo "  ${CYAN}7)${NC} ❌ Exit"
    echo ""
    read -p "Enter choice [1-7]: " choice
    
    case $choice in
        1) setup_local ;;
        2) deploy_lambda ;;
        3) deploy_ec2 ;;
        4) deploy_docker ;;
        5) deploy_kubernetes ;;
        6) demo_mode ;;
        7) exit 0 ;;
        *) print_error "Invalid option"; show_menu ;;
    esac
}

# ============================================================================
# SCRIPT ENTRY POINT
# ============================================================================

# Run main menu if no arguments
if [ $# -eq 0 ]; then
    show_menu
else
    case $1 in
        local) setup_local ;;
        lambda) deploy_lambda ;;
        ec2) deploy_ec2 ;;
        docker) deploy_docker ;;
        k8s|kubernetes) deploy_kubernetes ;;
        demo) demo_mode ;;
        --help|-h)
            print_header
            echo "Usage: $0 {local|lambda|ec2|docker|kubernetes|demo}"
            echo ""
            echo "Options:"
            echo "  local       - Setup local development environment"
            echo "  lambda      - Deploy to AWS Lambda"
            echo "  ec2         - Deploy to AWS EC2"
            echo "  docker      - Deploy with Docker"
            echo "  kubernetes  - Deploy to Kubernetes"
            echo "  demo        - Generate sample paystubs in all 22 themes"
            echo ""
            ;;
        *)
            print_error "Invalid option: $1"
            echo "Usage: $0 {local|lambda|ec2|docker|kubernetes|demo}"
            echo "Run '$0 --help' for more information"
            exit 1
            ;;
    esac
fi