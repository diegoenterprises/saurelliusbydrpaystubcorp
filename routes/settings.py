#!/usr/bin/env python3
"""
Saurellius Platform - Settings Routes
Company settings, account preferences, notifications, subscription management
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, AuditLog
from datetime import datetime, timezone
import os

settings_bp = Blueprint('settings', __name__)

# ============================================================================
# COMPANY SETTINGS
# ============================================================================

@settings_bp.route('/api/settings/company', methods=['GET'])
@jwt_required()
def get_company_settings():
    """
    Get company information
    
    GET /api/settings/company
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'company': {
                'name': user.company_name,
                'ein': user.company_ein,
                'address': user.company_address,
                'phone': user.company_phone,
                'logo_url': user.company_logo_url
            }
        }), 200
        
    except Exception as e:
        print(f"Get company settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get company settings'
        }), 500


@settings_bp.route('/api/settings/company', methods=['PUT'])
@jwt_required()
def update_company_settings():
    """
    Update company information
    
    PUT /api/settings/company
    Body: {
        "name": "Company Name",
        "ein": "XX-XXXXXXX",
        "address": "123 Main St",
        "phone": "+1-555-123-4567",
        "logo_url": "https://..."
    }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Track changes
        changes = {}
        
        if 'name' in data:
            old_name = user.company_name
            user.company_name = data['name']
            changes['company_name'] = f"{old_name} -> {data['name']}"
        
        if 'ein' in data:
            user.company_ein = data['ein']
            changes['company_ein'] = 'updated'
        
        if 'address' in data:
            user.company_address = data['address']
            changes['company_address'] = 'updated'
        
        if 'phone' in data:
            user.company_phone = data['phone']
            changes['company_phone'] = data['phone']
        
        if 'logo_url' in data:
            user.company_logo_url = data['logo_url']
            changes['company_logo'] = 'updated'
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='company_settings_updated',
            resource_type='settings',
            changes=changes,
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Company settings updated successfully',
            'company': {
                'name': user.company_name,
                'ein': user.company_ein,
                'address': user.company_address,
                'phone': user.company_phone,
                'logo_url': user.company_logo_url
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Update company settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to update company settings'
        }), 500


# ============================================================================
# ACCOUNT SETTINGS
# ============================================================================

@settings_bp.route('/api/settings/account', methods=['GET'])
@jwt_required()
def get_account_settings():
    """
    Get account settings
    
    GET /api/settings/account
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'account': {
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'timezone': user.timezone,
                'locale': user.locale,
                'email_verified': user.email_verified,
                'phone_verified': user.phone_verified,
                'two_factor_enabled': user.two_factor_enabled
            }
        }), 200
        
    except Exception as e:
        print(f"Get account settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get account settings'
        }), 500


@settings_bp.route('/api/settings/account', methods=['PUT'])
@jwt_required()
def update_account_settings():
    """
    Update account settings
    
    PUT /api/settings/account
    Body: {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-123-4567",
        "timezone": "America/Los_Angeles",
        "locale": "en_US"
    }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Track changes
        changes = {}
        
        if 'name' in data:
            old_name = user.name
            user.name = data['name']
            changes['name'] = f"{old_name} -> {data['name']}"
        
        if 'email' in data and data['email'] != user.email:
            # Check if email already exists
            existing = User.query.filter_by(email=data['email']).first()
            if existing and existing.id != user_id:
                return jsonify({
                    'success': False,
                    'message': 'Email already in use'
                }), 400
            
            user.email = data['email']
            user.email_verified = False  # Require re-verification
            changes['email'] = 'updated (verification required)'
        
        if 'phone' in data:
            user.phone = data['phone']
            user.phone_verified = False  # Require re-verification
            changes['phone'] = data['phone']
        
        if 'timezone' in data:
            user.timezone = data['timezone']
            changes['timezone'] = data['timezone']
        
        if 'locale' in data:
            user.locale = data['locale']
            changes['locale'] = data['locale']
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='account_settings_updated',
            resource_type='settings',
            changes=changes,
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Account settings updated successfully',
            'account': {
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'timezone': user.timezone,
                'locale': user.locale,
                'email_verified': user.email_verified,
                'phone_verified': user.phone_verified
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Update account settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to update account settings'
        }), 500


# ============================================================================
# NOTIFICATION SETTINGS
# ============================================================================

@settings_bp.route('/api/settings/notifications', methods=['GET'])
@jwt_required()
def get_notification_settings():
    """
    Get notification preferences
    
    GET /api/settings/notifications
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'notifications': {
                'email': user.notification_email,
                'sms': user.notification_sms,
                'push': user.notification_push,
                'marketing': user.notification_marketing
            }
        }), 200
        
    except Exception as e:
        print(f"Get notification settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get notification settings'
        }), 500


