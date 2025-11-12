#!/usr/bin/env python3
"""
Saurellius Platform - Stripe Integration Routes
Payment processing, subscriptions, webhooks
"""

from flask import Blueprint, request, jsonify, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, AuditLog
from datetime import datetime, timezone, timedelta
import stripe
import os

stripe_bp = Blueprint('stripe', __name__)

# Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

# Subscription tiers and prices
SUBSCRIPTION_PLANS = {
    'starter': {
        'price_id': os.environ.get('STRIPE_STARTER_PRICE_ID'),
        'amount': 5000,  # $50.00
        'paystub_limit': 10,
        'name': 'Starter Plan'
    },
    'professional': {
        'price_id': os.environ.get('STRIPE_PROFESSIONAL_PRICE_ID'),
        'amount': 10000,  # $100.00
        'paystub_limit': 30,
        'name': 'Professional Plan'
    },
    'business': {
        'price_id': os.environ.get('STRIPE_BUSINESS_PRICE_ID'),
        'amount': 15000,  # $150.00
        'paystub_limit': -1,  # Unlimited
        'name': 'Business Plan'
    }
}

# ============================================================================
# CREATE CHECKOUT SESSION
# ============================================================================

@stripe_bp.route('/api/stripe/create-checkout-session', methods=['POST'])
@jwt_required()
def create_checkout_session():
    """
    Create Stripe Checkout session for subscription
    
    POST /api/stripe/create-checkout-session
    Body: {
        "plan": "professional",
        "success_url": "https://...",
        "cancel_url": "https://..."
    }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        plan = data.get('plan', 'professional')
        
        if plan not in SUBSCRIPTION_PLANS:
            return jsonify({
                'success': False,
                'message': 'Invalid plan selected'
            }), 400
        
        plan_info = SUBSCRIPTION_PLANS[plan]
        
        # Create or get Stripe customer
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.name,
                metadata={
                    'user_id': user.id
                }
            )
            user.stripe_customer_id = customer.id
            db.session.commit()
        else:
            customer_id = user.stripe_customer_id
        
        # Create checkout session
        success_url = data.get('success_url', f"{os.environ.get('FRONTEND_URL')}/dashboard?success=true&session_id={{CHECKOUT_SESSION_ID}}")
        cancel_url = data.get('cancel_url', f"{os.environ.get('FRONTEND_URL')}/pricing?canceled=true")
        
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': plan_info['price_id'],
                'quantity': 1
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user.id,
                'plan': plan
            },
            subscription_data={
                'trial_period_days': 14,  # 14-day free trial
                'metadata': {
                    'user_id': user.id,
                    'plan': plan
                }
            }
        )
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='checkout_session_created',
            resource_type='stripe',
            changes={'plan': plan, 'session_id': checkout_session.id},
            ip_address=request.remote_addr,
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'checkout_url': checkout_session.url,
            'session_id': checkout_session.id
        }), 200
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Payment processing error',
            'error': str(e)
        }), 400
    except Exception as e:
        print(f"Checkout session error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to create checkout session'
        }), 500


# ============================================================================
# CREATE CUSTOMER PORTAL SESSION
# ============================================================================

@stripe_bp.route('/api/stripe/create-portal-session', methods=['POST'])
@jwt_required()
def create_portal_session():
    """
    Create Stripe Customer Portal session
    
    POST /api/stripe/create-portal-session
    Body: {
        "return_url": "https://..."
    }
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        data = request.get_json()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if not user.stripe_customer_id:
            return jsonify({
                'success': False,
                'message': 'No active subscription found'
            }), 400
        
        return_url = data.get('return_url', f"{os.environ.get('FRONTEND_URL')}/settings")
        
        # Create portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url
        )
        
        return jsonify({
            'success': True,
            'portal_url': portal_session.url
        }), 200
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Portal creation error',
            'error': str(e)
        }), 400
    except Exception as e:
        print(f"Portal session error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to create portal session'
        }), 500


# ============================================================================
# WEBHOOK HANDLER
# ============================================================================

