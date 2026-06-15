import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.services.email.resend_provider import ResendProvider
from app.config.settings import settings

class EmailService:
    def __init__(self):
        self.provider = ResendProvider()
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"])
        )

    def _render_template(self, template_name: str, **kwargs):
        template = self.jinja_env.get_template(template_name)
        # Pass app_name by default to all templates
        return template.render(app_name=settings.APP_NAME, **kwargs)

    def send_welcome_email(self, to_email: str, user_name: str):
        subject = f"Bem-vindo ao {settings.APP_NAME}! 🐾"
        html_content = self._render_template("welcome.html", user_name=user_name)
        text_content = f"Olá {user_name}, bem-vindo ao {settings.APP_NAME}!"
        
        return self.provider.send_email(
            to=to_email,
            subject=subject,
            html=html_content,
            text=text_content
        )

    def send_password_reset_email(self, to_email: str, user_name: str, otp_code: str):
        subject = f"Código de Recuperação - {settings.APP_NAME}"
        html_content = self._render_template(
            "password_reset.html", 
            user_name=user_name, 
            otp_code=otp_code
        )
        text_content = f"Olá {user_name}, seu código de recuperação é: {otp_code}. Ele expira em 15 minutos."
        
        return self.provider.send_email(
            to=to_email,
            subject=subject,
            html=html_content,
            text=text_content
        )

    def send_email_verification(self, to_email: str, user_name: str, otp_code: str):
        subject = f"Confirme seu e-mail - {settings.APP_NAME}"
        html_content = self._render_template(
            "email_verification.html",
            user_name=user_name,
            otp_code=otp_code
        )
        text_content = f"Olá {user_name}, seu código de verificação é: {otp_code}. Ele expira em 15 minutos."

        return self.provider.send_email(
            to=to_email,
            subject=subject,
            html=html_content,
            text=text_content
        )


