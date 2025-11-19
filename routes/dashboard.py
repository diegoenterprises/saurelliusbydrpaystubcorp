#!/usr/bin/env python3
"""
Saurellius Platform - Dashboard & Analytics Routes
YTD stats, rewards, activity feeds, reports
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, Employee, Paystub, AuditLog
from sqlalchemy import func, extract
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from utils.weather_service import WeatherService

weather_service = WeatherService()

dashboard_bp = Blueprint('dashboard', __name__)

# ============================================================================
# DASHBOARD SUMMARY
# ============================================================================

# ============================================================================
# WEATHER AND LOCATION
# ============================================================================

@dashboard_bp.route('/api/dashboard/weather', methods=['GET'])
@jwt_required()
def get_weather_data():
    """
    Get real-time weather and location data for the user's IP.
    
    GET /api/dashboard/weather
    """
    try:
        # In a real-world scenario, we would get the user's IP from the request
        # (e.g., request.headers.get('X-Forwarded-For') or request.remote_addr).
        # For this mock implementation, we'll use a placeholder or the request IP.
        
        # NOTE: Elastic Beanstalk will forward the client IP in the 
        # X-Forwarded-For header. We'll use a safe fallback.
        
        # Get client IP address
        if request.headers.getlist("X-Forwarded-For"):
            ip_address = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip_address = request.remote_addr
            
        # Use a dummy IP for testing if the remote_addr is localhost/127.0.0.1
        if ip_address in ['127.0.0.1', 'localhost', '::1']:
            ip_address = '8.8.8.8' # Google DNS for a reliable test location
            
        weather_data = weather_service.get_full_weather_data(ip_address)
        
        if weather_data['status'] == 'error':
            return jsonify({'success': False, 'message': weather_data['message']}), 500
            
        return jsonify({
            'success': True,
            'data': weather_data
        }), 200
        
    except Exception as e:
        print(f"Weather data error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to load weather data'
        }), 500


# ============================================================================
# DASHBOARD SUMMARY
# ============================================================================

@dashboard_bp.route('/api/dashboard/summary', methods=['GET'])
@jwt_required()
def get_dashboard_summary():
    """
    Get complete dashboard summary
    
    GET /api/dashboard/summary
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # ====================================================================
        # PAYSTUB STATISTICS
        # ====================================================================
        
        total_paystubs = Paystub.query.filter_by(
            user_id=user_id,
            status='finalized'
        ).count()
        
        # This month's paystubs
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        this_month_count = Paystub.query.filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.created_at >= month_start
        ).count()
        
        # Last month's paystubs for comparison
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        last_month_end = month_start
        
        last_month_count = Paystub.query.filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.created_at >= last_month_start,
            Paystub.created_at < last_month_end
        ).count()
        
        # Calculate percentage change
        if last_month_count > 0:
            paystub_change = ((this_month_count - last_month_count) / last_month_count) * 100
        else:
            paystub_change = 100 if this_month_count > 0 else 0
        
        # ====================================================================
        # YTD TOTALS
        # ====================================================================
        
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        ytd_data = db.session.query(
            func.sum(Paystub.gross_pay).label('ytd_gross'),
            func.sum(Paystub.net_pay).label('ytd_net'),
            func.sum(Paystub.federal_income_tax).label('ytd_federal'),
            func.sum(Paystub.social_security_tax).label('ytd_ss'),
            func.sum(Paystub.medicare_tax).label('ytd_medicare'),
            func.sum(Paystub.state_income_tax).label('ytd_state'),
            func.sum(Paystub.total_taxes).label('ytd_total_taxes'),
            func.avg(Paystub.net_pay).label('avg_net_pay')
        ).filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.created_at >= year_start
        ).first()
        
        # ====================================================================
        # EMPLOYEE STATISTICS
        # ====================================================================
        
        total_employees = Employee.query.filter_by(
            user_id=user_id,
            status='active'
        ).count()
        
        # New employees this month
        new_employees_count = Employee.query.filter(
            Employee.user_id == user_id,
            Employee.created_at >= month_start
        ).count()
        
        # Get active employees list
        employees = Employee.query.filter_by(
            user_id=user_id,
            status='active'
        ).order_by(Employee.last_name).limit(10).all()
        
        # ====================================================================
        # RECENT ACTIVITY
        # ====================================================================
        
        recent_paystubs = Paystub.query.filter_by(
            user_id=user_id,
            status='finalized'
        ).order_by(Paystub.created_at.desc()).limit(10).all()
        
        recent_activity = []
        for stub in recent_paystubs:
            recent_activity.append({
                'type': 'paystub_generated',
                'employee_name': stub.employee.full_name,
                'employee_id': stub.employee_id,
                'amount': float(stub.net_pay),
                'date': stub.created_at.isoformat(),
                'verification_id': stub.verification_id
            })
        
        # Add employee additions
        recent_employees = Employee.query.filter(
            Employee.user_id == user_id,
            Employee.created_at >= (now - timedelta(days=30))
        ).order_by(Employee.created_at.desc()).limit(5).all()
        
        for emp in recent_employees:
            recent_activity.append({
                'type': 'employee_added',
                'employee_name': emp.full_name,
                'employee_id': emp.id,
                'date': emp.created_at.isoformat(),
                'job_title': emp.job_title
            })
        
        # Sort by date
        recent_activity.sort(key=lambda x: x['date'], reverse=True)
        recent_activity = recent_activity[:10]
        
        # ====================================================================
        # NEXT PAY DATE
        # ====================================================================
        
        # Find most recent paystub to predict next pay date
        latest_paystub = Paystub.query.filter_by(
            user_id=user_id
        ).order_by(Paystub.pay_date.desc()).first()
        
        if latest_paystub:
            # Average pay frequency (biweekly = 14 days)
            next_pay_date = latest_paystub.pay_date + timedelta(days=14)
            days_until_paydate = (next_pay_date - now.date()).days
        else:
            next_pay_date = None
            days_until_paydate = None
        
        # ====================================================================
        # MONTHLY BREAKDOWN
        # ====================================================================
        
        # Get paystubs by month for chart
        monthly_data = db.session.query(
            extract('month', Paystub.pay_date).label('month'),
            func.sum(Paystub.gross_pay).label('gross'),
            func.sum(Paystub.net_pay).label('net'),
            func.sum(Paystub.total_taxes).label('taxes'),
            func.count(Paystub.id).label('count')
        ).filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= year_start.date()
        ).group_by('month').all()
        
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
        
        # ====================================================================
        # COMPILE RESPONSE
        # ====================================================================
        
        return jsonify({
            'success': True,
            'statistics': {
                'total_paystubs': total_paystubs,
                'this_month_paystubs': this_month_count,
                'paystub_change_percent': round(paystub_change, 1),
                'total_employees': total_employees,
                'new_employees_this_month': new_employees_count
            },
            'ytd': {
                'gross_pay': float(ytd_data.ytd_gross or 0),
                'net_pay': float(ytd_data.ytd_net or 0),
                'total_taxes': float(ytd_data.ytd_total_taxes or 0),
                'taxes_breakdown': {
                    'federal': float(ytd_data.ytd_federal or 0),
                    'social_security': float(ytd_data.ytd_ss or 0),
                    'medicare': float(ytd_data.ytd_medicare or 0),
                    'state': float(ytd_data.ytd_state or 0)
                },
                'average_net_pay': float(ytd_data.avg_net_pay or 0)
            },
            'next_pay_date': next_pay_date.isoformat() if next_pay_date else None,
            'days_until_paydate': days_until_paydate,
            'employees': [{
                'id': emp.id,
                'name': emp.full_name,
                'job_title': emp.job_title,
                'state': emp.address_state,
                'pay_rate': float(emp.pay_rate),
                'ytd_gross': float(emp.ytd_gross_pay),
                'ytd_net': float(emp.ytd_net_pay)
            } for emp in employees],
            'recent_activity': recent_activity,
            'monthly_breakdown': monthly_breakdown,
            'rewards': {
                'points': user.reward_points,
                'tier': user.reward_tier,
                'lifetime_points': user.total_lifetime_points,
                'tier_progress': calculate_tier_progress(user.total_lifetime_points, user.reward_tier)
            },
            'subscription': {
                'tier': user.subscription_tier,
                'status': user.subscription_status,
                'paystubs_used': user.paystubs_used_this_month,
                'paystubs_limit': user.monthly_paystub_limit,
                'usage_percent': (user.paystubs_used_this_month / user.monthly_paystub_limit * 100) if user.monthly_paystub_limit > 0 else 0
            }
        }), 200
        
    except Exception as e:
        print(f"Dashboard summary error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': 'Failed to load dashboard'
        }), 500


