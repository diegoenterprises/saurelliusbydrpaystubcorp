# Saurellius Platform - Backend Integration Guide

## 🎯 Overview

This guide connects the **Jony Ive-inspired frontend** to your existing **AWS Elastic Beanstalk backend** running on `saurellius.drpaystub.com`.

---

## 📁 Repository Structure

```
saurellius-platform/
├── application.py                 # Flask main app
├── models.py                      # SQLAlchemy models
├── routes/
│   ├── auth.py                   # Authentication routes
│   ├── paystubs.py               # Paystub generation routes
│   ├── employees.py              # Employee management routes
│   └── dashboard.py              # Dashboard API routes
├── utils/
│   ├── SAURELLIUS2026.py  # PDF generator (DO NOT MODIFY)
│   ├── tax_calculator.py         # Tax calculation engine
│   └── verification.py           # QR code and verification
├── static/
│   ├── css/
│   ├── js/
│   └── index.html                # NEW: Frontend UI (from artifact)
└── requirements.txt
```

---

## 🔌 API Endpoints to Implement

### 1. **Dashboard Summary** 
**Route:** `GET /api/dashboard/summary`

```python
# routes/dashboard.py
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User, Paystub, Employee
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/api/dashboard/summary', methods=['GET'])
@jwt_required()
def get_dashboard_summary():
    user_id = get_jwt_identity()
    
    # Get stats
    total_paystubs = Paystub.query.filter_by(user_id=user_id).count()
    
    ytd_data = db.session.query(
        func.sum(Paystub.gross_pay).label('ytd_gross'),
        func.sum(Paystub.net_pay).label('ytd_net'),
        func.sum(Paystub.federal_tax).label('ytd_federal'),
        func.sum(Paystub.social_security_tax).label('ytd_ss'),
        func.sum(Paystub.medicare_tax).label('ytd_medicare'),
        func.sum(Paystub.state_tax).label('ytd_state')
    ).filter_by(user_id=user_id).first()
    
    # Get active employees
    employees = Employee.query.filter_by(user_id=user_id, status='active').all()
    
    # Recent activity
    recent_paystubs = Paystub.query.filter_by(user_id=user_id)\
        .order_by(Paystub.created_at.desc())\
        .limit(5)\
        .all()
    
    # Rewards
    user = User.query.get(user_id)
    
    return jsonify({
        'total_paystubs': total_paystubs,
        'ytd_gross': float(ytd_data.ytd_gross or 0),
        'ytd_net': float(ytd_data.ytd_net or 0),
        'ytd_taxes': {
            'federal': float(ytd_data.ytd_federal or 0),
            'social_security': float(ytd_data.ytd_ss or 0),
            'medicare': float(ytd_data.ytd_medicare or 0),
            'state': float(ytd_data.ytd_state or 0)
        },
        'employees': [{
            'id': emp.id,
            'name': f"{emp.first_name} {emp.last_name}",
            'job_title': emp.job_title,
            'state': emp.state
        } for emp in employees],
        'recent_activity': [{
            'type': 'paystub_generated',
            'employee_name': stub.employee.full_name,
            'amount': float(stub.net_pay),
            'date': stub.created_at.isoformat()
        } for stub in recent_paystubs],
        'rewards': {
            'points': user.reward_points,
            'tier': user.reward_tier,
            'lifetime_points': user.total_lifetime_points
        }
    }), 200
```

---

### 2. **Generate Paystub (Connected to SAURELLIUS2026.py)**
**Route:** `POST /api/paystubs/generate-complete`

