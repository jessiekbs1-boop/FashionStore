import requests
import hmac
import hashlib

class CinetPayAPI:
    """CinetPay API client for real payments."""
    
    BASE_URL = "https://api-checkout.cinetpay.com"
    
    def __init__(self, api_key, site_id):
        self.api_key = api_key
        self.site_id = site_id
    
    def generate_payment_link(self, transaction_id, amount, description, return_url, notify_url, customer_email=None, currency="XOF"):
        """
        Generate a payment link for CinetPay.
        Returns the payment URL to redirect the user to.
        """
        payload = {
            'apikey': self.api_key,
            'site_id': int(self.site_id),
            'transaction_id': str(transaction_id),
            'amount': float(amount),
            'description': description,
            'return_url': return_url,
            'notify_url': notify_url,
            'currency': currency,
        }
        if customer_email:
            payload['customer_email'] = customer_email
        
        try:
            resp = requests.post(
                f"{self.BASE_URL}/v2/payment",
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            if str(data.get('code')) in ('0', '201'):
                return data.get('data', {}).get('payment_url') or data.get('data', {}).get('payment_url_redirect')
        except Exception as e:
            print(f"CinetPay error: {e}")
        
        return None
    
    def verify_payment(self, transaction_id):
        """
        Verify payment status from CinetPay.
        Returns True if payment is confirmed, False otherwise.
        """
        payload = {
            'apikey': self.api_key,
            'site_id': int(self.site_id),
            'transaction_id': str(transaction_id),
        }
        
        try:
            resp = requests.post(
                f"{self.BASE_URL}/v2/payment/check",
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            status = (
                data.get('data', {}).get('status')
                or data.get('data', {}).get('payment_status')
                or ''
            ).lower()
            return status in ('accepted', 'confirmed')
        except Exception as e:
            print(f"CinetPay verify error: {e}")
        
        return False
    
    def validate_webhook(self, signature, payload_str, secret=None):
        """
        Validate CinetPay webhook signature.
        CinetPay uses HMAC-SHA256 for signature validation.
        """
        if secret is None:
            secret = self.api_key
        
        expected_sig = hmac.new(
            secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_sig)
