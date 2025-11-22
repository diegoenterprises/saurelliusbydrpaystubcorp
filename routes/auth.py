#!/usr/bin/env python3
"""
Saurellius Platform - Authentication Routes
Complete login, register, JWT management, OAuth, 2FA
"""

from flask import Blueprint, request, jsonify, redirect, url_for
from flask_jwt_extended import (
    create_access_token, create_refresh_token, 
    jwt_required, get_jwt_identity, get_jwt
)
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, AuditLog
from datetime import datetime, timezone, timedelta
import re
import secrets
import pyotp
import os
from functools import wraps
from utils.email_service import EmailService

email_service = EmailService()

auth_bp = Blueprint('auth', __name__)

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain an uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain a lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain a number"
    return True, "Password is strong"

def validate_phone(phone):
    """Validate phone format"""
    pattern = r'^\+?1?\d{9,15}$'
    cleaned = re.sub(r'[^\d+]', '', phone)
    return re.match(pattern, cleaned) is not None

# ============================================================================
# SUBSCRIPTION TIER LIMITS
# ============================================================================

SUBSCRIPTION_LIMITS = {
    'starter': {
        'monthly_paystubs': 10,
        'employees': 5,
        'templates': ['eusotrip_original'],
        'api_access': False,
        'price': 50
    },
    'professional': {
        'monthly_paystubs': 30,
        'employees': 15,
        'templates': ['eusotrip_original', 'premium_blue', 'modern_gradient'],
        'api_access': False,
        'price': 100
    },
    'business': {
        'monthly_paystubs': -1,  # Unlimited
        'employees': -1,
        'templates': 'all',
        'api_access': True,
        'price': 150
    }
}

# ============================================================================
# AUDIT LOG DECORATOR
# ============================================================================

def audit_action(action, resource_type=None):
    """Decorator to log user actions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            result = f(*args, **kwargs)
            
            try:
                user_id = get_jwt_identity() if jwt_required else None
                
                log = AuditLog(
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', ''),
                    request_id=request.headers.get('X-Request-ID'),
                    severity='info'
                )
                db.session.add(log)
                db.session.commit()
            except Exception as e:
                print(f"Audit log error: {str(e)}")
            
            return result
        return decorated_function
    return decorator

# ============================================================================
# REGISTRATION
# ============================================================================

@auth_bp.route('/api/auth/register', methods=['POST'])
@audit_action('user_registration')
def register():
    """
    Register new user
    POST /api/auth/register
    Body: {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-123-4567",
        "password": "SecurePass123",
        "subscription_tier": "professional"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['name', 'email', 'password']
        if not all(k in data for k in required):
            return jsonify({
                'success': False,
                'message': 'Missing required fields'
            }), 400
        
        # Validate email
        if not validate_email(data['email']):
            return jsonify({
                'success': False,
                'message': 'Invalid email format'
            }), 400
        
        # Check if email exists
        if User.query.filter_by(email=data['email'].lower()).first():
            return jsonify({
                'success': False,
                'message': 'Email already registered'
            }), 409
        
        # Validate password
        is_valid, message = validate_password(data['password'])
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            }), 400
        
        # Validate phone if provided
        if 'phone' in data and data['phone']:
            if not validate_phone(data['phone']):
                return jsonify({
                    'success': False,
                    'message': 'Invalid phone format'
                }), 400
        
        # Get subscription tier
        tier = data.get('subscription_tier', 'starter')
        if tier not in SUBSCRIPTION_LIMITS:
            tier = 'starter'
        
        # Create user
        user = User(
            name=data['name'],
            email=data['email'].lower(),
            phone=data.get('phone'),
            password_hash=generate_password_hash(data['password']),
            subscription_tier=tier,
            subscription_status='trial',
            subscription_starts_at=datetime.now(timezone.utc),
            subscription_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            monthly_paystub_limit=SUBSCRIPTION_LIMITS[tier]['monthly_paystubs'],
            reward_points=500,  # Welcome bonus
            total_lifetime_points=500,
            email_verification_token=secrets.token_urlsafe(32)
        )
        
        # Handle referral
        if 'referral_code' in data:
            referrer = User.query.filter_by(referral_code=data['referral_code']).first()
            if referrer:
                user.referred_by = referrer.id
                referrer.referral_count += 1
                referrer.reward_points += 100
                referrer.total_lifetime_points += 100
        
        db.session.add(user)
        db.session.commit()
        
        # Generate tokens
        access_token = create_access_token(
            identity=user.id,
            additional_claims={
                'email': user.email,
                'tier': user.subscription_tier
            }
        )
        refresh_token = create_refresh_token(identity=user.id)
        
        # Log registration
        log = AuditLog(
            user_id=user.id,
            action='user_registered',
            resource_type='user',
            resource_id=user.id,
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'user': user.to_dict(),
            'token': access_token,
            'refresh_token': refresh_token,
            'subscription': {
                'tier': user.subscription_tier,
                'status': user.subscription_status,
                'monthly_limit': user.monthly_paystub_limit,
                'trial_ends': user.subscription_ends_at.isoformat()
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Registration error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Registration failed',
            'error': str(e)
        }), 500