```python
# routes/paystubs.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Paystub, Employee, db
from utils.SAURELLIUS2026 import generate_snappt_compliant_paystub
from utils.tax_calculator import calculate_all_taxes
from utils.verification import generate_verification_id, generate_document_hash
import boto3
from datetime import datetime

paystubs_bp = Blueprint('paystubs', __name__)

@paystubs_bp.route('/api/paystubs/generate-complete', methods=['POST'])
@jwt_required()
def generate_complete_paystub():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    # Get employee
    employee = Employee.query.filter_by(
        id=data['employee_id'],
        user_id=user_id
    ).first_or_404()
    
    # Calculate earnings
    regular_pay = data['earnings']['regular_hours'] * data['earnings']['hourly_rate']
    overtime_pay = data['earnings']['overtime_hours'] * data['earnings']['hourly_rate'] * 1.5
    bonus = data['earnings'].get('bonus', 0)
    gross_pay = regular_pay + overtime_pay + bonus
    
    # Calculate taxes using tax_calculator.py
    tax_results = calculate_all_taxes(
        gross_pay=gross_pay,
        state=employee.state,
        filing_status=employee.filing_status,
        allowances=employee.federal_allowances,
        ytd_gross=employee.ytd_gross_pay,
        ytd_ss_wages=employee.ytd_ss_wages
    )
    
    # Calculate deductions
    total_deductions = (
        tax_results['federal_income_tax'] +
        tax_results['social_security_tax'] +
        tax_results['medicare_tax'] +
        tax_results['state_income_tax'] +
        tax_results.get('state_disability_tax', 0) +
        tax_results.get('local_income_tax', 0) +
        data['deductions'].get('contribution_401k', 0) +
        data['deductions'].get('health_insurance', 0) +
        data['deductions'].get('dental_insurance', 0)
    )
    
    net_pay = gross_pay - total_deductions
    
    # Generate verification
    verification_id = generate_verification_id()
    
    # Create paystub record
    paystub = Paystub(
        user_id=user_id,
        employee_id=employee.id,
        pay_date=data['pay_info']['pay_date'],
        period_start=data['pay_info']['period_start'],
        period_end=data['pay_info']['period_end'],
        
        # Earnings
        regular_hours=data['earnings']['regular_hours'],
        regular_pay=regular_pay,
        overtime_hours=data['earnings']['overtime_hours'],
        overtime_pay=overtime_pay,
        bonus=bonus,
        gross_pay=gross_pay,
        
        # Taxes
        federal_income_tax=tax_results['federal_income_tax'],
        social_security_tax=tax_results['social_security_tax'],
        medicare_tax=tax_results['medicare_tax'],
        state_income_tax=tax_results['state_income_tax'],
        state_disability_tax=tax_results.get('state_disability_tax', 0),
        local_income_tax=tax_results.get('local_income_tax', 0),
        
        # Deductions
        deduction_401k=data['deductions'].get('contribution_401k', 0),
        deduction_health=data['deductions'].get('health_insurance', 0),
        deduction_dental=data['deductions'].get('dental_insurance', 0),
        
        # Totals
        total_taxes=sum([
            tax_results['federal_income_tax'],
            tax_results['social_security_tax'],
            tax_results['medicare_tax'],
            tax_results['state_income_tax'],
            tax_results.get('state_disability_tax', 0),
            tax_results.get('local_income_tax', 0)
        ]),
        total_deductions=total_deductions,
        net_pay=net_pay,
        
        # Verification
        verification_id=verification_id,
        verification_status='verified',
        
        # Status
        status='finalized'
    )
    
    db.session.add(paystub)
    db.session.flush()  # Get paystub ID
    
    # Prepare data for PDF generator (SAURELLIUS2026.py)
    pdf_data = {
        'company': {
            'name': employee.company.name,
            'address': employee.company.address
        },
        'employee': {
            'name': employee.full_name,
            'state': employee.state,
            'ssn_masked': f"XXX-XX-{employee.ssn_encrypted[-4:]}"
        },
        'pay_info': {
            'period_start': data['pay_info']['period_start'],
            'period_end': data['pay_info']['period_end'],
            'pay_date': data['pay_info']['pay_date']
        },
        'earnings': [
            {
                'description': 'Regular Earnings',
                'rate': data['earnings']['hourly_rate'],
                'hours': data['earnings']['regular_hours'],
                'current': regular_pay,
                'ytd': employee.ytd_gross_pay + regular_pay
            },
            {
                'description': 'Overtime Earnings',
                'rate': data['earnings']['hourly_rate'] * 1.5,
                'hours': data['earnings']['overtime_hours'],
                'current': overtime_pay,
                'ytd': employee.ytd_overtime_pay + overtime_pay
            }
        ],
        'deductions': [
            {'description': 'Federal Tax', 'type': 'Statutory', 'current': tax_results['federal_income_tax'], 'ytd': employee.ytd_federal_tax + tax_results['federal_income_tax']},
            {'description': 'Social Security', 'type': 'Statutory', 'current': tax_results['social_security_tax'], 'ytd': employee.ytd_ss_tax + tax_results['social_security_tax']},
            {'description': 'Medicare', 'type': 'Statutory', 'current': tax_results['medicare_tax'], 'ytd': employee.ytd_medicare_tax + tax_results['medicare_tax']},
            {'description': 'State Income Tax', 'type': 'Statutory', 'current': tax_results['state_income_tax'], 'ytd': employee.ytd_state_tax + tax_results['state_income_tax']}
        ],
        'totals': {
            'gross_pay': gross_pay,
            'gross_pay_ytd': employee.ytd_gross_pay + gross_pay,
            'net_pay': net_pay,
            'net_pay_ytd': employee.ytd_net_pay + net_pay,
            'amount_words': number_to_words(net_pay)
        },
        'check_info': {
            'number': f"{paystub.id:04d}"
        }
    }
    
    # Generate PDF using SAURELLIUS2026.py
    pdf_bytes = generate_snappt_compliant_paystub(
        paystub_data=pdf_data,
        template_id="eusotrip_original",
        output_path=f"/tmp/paystub_{paystub.id}.pdf"
    )
    
    # Upload to S3
    s3_client = boto3.client('s3')
    s3_bucket = os.environ.get('S3_BUCKET')
    s3_key = f"paystubs/{user_id}/{paystub.id}.pdf"
    
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=pdf_bytes,
        ContentType='application/pdf'
    )
    
    # Generate signed URL
    pdf_url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': s3_bucket, 'Key': s3_key},
        ExpiresIn=604800  # 7 days
    )
    
    # Update paystub record
    paystub.s3_bucket = s3_bucket
    paystub.s3_key = s3_key
    paystub.pdf_url = pdf_url
    paystub.document_hash = generate_document_hash(pdf_bytes)
    
    # Update employee YTD
    employee.ytd_gross_pay += gross_pay
    employee.ytd_net_pay += net_pay
    employee.ytd_federal_tax += tax_results['federal_income_tax']
    employee.ytd_ss_tax += tax_results['social_security_tax']
    employee.ytd_medicare_tax += tax_results['medicare_tax']
    employee.ytd_state_tax += tax_results['state_income_tax']
    employee.ytd_ss_wages += gross_pay
    
    # Award points
    user = User.query.get(user_id)
    user.reward_points += 10
    user.total_lifetime_points += 10
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'paystub_id': paystub.id,
        'verification_id': verification_id,
        'pdf_url': pdf_url,
        'net_pay': float(net_pay),
        'gross_pay': float(gross_pay),
        'points_earned': 10
    }), 201
```

