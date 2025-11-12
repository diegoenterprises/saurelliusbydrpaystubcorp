#!/usr/bin/env python3
"""
Saurellius Platform - Employee Management Routes
Complete CRUD operations with encryption
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Employee, User, AuditLog
from cryptography.fernet import Fernet
from datetime import datetime, timezone
import os
import re

employees_bp = Blueprint('employees', __name__)

# Encryption setup
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key()
    print(f"⚠️  Generated new encryption key: {ENCRYPTION_KEY.decode()}")
    print("⚠️  Set ENCRYPTION_KEY environment variable!")

fernet = Fernet(ENCRYPTION_KEY if isinstance(ENCRYPTION_KEY, bytes) else ENCRYPTION_KEY.encode())

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_ssn(ssn):
    """Validate SSN format"""
    # Remove any non-digits
    ssn_clean = re.sub(r'[^\d]', '', ssn)
    
    if len(ssn_clean) != 9:
        return False, "SSN must be 9 digits"
    
    # Check for invalid patterns
    if ssn_clean == '000000000' or ssn_clean == '999999999':
        return False, "Invalid SSN"
    
    if ssn_clean[0:3] == '000' or ssn_clean[3:5] == '00' or ssn_clean[5:9] == '0000':
        return False, "Invalid SSN format"
    
    return True, ssn_clean


def encrypt_data(data):
    """Encrypt sensitive data"""
    return fernet.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data):
    """Decrypt sensitive data"""
    try:
        return fernet.decrypt(encrypted_data.encode()).decode()
    except:
        return None


# ============================================================================
# GET ALL EMPLOYEES
# ============================================================================

@employees_bp.route('/api/employees', methods=['GET'])
@jwt_required()
def get_employees():
    """
    Get all employees for user
    
    GET /api/employees?status=active&limit=50&offset=0
    """
    try:
        user_id = get_jwt_identity()
        
        # Query parameters
        status = request.args.get('status', 'active')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '')
        
        # Build query
        query = Employee.query.filter_by(user_id=user_id)
        
        if status and status != 'all':
            query = query.filter_by(status=status)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                db.or_(
                    Employee.first_name.ilike(search_pattern),
                    Employee.last_name.ilike(search_pattern),
                    Employee.email.ilike(search_pattern),
                    Employee.job_title.ilike(search_pattern)
                )
            )
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        employees = query.order_by(Employee.last_name, Employee.first_name)\
            .limit(limit)\
            .offset(offset)\
            .all()
        
        return jsonify({
            'success': True,
            'employees': [{
                'id': emp.id,
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'full_name': emp.full_name,
                'email': emp.email,
                'phone': emp.phone,
                'job_title': emp.job_title,
                'department': emp.department,
                'state': emp.address_state,
                'pay_rate': float(emp.pay_rate),
                'pay_frequency': emp.pay_frequency,
                'employment_type': emp.employment_type,
                'hire_date': emp.hire_date.isoformat(),
                'status': emp.status,
                'ytd_gross': float(emp.ytd_gross_pay),
                'ytd_net': float(emp.ytd_net_pay)
            } for emp in employees],
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
        
    except Exception as e:
        print(f"Get employees error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get employees'
        }), 500


# ============================================================================
# GET SINGLE EMPLOYEE
# ============================================================================

@employees_bp.route('/api/employees/<int:employee_id>', methods=['GET'])
@jwt_required()
def get_employee(employee_id):
    """Get single employee details"""
    try:
        user_id = get_jwt_identity()
        
        employee = Employee.query.filter_by(
            id=employee_id,
            user_id=user_id
        ).first()
        
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
        
        # Decrypt SSN (last 4 only)
        ssn_decrypted = decrypt_data(employee.ssn_encrypted)
        ssn_masked = f"XXX-XX-{ssn_decrypted[-4:]}" if ssn_decrypted else "XXX-XX-XXXX"
        
        return jsonify({
            'success': True,
            'employee': {
                'id': employee.id,
                'personal': {
                    'first_name': employee.first_name,
                    'middle_name': employee.middle_name,
                    'last_name': employee.last_name,
                    'ssn_masked': ssn_masked,
                    'email': employee.email,
                    'phone': employee.phone,
                    'date_of_birth': employee.date_of_birth.isoformat()
                },
                'address': {
                    'street': employee.address_street,
                    'street2': employee.address_street2,
                    'city': employee.address_city,
                    'state': employee.address_state,
                    'zip': employee.address_zip
                },
                'employment': {
                    'job_title': employee.job_title,
                    'department': employee.department,
                    'employee_id': employee.employee_id,
                    'hire_date': employee.hire_date.isoformat(),
                    'employment_type': employee.employment_type,
                    'employment_status': employee.employment_status,
                    'pay_rate': float(employee.pay_rate),
                    'pay_frequency': employee.pay_frequency,
                    'salary_or_hourly': employee.salary_or_hourly
                },
                'tax_info': {
                    'filing_status': employee.filing_status,
                    'federal_allowances': employee.federal_allowances,
                    'federal_additional_withholding': float(employee.federal_additional_withholding),
                    'state_allowances': employee.state_allowances,
                    'state_additional_withholding': float(employee.state_additional_withholding),
                    'local_jurisdiction': employee.local_jurisdiction
                },
                'ytd': {
                    'gross_pay': float(employee.ytd_gross_pay),
                    'net_pay': float(employee.ytd_net_pay),
                    'federal_tax': float(employee.ytd_federal_tax),
                    'state_tax': float(employee.ytd_state_tax),
                    'ss_tax': float(employee.ytd_ss_tax),
                    'medicare_tax': float(employee.ytd_medicare_tax)
                },
                'benefits': {
                    '401k_percent': float(employee.contribution_401k_percent),
                    '401k_fixed': float(employee.contribution_401k_fixed),
                    'health_insurance': float(employee.health_insurance_deduction),
                    'dental_insurance': float(employee.dental_insurance_deduction),
                    'vision_insurance': float(employee.vision_insurance_deduction)
                },
                'pto': {
                    'vacation_balance': float(employee.vacation_hours_balance),
                    'sick_balance': float(employee.sick_hours_balance),
                    'personal_balance': float(employee.personal_hours_balance),
                    'accrual_rate': float(employee.pto_accrual_rate)
                },
                'status': employee.status,
                'created_at': employee.created_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        print(f"Get employee error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get employee'
        }), 500


# ============================================================================
# CREATE EMPLOYEE
# ============================================================================

@employees_bp.route('/api/employees', methods=['POST'])
@jwt_required()
def create_employee():
    """
    Create new employee
    
    POST /api/employees
    Body: {
        "personal": {
            "first_name": "John",
            "last_name": "Doe",
            "ssn": "123456789",
            "email": "john.doe@example.com",
            "phone": "+1-555-123-4567",
            "date_of_birth": "1990-01-15"
        },
        "address": {
            "street": "123 Main St",
            "city": "Los Angeles",
            "state": "CA",
            "zip": "90001"
        },
        "employment": {
            "job_title": "Software Engineer",
            "department": "Engineering",
            "hire_date": "2025-01-01",
            "pay_rate": 45.00,
            "pay_frequency": "biweekly",
            "employment_type": "full_time"
        },
        "tax_info": {
            "filing_status": "single",
            "federal_allowances": 1
        }
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Validate required fields
        if not data.get('personal') or not data.get('address') or not data.get('employment'):
            return jsonify({
                'success': False,
                'message': 'Missing required sections'
            }), 400
        
        personal = data['personal']
        address = data['address']
        employment = data['employment']
        tax_info = data.get('tax_info', {})
        
        # Validate SSN
        is_valid_ssn, ssn_result = validate_ssn(personal.get('ssn', ''))
        if not is_valid_ssn:
            return jsonify({
                'success': False,
                'message': ssn_result
            }), 400
        
        # Encrypt SSN
        encrypted_ssn = encrypt_data(ssn_result)
        
        # Create employee
        employee = Employee(
            user_id=user_id,
            
            # Personal
            first_name=personal['first_name'],
            middle_name=personal.get('middle_name'),
            last_name=personal['last_name'],
            ssn_encrypted=encrypted_ssn,
            email=personal.get('email'),
            phone=personal.get('phone'),
            date_of_birth=personal['date_of_birth'],
            
            # Address
            address_street=address['street'],
            address_street2=address.get('street2'),
            address_city=address['city'],
            address_state=address['state'],
            address_zip=address['zip'],
            
            # Employment
            job_title=employment['job_title'],
            department=employment.get('department'),
            employee_id=employment.get('employee_id'),
            hire_date=employment['hire_date'],
            employment_type=employment.get('employment_type', 'full_time'),
            employment_status='active',
            pay_rate=employment['pay_rate'],
            pay_frequency=employment.get('pay_frequency', 'biweekly'),
            salary_or_hourly=employment.get('salary_or_hourly', 'hourly'),
            
            # Tax info
            filing_status=tax_info.get('filing_status', 'single'),
            federal_allowances=tax_info.get('federal_allowances', 0),
            federal_additional_withholding=tax_info.get('federal_additional_withholding', 0),
            state_allowances=tax_info.get('state_allowances', 0),
            state_additional_withholding=tax_info.get('state_additional_withholding', 0),
            local_jurisdiction=tax_info.get('local_jurisdiction'),
            
            # Benefits (optional)
            contribution_401k_percent=data.get('benefits', {}).get('401k_percent', 0),
            health_insurance_deduction=data.get('benefits', {}).get('health_insurance', 0),
            dental_insurance_deduction=data.get('benefits', {}).get('dental_insurance', 0),
            
            # PTO
            pto_accrual_rate=data.get('pto', {}).get('accrual_rate', 0.0384),
            
            # Status
            status='active'
        )
        
        db.session.add(employee)
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='employee_created',
            resource_type='employee',
            resource_id=employee.id,
            changes={
                'name': employee.full_name,
                'job_title': employee.job_title
            },
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Employee {employee.full_name} created successfully',
            'employee_id': employee.id,
            'employee': {
                'id': employee.id,
                'full_name': employee.full_name,
                'job_title': employee.job_title,
                'state': employee.address_state
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Create employee error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to create employee',
            'error': str(e)
        }), 500