# ============================================================================
# LOGIN
# ============================================================================

@auth_bp.route('/api/auth/login', methods=['POST'])
@audit_action('user_login')
def login():
    """
    Login user
    POST /api/auth/login
    Body: {
        "email": "john@example.com",
        "password": "SecurePass123",
        "remember_me": true
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('email') or not data.get('password'):
            return jsonify({
                'success': False,
                'message': 'Email and password required'
            }), 400
        
        user = User.query.filter_by(email=data['email'].lower()).first()
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'Invalid credentials'
            }), 401
        
        # Check if account is locked
        if user.account_locked:
            if user.account_locked_until and user.account_locked_until > datetime.now(timezone.utc):
                return jsonify({
                    'success': False,
                    'message': f'Account locked until {user.account_locked_until.isoformat()}',
                    'locked_until': user.account_locked_until.isoformat()
                }), 403
            else:
                # Unlock account if time has passed
                user.account_locked = False
                user.account_locked_until = None
                user.failed_login_attempts = 0
        
        # Verify password
        if not check_password_hash(user.password_hash, data['password']):
            user.failed_login_attempts += 1
            user.last_failed_login = datetime.now(timezone.utc)
            
            # Lock account after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.account_locked = True
                user.account_locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
                user.account_locked_reason = 'Too many failed login attempts'
            
            db.session.commit()
            
            return jsonify({
                'success': False,
                'message': 'Invalid credentials',
                'attempts_remaining': 5 - user.failed_login_attempts
            }), 401
        
        # Check if 2FA is enabled
        if user.two_factor_enabled:
            if not data.get('two_factor_code'):
                return jsonify({
                    'success': False,
                    'message': '2FA code required',
                    'requires_2fa': True
                }), 401
            
            # Verify 2FA code
            totp = pyotp.TOTP(user.two_factor_secret)
            if not totp.verify(data['two_factor_code']):
                return jsonify({
                    'success': False,
                    'message': 'Invalid 2FA code'
                }), 401
        
        # Successful login - reset failed attempts
        user.failed_login_attempts = 0
        user.last_login = datetime.now(timezone.utc)
        user.last_activity_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Generate tokens
        remember_me = data.get('remember_me', False)
        expires_delta = timedelta(days=30) if remember_me else timedelta(hours=12)
        
        access_token = create_access_token(
            identity=user.id,
            additional_claims={
                'email': user.email,
                'tier': user.subscription_tier
            },
            expires_delta=expires_delta
        )
        refresh_token = create_refresh_token(
            identity=user.id,
            expires_delta=timedelta(days=90)
        )
        
        # Log successful login
        log = AuditLog(
            user_id=user.id,
            action='user_login_success',
            resource_type='user',
            resource_id=user.id,
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': user.to_dict(),
            'token': access_token,
            'refresh_token': refresh_token,
            'subscription': {
                'tier': user.subscription_tier,
                'status': user.subscription_status,
                'paystubs_used': user.paystubs_used_this_month,
                'paystubs_limit': user.monthly_paystub_limit
            }
        }), 200
        
    except Exception as e:
        print(f"Login error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Login failed',
            'error': str(e)
        }), 500


# ============================================================================
# TOKEN REFRESH
# ============================================================================

@auth_bp.route('/api/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token
    POST /api/auth/refresh
    Headers: Authorization: Bearer <refresh_token>
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Update last activity
        user.last_activity_at = datetime.now(timezone.utc)
        db.session.commit()
        
        # Generate new access token
        access_token = create_access_token(
            identity=user.id,
            additional_claims={
                'email': user.email,
                'tier': user.subscription_tier
            }
        )
        
        return jsonify({
            'success': True,
            'token': access_token
        }), 200
        
    except Exception as e:
        print(f"Token refresh error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Token refresh failed'
        }), 500


# ============================================================================
# LOGOUT
# ============================================================================

@auth_bp.route('/api/auth/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout user (client-side token deletion)
    POST /api/auth/logout
    """
    try:
        user_id = get_jwt_identity()
        
        # Log logout
        log = AuditLog(
            user_id=user_id,
            action='user_logout',
            resource_type='user',
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        }), 200
        
    except Exception as e:
        print(f"Logout error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Logout failed'
        }), 500


# ============================================================================
# PASSWORD RESET
# ============================================================================

@auth_bp.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    """
    Send password reset link to user's email.
    
    POST /api/auth/forgot-password
    Body: {
        "email": "john@example.com"
    }
    """
    try:
        data = request.get_json()
        email = data.get('email', '').lower()
        
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
            
        user = User.query.filter_by(email=email).first()
        
        # Prevent email enumeration by always returning a success message
        # but only sending the email if the user exists.
        if user:
            # Generate a secure, time-limited token for password reset
            token = secrets.token_urlsafe(32)
            user.password_reset_token = token
            user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
            db.session.commit()
            
            # Construct the reset link (FRONTEND_URL must be set in env)
            reset_link = f"{os.environ.get('FRONTEND_URL')}/reset-password?token={token}&email={email}"
            
            # Email content
            subject = "Saurellius Platform - Password Reset Request"
            body_html = f"""
                <html>
                    <body>
                        <p>Hello {user.name},</p>
                        <p>You have requested a password reset for your Saurellius Platform account.</p>
                        <p>Please click the link below to reset your password. This link will expire in 1 hour.</p>
                        <p><a href="{reset_link}">Reset My Password</a></p>
                        <p>If you did not request a password reset, please ignore this email.</p>
                        <p>Thank you,<br>The Saurellius Team</p>
                    </body>
                </html>
            """
            
            # Send email
            email_service.send_email(
                recipient=user.email,
                subject=subject,
                body_html=body_html
            )
            
            # Audit log
            log = AuditLog(
                user_id=user.id,
                action='password_reset_requested',
                resource_type='user',
                resource_id=user.id,
                ip_address=request.remote_addr,
                severity='warning'
            )
            db.session.add(log)
            db.session.commit()
            
        return jsonify({
            'success': True,
            'message': 'If an account with that email exists, a password reset link has been sent.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Forgot password error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Request failed'
        }), 500


@auth_bp.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    """
    Reset user password using a valid token.
    
    POST /api/auth/reset-password
    Body: {
        "email": "john@example.com",
        "token": "secure_token",
        "new_password": "NewSecurePass123"
    }
    """
    try:
        data = request.get_json()
        email = data.get('email', '').lower()
        token = data.get('token')
        new_password = data.get('new_password')
        
        if not all([email, token, new_password]):
            return jsonify({'success': False, 'message': 'Missing email, token, or new password'}), 400
            
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
            
        # 1. Check token validity
        if user.password_reset_token != token:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 400
            
        # 2. Check token expiration
        if user.password_reset_expires < datetime.now(timezone.utc):
            return jsonify({'success': False, 'message': 'Token has expired'}), 400
            
        # 3. Validate new password strength
        is_valid, message = validate_password(new_password)
        if not is_valid:
            return jsonify({'success': False, 'message': message}), 400
            
        # 4. Reset password and clear token
        user.password_hash = generate_password_hash(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.failed_login_attempts = 0
        user.account_locked = False
        
        # 5. Log and commit
        log = AuditLog(
            user_id=user.id,
            action='password_reset_successful',
            resource_type='user',
            resource_id=user.id,
            ip_address=request.remote_addr,
            severity='critical'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Password has been successfully reset. You can now log in.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Password reset error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred during password reset'
        }), 500


# ============================================================================
# 2FA SETUP
# ============================================================================

@auth_bp.route('/api/auth/2fa/setup', methods=['POST'])
@jwt_required()
def setup_2fa():
    """
    Setup 2FA for user
    POST /api/auth/2fa/setup
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Generate 2FA secret
        secret = pyotp.random_base32()
        user.two_factor_secret = secret
        
        # Generate QR code data
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name='Saurellius'
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'secret': secret,
            'qr_code_url': provisioning_uri
        }), 200
        
    except Exception as e:
        print(f"2FA setup error: {str(e)}")
        return jsonify({
            'success': False,
            'message': '2FA setup failed'
        }), 500


@auth_bp.route('/api/auth/2fa/verify', methods=['POST'])
@jwt_required()
def verify_2fa():
    """
    Verify and enable 2FA
    POST /api/auth/2fa/verify
    Body: { "code": "123456" }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user or not user.two_factor_secret:
            return jsonify({
                'success': False,
                'message': 'Setup 2FA first'
            }), 400
        
        # Verify code
        totp = pyotp.TOTP(user.two_factor_secret)
        if not totp.verify(data.get('code', '')):
            return jsonify({
                'success': False,
                'message': 'Invalid code'
            }), 400
        
        # Enable 2FA
        user.two_factor_enabled = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '2FA enabled successfully'
        }), 200
        
    except Exception as e:
        print(f"2FA verify error: {str(e)}")
        return jsonify({
            'success': False,
            'message': '2FA verification failed'
        }), 500


# ============================================================================
# PROFILE
# ============================================================================

@auth_bp.route('/api/auth/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        return jsonify({
            'success': True,
            'user': user.to_dict(),
            'subscription': {
                'tier': user.subscription_tier,
                'status': user.subscription_status,
                'paystubs_used': user.paystubs_used_this_month,
                'paystubs_limit': user.monthly_paystub_limit
            },
            'rewards': {
                'points': user.reward_points,
                'tier': user.reward_tier,
                'lifetime_points': user.total_lifetime_points
            }
        }), 200
        
    except Exception as e:
        print(f"Get profile error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get profile'
        }), 500


@auth_bp.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({
                'success': False,
                'message': 'User not found'
            }), 404
        
        # Update allowed fields
        if 'name' in data:
            user.name = data['name']
        if 'phone' in data:
            user.phone = data['phone']
        if 'timezone' in data:
            user.timezone = data['timezone']
        if 'notification_email' in data:
            user.notification_email = data['notification_email']
        if 'notification_sms' in data:
            user.notification_sms = data['notification_sms']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile updated',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        print(f"Update profile error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to update profile'
        }), 500
