import requests
import hmac
import hashlib
import time

class CinetPayAPI:
    """CinetPay API client for real payments."""
    
    BASE_URL = "https://api-checkout.cinetpay.com"
    
    def __init__(self, api_key, site_id):
        self.api_key = api_key
        self.site_id = site_id
        # last call diagnostics
        self.last_error = None
        self.last_response = None
    
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
        
        # Try with exponential backoff retries to be resilient to transient network issues
        attempts = 3
        backoffs = (0.5, 1.0, 2.0)
        self.last_error = None
        self.last_response = None
        for attempt in range(attempts):
            try:
                resp = requests.post(
                    f"{self.BASE_URL}/v2/payment",
                    json=payload,
                    timeout=10
                )
                resp.raise_for_status()
                data = resp.json()
                # store the raw response for diagnostics
                self.last_response = data
                code = str(data.get('code') or '')
                # success codes 0 or 201 sometimes used by API
                if code in ('0', '201'):
                    # prefer common keys that CinetPay may return
                    d = data.get('data') or {}
                    return d.get('payment_url') or d.get('payment_url_redirect') or d.get('checkout_url')
                # unexpected but capture message
                self.last_error = f"unexpected_code:{code}"
                # no need to retry on logical API error; break
                break
            except Exception as e:
                # record error and retry after backoff (unless last attempt)
                self.last_error = str(e)
                if attempt < attempts - 1:
                    time.sleep(backoffs[attempt] if attempt < len(backoffs) else 1.0)
                    continue
                # final failure
                try:
                    print(f"CinetPay error after {attempt+1} attempts: {e}")
                except Exception:
                    pass
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
