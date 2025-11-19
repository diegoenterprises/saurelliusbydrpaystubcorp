#!/usr/bin/env python3
"""
Saurellius Platform - Reports Routes
Complete reporting system for payroll, taxes, earnings, and PTO
"""

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, Employee, Paystub
from sqlalchemy import func, extract
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import io
import csv

reports_bp = Blueprint('reports', __name__)

# ============================================================================
# PAYROLL SUMMARY REPORT
# ============================================================================

@reports_bp.route('/api/reports/payroll-summary', methods=['GET'])
@jwt_required()
def payroll_summary():
    """
    Generate payroll summary report
    
    GET /api/reports/payroll-summary?start_date=2025-01-01&end_date=2025-12-31&format=json
    
    Query Parameters:
    - start_date: Start date (YYYY-MM-DD)
    - end_date: End date (YYYY-MM-DD)
    - format: json or csv (default: json)
    """
    try:
        user_id = get_jwt_identity()
        
        # Parse dates
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        format_type = request.args.get('format', 'json')
        
        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'message': 'start_date and end_date are required'
            }), 400
        
        # Query paystubs
        paystubs = Paystub.query.filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= start_date,
            Paystub.pay_date <= end_date
        ).all()
        
        # Calculate totals
        total_gross = sum([p.gross_pay for p in paystubs])
        total_net = sum([p.net_pay for p in paystubs])
        total_taxes = sum([p.total_taxes for p in paystubs])
        total_deductions = sum([p.total_deductions for p in paystubs])
        
        # Breakdown by category
        federal_tax = sum([p.federal_income_tax for p in paystubs])
        ss_tax = sum([p.social_security_tax for p in paystubs])
        medicare_tax = sum([p.medicare_tax for p in paystubs])
        state_tax = sum([p.state_income_tax for p in paystubs])
        
        # Monthly breakdown
        monthly_data = db.session.query(
            extract('month', Paystub.pay_date).label('month'),
            func.sum(Paystub.gross_pay).label('gross'),
            func.sum(Paystub.net_pay).label('net'),
            func.sum(Paystub.total_taxes).label('taxes'),
            func.count(Paystub.id).label('count')
        ).filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= start_date,
            Paystub.pay_date <= end_date
        ).group_by('month').order_by('month').all()
        
        monthly_breakdown = []
        for row in monthly_data:
            monthly_breakdown.append({
                'month': int(row.month),
                'month_name': datetime(2025, int(row.month), 1).strftime('%B'),
                'gross_pay': float(row.gross or 0),
                'net_pay': float(row.net or 0),
                'taxes': float(row.taxes or 0),
                'paystub_count': int(row.count)
            })
        
        report_data = {
            'report_type': 'Payroll Summary',
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_paystubs': len(paystubs),
                'total_gross_pay': float(total_gross),
                'total_net_pay': float(total_net),
                'total_taxes': float(total_taxes),
                'total_deductions': float(total_deductions)
            },
            'tax_breakdown': {
                'federal_income_tax': float(federal_tax),
                'social_security_tax': float(ss_tax),
                'medicare_tax': float(medicare_tax),
                'state_income_tax': float(state_tax)
            },
            'monthly_breakdown': monthly_breakdown
        }
        
        if format_type == 'csv':
            return generate_csv_report(report_data, 'payroll_summary')
        
        return jsonify({
            'success': True,
            'report': report_data
        }), 200
        
    except Exception as e:
        print(f"Payroll summary error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to generate payroll summary'
        }), 500


# ============================================================================
# TAX SUMMARY REPORT
# ============================================================================

