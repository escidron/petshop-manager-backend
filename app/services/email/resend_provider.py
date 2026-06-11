import resend
from app.config.settings import settings

class ResendProvider:
    def __init__(self):
        resend.api_key = settings.RESEND_KEY

    def send_email(self, to: str, subject: str, html: str, text: str = None):
        from_email = settings.DEFAULT_FROM_EMAIL
        if "<" not in from_email:
            from_email = f"{settings.APP_NAME} <{from_email}>"

        params = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text
            
        return resend.Emails.send(params)