@stripe_bp.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """
    Handle Stripe webhook events
    
    POST /api/stripe/webhook
    """
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        print(f"Invalid payload: {e}")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Invalid signature: {e}")
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    
    print(f"Received Stripe event: {event_type}")
    
    # Subscription created
    if event_type == 'customer.subscription.created':
        handle_subscription_created(event_data)
    
    # Subscription updated
    elif event_type == 'customer.subscription.updated':
        handle_subscription_updated(event_data)
    
    # Subscription deleted
    elif event_type == 'customer.subscription.deleted':
        handle_subscription_deleted(event_data)
    
    # Payment succeeded
    elif event_type == 'invoice.payment_succeeded':
        handle_payment_succeeded(event_data)
    
    # Payment failed
    elif event_type == 'invoice.payment_failed':
        handle_payment_failed(event_data)
    
    # Checkout session completed
    elif event_type == 'checkout.session.completed':
        handle_checkout_completed(event_data)
    
    return jsonify({'success': True}), 200


# ============================================================================
# WEBHOOK EVENT HANDLERS
# ============================================================================

def handle_subscription_created(subscription):
    """Handle new subscription creation"""
    try:
        customer_id = subscription['customer']
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        
        if not user:
            print(f"User not found for customer: {customer_id}")
            return
        
        # Get plan from metadata
        plan = subscription['metadata'].get('plan', 'professional')
        plan_info = SUBSCRIPTION_PLANS.get(plan, SUBSCRIPTION_PLANS['professional'])
        
        # Update user subscription
        user.subscription_tier = plan
        user.subscription_status = subscription['status']
        user.stripe_subscription_id = subscription['id']
        user.subscription_starts_at = datetime.fromtimestamp(subscription['current_period_start'], tz=timezone.utc)
        user.subscription_ends_at = datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc)
        user.subscription_renews_at = datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc)
        user.monthly_paystub_limit = plan_info['paystub_limit']
        
        # Award bonus points for subscription
        user.reward_points += 100
        user.total_lifetime_points += 100
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user.id,
            action='subscription_created',
            resource_type='stripe',
            changes={
                'plan': plan,
                'subscription_id': subscription['id']
            },
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        print(f"Subscription created for user {user.id}: {plan}")
        
    except Exception as e:
        print(f"Error handling subscription created: {str(e)}")
        db.session.rollback()


def handle_subscription_updated(subscription):
    """Handle subscription updates"""
    try:
        subscription_id = subscription['id']
        user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
        
        if not user:
            print(f"User not found for subscription: {subscription_id}")
            return
        
        # Update subscription status
        user.subscription_status = subscription['status']
        user.subscription_ends_at = datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc)
        user.subscription_renews_at = datetime.fromtimestamp(subscription['current_period_end'], tz=timezone.utc)
        
        db.session.commit()
        
        print(f"Subscription updated for user {user.id}")
        
    except Exception as e:
        print(f"Error handling subscription updated: {str(e)}")
        db.session.rollback()


def handle_subscription_deleted(subscription):
    """Handle subscription cancellation"""
    try:
        subscription_id = subscription['id']
        user = User.query.filter_by(stripe_subscription_id=subscription_id).first()
        
        if not user:
            print(f"User not found for subscription: {subscription_id}")
            return
        
        # Update subscription status
        user.subscription_status = 'canceled'
        user.subscription_ends_at = datetime.now(timezone.utc)
        
        # Revert to free tier
        user.subscription_tier = 'starter'
        user.monthly_paystub_limit = 10
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user.id,
            action='subscription_canceled',
            resource_type='stripe',
            changes={'subscription_id': subscription_id},
            severity='warning'
        )
        db.session.add(log)
        db.session.commit()
        
        print(f"Subscription canceled for user {user.id}")
        
    except Exception as e:
        print(f"Error handling subscription deleted: {str(e)}")
        db.session.rollback()