# ============================================================================
# UPDATE EMPLOYEE
# ============================================================================

@employees_bp.route('/api/employees/<int:employee_id>', methods=['PUT'])
@jwt_required()
def update_employee(employee_id):
    """Update employee information"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        employee = Employee.query.filter_by(
            id=employee_id,
            user_id=user_id
        ).first()
        
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
        
        # Track changes for audit
        changes = {}
        
        # Update personal info
        if 'personal' in data:
            personal = data['personal']
            if 'first_name' in personal:
                employee.first_name = personal['first_name']
                changes['first_name'] = personal['first_name']
            if 'middle_name' in personal:
                employee.middle_name = personal['middle_name']
            if 'last_name' in personal:
                employee.last_name = personal['last_name']
                changes['last_name'] = personal['last_name']
            if 'email' in personal:
                employee.email = personal['email']
            if 'phone' in personal:
                employee.phone = personal['phone']
        
        # Update address
        if 'address' in data:
            address = data['address']
            if 'street' in address:
                employee.address_street = address['street']
            if 'street2' in address:
                employee.address_street2 = address['street2']
            if 'city' in address:
                employee.address_city = address['city']
            if 'state' in address:
                employee.address_state = address['state']
                changes['state'] = address['state']
            if 'zip' in address:
                employee.address_zip = address['zip']
        
        # Update employment
        if 'employment' in data:
            employment = data['employment']
            if 'job_title' in employment:
                employee.job_title = employment['job_title']
                changes['job_title'] = employment['job_title']
            if 'department' in employment:
                employee.department = employment['department']
            if 'pay_rate' in employment:
                old_rate = employee.pay_rate
                employee.pay_rate = employment['pay_rate']
                changes['pay_rate'] = f"{old_rate} -> {employment['pay_rate']}"
            if 'pay_frequency' in employment:
                employee.pay_frequency = employment['pay_frequency']
            if 'employment_status' in employment:
                employee.employment_status = employment['employment_status']
        
        # Update tax info
        if 'tax_info' in data:
            tax_info = data['tax_info']
            if 'filing_status' in tax_info:
                employee.filing_status = tax_info['filing_status']
            if 'federal_allowances' in tax_info:
                employee.federal_allowances = tax_info['federal_allowances']
            if 'federal_additional_withholding' in tax_info:
                employee.federal_additional_withholding = tax_info['federal_additional_withholding']
            if 'state_allowances' in tax_info:
                employee.state_allowances = tax_info['state_allowances']
            if 'local_jurisdiction' in tax_info:
                employee.local_jurisdiction = tax_info['local_jurisdiction']
        
        # Update benefits
        if 'benefits' in data:
            benefits = data['benefits']
            if '401k_percent' in benefits:
                employee.contribution_401k_percent = benefits['401k_percent']
            if 'health_insurance' in benefits:
                employee.health_insurance_deduction = benefits['health_insurance']
            if 'dental_insurance' in benefits:
                employee.dental_insurance_deduction = benefits['dental_insurance']
            if 'vision_insurance' in benefits:
                employee.vision_insurance_deduction = benefits['vision_insurance']
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='employee_updated',
            resource_type='employee',
            resource_id=employee.id,
            changes=changes,
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Employee {employee.full_name} updated successfully',
            'employee': {
                'id': employee.id,
                'full_name': employee.full_name,
                'job_title': employee.job_title
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Update employee error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to update employee',
            'error': str(e)
        }), 500


# ============================================================================
# DELETE EMPLOYEE (Soft Delete)
# ============================================================================

@employees_bp.route('/api/employees/<int:employee_id>', methods=['DELETE'])
@jwt_required()
def delete_employee(employee_id):
    """Soft delete employee"""
    try:
        user_id = get_jwt_identity()
        
        employee = Employee.query.filter_by(
            id=employee_id,
            user_id=user_id
        ).first()
        
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
        
        # Soft delete
        employee.status = 'terminated'
        employee.deleted_at = datetime.now(timezone.utc)
        employee.termination_date = datetime.now(timezone.utc).date()
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='employee_deleted',
            resource_type='employee',
            resource_id=employee.id,
            changes={'name': employee.full_name},
            ip_address=request.remote_addr,
            severity='warning'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Employee {employee.full_name} deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Delete employee error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to delete employee'
        }), 500


# ============================================================================
# BULK IMPORT EMPLOYEES
# ============================================================================

@employees_bp.route('/api/employees/bulk-import', methods=['POST'])
@jwt_required()
def bulk_import_employees():
    """
    Bulk import employees from CSV/JSON
    
    POST /api/employees/bulk-import
    Body: {
        "employees": [
            { employee_data },
            { employee_data }
        ]
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if 'employees' not in data or not isinstance(data['employees'], list):
            return jsonify({
                'success': False,
                'message': 'Invalid data format'
            }), 400
        
        employees_data = data['employees']
        created_count = 0
        failed_count = 0
        errors = []
        
        for emp_data in employees_data:
            try:
                # Validate SSN
                is_valid_ssn, ssn_result = validate_ssn(emp_data['personal'].get('ssn', ''))
                if not is_valid_ssn:
                    errors.append({
                        'employee': emp_data['personal'].get('first_name', 'Unknown'),
                        'error': ssn_result
                    })
                    failed_count += 1
                    continue
                
                # Encrypt SSN
                encrypted_ssn = encrypt_data(ssn_result)
                
                # Create employee
                employee = Employee(
                    user_id=user_id,
                    first_name=emp_data['personal']['first_name'],
                    last_name=emp_data['personal']['last_name'],
                    ssn_encrypted=encrypted_ssn,
                    email=emp_data['personal'].get('email'),
                    phone=emp_data['personal'].get('phone'),
                    date_of_birth=emp_data['personal']['date_of_birth'],
                    address_street=emp_data['address']['street'],
                    address_city=emp_data['address']['city'],
                    address_state=emp_data['address']['state'],
                    address_zip=emp_data['address']['zip'],
                    job_title=emp_data['employment']['job_title'],
                    hire_date=emp_data['employment']['hire_date'],
                    pay_rate=emp_data['employment']['pay_rate'],
                    pay_frequency=emp_data['employment'].get('pay_frequency', 'biweekly'),
                    filing_status=emp_data.get('tax_info', {}).get('filing_status', 'single'),
                    status='active'
                )
                
                db.session.add(employee)
                created_count += 1
                
            except Exception as e:
                errors.append({
                    'employee': emp_data.get('personal', {}).get('first_name', 'Unknown'),
                    'error': str(e)
                })
                failed_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Imported {created_count} employees',
            'created': created_count,
            'failed': failed_count,
            'errors': errors if errors else None
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Bulk import error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Bulk import failed',
            'error': str(e)
        }), 500