---

### 3. **YTD Continuation**
**Route:** `GET /api/paystubs/continuation/<employee_id>`

```python
@paystubs_bp.route('/api/paystubs/continuation/<int:employee_id>', methods=['GET'])
@jwt_required()
def get_ytd_continuation(employee_id):
    user_id = get_jwt_identity()
    
    employee = Employee.query.filter_by(
        id=employee_id,
        user_id=user_id
    ).first_or_404()
    
    # Get last paystub
    last_paystub = Paystub.query.filter_by(
        employee_id=employee_id
    ).order_by(Paystub.pay_date.desc()).first()
    
    # Calculate next pay date based on frequency
    next_pay_date = calculate_next_pay_date(
        last_pay_date=last_paystub.pay_date if last_paystub else employee.hire_date,
        frequency=employee.pay_frequency
    )
    
    # Calculate average values from last 3 paystubs
    recent_stubs = Paystub.query.filter_by(
        employee_id=employee_id
    ).order_by(Paystub.pay_date.desc()).limit(3).all()
    
    avg_hours = sum([s.regular_hours for s in recent_stubs]) / len(recent_stubs) if recent_stubs else 80
    avg_federal_tax = sum([s.federal_income_tax for s in recent_stubs]) / len(recent_stubs) if recent_stubs else 0
    avg_state_tax = sum([s.state_income_tax for s in recent_stubs]) / len(recent_stubs) if recent_stubs else 0
    
    return jsonify({
        'ytd_summary': {
            'ytd_gross': float(employee.ytd_gross_pay),
            'ytd_net': float(employee.ytd_net_pay),
            'ytd_federal_tax': float(employee.ytd_federal_tax),
            'ytd_ss_tax': float(employee.ytd_ss_tax),
            'ytd_medicare_tax': float(employee.ytd_medicare_tax),
            'ytd_state_tax': float(employee.ytd_state_tax),
            'ytd_ss_wages': float(employee.ytd_ss_wages),
            'avg_federal_tax': float(avg_federal_tax),
            'avg_state_tax': float(avg_state_tax)
        },
        'next_pay_date': next_pay_date.isoformat(),
        'suggested_hours': float(avg_hours),
        'last_paystub_date': last_paystub.pay_date.isoformat() if last_paystub else None
    }), 200
```

