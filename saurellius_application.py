#!/usr/bin/env python3
"""
Saurellius Platform - Main Application
Production-ready Flask application with all routes
"""

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import timedelta
import os

# Import models and database
from models import db

# Import blueprints
from routes.auth import auth_bp
from routes.paystubs import paystubs_bp
from routes.employees import employees_bp
from routes.dashboard import dashboard_bp

# ============================================================================
# APPLICATION FACTORY
# ============================================================================

def create_app():
    """Create and configure Flask application"""
    
    app = Flask(__name__, static_folder='static')
    
    # ========================================================================
    # CONFIGURATION
    # ========================================================================
    
    # Database
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://localhost/saurellius'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True
    }
    
    # JWT
    app.config['JWT_SECRET_KEY'] = os.environ.get(
        'JWT_SECRET_KEY',
        'your-super-secret-jwt-key-change-in-production'
    )
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=12)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=90)
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    app.config['JWT_HEADER_NAME'] = 'Authorization'
    app.config['JWT_HEADER_TYPE'] = 'Bearer'
    
    # CORS
    app.config['CORS_HEADERS'] = 'Content-Type'
    
    # File Upload
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
    
    # S3 Configuration
    app.config['S3_BUCKET'] = os.environ.get('S3_BUCKET', 'saurellius-paystubs')
    app.config['AWS_REGION'] = os.environ.get('AWS_REGION', 'us-east-1')
    
    # Stripe Configuration
    app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')
    app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Application Settings
    app.config['APP_NAME'] = 'Saurellius'
    app.config['APP_VERSION'] = '1.0.0'
    app.config['ENVIRONMENT'] = os.environ.get('ENVIRONMENT', 'production')
    
    # ========================================================================
    # EXTENSIONS
    # ========================================================================
    
    # Initialize database
    db.init_app(app)
    
    # Initialize JWT
    jwt = JWTManager(app)
    
    # Initialize CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": ["https://saurellius.drpaystub.com", "http://localhost:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    })
    
    # ========================================================================
    # JWT HANDLERS
    # ========================================================================
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'success': False,
            'message': 'Token has expired',
            'error': 'token_expired'
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            'success': False,
            'message': 'Invalid token',
            'error': 'invalid_token'
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            'success': False,
            'message': 'Authorization token required',
            'error': 'authorization_required'
        }), 401
    
    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'success': False,
            'message': 'Token has been revoked',
            'error': 'token_revoked'
        }), 401
    
    # ========================================================================
    # REGISTER BLUEPRINTS
    # ========================================================================
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(paystubs_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(dashboard_bp)
    
    # ========================================================================
    # FRONTEND ROUTES
    # ========================================================================
    
    @app.route('/')
    def serve_landing():
        """Serve landing/auth page"""
        return send_from_directory('static', 'auth-pages.html')
    
    @app.route('/dashboard')
    def serve_dashboard():
        """Serve dashboard"""
        return send_from_directory('static', 'dashboard.html')
    
    # Serve static assets
    @app.route('/static/<path:filename>')
    def serve_static(filename):
        """Serve static files"""
        return send_from_directory('static', filename)
    
    # ========================================================================
    # API HEALTH CHECK
    # ========================================================================
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        try:
            # Test database connection
            db.session.execute(db.text('SELECT 1'))
            db_status = 'healthy'
        except Exception as e:
            db_status = 'unhealthy'
            print(f"Database health check failed: {str(e)}")
        
        return jsonify({
            'status': 'healthy' if db_status == 'healthy' else 'degraded',
            'service': 'Saurellius API',
            'version': app.config['APP_VERSION'],
            'database': db_status,
            'environment': app.config['ENVIRONMENT']
        }), 200 if db_status == 'healthy' else 503
    
    @app.route('/api/info', methods=['GET'])
    def api_info():
        """API information endpoint"""
        return jsonify({
            'service': 'Saurellius Payroll API',
            'version': app.config['APP_VERSION'],
            'endpoints': {
                'auth': {
                    'register': 'POST /api/auth/register',
                    'login': 'POST /api/auth/login',
                    'refresh': 'POST /api/auth/refresh',
                    'logout': 'POST /api/auth/logout',
                    'profile': 'GET /api/auth/profile'
                },
                'employees': {
                    'list': 'GET /api/employees',
                    'get': 'GET /api/employees/<id>',
                    'create': 'POST /api/employees',
                    'update': 'PUT /api/employees/<id>',
                    'delete': 'DELETE /api/employees/<id>'
                },
                'paystubs': {
                    'generate': 'POST /api/paystubs/generate-complete',
                    'history': 'GET /api/paystubs/history',
                    'get': 'GET /api/paystubs/<id>',
                    'download': 'GET /api/paystubs/<id>/download',
                    'verify': 'GET /api/paystubs/verify/<verification_id>'
                },
                'dashboard': {
                    'summary': 'GET /api/dashboard/summary',
                    'analytics': 'GET /api/dashboard/analytics/*',
                    'reports': 'GET /api/dashboard/reports/*'
                }
            }
        }), 200
    
    # ========================================================================
    # ERROR HANDLERS
    # ========================================================================
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'success': False,
            'message': 'Bad request',
            'error': str(error)
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'success': False,
            'message': 'Unauthorized',
            'error': str(error)
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'success': False,
            'message': 'Forbidden',
            'error': str(error)
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'message': 'Resource not found',
            'error': str(error)
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Internal server error',
            'error': str(error) if app.config['ENVIRONMENT'] == 'development' else 'An error occurred'
        }), 500
    
    # ========================================================================
    # DATABASE INITIALIZATION
    # ========================================================================
    
    @app.cli.command()
    def init_db():
        """Initialize database tables"""
        db.create_all()
        print("✅ Database tables created successfully!")
    
    @app.cli.command()
    def reset_db():
        """Reset database (CAUTION: Deletes all data)"""
        if input("⚠️  This will delete ALL data. Type 'yes' to confirm: ") == 'yes':
            db.drop_all()
            db.create_all()
            print("✅ Database reset successfully!")
        else:
            print("❌ Database reset cancelled")
    
    # ========================================================================
    # LOGGING
    # ========================================================================
    
    if app.config['ENVIRONMENT'] == 'production':
        import logging
        from logging.handlers import RotatingFileHandler
        
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            'logs/saurellius.log',
            maxBytes=10240000,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('Saurellius startup')
    
    return app


# ============================================================================
# APPLICATION INSTANCE
# ============================================================================

application = create_app()
app = application  # For Elastic Beanstalk

# ============================================================================
# DEVELOPMENT SERVER
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('ENVIRONMENT', 'production') == 'development'
    
    print("=" * 60)
    print(f"🚀 Saurellius Platform Starting...")
    print(f"📝 Environment: {os.environ.get('ENVIRONMENT', 'production')}")
    print(f"🔌 Port: {port}")
    print(f"🛠 Debug: {debug}")
    print(f"💾 Database: {os.environ.get('DATABASE_URL', 'postgresql://localhost/saurellius')}")
    print("=" * 60)
    
    application.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )