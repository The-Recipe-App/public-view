# api/v1/auth/mailer.py
from mailjet_rest import Client
from utilities.common.common_utility import debug_print
from .enums import EmailKind
from .renderer import render_email
import os

LOCAL_ENV = os.getenv("ENV", "local") == "local"

class Mailer:
    def __init__(self):
        self.client = Client(
            auth=(
                os.getenv("MAILJET_API_KEY"),
                os.getenv("MAILJET_API_SECRET"),
            ),
            version="v3.1",
        )
        self._from = {
            "Email": os.getenv("MAILJET_SENDER_EMAIL"),
            "Name": os.getenv("MAILJET_SENDER_NAME"),
        }

    async def send(self, *, to_email: str, kind: EmailKind, **data):
        if LOCAL_ENV:
            debug_print(f"[EMAIL:{kind}] → {to_email} | {data}", color="green")
            return

        subject, html = render_email(kind, **data)

        payload = {
            "Messages": [
                {
                    "From": self._from,
                    "To": [{"Email": to_email}],
                    "Subject": subject,
                    "HTMLPart": html,
                }
            ]
        }

        result = self.client.send.create(data=payload)
        if result.status_code >= 400:
            raise RuntimeError(result.json())

        return result.json()