---

### 4. **Add Employee**
**Route:** `POST /api/employees`

```python
# routes/employees.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Employee, db
from cryptography.fernet import Fernet
import os

employees_bp = Blueprint('employees', __name__)

@employees_bp.route('/api/employees', methods=['POST'])
@jwt_required()
def add_employee():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    # Encrypt SSN
    fernet = Fernet(os.environ.get('ENCRYPTION_KEY'))
    encrypted_ssn = fernet.encrypt(data['ssn'].encode()).decode()
    
    employee = Employee(
        user_id=user_id,
        
        # Personal
        first_name=data['first_name'],
        last_name=data['last_name'],
        ssn_encrypted=encrypted_ssn,
        email=data['email'],
        phone=data.get('phone'),
        date_of_birth=data['date_of_birth'],
        
        # Address
        address_street=data['address']['street'],
        address_city=data['address']['city'],
        address_state=data['address']['state'],
        address_zip=data['address']['zip'],
        
        # Employment
        job_title=data['employment']['job_title'],
        department=data['employment'].get('department'),
        hire_date=data['employment']['hire_date'],
        pay_rate=data['employment']['pay_rate'],
        pay_frequency=data['employment']['pay_frequency'],
        employment_type=data['employment']['employment_type'],
        
        # Tax
        filing_status=data['tax_info']['filing_status'],
        federal_allowances=data['tax_info']['allowances'],
        federal_additional_withholding=data['tax_info']['additional_withholding'],
        
        # Status
        status='active'
    )
    
    db.session.add(employee)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'employee_id': employee.id,
        'message': f'Employee {employee.full_name} added successfully'
    }), 201
```

---

### 5. **Get Employees List**
**Route:** `GET /api/employees`

```python
@employees_bp.route('/api/employees', methods=['GET'])
@jwt_required()
def get_employees():
    user_id = get_jwt_identity()
    
    employees = Employee.query.filter_by(
        user_id=user_id,
        status='active'
    ).all()
    
    return jsonify({
        'employees': [{
            'id': emp.id,
            'first_name': emp.first_name,
            'last_name': emp.last_name,
            'full_name': emp.full_name,
            'job_title': emp.job_title,
            'department': emp.department,
            'state': emp.state,
            'pay_rate': float(emp.pay_rate),
            'pay_frequency': emp.pay_frequency,
            'hire_date': emp.hire_date.isoformat()
        } for emp in employees]
    }), 200
```

---

### 6. **Get Paystubs History**
**Route:** `GET /api/paystubs/history`

```python
@paystubs_bp.route('/api/paystubs/history', methods=['GET'])
@jwt_required()
def get_paystubs_history():
    user_id = get_jwt_identity()
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    paystubs = Paystub.query.filter_by(user_id=user_id)\
        .order_by(Paystub.pay_date.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()
    
    return jsonify({
        'paystubs': [{
            'id': stub.id,
            'employee_id': stub.employee_id,
            'employee_name': stub.employee.full_name,
            'pay_date': stub.pay_date.isoformat(),
            'gross_pay': float(stub.gross_pay),
            'net_pay': float(stub.net_pay),
            'verification_id': stub.verification_id,
            'verification_status': stub.verification_status,
            'pdf_url': stub.pdf_url,
            'created_at': stub.created_at.isoformat()
        } for stub in paystubs],
        'total': Paystub.query.filter_by(user_id=user_id).count()
    }), 200
```