@settings_bp.route('/api/settings/notifications', methods=['PUT'])
@jwt_required()
def update_notification_settings():
    """
    Update notification preferences
    
    PUT /api/settings/notifications
    Body: {
        "email": true,
        "sms": false,
        "push": true,
        "marketing": false
    }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Update preferences
        if 'email' in data:
            user.notification_email = data['email']
        
        if 'sms' in data:
            user.notification_sms = data['sms']
        
        if 'push' in data:
            user.notification_push = data['push']
        
        if 'marketing' in data:
            user.notification_marketing = data['marketing']
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='notification_settings_updated',
            resource_type='settings',
            changes=data,
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification settings updated successfully',
            'notifications': {
                'email': user.notification_email,
                'sms': user.notification_sms,
                'push': user.notification_push,
                'marketing': user.notification_marketing
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Update notification settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to update notification settings'
        }), 500


# ============================================================================
# SUBSCRIPTION SETTINGS
# ============================================================================

@settings_bp.route('/api/settings/subscription', methods=['GET'])
@jwt_required()
def get_subscription_settings():
    """
    Get subscription details
    
    GET /api/settings/subscription
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'subscription': {
                'tier': user.subscription_tier,
                'status': user.subscription_status,
                'starts_at': user.subscription_starts_at.isoformat() if user.subscription_starts_at else None,
                'ends_at': user.subscription_ends_at.isoformat() if user.subscription_ends_at else None,
                'renews_at': user.subscription_renews_at.isoformat() if user.subscription_renews_at else None,
                'paystubs_limit': user.monthly_paystub_limit,
                'paystubs_used': user.paystubs_used_this_month,
                'stripe_customer_id': user.stripe_customer_id,
                'stripe_subscription_id': user.stripe_subscription_id
            }
        }), 200
        
    except Exception as e:
        print(f"Get subscription settings error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get subscription settings'
        }), 500


# ============================================================================
# PREFERENCES
# ============================================================================

@settings_bp.route('/api/settings/preferences', methods=['GET'])
@jwt_required()
def get_preferences():
    """
    Get user preferences
    
    GET /api/settings/preferences
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'preferences': {
                'default_template': user.default_template,
                'auto_calculate_taxes': user.auto_calculate_taxes,
                'require_2fa_for_paystubs': user.require_2fa_for_paystubs,
                'theme_preference': user.theme_preference
            }
        }), 200
        
    except Exception as e:
        print(f"Get preferences error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get preferences'
        }), 500


@settings_bp.route('/api/settings/preferences', methods=['PUT'])
@jwt_required()
def update_preferences():
    """
    Update user preferences
    
    PUT /api/settings/preferences
    Body: {
        "default_template": "eusotrip_original",
        "auto_calculate_taxes": true,
        "require_2fa_for_paystubs": false,
        "theme_preference": "system"
    }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Update preferences
        if 'default_template' in data:
            user.default_template = data['default_template']
        
        if 'auto_calculate_taxes' in data:
            user.auto_calculate_taxes = data['auto_calculate_taxes']
        
        if 'require_2fa_for_paystubs' in data:
            user.require_2fa_for_paystubs = data['require_2fa_for_paystubs']
        
        if 'theme_preference' in data:
            user.theme_preference = data['theme_preference']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Preferences updated successfully',
            'preferences': {
                'default_template': user.default_template,
                'auto_calculate_taxes': user.auto_calculate_taxes,
                'require_2fa_for_paystubs': user.require_2fa_for_paystubs,
                'theme_preference': user.theme_preference
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Update preferences error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to update preferences'
        }), 500


# ============================================================================
# SECURITY SETTINGS
# ============================================================================

@settings_bp.route('/api/settings/security/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """
    Change user password
    
    POST /api/settings/security/change-password
    Body: {
        "current_password": "oldpass",
        "new_password": "newpass",
        "confirm_password": "newpass"
    }
    """
    try:
        from werkzeug.security import check_password_hash, generate_password_hash
        
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Verify current password
        if not check_password_hash(user.password_hash, data['current_password']):
            return jsonify({
                'success': False,
                'message': 'Current password is incorrect'
            }), 400
        
        # Validate new password
        if data['new_password'] != data['confirm_password']:
            return jsonify({
                'success': False,
                'message': 'New passwords do not match'
            }), 400
        
        if len(data['new_password']) < 8:
            return jsonify({
                'success': False,
                'message': 'Password must be at least 8 characters'
            }), 400
        
        # Update password
        user.password_hash = generate_password_hash(data['new_password'])
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='password_changed',
            resource_type='security',
            ip_address=request.remote_addr,
            severity='warning'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Change password error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to change password'
        }), 500


# ============================================================================
# API KEY MANAGEMENT
# ============================================================================

@settings_bp.route('/api/settings/api-key', methods=['GET'])
@jwt_required()
def get_api_key():
    """
    Get API key (masked)
    
    GET /api/settings/api-key
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Mask API key
        if user.api_key_hash:
            masked_key = f"sk_live_...{user.api_key_hash[-8:]}"
        else:
            masked_key = None
        
        return jsonify({
            'success': True,
            'api_key': masked_key,
            'requests_this_month': user.api_requests_this_month,
            'rate_limit': user.api_rate_limit
        }), 200
        
    except Exception as e:
        print(f"Get API key error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get API key'
        }), 500


@settings_bp.route('/api/settings/api-key/regenerate', methods=['POST'])
@jwt_required()
def regenerate_api_key():
    """
    Regenerate API key
    
    POST /api/settings/api-key/regenerate
    """
    try:
        import secrets
        import hashlib
        
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Generate new API key
        new_key = f"sk_live_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(new_key.encode()).hexdigest()
        
        user.api_key_hash = key_hash
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='api_key_regenerated',
            resource_type='security',
            ip_address=request.remote_addr,
            severity='warning'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'API key regenerated successfully',
            'api_key': new_key,
            'warning': 'Save this key securely. It will not be shown again.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Regenerate API key error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to regenerate API key'
        }), 500
