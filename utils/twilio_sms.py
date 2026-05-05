import os

try:
    from twilio.rest import Client
except ImportError:
    Client = None

def send_sms(to_phone_number: str, message: str) -> bool:
    """
    Send SMS using Twilio API.
    Returns True if message sent successfully, False otherwise.
    """
    try:
        if Client is None:
            raise ImportError("Twilio is not installed.")
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_phone = os.getenv('TWILIO_PHONE_NUMBER')
        if not all([account_sid, auth_token, from_phone]):
            raise ValueError("Twilio credentials are not set in environment variables.")
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=message,
            from_=from_phone,
            to=to_phone_number
        )
        return True
    except Exception as e:
        print(f"Failed to send SMS: {e}")
        return False
