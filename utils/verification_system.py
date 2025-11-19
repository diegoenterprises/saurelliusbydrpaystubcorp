"""
Verification System - QR Codes, Document Hashing, Verification IDs
Implements security features for paystub verification
"""
import hashlib
import uuid
import qrcode
from io import BytesIO
import base64
from datetime import datetime
import json

class VerificationSystem:
    """
    Handle paystub verification, QR codes, and document integrity
    """
    
    BASE_VERIFICATION_URL = "https://verify.saurellius.com/paystub/"
    
    @staticmethod
    def generate_verification_id():
        """
        Generate unique verification ID for paystub
        Format: SAUR-YYYY-XXXXXXXX
        """
        year = datetime.now().year
        unique_id = str(uuid.uuid4()).replace('-', '').upper()[:8]
        return f"SAUR-{year}-{unique_id}"
    
    @staticmethod
    def calculate_document_hash(pdf_content):
        """
        Calculate SHA-256 hash of PDF document
        Used for tamper detection
        """
        if isinstance(pdf_content, str):
            pdf_content = pdf_content.encode('utf-8')
        
        sha256_hash = hashlib.sha256(pdf_content).hexdigest()
        return sha256_hash
    
    @staticmethod
    def generate_qr_code(verification_id, paystub_data):
        """
        Generate QR code for paystub verification
        QR code contains verification URL and basic paystub info
        """
        # Create verification URL
        verification_url = f"{VerificationSystem.BASE_VERIFICATION_URL}{verification_id}"
        
        # Create QR code data (JSON-like string)
        qr_data = {
            'url': verification_url,
            'id': verification_id,
            'employee_name': paystub_data.get('employee_name', ''),
            'pay_date': paystub_data.get('pay_date', ''),
            'gross_pay': paystub_data.get('gross_pay', ''),
            'net_pay': paystub_data.get('net_pay', ''),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Convert to string
        qr_string = json.dumps(qr_data)
        
        # Generate QR code image
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_string)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 for embedding
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return {
            'qr_code_data': qr_string,
            'qr_code_image_base64': img_base64,
            'verification_url': verification_url
        }
    
    @staticmethod
    def create_verification_package(paystub, pdf_content):
        """
        Create complete verification package for a paystub
        Returns all verification data needed
        """
        # Generate verification ID
        verification_id = VerificationSystem.generate_verification_id()
        
        # Calculate document hash
        document_hash = VerificationSystem.calculate_document_hash(pdf_content)
        
        # Prepare data for QR code
        paystub_data = {
            'employee_name': paystub.employee.full_name,
            'pay_date': paystub.pay_date.isoformat(),
            'gross_pay': str(paystub.gross_pay),
            'net_pay': str(paystub.net_pay),
        }
        
        qr_package = VerificationSystem.generate_qr_code(verification_id, paystub_data)
        
        return {
            'verification_id': verification_id,
            'document_hash': document_hash,
            'qr_code_data': qr_package['qr_code_data'],
            'qr_code_image_base64': qr_package['qr_code_image_base64'],
            'verification_url': qr_package['verification_url']
        }