@reports_bp.route('/api/reports/tax-summary', methods=['GET'])
@jwt_required()
def tax_summary():
    """
    Generate tax summary report
    
    GET /api/reports/tax-summary?year=2025&format=json
    """
    try:
        user_id = get_jwt_identity()
        
        year = request.args.get('year', datetime.now().year, type=int)
        format_type = request.args.get('format', 'json')
        
        year_start = datetime(year, 1, 1).date()
        year_end = datetime(year, 12, 31).date()
        
        # Get tax totals by type
        tax_summary_data = db.session.query(
            func.sum(Paystub.federal_income_tax).label('federal'),
            func.sum(Paystub.social_security_tax).label('ss'),
            func.sum(Paystub.medicare_tax).label('medicare'),
            func.sum(Paystub.state_income_tax).label('state'),
            func.sum(Paystub.state_disability_tax).label('sdi'),
            func.sum(Paystub.local_income_tax).label('local'),
            func.sum(Paystub.total_taxes).label('total'),
            func.sum(Paystub.gross_pay).label('gross')
        ).filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= year_start,
            Paystub.pay_date <= year_end
        ).first()
        
        # Quarterly breakdown
        quarterly = []
        for quarter in range(1, 5):
            q_start = datetime(year, (quarter-1)*3 + 1, 1).date()
            if quarter == 4:
                q_end = year_end
            else:
                q_end_month = quarter * 3
                next_month = datetime(year, q_end_month, 1) + timedelta(days=32)
                q_end = next_month.replace(day=1) - timedelta(days=1)
            
            q_data = db.session.query(
                func.sum(Paystub.total_taxes).label('total_taxes'),
                func.sum(Paystub.gross_pay).label('gross_pay'),
                func.sum(Paystub.federal_income_tax).label('federal'),
                func.sum(Paystub.social_security_tax).label('ss'),
                func.sum(Paystub.medicare_tax).label('medicare'),
                func.sum(Paystub.state_income_tax).label('state')
            ).filter(
                Paystub.user_id == user_id,
                Paystub.status == 'finalized',
                Paystub.pay_date >= q_start,
                Paystub.pay_date <= q_end
            ).first()
            
            quarterly.append({
                'quarter': quarter,
                'period': f'Q{quarter} {year}',
                'total_taxes': float(q_data.total_taxes or 0),
                'gross_pay': float(q_data.gross_pay or 0),
                'federal': float(q_data.federal or 0),
                'social_security': float(q_data.ss or 0),
                'medicare': float(q_data.medicare or 0),
                'state': float(q_data.state or 0),
                'effective_rate': round((float(q_data.total_taxes or 0) / float(q_data.gross_pay or 1)) * 100, 2)
            })
        
        # Employee breakdown
        employee_taxes = db.session.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            func.sum(Paystub.federal_income_tax).label('federal'),
            func.sum(Paystub.social_security_tax).label('ss'),
            func.sum(Paystub.medicare_tax).label('medicare'),
            func.sum(Paystub.state_income_tax).label('state'),
            func.sum(Paystub.total_taxes).label('total')
        ).join(
            Paystub, Paystub.employee_id == Employee.id
        ).filter(
            Employee.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= year_start,
            Paystub.pay_date <= year_end
        ).group_by(
            Employee.id, Employee.first_name, Employee.last_name
        ).all()
        
        employee_breakdown = []
        for emp in employee_taxes:
            employee_breakdown.append({
                'employee_id': emp.id,
                'employee_name': f"{emp.first_name} {emp.last_name}",
                'federal_tax': float(emp.federal or 0),
                'social_security': float(emp.ss or 0),
                'medicare': float(emp.medicare or 0),
                'state_tax': float(emp.state or 0),
                'total_taxes': float(emp.total or 0)
            })
        
        report_data = {
            'report_type': 'Tax Summary',
            'year': year,
            'summary': {
                'total_gross_pay': float(tax_summary_data.gross or 0),
                'total_taxes': float(tax_summary_data.total or 0),
                'effective_tax_rate': round((float(tax_summary_data.total or 0) / float(tax_summary_data.gross or 1)) * 100, 2),
                'federal_income_tax': float(tax_summary_data.federal or 0),
                'social_security': float(tax_summary_data.ss or 0),
                'medicare': float(tax_summary_data.medicare or 0),
                'state_income_tax': float(tax_summary_data.state or 0),
                'state_disability': float(tax_summary_data.sdi or 0),
                'local_income_tax': float(tax_summary_data.local or 0)
            },
            'quarterly_breakdown': quarterly,
            'employee_breakdown': employee_breakdown
        }
        
        if format_type == 'csv':
            return generate_csv_report(report_data, 'tax_summary')
        
        return jsonify({
            'success': True,
            'report': report_data
        }), 200
        
    except Exception as e:
        print(f"Tax summary error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to generate tax summary'
        }), 500


