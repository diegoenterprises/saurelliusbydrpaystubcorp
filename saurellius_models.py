#!/usr/bin/env python3
"""
Saurellius Platform - Complete Database Models
117+ fields across all models for production-ready payroll system
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, func
from sqlalchemy.dialects.postgresql import JSONB
import hashlib
import uuid

db = SQLAlchemy()

# ============================================================================
# USER MODEL - Authentication & Account Management
# ============================================================================

class User(db.Model):
    __tablename__ = 'users'
    
    # Primary Identity (8 fields)
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(64))
    email_verification_sent_at = db.Column(db.DateTime)
    
    # Authentication (6 fields)
    password_hash = db.Column(db.String(255), nullable=False)
    password_reset_token = db.Column(db.String(64))
    password_reset_expires = db.Column(db.DateTime)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32))
    last_login = db.Column(db.DateTime)
    
    # Personal Information (6 fields)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    phone_verified = db.Column(db.Boolean, default=False)
    date_of_birth = db.Column(db.Date)
    timezone = db.Column(db.String(50), default='America/Los_Angeles')
    locale = db.Column(db.String(10), default='en_US')
    
    # Subscription & Billing (12 fields)
    subscription_tier = db.Column(db.String(20), default='starter')  # starter, professional, business
    subscription_status = db.Column(db.String(20), default='trial')  # trial, active, past_due, canceled
    subscription_starts_at = db.Column(db.DateTime)
    subscription_ends_at = db.Column(db.DateTime)
    subscription_renews_at = db.Column(db.DateTime)
    stripe_customer_id = db.Column(db.String(50), unique=True)
    stripe_subscription_id = db.Column(db.String(50))
    stripe_payment_method_id = db.Column(db.String(50))
    monthly_paystub_limit = db.Column(db.Integer, default=10)
    paystubs_used_this_month = db.Column(db.Integer, default=0)
    billing_cycle_starts_at = db.Column(db.DateTime)
    billing_address = db.Column(JSONB)
    
    # Rewards System (8 fields)
    reward_points = db.Column(db.Integer, default=500)  # Welcome bonus
    total_lifetime_points = db.Column(db.Integer, default=500)
    reward_tier = db.Column(db.String(20), default='bronze')  # bronze, silver, gold, platinum
    tier_progress = db.Column(db.Float, default=0.0)
    achievements = db.Column(JSONB, default=list)
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    referral_count = db.Column(db.Integer, default=0)
    
    # Company Information (Optional - 5 fields)
    company_name = db.Column(db.String(255))
    company_ein = db.Column(db.String(20))
    company_address = db.Column(db.Text)
    company_phone = db.Column(db.String(20))
    company_logo_url = db.Column(db.String(500))
    
    # Security & Compliance (7 fields)
    account_locked = db.Column(db.Boolean, default=False)
    account_locked_reason = db.Column(db.String(255))
    account_locked_until = db.Column(db.DateTime)
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    ip_whitelist = db.Column(JSONB)
    security_questions = db.Column(JSONB)
    
    # Preferences & Settings (8 fields)
    notification_email = db.Column(db.Boolean, default=True)
    notification_sms = db.Column(db.Boolean, default=False)
    notification_push = db.Column(db.Boolean, default=True)
    notification_marketing = db.Column(db.Boolean, default=False)
    default_template = db.Column(db.String(50), default='eusotrip_original')
    auto_calculate_taxes = db.Column(db.Boolean, default=True)
    require_2fa_for_paystubs = db.Column(db.Boolean, default=False)
    theme_preference = db.Column(db.String(20), default='system')
    
    # Platform Metadata (6 fields)
    oauth_provider = db.Column(db.String(20))  # google, microsoft, apple
    oauth_provider_id = db.Column(db.String(100))
    api_key_hash = db.Column(db.String(64))
    api_requests_this_month = db.Column(db.Integer, default=0)
    api_rate_limit = db.Column(db.Integer, default=1000)
    api_last_request = db.Column(db.DateTime)
    
    # Timestamps (4 fields)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime)  # Soft delete
    last_activity_at = db.Column(db.DateTime)
    
    # Relationships
    employees = db.relationship('Employee', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    paystubs = db.relationship('Paystub', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', back_populates='user', lazy='dynamic')
    
    def __repr__(self):
        return f'<User {self.email}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'email': self.email,
            'name': self.name,
            'subscription_tier': self.subscription_tier,
            'reward_points': self.reward_points,
            'reward_tier': self.reward_tier
        }


# ============================================================================
# EMPLOYEE MODEL - Employee Management & Tax Information
# ============================================================================

class Employee(db.Model):
    __tablename__ = 'employees'
    
    # Primary Identity (3 fields)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Personal Information (9 fields)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100), nullable=False)
    ssn_encrypted = db.Column(db.Text, nullable=False)  # Encrypted
    email = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date, nullable=False)
    profile_photo_url = db.Column(db.String(500))
    emergency_contact = db.Column(JSONB)
    
    # Address Information (6 fields)
    address_street = db.Column(db.String(255), nullable=False)
    address_street2 = db.Column(db.String(255))
    address_city = db.Column(db.String(100), nullable=False)
    address_state = db.Column(db.String(2), nullable=False, index=True)
    address_zip = db.Column(db.String(10), nullable=False)
    address_country = db.Column(db.String(2), default='US')
    
    # Employment Information (10 fields)
    job_title = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(100))
    employee_id = db.Column(db.String(50))  # Company's internal ID
    hire_date = db.Column(db.Date, nullable=False)
    termination_date = db.Column(db.Date)
    employment_type = db.Column(db.String(20), default='full_time')  # full_time, part_time, contractor
    employment_status = db.Column(db.String(20), default='active')  # active, on_leave, terminated
    pay_rate = db.Column(db.Numeric(10, 2), nullable=False)
    pay_frequency = db.Column(db.String(20), default='biweekly')  # weekly, biweekly, semimonthly, monthly
    salary_or_hourly = db.Column(db.String(10), default='hourly')  # salary, hourly
    
    # Tax Information - Federal (7 fields)
    filing_status = db.Column(db.String(30), default='single')  # single, married, married_separate, head_of_household
    federal_allowances = db.Column(db.Integer, default=0)
    federal_additional_withholding = db.Column(db.Numeric(10, 2), default=0.00)
    federal_exempt = db.Column(db.Boolean, default=False)
    w4_year = db.Column(db.Integer)
    w4_form_type = db.Column(db.String(20), default='2020')  # pre2020, 2020+
    claimed_dependents = db.Column(db.Integer, default=0)
    
    # Tax Information - State (6 fields)
    state_filing_status = db.Column(db.String(30))
    state_allowances = db.Column(db.Integer, default=0)
    state_additional_withholding = db.Column(db.Numeric(10, 2), default=0.00)
    state_exempt = db.Column(db.Boolean, default=False)
    state_tax_id = db.Column(db.String(50))
    multiple_state_work = db.Column(db.Boolean, default=False)
    
    # Tax Information - Local (4 fields)
    local_jurisdiction = db.Column(db.String(100))
    local_tax_code = db.Column(db.String(20))
    local_additional_withholding = db.Column(db.Numeric(10, 2), default=0.00)
    local_exempt = db.Column(db.Boolean, default=False)
    
    # Year-to-Date Totals (15 fields)
    ytd_gross_pay = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_net_pay = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_federal_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_state_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_local_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_ss_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_medicare_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_ss_wages = db.Column(db.Numeric(12, 2), default=0.00)  # Social Security wage base tracking
    ytd_medicare_wages = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_401k = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_health_insurance = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_overtime_pay = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_bonus = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_commission = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_reimbursements = db.Column(db.Numeric(12, 2), default=0.00)
    
    # Benefits & Deductions (8 fields)
    contribution_401k_percent = db.Column(db.Numeric(5, 2), default=0.00)
    contribution_401k_fixed = db.Column(db.Numeric(10, 2), default=0.00)
    health_insurance_deduction = db.Column(db.Numeric(10, 2), default=0.00)
    dental_insurance_deduction = db.Column(db.Numeric(10, 2), default=0.00)
    vision_insurance_deduction = db.Column(db.Numeric(10, 2), default=0.00)
    life_insurance_deduction = db.Column(db.Numeric(10, 2), default=0.00)
    hsa_contribution = db.Column(db.Numeric(10, 2), default=0.00)
    other_deductions = db.Column(JSONB)
    
    # PTO Tracking (9 fields)
    vacation_hours_accrued = db.Column(db.Numeric(8, 2), default=0.00)
    vacation_hours_used = db.Column(db.Numeric(8, 2), default=0.00)
    vacation_hours_balance = db.Column(db.Numeric(8, 2), default=0.00)
    sick_hours_accrued = db.Column(db.Numeric(8, 2), default=0.00)
    sick_hours_used = db.Column(db.Numeric(8, 2), default=0.00)
    sick_hours_balance = db.Column(db.Numeric(8, 2), default=0.00)
    personal_hours_accrued = db.Column(db.Numeric(8, 2), default=0.00)
    personal_hours_used = db.Column(db.Numeric(8, 2), default=0.00)
    personal_hours_balance = db.Column(db.Numeric(8, 2), default=0.00)
    
    # PTO Accrual Rules (5 fields)
    pto_accrual_rate = db.Column(db.Numeric(8, 4), default=0.0384)  # hours per hour worked
    pto_accrual_frequency = db.Column(db.String(20), default='per_pay_period')
    pto_carryover_limit = db.Column(db.Numeric(8, 2), default=40.00)
    pto_max_balance = db.Column(db.Numeric(8, 2), default=160.00)
    pto_policy = db.Column(JSONB)
    
    # Direct Deposit (7 fields)
    direct_deposit_enabled = db.Column(db.Boolean, default=False)
    bank_name = db.Column(db.String(100))
    bank_routing_number_encrypted = db.Column(db.Text)  # Encrypted
    bank_account_number_encrypted = db.Column(db.Text)  # Encrypted
    bank_account_type = db.Column(db.String(20))  # checking, savings
    direct_deposit_allocation_percent = db.Column(db.Numeric(5, 2), default=100.00)
    direct_deposit_allocation_fixed = db.Column(db.Numeric(10, 2))
    
    # Performance & Notes (4 fields)
    performance_rating = db.Column(db.String(20))
    manager_id = db.Column(db.Integer)
    notes = db.Column(db.Text)
    tags = db.Column(JSONB)
    
    # Status & Metadata (4 fields)
    status = db.Column(db.String(20), default='active', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', back_populates='employees')
    paystubs = db.relationship('Paystub', back_populates='employee', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def state(self):
        return self.address_state
    
    def __repr__(self):
        return f'<Employee {self.full_name}>'


# ============================================================================
# PAYSTUB MODEL - Complete Paystub with All Calculations
# ============================================================================

class Paystub(db.Model):
    __tablename__ = 'paystubs'
    
    # Primary Identity (4 fields)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False, index=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Pay Period Information (5 fields)
    pay_date = db.Column(db.Date, nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    check_number = db.Column(db.String(20))
    pay_frequency = db.Column(db.String(20))
    
    # Earnings - Regular (5 fields)
    regular_hours = db.Column(db.Numeric(8, 2), default=0.00)
    regular_rate = db.Column(db.Numeric(10, 2), default=0.00)
    regular_pay = db.Column(db.Numeric(10, 2), default=0.00)
    salary_amount = db.Column(db.Numeric(10, 2), default=0.00)
    earnings_type = db.Column(db.String(20), default='hourly')  # hourly, salary
    
    # Earnings - Overtime (4 fields)
    overtime_hours = db.Column(db.Numeric(8, 2), default=0.00)
    overtime_rate = db.Column(db.Numeric(10, 2), default=0.00)
    overtime_pay = db.Column(db.Numeric(10, 2), default=0.00)
    overtime_multiplier = db.Column(db.Numeric(4, 2), default=1.5)
    
    # Earnings - Additional (5 fields)
    bonus = db.Column(db.Numeric(10, 2), default=0.00)
    commission = db.Column(db.Numeric(10, 2), default=0.00)
    tips = db.Column(db.Numeric(10, 2), default=0.00)
    reimbursements = db.Column(db.Numeric(10, 2), default=0.00)
    other_earnings = db.Column(JSONB)
    
    # Total Earnings (3 fields)
    gross_pay = db.Column(db.Numeric(10, 2), nullable=False)
    taxable_gross = db.Column(db.Numeric(10, 2))
    non_taxable_gross = db.Column(db.Numeric(10, 2), default=0.00)
    
    # Federal Taxes (6 fields)
    federal_income_tax = db.Column(db.Numeric(10, 2), default=0.00)
    social_security_tax = db.Column(db.Numeric(10, 2), default=0.00)
    medicare_tax = db.Column(db.Numeric(10, 2), default=0.00)
    additional_medicare_tax = db.Column(db.Numeric(10, 2), default=0.00)
    federal_unemployment_tax = db.Column(db.Numeric(10, 2), default=0.00)
    federal_tax_calculation = db.Column(JSONB)
    
    # State Taxes (5 fields)
    state_income_tax = db.Column(db.Numeric(10, 2), default=0.00)
    state_disability_tax = db.Column(db.Numeric(10, 2), default=0.00)
    state_unemployment_tax = db.Column(db.Numeric(10, 2), default=0.00)
    state_code = db.Column(db.String(2))
    state_tax_calculation = db.Column(JSONB)
    
    # Local Taxes (4 fields)
    local_income_tax = db.Column(db.Numeric(10, 2), default=0.00)
    local_jurisdiction = db.Column(db.String(100))
    local_tax_code = db.Column(db.String(20))
    local_tax_calculation = db.Column(JSONB)
    
    # Pre-Tax Deductions (5 fields)
    deduction_401k = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_hsa = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_fsa = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_transit = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_parking = db.Column(db.Numeric(10, 2), default=0.00)
    
    # Post-Tax Deductions (6 fields)
    deduction_health = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_dental = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_vision = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_life = db.Column(db.Numeric(10, 2), default=0.00)
    deduction_garnishment = db.Column(db.Numeric(10, 2), default=0.00)
    other_deductions = db.Column(JSONB)
    
    # Totals (4 fields)
    total_taxes = db.Column(db.Numeric(10, 2), default=0.00)
    total_deductions = db.Column(db.Numeric(10, 2), default=0.00)
    net_pay = db.Column(db.Numeric(10, 2), nullable=False)
    amount_in_words = db.Column(db.String(255))
    
    # PTO This Period (6 fields)
    vacation_hours_accrued = db.Column(db.Numeric(8, 2), default=0.00)
    vacation_hours_used = db.Column(db.Numeric(8, 2), default=0.00)
    sick_hours_accrued = db.Column(db.Numeric(8, 2), default=0.00)
    sick_hours_used = db.Column(db.Numeric(8, 2), default=0.00)
    personal_hours_accrued = db.Column(db.Numeric(8, 2), default=0.00)
    personal_hours_used = db.Column(db.Numeric(8, 2), default=0.00)
    
    # YTD Totals at Time of Generation (8 fields)
    ytd_gross_pay = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_net_pay = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_federal_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_state_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_ss_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_medicare_tax = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_401k = db.Column(db.Numeric(12, 2), default=0.00)
    ytd_hours_worked = db.Column(db.Numeric(10, 2), default=0.00)
    
    # Verification & Security (7 fields)
    verification_id = db.Column(db.String(20), unique=True, nullable=False)
    verification_qr_data = db.Column(db.Text)
    document_hash = db.Column(db.String(64))
    security_hash = db.Column(db.String(64))
    verification_status = db.Column(db.String(20), default='verified')
    verification_url = db.Column(db.String(500))
    tamper_proof_seal = db.Column(db.Text)
    
    # PDF & Storage (6 fields)
    pdf_url = db.Column(db.String(500))
    pdf_expires_at = db.Column(db.DateTime)
    s3_bucket = db.Column(db.String(100))
    s3_key = db.Column(db.String(255))
    file_size_bytes = db.Column(db.Integer)
    pdf_generated_at = db.Column(db.DateTime)
    
    # Template & Customization (4 fields)
    template_id = db.Column(db.String(50), default='eusotrip_original')
    template_version = db.Column(db.String(20))
    custom_branding = db.Column(JSONB)
    custom_fields = db.Column(JSONB)
    
    # Compliance & Audit (5 fields)
    snappt_verified = db.Column(db.Boolean, default=True)
    snappt_verification_date = db.Column(db.DateTime)
    compliance_flags = db.Column(JSONB)
    audit_trail = db.Column(JSONB)
    regeneration_count = db.Column(db.Integer, default=0)
    
    # Status & Workflow (5 fields)
    status = db.Column(db.String(20), default='draft')  # draft, finalized, voided, archived
    finalized_at = db.Column(db.DateTime)
    finalized_by = db.Column(db.Integer)
    voided_at = db.Column(db.DateTime)
    void_reason = db.Column(db.String(255))
    
    # Notifications (3 fields)
    emailed_at = db.Column(db.DateTime)
    emailed_to = db.Column(db.String(255))
    notification_log = db.Column(JSONB)
    
    # Metadata (4 fields)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime)
    generation_time_ms = db.Column(db.Integer)
    
    # Relationships
    user = db.relationship('User', back_populates='paystubs')
    employee = db.relationship('Employee', back_populates='paystubs')
    
    def __repr__(self):
        return f'<Paystub {self.verification_id} - {self.employee.full_name}>'


# ============================================================================
# AUDIT LOG MODEL - Complete Activity Tracking
# ============================================================================

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.Integer)
    changes = db.Column(JSONB)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    request_id = db.Column(db.String(36))
    severity = db.Column(db.String(20))  # info, warning, error, critical
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    user = db.relationship('User', back_populates='audit_logs')


# ============================================================================
# EVENTS - Auto-update timestamps and calculations
# ============================================================================

@event.listens_for(User, 'before_insert')
@event.listens_for(User, 'before_update')
def generate_referral_code(mapper, connection, target):
    if not target.referral_code:
        target.referral_code = hashlib.md5(f"{target.email}{datetime.now().timestamp()}".encode()).hexdigest()[:10].upper()


@event.listens_for(Paystub, 'before_insert')
def generate_verification_id(mapper, connection, target):
    if not target.verification_id:
        target.verification_id = f"SAU{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"


@event.listens_for(Employee, 'before_update')
def update_pto_balances(mapper, connection, target):
    """Auto-calculate PTO balances"""
    target.vacation_hours_balance = target.vacation_hours_accrued - target.vacation_hours_used
    target.sick_hours_balance = target.sick_hours_accrued - target.sick_hours_used
    target.personal_hours_balance = target.personal_hours_accrued - target.personal_hours_used
