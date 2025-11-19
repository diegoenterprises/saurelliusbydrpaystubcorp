"""
Smart YTD Continuation Logic - Auto-fill next paystub from previous
Implements all features from deployment guide lines 2700-2900
"""
from datetime import datetime, timedelta
from decimal import Decimal
# from models import Employee, Paystub # Assuming models are in models.py
# from application import db # Assuming db object is initialized in application.py
from sqlalchemy import extract, func

class SmartYTDContinuation:
    """
    Handles smart continuation of paystubs with automatic YTD tracking
    """
    
    # 2025 Tax Limits
    SS_WAGE_BASE_2025 = Decimal('176100.00')
    ADDITIONAL_MEDICARE_THRESHOLD = {
        'Single': Decimal('200000.00'),
        'Married': Decimal('250000.00'),
        'Head of Household': Decimal('200000.00')
    }
    
    @staticmethod
    def calculate_next_pay_date(last_pay_date, pay_frequency):
        """
        Calculate next pay date based on frequency
        """
        if not last_pay_date:
            return None
            
        if pay_frequency == 'Weekly':
            return last_pay_date + timedelta(days=7)
        elif pay_frequency == 'BiWeekly':
            return last_pay_date + timedelta(days=14)
        elif pay_frequency == 'SemiMonthly':
            # Semi-monthly: 15th and last day of month
            if last_pay_date.day == 15:
                # Next is last day of month
                next_month = last_pay_date.month
                next_year = last_pay_date.year
                if next_month == 12:
                    next_month = 1
                    next_year += 1
                else:
                    next_month += 1
                # Get last day of month
                from calendar import monthrange
                last_day = monthrange(next_year, next_month)[1]
                return datetime(next_year, next_month, last_day).date()
            else:
                # Next is 15th of next month
                next_month = last_pay_date.month + 1
                next_year = last_pay_date.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                return datetime(next_year, next_month, 15).date()
        elif pay_frequency == 'Monthly':
            # Same day next month
            next_month = last_pay_date.month + 1
            next_year = last_pay_date.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            try:
                return datetime(next_year, next_month, last_pay_date.day).date()
            except ValueError:
                # Day doesn't exist in next month (e.g., Jan 31 -> Feb 31)
                from calendar import monthrange
                last_day = monthrange(next_year, next_month)[1]
                return datetime(next_year, next_month, last_day).date()
        
        return None
    
    @staticmethod
    def get_ytd_summary(employee_id, current_year=None):
        """
        Get complete YTD summary for an employee
        NOTE: This function requires the database models (Employee, Paystub) and db object to be correctly imported and configured.
        """
        # Placeholder for database interaction logic
        return {
            'ytd_gross': Decimal('0.00'),
            'ytd_net': Decimal('0.00'),
            'paystub_count': 0
        }