# ============================================================================
# EMPLOYEE EARNINGS REPORT
# ============================================================================

@reports_bp.route('/api/reports/employee-earnings', methods=['GET'])
@jwt_required()
def employee_earnings():
    """
    Generate employee earnings report
    
    GET /api/reports/employee-earnings?employee_id=1&year=2025&format=json
    """
    try:
        user_id = get_jwt_identity()
        
        employee_id = request.args.get('employee_id', type=int)
        year = request.args.get('year', datetime.now().year, type=int)
        format_type = request.args.get('format', 'json')
        
        year_start = datetime(year, 1, 1).date()
        year_end = datetime(year, 12, 31).date()
        
        # Build query
        query = db.session.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            Employee.job_title,
            Employee.address_state,
            Employee.ytd_gross_pay,
            Employee.ytd_net_pay,
            Employee.ytd_federal_tax,
            Employee.ytd_ss_tax,
            Employee.ytd_medicare_tax,
            Employee.ytd_state_tax,
            func.count(Paystub.id).label('paystub_count'),
            func.sum(Paystub.regular_pay).label('regular_earnings'),
            func.sum(Paystub.overtime_pay).label('overtime_earnings'),
            func.sum(Paystub.bonus).label('bonus_earnings')
        ).outerjoin(
            Paystub, Paystub.employee_id == Employee.id
        ).filter(
            Employee.user_id == user_id,
            Employee.status == 'active'
        ).group_by(
            Employee.id, Employee.first_name, Employee.last_name,
            Employee.job_title, Employee.address_state,
            Employee.ytd_gross_pay, Employee.ytd_net_pay,
            Employee.ytd_federal_tax, Employee.ytd_ss_tax,
            Employee.ytd_medicare_tax, Employee.ytd_state_tax
        )
        
        if employee_id:
            query = query.filter(Employee.id == employee_id)
        
        employees = query.all()
        
        earnings_report = []
        for emp in employees:
            earnings_report.append({
                'employee_id': emp.id,
                'employee_name': f"{emp.first_name} {emp.last_name}",
                'job_title': emp.job_title,
                'state': emp.address_state,
                'ytd_gross': float(emp.ytd_gross_pay),
                'ytd_net': float(emp.ytd_net_pay),
                'ytd_taxes': {
                    'federal': float(emp.ytd_federal_tax),
                    'social_security': float(emp.ytd_ss_tax),
                    'medicare': float(emp.ytd_medicare_tax),
                    'state': float(emp.ytd_state_tax),
                    'total': float(emp.ytd_federal_tax + emp.ytd_ss_tax + emp.ytd_medicare_tax + emp.ytd_state_tax)
                },
                'earnings_breakdown': {
                    'regular': float(emp.regular_earnings or 0),
                    'overtime': float(emp.overtime_earnings or 0),
                    'bonus': float(emp.bonus_earnings or 0)
                },
                'paystub_count': int(emp.paystub_count or 0)
            })
        
        report_data = {
            'report_type': 'Employee Earnings',
            'year': year,
            'employee_count': len(earnings_report),
            'total_ytd_gross': sum([e['ytd_gross'] for e in earnings_report]),
            'total_ytd_net': sum([e['ytd_net'] for e in earnings_report]),
            'employees': earnings_report
        }
        
        if format_type == 'csv':
            return generate_csv_report(report_data, 'employee_earnings')
        
        return jsonify({
            'success': True,
            'report': report_data
        }), 200
        
    except Exception as e:
        print(f"Employee earnings error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to generate employee earnings report'
        }), 500


