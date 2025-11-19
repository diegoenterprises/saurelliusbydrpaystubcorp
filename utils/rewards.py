"""
Rewards and Gamification System
Handles point awards, tier progression, and achievements
"""

from models import User, RewardActivity # Assuming models are in models.py
from application import db # Assuming db object is initialized in application.py
from datetime import datetime, date, timedelta
from decimal import Decimal

# Reward Points Configuration
POINTS_CONFIG = {
    'paystub_generated': 50,
    'first_paystub': 100,
    'login_streak_3': 15,
    'login_streak_7': 25,
    'login_streak_30': 50,
    'profile_completed': 25,
    'referral': 100,
    'milestone_10_paystubs': 100,
    'milestone_25_paystubs': 250,
    'milestone_50_paystubs': 500,
    'milestone_100_paystubs': 1000
}

# Tier Thresholds
TIER_THRESHOLDS = {
    'bronze': 0,
    'silver': 500,
    'gold': 1000,
    'platinum': 1500
}


def calculate_tier(points):
    """Calculate reward tier based on points"""
    if points >= TIER_THRESHOLDS['platinum']:
        return 'platinum'
    elif points >= TIER_THRESHOLDS['gold']:
        return 'gold'
    elif points >= TIER_THRESHOLDS['silver']:
        return 'silver'
    else:
        return 'bronze'

def award_points(user_id, activity_type, description=None, custom_points=None):
    """Award points to a user for an activity"""
    # NOTE: This function assumes the Flask app context and database session are available.
    # The imports are adjusted for the current repository structure.
    
    # Placeholder for database interaction logic
    # In a real application, you would need to ensure the models and db object are correctly imported and configured.
    
    # Example logic (needs correct ORM setup in models.py and application.py)
    # user = User.query.get(user_id)
    # if not user:
    #     return False
    
    # points = custom_points if custom_points else POINTS_CONFIG.get(activity_type, 0)
    
    # # Update user points and check for tier upgrade
    # user.reward_points += points
    # user.total_lifetime_points += points
    # new_tier = calculate_tier(user.reward_points)
    # if new_tier != user.reward_tier:
    #     user.reward_tier = new_tier
    
    # # db.session.add(reward_activity)
    # # db.session.commit()
    
    return True


def check_and_award_milestones(user_id, paystub_count):
    """Check if user has reached any milestones and award points"""
    # Placeholder for milestone logic
    return True