---

## 🚀 Deployment Steps

### 1. **Update application.py**

```python
# application.py
from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS

app = Flask(__name__, static_folder='static')
CORS(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
app.config['S3_BUCKET'] = os.environ.get('S3_BUCKET')

db = SQLAlchemy(app)
jwt = JWTManager(app)

# Register blueprints
from routes.auth import auth_bp
from routes.paystubs import paystubs_bp
from routes.employees import employees_bp
from routes.dashboard import dashboard_bp

app.register_blueprint(auth_bp)
app.register_blueprint(paystubs_bp)
app.register_blueprint(employees_bp)
app.register_blueprint(dashboard_bp)

# Serve frontend
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    app.run()
```

### 2. **Update requirements.txt**

```txt
Flask==2.3.0
Flask-SQLAlchemy==3.0.5
Flask-JWT-Extended==4.5.2
Flask-CORS==4.0.0
psycopg2-binary==2.9.6
boto3==1.28.0
cryptography==41.0.3
WeasyPrint==59.0
qrcode==7.4.2
Pillow==10.0.0
```

### 3. **Deploy to Elastic Beanstalk**

```bash
# From your local machine
cd saurellius-platform

# Copy the frontend HTML to static folder
cp path/to/saurellius-dashboard.html static/index.html

# Update API_BASE_URL in index.html
# Change: const API_BASE_URL = 'https://your-api...';
# To: const API_BASE_URL = 'https://saurellius.drpaystub.com';

# Initialize EB if not already done
eb init -p python-3.11 saurellius-platform --region us-east-1

# Deploy
eb deploy SaurelliusEnvFinal

# Check status
eb status
eb logs
```

### 4. **Environment Variables**

Set these in Elastic Beanstalk console:

```
DATABASE_URL=postgresql://username:password@rds-endpoint/saurellius-db-new
JWT_SECRET_KEY=your-super-secret-jwt-key
ENCRYPTION_KEY=your-fernet-encryption-key
S3_BUCKET=paystub-storage-your-account-id
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

---

## 🧪 Testing

### Test Dashboard API
```bash
curl https://saurellius.drpaystub.com/api/dashboard/summary \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Test Paystub Generation
```bash
curl -X POST https://saurellius.drpaystub.com/api/paystubs/generate-complete \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
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

---

## ✅ Success Checklist

- [ ] Frontend deployed to `/static/index.html`
- [ ] API endpoints implemented in Flask routes
- [ ] `SAURELLIUS2026.py` connected to paystub generation
- [ ] S3 bucket configured for PDF storage
- [ ] JWT authentication working
- [ ] Database models match frontend expectations
- [ ] CORS enabled for frontend-backend communication
- [ ] Environment variables set in Elastic Beanstalk
- [ ] SSL certificate active on `saurellius.drpaystub.com`
- [ ] Frontend `API_BASE_URL` pointing to production domain

---

## 🎨 Frontend Features Connected

✅ **Dashboard** → `/api/dashboard/summary`  
✅ **Generate Paystub** → `/api/paystubs/generate-complete`  
✅ **Add Employee** → `/api/employees` (POST)  
✅ **View Employees** → `/api/employees` (GET)  
✅ **Previous Paystubs** → `/api/paystubs/history`  
✅ **YTD Continuation** → `/api/paystubs/continuation/<id>`  
✅ **Reports** → `/api/reports/<type>`  
✅ **Settings** → `/api/settings` (PUT)

---

## 🔥 Next Steps

1. **Deploy frontend** to `/static/index.html`
2. **Implement missing routes** (dashboard, paystubs, employees)
3. **Test paystub generation** with `SAURELLIUS2026.py`
4. **Configure S3 bucket** for PDF storage
5. **Update frontend API_BASE_URL** to production domain
6. **Test end-to-end flow**: Login → Generate Paystub → Download PDF

---

**Your legendary Jony Ive-inspired frontend is ready to connect! 🚀**