def handle_payment_succeeded(invoice):
    """Handle successful payment"""
    try:
        customer_id = invoice['customer']
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        
        if not user:
            print(f"User not found for customer: {customer_id}")
            return
        
        # Update payment status
        user.subscription_status = 'active'
        
        # Reset monthly usage
        if invoice['billing_reason'] == 'subscription_cycle':
            user.paystubs_used_this_month = 0
            user.billing_cycle_starts_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user.id,
            action='payment_succeeded',
            resource_type='stripe',
            changes={
                'amount': invoice['amount_paid'],
                'invoice_id': invoice['id']
            },
            severity='info'
        )
        db.session.add(log)
        db.session.commit()
        
        print(f"Payment succeeded for user {user.id}: ${invoice['amount_paid']/100}")
        
    except Exception as e:
        print(f"Error handling payment succeeded: {str(e)}")
        db.session.rollback()


def handle_payment_failed(invoice):
    """Handle failed payment"""
    try:
        customer_id = invoice['customer']
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        
        if not user:
            print(f"User not found for customer: {customer_id}")
            return
        
        # Update subscription status
        user.subscription_status = 'past_due'
        
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user.id,
            action='payment_failed',
            resource_type='stripe',
            changes={
                'amount': invoice['amount_due'],
                'invoice_id': invoice['id']
            },
            severity='error'
        )
        db.session.add(log)
        db.session.commit()
        
        print(f"Payment failed for user {user.id}")
        
    except Exception as e:
        print(f"Error handling payment failed: {str(e)}")
        db.session.rollback()


def handle_checkout_completed(session):
    """Handle completed checkout session"""
    try:
        customer_id = session['customer']
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        
        if not user:
            print(f"User not found for customer: {customer_id}")
            return
        
        # Get subscription if present
        if session.get('subscription'):
            subscription = stripe.Subscription.retrieve(session['subscription'])
            handle_subscription_created(subscription)
        
        print(f"Checkout completed for user {user.id}")
        
    except Exception as e:
        print(f"Error handling checkout completed: {str(e)}")


# ============================================================================
# GET SUBSCRIPTION STATUS
# ============================================================================

@stripe_bp.route('/api/stripe/subscription', methods=['GET'])
@jwt_required()
def get_subscription_status():
    """
    Get current subscription status
    
    GET /api/stripe/subscription
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        subscription_data = {
            'tier': user.subscription_tier,
            'status': user.subscription_status,
            'paystubs_limit': user.monthly_paystub_limit,
            'paystubs_used': user.paystubs_used_this_month,
            'starts_at': user.subscription_starts_at.isoformat() if user.subscription_starts_at else None,
            'ends_at': user.subscription_ends_at.isoformat() if user.subscription_ends_at else None,
            'renews_at': user.subscription_renews_at.isoformat() if user.subscription_renews_at else None
        }
        
        # Get Stripe subscription details if available
        if user.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user.stripe_subscription_id)
                subscription_data['stripe_status'] = subscription['status']
                subscription_data['cancel_at_period_end'] = subscription['cancel_at_period_end']
            except stripe.error.StripeError:
                pass
        
        return jsonify({
            'success': True,
            'subscription': subscription_data
        }), 200
        
    except Exception as e:
        print(f"Get subscription error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to get subscription status'
        }), 500


# ============================================================================
# CANCEL SUBSCRIPTION
# ============================================================================

@stripe_bp.route('/api/stripe/subscription/cancel', methods=['POST'])
@jwt_required()
def cancel_subscription():
    """
    Cancel subscription at period end
    
    POST /api/stripe/subscription/cancel
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if not user.stripe_subscription_id:
            return jsonify({
                'success': False,
                'message': 'No active subscription found'
            }), 400
        
        # Cancel subscription at period end
        subscription = stripe.Subscription.modify(
            user.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        # Update user status
        user.subscription_status = 'canceling'
        db.session.commit()
        
        # Audit log
        log = AuditLog(
            user_id=user_id,
            action='subscription_cancel_requested',
            resource_type='stripe',
            changes={'subscription_id': user.stripe_subscription_id},
            ip_address=request.remote_addr,
            severity='warning'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Subscription will be canceled at period end',
            'ends_at': datetime.fromtimestamp(subscription['current_period_end']).isoformat()
        }), 200
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Cancellation error',
            'error': str(e)
        }), 400
    except Exception as e:
        print(f"Cancel subscription error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to cancel subscription'
        }), 500
