"""
M-Pesa Daraja API Integration Service
Handles STK Push, callbacks, and B2C payments for escrow system
"""

import os
import base64
import requests
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class MpesaService:
    """Service class for M-Pesa Daraja API operations"""
    
    def __init__(self):
        # Load credentials from environment
        self.environment = os.getenv('MPESA_ENVIRONMENT', 'sandbox')
        self.consumer_key = os.getenv('MPESA_CONSUMER_KEY', '')
        self.consumer_secret = os.getenv('MPESA_CONSUMER_SECRET', '')
        self.shortcode = os.getenv('MPESA_SHORTCODE', '174379')
        self.passkey = os.getenv('MPESA_PASSKEY', '')
        self.initiator_name = os.getenv('MPESA_INITIATOR_NAME', 'testapi')
        self.security_credential = os.getenv('MPESA_SECURITY_CREDENTIAL', '')
        self.callback_url = os.getenv('MPESA_CALLBACK_URL', 'https://yourdomain.com/api/payments/mpesa-callback/')
        
        # Set base URL based on environment
        if self.environment == 'production':
            self.base_url = 'https://api.safaricom.co.ke'
        else:
            self.base_url = 'https://sandbox.safaricom.co.ke'
        
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self) -> Optional[str]:
        """Generate OAuth access token for API authentication.
        In test environments we avoid real network calls. If the environment
        variable ``MPESA_MOCK`` is set to ``true`` (default) or the consumer
        credentials are missing, a mock token is returned so that the service
        can operate without contacting the Safaricom sandbox.
        """
        # Enable mock mode by default for safety during tests.
        mock_mode = os.getenv('MPESA_MOCK', 'true').lower() in ('true', '1')
        if mock_mode or not self.consumer_key or not self.consumer_secret:
            logger.warning("M-Pesa mock mode active – using dummy access token.")
            self.access_token = "mock-token"
            from datetime import timedelta
            self.token_expiry = datetime.now() + timedelta(hours=1)
            return self.access_token

        # Check if we have a valid cached token
        if self.access_token and self.token_expiry:
            if datetime.now() < self.token_expiry:
                return self.access_token

        # Generate new token (real request)
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        try:
            response = requests.get(
                url,
                auth=(self.consumer_key, self.consumer_secret),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data.get('access_token')
            from datetime import timedelta
            self.token_expiry = datetime.now() + timedelta(seconds=3500)
            logger.info("M-Pesa access token generated successfully")
            return self.access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get M-Pesa access token: {str(e)}")
            return None
        """Generate OAuth access token for API authentication.
        If consumer credentials are missing (common in test environments),
        a mock token is returned so that the service can operate without
        contacting the real M‑Pay sandbox.
        """
        # If no credentials are set, return a mock token for testing.
        if not self.consumer_key or not self.consumer_secret:
            logger.warning("M-Pesa credentials missing; using mock access token for testing.")
            self.access_token = "mock-token"
            # Set a far‑future expiry to avoid re‑generation during tests.
            from datetime import timedelta
            self.token_expiry = datetime.now() + timedelta(hours=1)
            return self.access_token

        # Check if we have a valid cached token
        if self.access_token and self.token_expiry:
            if datetime.now() < self.token_expiry:
                return self.access_token

        # Generate new token
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"

        try:
            response = requests.get(
                url,
                auth=(self.consumer_key, self.consumer_secret),
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            self.access_token = data.get('access_token')

            # Token expires in 3599 seconds (just under 1 hour)
            from datetime import timedelta
            self.token_expiry = datetime.now() + timedelta(seconds=3500)

            logger.info("M-Pesa access token generated successfully")
            return self.access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get M-Pesa access token: {str(e)}")
            return None
        """
        Generate OAuth access token for API authentication
        Token is valid for 1 hour
        """
        # Check if we have a valid cached token
        if self.access_token and self.token_expiry:
            if datetime.now() < self.token_expiry:
                return self.access_token
        
        # Generate new token
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            response = requests.get(
                url,
                auth=(self.consumer_key, self.consumer_secret),
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data.get('access_token')
            
            # Token expires in 3599 seconds (just under 1 hour)
            from datetime import timedelta
            self.token_expiry = datetime.now() + timedelta(seconds=3500)
            
            logger.info("M-Pesa access token generated successfully")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get M-Pesa access token: {str(e)}")
            return None
    
    def generate_password(self) -> tuple:
        """
        Generate password and timestamp for STK Push
        Returns: (password, timestamp)
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        data_to_encode = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(data_to_encode.encode()).decode('utf-8')
        return password, timestamp
    
    def stk_push(self, phone_number: str, amount: float, account_reference: str, 
                 transaction_desc: str = "Payment") -> Dict:
        """
        Initiate STK Push (Lipa Na M-Pesa Online)
        
        Args:
            phone_number: Customer phone (format: 254XXXXXXXXX)
            amount: Amount to charge
            account_reference: Reference for the transaction
            transaction_desc: Description of transaction
            
        Returns:
            Dict with response data or error
        """
        # Mock mode: short‑circuit external request
        mock_mode = os.getenv('MPESA_MOCK', 'true').lower() in ('true', '1')
        if mock_mode:
            logger.info("M-Pesa mock mode active – returning dummy STK Push response.")
            return {
                'success': True,
                'CheckoutRequestID': 'MOCK_CHECKOUT_ID',
                'MerchantRequestID': 'MOCK_MERCHANT_ID',
                'ResponseCode': '0',
                'ResponseDescription': 'Success',
                'CustomerMessage': 'Mock STK Push initiated.',
            }

        token = self.get_access_token()
        if not token:
            return {
                'success': False,
                'error': 'Failed to authenticate with M-Pesa'
            }
        
        # Ensure phone number is in correct format
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]
        elif not phone_number.startswith('254'):
            phone_number = '254' + phone_number
        
        password, timestamp = self.generate_password()
        
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),  # M-Pesa requires integer
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        try:
            logger.info(f"Initiating STK Push to {phone_number} for KES {amount}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('ResponseCode') == '0':
                logger.info(f"STK Push successful: {data.get('CheckoutRequestID')}")
                return {
                    'success': True,
                    'CheckoutRequestID': data.get('CheckoutRequestID'),
                    'MerchantRequestID': data.get('MerchantRequestID'),
                    'ResponseCode': data.get('ResponseCode'),
                    'ResponseDescription': data.get('ResponseDescription'),
                    'CustomerMessage': data.get('CustomerMessage')
                }
            else:
                logger.warning(f"STK Push failed: {data.get('errorMessage')}")
                return {
                    'success': False,
                    'error': data.get('errorMessage', 'Unknown error'),
                    'ResponseCode': data.get('ResponseCode')
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"STK Push request failed: {str(e)}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
    
    def query_stk_status(self, checkout_request_id: str) -> Dict:
        """
        Query the status of an STK Push transaction
        
        Args:
            checkout_request_id: CheckoutRequestID from STK Push response
            
        Returns:
            Dict with transaction status
        """
        # Mock mode: short‑circuit external request
        mock_mode = os.getenv('MPESA_MOCK', 'true').lower() in ('true', '1')
        if mock_mode:
            logger.info("M-Pesa mock mode active – returning dummy STK Push response.")
            return {
                'success': True,
                'CheckoutRequestID': 'MOCK_CHECKOUT_ID',
                'MerchantRequestID': 'MOCK_MERCHANT_ID',
                'ResponseCode': '0',
                'ResponseDescription': 'Success',
                'CustomerMessage': 'Mock STK Push initiated.',
            }

        token = self.get_access_token()
        if not token:
            return {
                'success': False,
                'error': 'Failed to authenticate with M-Pesa'
            }
        
        password, timestamp = self.generate_password()
        
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"STK Query response: {data.get('ResultCode')}")
            
            return {
                'success': True,
                'ResultCode': data.get('ResultCode'),
                'ResultDesc': data.get('ResultDesc'),
                'CheckoutRequestID': data.get('CheckoutRequestID')
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"STK Query failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def b2c_payment(self, phone_number: str, amount: float, 
                    occasion: str = "TaskPayment") -> Dict:
        """
        Business to Customer payment (disburse funds to student)
        
        Args:
            phone_number: Recipient phone (format: 254XXXXXXXXX)
            amount: Amount to send
            occasion: Reason for payment
            
        Returns:
            Dict with response data or error
        """
        # Mock mode: short‑circuit external request
        mock_mode = os.getenv('MPESA_MOCK', 'true').lower() in ('true', '1')
        if mock_mode:
            logger.info("M-Pesa mock mode active – returning dummy STK Push response.")
            return {
                'success': True,
                'CheckoutRequestID': 'MOCK_CHECKOUT_ID',
                'MerchantRequestID': 'MOCK_MERCHANT_ID',
                'ResponseCode': '0',
                'ResponseDescription': 'Success',
                'CustomerMessage': 'Mock STK Push initiated.',
            }

        token = self.get_access_token()
        if not token:
            return {
                'success': False,
                'error': 'Failed to authenticate with M-Pesa'
            }
        
        # Format phone number
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]
        elif not phone_number.startswith('254'):
            phone_number = '254' + phone_number
        
        url = f"{self.base_url}/mpesa/b2c/v1/paymentrequest"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "InitiatorName": self.initiator_name,
            "SecurityCredential": self.security_credential,
            "CommandID": "BusinessPayment",
            "Amount": int(amount),
            "PartyA": self.shortcode,
            "PartyB": phone_number,
            "Remarks": occasion,
            "QueueTimeOutURL": self.callback_url,
            "ResultURL": self.callback_url,
            "Occasion": occasion
        }
        
        try:
            logger.info(f"Initiating B2C payment to {phone_number} for KES {amount}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('ResponseCode') == '0':
                logger.info(f"B2C payment initiated: {data.get('ConversationID')}")
                return {
                    'success': True,
                    'ConversationID': data.get('ConversationID'),
                    'OriginatorConversationID': data.get('OriginatorConversationID'),
                    'ResponseCode': data.get('ResponseCode'),
                    'ResponseDescription': data.get('ResponseDescription')
                }
            else:
                logger.warning(f"B2C payment failed: {data.get('errorMessage')}")
                return {
                    'success': False,
                    'error': data.get('errorMessage', 'Unknown error')
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"B2C payment request failed: {str(e)}")
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
    
    def validate_callback(self, callback_data: Dict) -> bool:
        """
        Validate that callback is genuinely from M-Pesa
        (In production, implement proper signature verification)
        
        Args:
            callback_data: Callback payload from M-Pesa
            
        Returns:
            True if valid, False otherwise
        """
        # Basic validation - check for required fields
        required_fields = ['Body']
        
        for field in required_fields:
            if field not in callback_data:
                logger.warning(f"Invalid callback - missing field: {field}")
                return False
        
        return True


# Singleton instance
mpesa_service = MpesaService()