# ============================================================================
# HELPER: CALCULATE TIER PROGRESS
# ============================================================================

def calculate_tier_progress(lifetime_points, current_tier):
    """Calculate progress to next tier"""
    tiers = {
        'bronze': {'min': 0, 'max': 1000},
        'silver': {'min': 1000, 'max': 5000},
        'gold': {'min': 5000, 'max': 10000},
        'platinum': {'min': 10000, 'max': float('inf')}
    }
    
    tier_info = tiers.get(current_tier, tiers['bronze'])
    
    if tier_info['max'] == float('inf'):
        return 100.0
    
    points_in_tier = lifetime_points - tier_info['min']
    tier_range = tier_info['max'] - tier_info['min']
    
    progress = (points_in_tier / tier_range) * 100
    
    return round(min(progress, 100), 1)


# ============================================================================
# ANALYTICS - PAYROLL TRENDS
# ============================================================================

@dashboard_bp.route('/api/dashboard/analytics/payroll-trends', methods=['GET'])
@jwt_required()
def get_payroll_trends():
    """
    Get payroll trends over time
    
    GET /api/dashboard/analytics/payroll-trends?period=year
    """
    try:
        user_id = get_jwt_identity()
        
        period = request.args.get('period', 'year')  # year, quarter, month
        
        now = datetime.now(timezone.utc)
        
        if period == 'year':
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == 'quarter':
            quarter = (now.month - 1) // 3
            start_month = quarter * 3 + 1
            start_date = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # month
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Get weekly aggregates
        weekly_data = db.session.query(
            func.date_trunc('week', Paystub.pay_date).label('week'),
            func.sum(Paystub.gross_pay).label('gross'),
            func.sum(Paystub.net_pay).label('net'),
            func.sum(Paystub.total_taxes).label('taxes'),
            func.count(Paystub.id).label('count')
        ).filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= start_date.date()
        ).group_by('week').order_by('week').all()
        
        trends = []
        for row in weekly_data:
            trends.append({
                'week': row.week.isoformat() if row.week else None,
                'gross_pay': float(row.gross or 0),
                'net_pay': float(row.net or 0),
                'taxes': float(row.taxes or 0),
                'paystub_count': int(row.count)
            })
        
        return jsonify({
            'success': True,
            'period': period,
            'trends': trends
        }), 200
        
    except Exception as e:
        print(f"Payroll trends error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get payroll trends'
        }), 500