# ============================================================================
# PTO REPORT
# ============================================================================

@reports_bp.route('/api/reports/pto-report', methods=['GET'])
@jwt_required()
def pto_report():
    """
    Generate PTO balances report
    
    GET /api/reports/pto-report?employee_id=1&format=json
    """
    try:
        user_id = get_jwt_identity()
        
        employee_id = request.args.get('employee_id', type=int)
        format_type = request.args.get('format', 'json')
        
        # Build query
        query = db.session.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            Employee.job_title,
            Employee.hire_date,
            Employee.vacation_hours_accrued,
            Employee.vacation_hours_used,
            Employee.vacation_hours_balance,
            Employee.sick_hours_accrued,
            Employee.sick_hours_used,
            Employee.sick_hours_balance,
            Employee.personal_hours_accrued,
            Employee.personal_hours_used,
            Employee.personal_hours_balance,
            Employee.pto_accrual_rate
        ).filter(
            Employee.user_id == user_id,
            Employee.status == 'active'
        )
        
        if employee_id:
            query = query.filter(Employee.id == employee_id)
        
        employees = query.all()
        
        pto_data = []
        for emp in employees:
            total_accrued = float(emp.vacation_hours_accrued + emp.sick_hours_accrued + emp.personal_hours_accrued)
            total_used = float(emp.vacation_hours_used + emp.sick_hours_used + emp.personal_hours_used)
            total_balance = float(emp.vacation_hours_balance + emp.sick_hours_balance + emp.personal_hours_balance)
            
            pto_data.append({
                'employee_id': emp.id,
                'employee_name': f"{emp.first_name} {emp.last_name}",
                'job_title': emp.job_title,
                'hire_date': emp.hire_date.isoformat(),
                'vacation': {
                    'accrued': float(emp.vacation_hours_accrued),
                    'used': float(emp.vacation_hours_used),
                    'balance': float(emp.vacation_hours_balance)
                },
                'sick': {
                    'accrued': float(emp.sick_hours_accrued),
                    'used': float(emp.sick_hours_used),
                    'balance': float(emp.sick_hours_balance)
                },
                'personal': {
                    'accrued': float(emp.personal_hours_accrued),
                    'used': float(emp.personal_hours_used),
                    'balance': float(emp.personal_hours_balance)
                },
                'totals': {
                    'accrued': total_accrued,
                    'used': total_used,
                    'balance': total_balance
                },
                'accrual_rate': float(emp.pto_accrual_rate)
            })
        
        report_data = {
            'report_type': 'PTO Report',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'employee_count': len(pto_data),
            'total_pto_balance': sum([e['totals']['balance'] for e in pto_data]),
            'employees': pto_data
        }
        
        if format_type == 'csv':
            return generate_csv_report(report_data, 'pto_report')
        
        return jsonify({
            'success': True,
            'report': report_data
        }), 200
        
    except Exception as e:
        print(f"PTO report error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to generate PTO report'
        }), 500


# ============================================================================
# CSV EXPORT HELPER
# ============================================================================

