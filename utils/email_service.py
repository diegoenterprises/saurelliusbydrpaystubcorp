"""
Email Service Utility
Implements email sending via AWS SES (Simple Email Service) as the initial relay.
The full Postal self-hosted solution is an infrastructure task, but the application
code should be ready to use an email service.
"""

import os
import boto3
from botocore.exceptions import ClientError

class EmailService:
    def __init__(self):
        # AWS credentials will be picked up from environment variables on Elastic Beanstalk
        # or from the .env file locally.
        self.client = boto3.client(
            'ses',
            region_name='us-east-1' # Assuming SES is configured in us-east-1
        )
        self.sender_email = os.getenv('SENDER_EMAIL', 'noreply@saurellius.com')

    def send_email(self, recipient: str, subject: str, body_html: str, body_text: str = None) -> bool:
        """
        Sends an email using AWS SES.
        
        :param recipient: The email address of the recipient.
        :param subject: The subject line of the email.
        :param body_html: The HTML body of the email.
        :param body_text: The plain text body of the email (optional).
        :return: True if the email was sent successfully, False otherwise.
        """
        
        # If plain text body is not provided, use a simple version of the HTML body
        if body_text is None:
            body_text = "Please view this email in an HTML-compatible email client."

        try:
            response = self.client.send_email(
                Destination={
                    'ToAddresses': [
                        recipient,
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': 'UTF-8',
                            'Data': body_html,
                        },
                        'Text': {
                            'Charset': 'UTF-8',
                            'Data': body_text,
                        },
                    },
                    'Subject': {
                        'Charset': 'UTF-8',
                        'Data': subject,
                    },
                },
                Source=self.sender_email,
            )
            print(f"Email sent! Message ID: {response['MessageId']}")
            return True
        except ClientError as e:
            print(f"Email sending failed: {e.response['Error']['Message']}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred during email sending: {e}")
            return False

# Example usage (for local testing, requires AWS credentials configured)
if __name__ == '__main__':
    # This part would typically be run in a test environment
    # For now, it serves as a structural placeholder.
    print("EmailService utility created. Ready for integration into routes.")