# ============================================================================
# ANALYTICS - EMPLOYEE COSTS
# ============================================================================

@dashboard_bp.route('/api/dashboard/analytics/employee-costs', methods=['GET'])
@jwt_required()
def get_employee_costs():
    """Get cost breakdown by employee"""
    try:
        user_id = get_jwt_identity()
        
        employee_costs = db.session.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            func.sum(Paystub.gross_pay).label('total_gross'),
            func.sum(Paystub.net_pay).label('total_net'),
            func.sum(Paystub.total_taxes).label('total_taxes'),
            func.count(Paystub.id).label('paystub_count')
        ).join(
            Paystub, Paystub.employee_id == Employee.id
        ).filter(
            Employee.user_id == user_id,
            Paystub.status == 'finalized'
        ).group_by(
            Employee.id, Employee.first_name, Employee.last_name
        ).order_by(func.sum(Paystub.gross_pay).desc()).all()
        
        costs = []
        for row in employee_costs:
            costs.append({
                'employee_id': row.id,
                'employee_name': f"{row.first_name} {row.last_name}",
                'total_gross': float(row.total_gross or 0),
                'total_net': float(row.total_net or 0),
                'total_taxes': float(row.total_taxes or 0),
                'paystub_count': int(row.paystub_count)
            })
        
        return jsonify({
            'success': True,
            'employee_costs': costs
        }), 200
        
    except Exception as e:
        print(f"Employee costs error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get employee costs'
        }), 500


# ============================================================================
# REPORTS - TAX SUMMARY
# ============================================================================

@dashboard_bp.route('/api/dashboard/reports/tax-summary', methods=['GET'])
@jwt_required()
def get_tax_summary():
    """
    Get comprehensive tax summary report
    
    GET /api/dashboard/reports/tax-summary?year=2025
    """
    try:
        user_id = get_jwt_identity()
        
        year = request.args.get('year', datetime.now().year, type=int)
        year_start = datetime(year, 1, 1).date()
        year_end = datetime(year, 12, 31).date()
        
        # Get tax totals by type
        tax_summary = db.session.query(
            func.sum(Paystub.federal_income_tax).label('federal'),
            func.sum(Paystub.social_security_tax).label('ss'),
            func.sum(Paystub.medicare_tax).label('medicare'),
            func.sum(Paystub.state_income_tax).label('state'),
            func.sum(Paystub.state_disability_tax).label('sdi'),
            func.sum(Paystub.local_income_tax).label('local'),
            func.sum(Paystub.total_taxes).label('total')
        ).filter(
            Paystub.user_id == user_id,
            Paystub.status == 'finalized',
            Paystub.pay_date >= year_start,
            Paystub.pay_date <= year_end
        ).first()
        
        # Get quarterly breakdown
        quarterly = []
        for quarter in range(1, 5):
            q_start = datetime(year, (quarter-1)*3 + 1, 1).date()
            if quarter == 4:
                q_end = year_end
            else:
                q_end = datetime(year, quarter*3, 1).date()
                # Get last day of month
                next_month = q_end.replace(day=28) + timedelta(days=4)
                q_end = next_month - timedelta(days=next_month.day)
            
            q_data = db.session.query(
                func.sum(Paystub.total_taxes).label('total_taxes'),
                func.sum(Paystub.gross_pay).label('gross_pay')
            ).filter(
                Paystub.user_id == user_id,
                Paystub.status == 'finalized',
                Paystub.pay_date >= q_start,
                Paystub.pay_date <= q_end
            ).first()
            
            quarterly.append({
                'quarter': quarter,
                'total_taxes': float(q_data.total_taxes or 0),
                'gross_pay': float(q_data.gross_pay or 0)
            })
        
        return jsonify({
            'success': True,
            'year': year,
            'summary': {
                'federal_income_tax': float(tax_summary.federal or 0),
                'social_security': float(tax_summary.ss or 0),
                'medicare': float(tax_summary.medicare or 0),
                'state_income_tax': float(tax_summary.state or 0),
                'state_disability': float(tax_summary.sdi or 0),
                'local_income_tax': float(tax_summary.local or 0),
                'total_taxes': float(tax_summary.total or 0)
            },
            'quarterly': quarterly
        }), 200
        
    except Exception as e:
        print(f"Tax summary error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to generate tax summary'
        }), 500


# ============================================================================
# REPORTS - EMPLOYEE EARNINGS
# ============================================================================

@dashboard_bp.route('/api/dashboard/reports/employee-earnings', methods=['GET'])
@jwt_required()
def get_employee_earnings_report():
    """Get detailed employee earnings report"""
    try:
        user_id = get_jwt_identity()
        
        employee_id = request.args.get('employee_id', type=int)
        year = request.args.get('year', datetime.now().year, type=int)
        
        query = db.session.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            Employee.ytd_gross_pay,
            Employee.ytd_net_pay,
            Employee.ytd_federal_tax,
            Employee.ytd_ss_tax,
            Employee.ytd_medicare_tax,
            Employee.ytd_state_tax
        ).filter(
            Employee.user_id == user_id,
            Employee.status == 'active'
        )
        
        if employee_id:
            query = query.filter(Employee.id == employee_id)
        
        employees = query.all()
        
        earnings_report = []
        for emp in employees:
            earnings_report.append({
                'employee_id': emp.id,
                'employee_name': f"{emp.first_name} {emp.last_name}",
                'ytd_gross': float(emp.ytd_gross_pay),
                'ytd_net': float(emp.ytd_net_pay),
                'ytd_taxes': {
                    'federal': float(emp.ytd_federal_tax),
                    'social_security': float(emp.ytd_ss_tax),
                    'medicare': float(emp.ytd_medicare_tax),
                    'state': float(emp.ytd_state_tax)
                }
            })
        
        return jsonify({
            'success': True,
            'year': year,
            'employee_earnings': earnings_report
        }), 200
        
    except Exception as e:
        print(f"Employee earnings report error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to generate employee earnings report'
        }), 500


# ============================================================================
# AUDIT LOG
# ============================================================================

@dashboard_bp.route('/api/dashboard/audit-log', methods=['GET'])
@jwt_required()
def get_audit_log():
    """Get audit log for user"""
    try:
        user_id = get_jwt_identity()
        
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        action = request.args.get('action')
        
        query = AuditLog.query.filter_by(user_id=user_id)
        
        if action:
            query = query.filter_by(action=action)
        
        logs = query.order_by(AuditLog.created_at.desc())\
            .limit(limit)\
            .offset(offset)\
            .all()
        
        return jsonify({
            'success': True,
            'logs': [{
                'id': log.id,
                'action': log.action,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'changes': log.changes,
                'ip_address': log.ip_address,
                'created_at': log.created_at.isoformat()
            } for log in logs],
            'total': AuditLog.query.filter_by(user_id=user_id).count()
        }), 200
        
    except Exception as e:
        print(f"Audit log error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get audit log'
        }), 500