def generate_csv_report(report_data, report_type):
    """Generate CSV file from report data"""
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        if report_type == 'payroll_summary':
            writer.writerow(['Payroll Summary Report'])
            writer.writerow(['Period:', f"{report_data['period']['start_date']} to {report_data['period']['end_date']}"])
            writer.writerow([])
            writer.writerow(['Summary'])
            writer.writerow(['Total Paystubs', report_data['summary']['total_paystubs']])
            writer.writerow(['Total Gross Pay', f"${report_data['summary']['total_gross_pay']:,.2f}"])
            writer.writerow(['Total Net Pay', f"${report_data['summary']['total_net_pay']:,.2f}"])
            writer.writerow(['Total Taxes', f"${report_data['summary']['total_taxes']:,.2f}"])
            writer.writerow([])
            writer.writerow(['Monthly Breakdown'])
            writer.writerow(['Month', 'Gross Pay', 'Net Pay', 'Taxes', 'Paystub Count'])
            for month in report_data['monthly_breakdown']:
                writer.writerow([
                    month['month_name'],
                    f"${month['gross_pay']:,.2f}",
                    f"${month['net_pay']:,.2f}",
                    f"${month['taxes']:,.2f}",
                    month['paystub_count']
                ])
        
        elif report_type == 'tax_summary':
            writer.writerow(['Tax Summary Report'])
            writer.writerow(['Year:', report_data['year']])
            writer.writerow([])
            writer.writerow(['Summary'])
            writer.writerow(['Total Gross Pay', f"${report_data['summary']['total_gross_pay']:,.2f}"])
            writer.writerow(['Total Taxes', f"${report_data['summary']['total_taxes']:,.2f}"])
            writer.writerow(['Effective Tax Rate', f"{report_data['summary']['effective_tax_rate']}%"])
            writer.writerow([])
            writer.writerow(['Quarterly Breakdown'])
            writer.writerow(['Quarter', 'Gross Pay', 'Total Taxes', 'Federal', 'Social Security', 'Medicare', 'State', 'Rate'])
            for q in report_data['quarterly_breakdown']:
                writer.writerow([
                    q['period'],
                    f"${q['gross_pay']:,.2f}",
                    f"${q['total_taxes']:,.2f}",
                    f"${q['federal']:,.2f}",
                    f"${q['social_security']:,.2f}",
                    f"${q['medicare']:,.2f}",
                    f"${q['state']:,.2f}",
                    f"{q['effective_rate']}%"
                ])
        
        elif report_type == 'employee_earnings':
            writer.writerow(['Employee Earnings Report'])
            writer.writerow(['Year:', report_data['year']])
            writer.writerow([])
            writer.writerow(['Employee Name', 'Job Title', 'State', 'YTD Gross', 'YTD Net', 'Regular', 'Overtime', 'Bonus', 'Paystub Count'])
            for emp in report_data['employees']:
                writer.writerow([
                    emp['employee_name'],
                    emp['job_title'],
                    emp['state'],
                    f"${emp['ytd_gross']:,.2f}",
                    f"${emp['ytd_net']:,.2f}",
                    f"${emp['earnings_breakdown']['regular']:,.2f}",
                    f"${emp['earnings_breakdown']['overtime']:,.2f}",
                    f"${emp['earnings_breakdown']['bonus']:,.2f}",
                    emp['paystub_count']
                ])
        
        elif report_type == 'pto_report':
            writer.writerow(['PTO Report'])
            writer.writerow(['Generated:', report_data['generated_at']])
            writer.writerow([])
            writer.writerow(['Employee Name', 'Job Title', 'Vacation Balance', 'Sick Balance', 'Personal Balance', 'Total Balance'])
            for emp in report_data['employees']:
                writer.writerow([
                    emp['employee_name'],
                    emp['job_title'],
                    f"{emp['vacation']['balance']:.2f}",
                    f"{emp['sick']['balance']:.2f}",
                    f"{emp['personal']['balance']:.2f}",
                    f"{emp['totals']['balance']:.2f}"
                ])
        
        # Prepare response
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{report_type}_{datetime.now().strftime("%Y%m%d")}.csv'
        )
        
    except Exception as e:
        print(f"CSV generation error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to generate CSV'
        }), 500


# ============================================================================
# CUSTOM REPORT BUILDER (Advanced)
# ============================================================================

@reports_bp.route('/api/reports/custom', methods=['POST'])
@jwt_required()
def custom_report():
    """
    Build custom report with flexible parameters
    
    POST /api/reports/custom
    Body: {
        "report_name": "Custom Report",
        "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
        "metrics": ["gross_pay", "net_pay", "taxes"],
        "grouping": "monthly",
        "filters": {"employee_ids": [1, 2], "states": ["CA", "NY"]}
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Build custom query based on parameters
        # Implementation depends on specific requirements
        
        return jsonify({
            'success': True,
            'message': 'Custom report generation coming soon'
        }), 200
        
    except Exception as e:
        print(f"Custom report error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to generate custom report'
        }), 500
