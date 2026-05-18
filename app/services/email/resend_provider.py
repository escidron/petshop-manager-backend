import resend
from app.config.settings import settings

class ResendProvider:
    def __init__(self):
        resend.api_key = settings.RESEND_KEY

    def send_email(self, to: str, subject: str, html: str, text: str = None):
        params = {
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text
            
        return resend.Emails.send(params)
