#!/usr/bin/env python3
"""
Saurellius Platform - Paystub Generation Routes
Connected to snappt_compliant_generator.py (DO NOT MODIFY)
"""

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, Employee, Paystub, AuditLog
from utils.tax_calculator import calculate_all_taxes
from utils.saurellius_multicolor import SaurrelliusMultiThemeGenerator
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
import boto3
import os
import hashlib
import uuid

paystubs_bp = Blueprint('paystubs', __name__)

# Initialize Saurellius Playwright-based generator
saurellius_generator = SaurrelliusMultiThemeGenerator()

# ============================================================================
# S3 CONFIGURATION
# ============================================================================

s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=os.environ.get('AWS_REGION', 'us-east-1')
)

S3_BUCKET = os.environ.get('S3_BUCKET', 'saurellius-paystubs')

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def number_to_words(amount):
    """Convert number to words for check"""
    ones = ['', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE']
    tens = ['', '', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY', 'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY']
    teens = ['TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 'SEVENTEEN', 'EIGHTEEN', 'NINETEEN']
    
    amount = Decimal(str(amount))
    dollars = int(amount)
    cents = int((amount - dollars) * 100)
    
    if dollars == 0:
        return f"ZERO DOLLARS AND {cents:02d}/100"
    
    result = []
    
    # Thousands
    if dollars >= 1000:
        thousands = dollars // 1000
        if thousands < 10:
            result.append(ones[thousands])
        elif thousands < 20:
            result.append(teens[thousands - 10])
        else:
            result.append(tens[thousands // 10])
            if thousands % 10:
                result.append(ones[thousands % 10])
        result.append('THOUSAND')
        dollars = dollars % 1000
    
    # Hundreds
    if dollars >= 100:
        result.append(ones[dollars // 100])
        result.append('HUNDRED')
        dollars = dollars % 100
    
    # Tens and ones
    if dollars >= 20:
        result.append(tens[dollars // 10])
        if dollars % 10:
            result.append(ones[dollars % 10])
    elif dollars >= 10:
        result.append(teens[dollars - 10])
    elif dollars > 0:
        result.append(ones[dollars])
    
    result.append('DOLLARS')
    result.append('AND')
    result.append(f"{cents:02d}/100")
    
    return ' '.join(result)


def calculate_next_pay_date(last_pay_date, frequency):
    """Calculate next pay date based on frequency"""
    from datetime import datetime, timedelta
    
    if isinstance(last_pay_date, str):
        last_pay_date = datetime.strptime(last_pay_date, '%Y-%m-%d').date()
    
    if frequency == 'weekly':
        return last_pay_date + timedelta(days=7)
    elif frequency == 'biweekly':
        return last_pay_date + timedelta(days=14)
    elif frequency == 'semimonthly':
        # 15th and last day of month
        if last_pay_date.day == 15:
            # Go to last day of month
            next_month = last_pay_date.replace(day=28) + timedelta(days=4)
            return next_month - timedelta(days=next_month.day)
        else:
            # Go to 15th of next month
            if last_pay_date.month == 12:
                return last_pay_date.replace(year=last_pay_date.year + 1, month=1, day=15)
            else:
                return last_pay_date.replace(month=last_pay_date.month + 1, day=15)
    elif frequency == 'monthly':
        if last_pay_date.month == 12:
            return last_pay_date.replace(year=last_pay_date.year + 1, month=1)
        else:
            return last_pay_date.replace(month=last_pay_date.month + 1)
    
    return last_pay_date + timedelta(days=14)


def upload_to_s3(file_bytes, key):
    """Upload file to S3 and return signed URL"""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType='application/pdf'
        )
        
        # Generate signed URL (7 days expiry)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': key},
            ExpiresIn=604800
        )
        
        return url
    except Exception as e:
        print(f"S3 upload error: {str(e)}")
        return None


# ============================================================================
# PAYSTUB GENERATION
# ============================================================================

@paystubs_bp.route('/api/paystubs/generate-complete', methods=['POST'])
@jwt_required()
def generate_complete_paystub():
    """
    Generate complete paystub with PDF
    
    POST /api/paystubs/generate-complete
    Body: {
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
            "health_insurance": 150,
            "dental_insurance": 50
        },
        "pto": {
            "vacation_used": 8,
            "sick_used": 0
        }
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Get user and check subscription
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Check paystub limit
        if user.monthly_paystub_limit != -1 and user.paystubs_used_this_month >= user.monthly_paystub_limit:
            return jsonify({
                'success': False,
                'message': 'Monthly paystub limit reached',
                'limit': user.monthly_paystub_limit,
                'used': user.paystubs_used_this_month
            }), 403
        
        # Get employee
        employee = Employee.query.filter_by(
            id=data['employee_id'],
            user_id=user_id,
            status='active'
        ).first()
        
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
        
        # ====================================================================
        # CALCULATE EARNINGS
        # ====================================================================
        
        earnings_data = data.get('earnings', {})
        
        # Regular pay
        regular_hours = Decimal(str(earnings_data.get('regular_hours', 0)))
        hourly_rate = Decimal(str(earnings_data.get('hourly_rate', employee.pay_rate)))
        regular_pay = regular_hours * hourly_rate
        
        # Overtime pay
        overtime_hours = Decimal(str(earnings_data.get('overtime_hours', 0)))
        overtime_multiplier = Decimal(str(earnings_data.get('overtime_multiplier', 1.5)))
        overtime_rate = hourly_rate * overtime_multiplier
        overtime_pay = overtime_hours * overtime_rate
        
        # Additional earnings
        bonus = Decimal(str(earnings_data.get('bonus', 0)))
        commission = Decimal(str(earnings_data.get('commission', 0)))
        tips = Decimal(str(earnings_data.get('tips', 0)))
        reimbursements = Decimal(str(earnings_data.get('reimbursements', 0)))
        
        # Gross pay
        gross_pay = regular_pay + overtime_pay + bonus + commission + tips
        
        # ====================================================================
        # CALCULATE TAXES
        # ====================================================================
        
        tax_results = calculate_all_taxes(
            gross_pay=float(gross_pay),
            state=employee.address_state,
            filing_status=employee.filing_status or 'single',
            pay_frequency=employee.pay_frequency or 'biweekly',
            allowances=employee.federal_allowances or 0,
            additional_withholding=float(employee.federal_additional_withholding or 0),
            ytd_gross=float(employee.ytd_gross_pay),
            ytd_ss_wages=float(employee.ytd_ss_wages),
            local_jurisdiction=employee.local_jurisdiction
        )
        
        # ====================================================================
        # CALCULATE DEDUCTIONS
        # ====================================================================
        
        deductions_data = data.get('deductions', {})
        
        # Pre-tax deductions
        deduction_401k = Decimal(str(deductions_data.get('contribution_401k', 0)))
        if employee.contribution_401k_percent > 0:
            deduction_401k = gross_pay * (employee.contribution_401k_percent / 100)
        
        deduction_hsa = Decimal(str(deductions_data.get('hsa', 0)))
        deduction_fsa = Decimal(str(deductions_data.get('fsa', 0)))
        
        # Post-tax deductions
        deduction_health = Decimal(str(deductions_data.get('health_insurance', employee.health_insurance_deduction or 0)))
        deduction_dental = Decimal(str(deductions_data.get('dental_insurance', employee.dental_insurance_deduction or 0)))
        deduction_vision = Decimal(str(deductions_data.get('vision_insurance', employee.vision_insurance_deduction or 0)))
        deduction_life = Decimal(str(deductions_data.get('life_insurance', employee.life_insurance_deduction or 0)))
        
        # Total deductions
        total_deductions = (
            Decimal(str(tax_results['total_taxes'])) +
            deduction_401k + deduction_hsa + deduction_fsa +
            deduction_health + deduction_dental + deduction_vision + deduction_life
        )
        
        # Net pay
        net_pay = gross_pay - total_deductions
        
        # ====================================================================
        # HANDLE PTO
        # ====================================================================
        
        pto_data = data.get('pto', {})
        vacation_used = Decimal(str(pto_data.get('vacation_used', 0)))
        sick_used = Decimal(str(pto_data.get('sick_used', 0)))
        personal_used = Decimal(str(pto_data.get('personal_used', 0)))
        
        # Calculate accrual (hours per pay period)
        hours_worked = regular_hours + overtime_hours
        vacation_accrued = hours_worked * employee.pto_accrual_rate
        sick_accrued = hours_worked * employee.pto_accrual_rate * Decimal('0.5')  # Half rate for sick
        
        # ====================================================================
        # CREATE PAYSTUB RECORD
        # ====================================================================
        
        paystub = Paystub(
            user_id=user_id,
            employee_id=employee.id,
            
            # Pay period
            pay_date=data['pay_info']['pay_date'],
            period_start=data['pay_info']['period_start'],
            period_end=data['pay_info']['period_end'],
            pay_frequency=employee.pay_frequency,
            
            # Earnings
            regular_hours=float(regular_hours),
            regular_rate=float(hourly_rate),
            regular_pay=float(regular_pay),
            overtime_hours=float(overtime_hours),
            overtime_rate=float(overtime_rate),
            overtime_pay=float(overtime_pay),
            overtime_multiplier=float(overtime_multiplier),
            bonus=float(bonus),
            commission=float(commission),
            tips=float(tips),
            reimbursements=float(reimbursements),
            gross_pay=float(gross_pay),
            
            # Taxes
            federal_income_tax=tax_results['federal_income_tax'],
            social_security_tax=tax_results['social_security_tax'],
            medicare_tax=tax_results['medicare_tax'],
            state_income_tax=tax_results['state_income_tax'],
            state_disability_tax=tax_results['state_disability_tax'],
            local_income_tax=tax_results['local_income_tax'],
            state_code=employee.address_state,
            local_jurisdiction=employee.local_jurisdiction,
            
            # Deductions
            deduction_401k=float(deduction_401k),
            deduction_hsa=float(deduction_hsa),
            deduction_fsa=float(deduction_fsa),
            deduction_health=float(deduction_health),
            deduction_dental=float(deduction_dental),
            deduction_vision=float(deduction_vision),
            deduction_life=float(deduction_life),
            
            # Totals
            total_taxes=tax_results['total_taxes'],
            total_deductions=float(total_deductions),
            net_pay=float(net_pay),
            amount_in_words=number_to_words(net_pay),
            
            # PTO
            vacation_hours_accrued=float(vacation_accrued),
            vacation_hours_used=float(vacation_used),
            sick_hours_accrued=float(sick_accrued),
            sick_hours_used=float(sick_used),
            personal_hours_used=float(personal_used),
            
            # YTD at time of generation
            ytd_gross_pay=float(employee.ytd_gross_pay + gross_pay),
            ytd_net_pay=float(employee.ytd_net_pay + net_pay),
            ytd_federal_tax=float(employee.ytd_federal_tax + Decimal(str(tax_results['federal_income_tax']))),
            ytd_state_tax=float(employee.ytd_state_tax + Decimal(str(tax_results['state_income_tax']))),
            ytd_ss_tax=float(employee.ytd_ss_tax + Decimal(str(tax_results['social_security_tax']))),
            ytd_medicare_tax=float(employee.ytd_medicare_tax + Decimal(str(tax_results['medicare_tax']))),
            ytd_401k=float(employee.ytd_401k + deduction_401k),
            ytd_hours_worked=float(hours_worked),
            
            # Status
            status='finalized',
            finalized_at=datetime.now(timezone.utc),
            finalized_by=user_id,
            template_id=data.get('template_id', 'eusotrip_original')
        )
        
        db.session.add(paystub)
        db.session.flush()  # Get paystub ID
        
        # ====================================================================
        # PREPARE DATA FOR PDF GENERATOR (snappt_compliant_generator.py)
        # ====================================================================
        
        pdf_data = {
            'company': {
                'name': user.company_name or 'YOUR COMPANY NAME',
                'address': user.company_address or '123 Business St, City, ST 12345'
            },
            'employee': {
                'name': employee.full_name,
                'state': employee.address_state,
                'ssn_masked': f"XXX-XX-{employee.ssn_encrypted[-4:]}"
            },
            'pay_info': {
                'period_start': data['pay_info']['period_start'],
                'period_end': data['pay_info']['period_end'],
                'pay_date': data['pay_info']['pay_date']
            },
            'earnings': [],
            'deductions': [],
            'totals': {
                'gross_pay': float(gross_pay),
                'gross_pay_ytd': float(employee.ytd_gross_pay + gross_pay),
                'net_pay': float(net_pay),
                'net_pay_ytd': float(employee.ytd_net_pay + net_pay),
                'amount_words': number_to_words(net_pay)
            },
            'check_info': {
                'number': f"{paystub.id:05d}"
            }
        }
        
        # Add earnings
        if regular_pay > 0:
            pdf_data['earnings'].append({
                'description': 'Regular Earnings',
                'rate': float(hourly_rate),
                'hours': float(regular_hours),
                'current': float(regular_pay),
                'ytd': float(employee.ytd_gross_pay + gross_pay)
            })
        
        if overtime_pay > 0:
            pdf_data['earnings'].append({
                'description': 'Overtime Earnings',
                'rate': float(overtime_rate),
                'hours': float(overtime_hours),
                'current': float(overtime_pay),
                'ytd': float(employee.ytd_overtime_pay + overtime_pay)
            })
        
        if bonus > 0:
            pdf_data['earnings'].append({
                'description': 'Bonus',
                'rate': '—',
                'hours': '—',
                'current': float(bonus),
                'ytd': float(employee.ytd_bonus + bonus)
            })
        
        # Add deductions (taxes)
        pdf_data['deductions'].append({
            'description': 'Federal Tax',
            'type': 'Statutory',
            'current': tax_results['federal_income_tax'],
            'ytd': float(employee.ytd_federal_tax + Decimal(str(tax_results['federal_income_tax'])))
        })
        
        pdf_data['deductions'].append({
            'description': 'Social Security',
            'type': 'Statutory',
            'current': tax_results['social_security_tax'],
            'ytd': float(employee.ytd_ss_tax + Decimal(str(tax_results['social_security_tax'])))
        })
        
        pdf_data['deductions'].append({
            'description': 'Medicare',
            'type': 'Statutory',
            'current': tax_results['medicare_tax'],
            'ytd': float(employee.ytd_medicare_tax + Decimal(str(tax_results['medicare_tax'])))
        })
        
        if tax_results['state_income_tax'] > 0:
            pdf_data['deductions'].append({
                'description': f'{employee.address_state} State Tax',
                'type': 'Statutory',
                'current': tax_results['state_income_tax'],
                'ytd': float(employee.ytd_state_tax + Decimal(str(tax_results['state_income_tax'])))
            })
        
        # Add voluntary deductions
        if deduction_401k > 0:
            pdf_data['deductions'].append({
                'description': '401(k)',
                'type': 'Voluntary',
                'current': float(deduction_401k),
                'ytd': float(employee.ytd_401k + deduction_401k)
            })
        
        if deduction_health > 0:
            pdf_data['deductions'].append({
                'description': 'Health Insurance',
                'type': 'Voluntary',
                'current': float(deduction_health),
                'ytd': float(employee.ytd_health_insurance + deduction_health)
            })
        
        # ====================================================================
        # GENERATE PDF USING snappt_compliant_generator.py
        # ====================================================================
        
        start_time = datetime.now()
        
        # Generate PDF using Saurellius Playwright-based generator
        output_path = f"/tmp/paystub_{paystub.id}.pdf"
        result = saurellius_generator.generate_paystub_pdf(
            paystub_data=pdf_data,
            output_path=output_path,
            theme=paystub.template_id or "anxiety"
        )
        if not result.get("success", False):
            raise Exception(f"Paystub generation failed: {result.get('error', 'unknown error')}")
        with open(output_path, "rb") as f:
            pdf_bytes = f.read()
        
        generation_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Generate document hash
        document_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16].upper()
        
        # Upload to S3
        s3_key = f"paystubs/{user_id}/{paystub.id}/{paystub.verification_id}.pdf"
        pdf_url = upload_to_s3(pdf_bytes, s3_key)
        
        # Update paystub record
        paystub.s3_bucket = S3_BUCKET
        paystub.s3_key = s3_key
        paystub.pdf_url = pdf_url
        paystub.document_hash = document_hash
        paystub.file_size_bytes = len(pdf_bytes)
        paystub.pdf_generated_at = datetime.now(timezone.utc)
        paystub.pdf_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        paystub.generation_time_ms = int(generation_time)
        paystub.snappt_verified = True
        paystub.snappt_verification_date = datetime.now(timezone.utc)
        
        # ====================================================================
        # UPDATE EMPLOYEE YTD
        # ====================================================================
        
        employee.ytd_gross_pay += gross_pay
        employee.ytd_net_pay += net_pay
        employee.ytd_federal_tax += Decimal(str(tax_results['federal_income_tax']))
        employee.ytd_ss_tax += Decimal(str(tax_results['social_security_tax']))
        employee.ytd_medicare_tax += Decimal(str(tax_results['medicare_tax']))
        employee.ytd_state_tax += Decimal(str(tax_results['state_income_tax']))
        employee.ytd_ss_wages += gross_pay
        employee.ytd_medicare_wages += gross_pay
        employee.ytd_401k += deduction_401k
        employee.ytd_health_insurance += deduction_health
        employee.ytd_overtime_pay += overtime_pay
        employee.ytd_bonus += bonus
        
        # Update PTO balances
        employee.vacation_hours_accrued += vacation_accrued
        employee.vacation_hours_used += vacation_used
        employee.sick_hours_accrued += sick_accrued
        employee.sick_hours_used += sick_used
        employee.personal_hours_used += personal_used
        
        # ====================================================================
        # UPDATE USER REWARDS & USAGE
        # ====================================================================
        
        user.paystubs_used_this_month += 1
        user.reward_points += 10
        user.total_lifetime_points += 10
        
        # Check tier progression
        if user.total_lifetime_points >= 10000 and user.reward_tier != 'platinum':
            user.reward_tier = 'platinum'
        elif user.total_lifetime_points >= 5000 and user.reward_tier not in ['platinum', 'gold']:
            user.reward_tier = 'gold'
        elif user.total_lifetime_points >= 1000 and user.reward_tier not in ['platinum', 'gold', 'silver']:
            user.reward_tier = 'silver'
        
        # ====================================================================
        # AUDIT LOG
        # ====================================================================
        
        log = AuditLog(
            user_id=user_id,
            action='paystub_generated',
            resource_type='paystub',
            resource_id=paystub.id,
            changes={
                'employee_id': employee.id,
                'verification_id': paystub.verification_id,
                'gross_pay': float(gross_pay),
                'net_pay': float(net_pay)
            },
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Paystub generated successfully',
            'paystub': {
                'id': paystub.id,
                'verification_id': paystub.verification_id,
                'employee_name': employee.full_name,
                'pay_date': paystub.pay_date.isoformat(),
                'gross_pay': float(gross_pay),
                'net_pay': float(net_pay),
                'pdf_url': pdf_url,
                'document_hash': document_hash
            },
            'rewards': {
                'points_earned': 10,
                'total_points': user.reward_points,
                'tier': user.reward_tier
            },
            'usage': {
                'paystubs_used': user.paystubs_used_this_month,
                'paystubs_limit': user.monthly_paystub_limit
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Paystub generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Paystub generation failed',
            'error': str(e)
        }), 500


# ============================================================================
# YTD CONTINUATION
# ============================================================================

@paystubs_bp.route('/api/paystubs/continuation/<int:employee_id>', methods=['GET'])
@jwt_required()
def get_ytd_continuation(employee_id):
    """Get YTD data and suggestions for next paystub"""
    try:
        user_id = get_jwt_identity()
        
        employee = Employee.query.filter_by(
            id=employee_id,
            user_id=user_id
        ).first()
        
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
        
        # Get last paystub
        last_paystub = Paystub.query.filter_by(
            employee_id=employee_id
        ).order_by(Paystub.pay_date.desc()).first()
        
        # Calculate next pay date
        next_pay_date = calculate_next_pay_date(
            last_paystub.pay_date if last_paystub else employee.hire_date,
            employee.pay_frequency
        )
        
        # Get average from last 3 paystubs
        recent_stubs = Paystub.query.filter_by(
            employee_id=employee_id
        ).order_by(Paystub.pay_date.desc()).limit(3).all()
        
        avg_hours = sum([s.regular_hours for s in recent_stubs]) / len(recent_stubs) if recent_stubs else 80
        avg_rate = employee.pay_rate
        
        return jsonify({
            'success': True,
            'ytd_summary': {
                'ytd_gross': float(employee.ytd_gross_pay),
                'ytd_net': float(employee.ytd_net_pay),
                'ytd_federal_tax': float(employee.ytd_federal_tax),
                'ytd_ss_tax': float(employee.ytd_ss_tax),
                'ytd_medicare_tax': float(employee.ytd_medicare_tax),
                'ytd_state_tax': float(employee.ytd_state_tax),
                'ytd_ss_wages': float(employee.ytd_ss_wages)
            },
            'next_pay_date': next_pay_date.isoformat(),
            'suggested_hours': float(avg_hours),
            'hourly_rate': float(avg_rate),
            'last_paystub_date': last_paystub.pay_date.isoformat() if last_paystub else None,
            'pto_balances': {
                'vacation': float(employee.vacation_hours_balance),
                'sick': float(employee.sick_hours_balance),
                'personal': float(employee.personal_hours_balance)
            }
        }), 200
        
    except Exception as e:
        print(f"Get paystubs history error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get paystub history'
        }), 500


# ============================================================================
# GET SINGLE PAYSTUB
# ============================================================================

@paystubs_bp.route('/api/paystubs/<int:paystub_id>', methods=['GET'])
@jwt_required()
def get_paystub(paystub_id):
    """Get single paystub details"""
    try:
        user_id = get_jwt_identity()
        
        paystub = Paystub.query.filter_by(
            id=paystub_id,
            user_id=user_id
        ).first()
        
        if not paystub:
            return jsonify({'success': False, 'message': 'Paystub not found'}), 404
        
        return jsonify({
            'success': True,
            'paystub': {
                'id': paystub.id,
                'verification_id': paystub.verification_id,
                'employee': {
                    'id': paystub.employee.id,
                    'name': paystub.employee.full_name,
                    'state': paystub.employee.address_state
                },
                'pay_info': {
                    'pay_date': paystub.pay_date.isoformat(),
                    'period_start': paystub.period_start.isoformat(),
                    'period_end': paystub.period_end.isoformat(),
                    'pay_frequency': paystub.pay_frequency
                },
                'earnings': {
                    'regular_hours': float(paystub.regular_hours),
                    'regular_rate': float(paystub.regular_rate),
                    'regular_pay': float(paystub.regular_pay),
                    'overtime_hours': float(paystub.overtime_hours),
                    'overtime_pay': float(paystub.overtime_pay),
                    'bonus': float(paystub.bonus),
                    'gross_pay': float(paystub.gross_pay)
                },
                'taxes': {
                    'federal': float(paystub.federal_income_tax),
                    'social_security': float(paystub.social_security_tax),
                    'medicare': float(paystub.medicare_tax),
                    'state': float(paystub.state_income_tax),
                    'sdi': float(paystub.state_disability_tax),
                    'local': float(paystub.local_income_tax),
                    'total': float(paystub.total_taxes)
                },
                'deductions': {
                    '401k': float(paystub.deduction_401k),
                    'health': float(paystub.deduction_health),
                    'dental': float(paystub.deduction_dental),
                    'vision': float(paystub.deduction_vision)
                },
                'totals': {
                    'gross_pay': float(paystub.gross_pay),
                    'total_deductions': float(paystub.total_deductions),
                    'net_pay': float(paystub.net_pay)
                },
                'ytd': {
                    'gross_pay': float(paystub.ytd_gross_pay),
                    'net_pay': float(paystub.ytd_net_pay),
                    'federal_tax': float(paystub.ytd_federal_tax),
                    'state_tax': float(paystub.ytd_state_tax),
                    'ss_tax': float(paystub.ytd_ss_tax),
                    'medicare_tax': float(paystub.ytd_medicare_tax)
                },
                'pdf_url': paystub.pdf_url,
                'verification_status': paystub.verification_status,
                'document_hash': paystub.document_hash,
                'created_at': paystub.created_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        print(f"Get paystub error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get paystub'
        }), 500


# ============================================================================
# DOWNLOAD PAYSTUB PDF
# ============================================================================

@paystubs_bp.route('/api/paystubs/<int:paystub_id>/download', methods=['GET'])
@jwt_required()
def download_paystub(paystub_id):
    """Download paystub PDF"""
    try:
        user_id = get_jwt_identity()
        
        paystub = Paystub.query.filter_by(
            id=paystub_id,
            user_id=user_id
        ).first()
        
        if not paystub:
            return jsonify({'success': False, 'message': 'Paystub not found'}), 404
        
        if not paystub.pdf_url:
            return jsonify({'success': False, 'message': 'PDF not available'}), 404
        
        # Generate fresh signed URL
        fresh_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': paystub.s3_bucket, 'Key': paystub.s3_key},
            ExpiresIn=3600  # 1 hour
        )
        
        return jsonify({
            'success': True,
            'download_url': fresh_url,
            'filename': f"paystub_{paystub.verification_id}.pdf"
        }), 200
        
    except Exception as e:
        print(f"Download paystub error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to generate download link'
        }), 500


# ============================================================================
# VOID PAYSTUB
# ============================================================================

@paystubs_bp.route('/api/paystubs/<int:paystub_id>/void', methods=['POST'])
@jwt_required()
def void_paystub(paystub_id):
    """Void a paystub and reverse YTD calculations"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        paystub = Paystub.query.filter_by(
            id=paystub_id,
            user_id=user_id
        ).first()
        
        if not paystub:
            return jsonify({'success': False, 'message': 'Paystub not found'}), 404
        
        if paystub.status == 'voided':
            return jsonify({'success': False, 'message': 'Paystub already voided'}), 400
        
        # Reverse YTD calculations
        employee = paystub.employee
        employee.ytd_gross_pay -= Decimal(str(paystub.gross_pay))
        employee.ytd_net_pay -= Decimal(str(paystub.net_pay))
        employee.ytd_federal_tax -= Decimal(str(paystub.federal_income_tax))
        employee.ytd_ss_tax -= Decimal(str(paystub.social_security_tax))
        employee.ytd_medicare_tax -= Decimal(str(paystub.medicare_tax))
        employee.ytd_state_tax -= Decimal(str(paystub.state_income_tax))
        employee.ytd_ss_wages -= Decimal(str(paystub.gross_pay))
        employee.ytd_401k -= Decimal(str(paystub.deduction_401k))
        
        # Reverse PTO
        employee.vacation_hours_accrued -= Decimal(str(paystub.vacation_hours_accrued))
        employee.vacation_hours_used -= Decimal(str(paystub.vacation_hours_used))
        employee.sick_hours_accrued -= Decimal(str(paystub.sick_hours_accrued))
        employee.sick_hours_used -= Decimal(str(paystub.sick_hours_used))
        
        # Update paystub status
        paystub.status = 'voided'
        paystub.voided_at = datetime.now(timezone.utc)
        paystub.void_reason = data.get('reason', 'User requested void')
        
        # Reverse user usage count
        user = User.query.get(user_id)
        if user.paystubs_used_this_month > 0:
            user.paystubs_used_this_month -= 1
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='paystub_voided',
            resource_type='paystub',
            resource_id=paystub.id,
            changes={'reason': paystub.void_reason},
            ip_address=request.remote_addr,
            severity='warning'
        )
        db.session.add(log)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Paystub voided successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Void paystub error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to void paystub'
        }), 500


# ============================================================================
# VERIFY PAYSTUB
# ============================================================================

@paystubs_bp.route('/api/paystubs/verify/<verification_id>', methods=['GET'])
def verify_paystub(verification_id):
    """Verify paystub authenticity (public endpoint)"""
    try:
        paystub = Paystub.query.filter_by(
            verification_id=verification_id
        ).first()
        
        if not paystub:
            return jsonify({
                'success': False,
                'verified': False,
                'message': 'Paystub not found'
            }), 404
        
        if paystub.status == 'voided':
            return jsonify({
                'success': False,
                'verified': False,
                'message': 'This paystub has been voided',
                'voided_at': paystub.voided_at.isoformat(),
                'void_reason': paystub.void_reason
            }), 400
        
        return jsonify({
            'success': True,
            'verified': True,
            'paystub': {
                'verification_id': paystub.verification_id,
                'employee_name': paystub.employee.full_name,
                'company_name': paystub.user.company_name or 'N/A',
                'pay_date': paystub.pay_date.isoformat(),
                'net_pay': float(paystub.net_pay),
                'gross_pay': float(paystub.gross_pay),
                'verification_status': paystub.verification_status,
                'document_hash': paystub.document_hash,
                'snappt_verified': paystub.snappt_verified,
                'created_at': paystub.created_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        print(f"Verify paystub error: {str(e)}")
        return jsonify({
            'success': False,
            'verified': False,
            'message': 'Verification failed'
        }), 500
        
    except Exception as e:
        print(f"YTD continuation error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get continuation data'
        }), 500


# ============================================================================
# PAYSTUB HISTORY
# ============================================================================

@paystubs_bp.route('/api/paystubs/history', methods=['GET'])
@jwt_required()
def get_paystubs_history():
    """Get paystub history"""
    try:
        user_id = get_jwt_identity()
        
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        employee_id = request.args.get('employee_id', type=int)
        
        query = Paystub.query.filter_by(user_id=user_id)
        
        if employee_id:
            query = query.filter_by(employee_id=employee_id)
        
        paystubs = query.order_by(Paystub.pay_date.desc())\
            .limit(limit)\
            .offset(offset)\
            .all()
        
        return jsonify({
            'success': True,
            'paystubs': [{
                'id': stub.id,
                'verification_id': stub.verification_id,
                'employee_id': stub.employee_id,
                'employee_name': stub.employee.full_name,
                'pay_date': stub.pay_date.isoformat(),
                'period_start': stub.period_start.isoformat(),
                'period_end': stub.period_end.isoformat(),
                'gross_pay': float(stub.gross_pay),
                'net_pay': float(stub.net_pay),
                'pdf_url': stub.pdf_url,
                'verification_status': stub.verification_status,
                'created_at': stub.created_at.isoformat()
            } for stub in paystubs],
            'total': Paystub.query.filter_by(user_id=user_id).count()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500