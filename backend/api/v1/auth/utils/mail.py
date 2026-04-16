# api/v1/auth/mail.py
import os
from mailjet_rest import Client
from utilities.common.common_utility import debug_print

# ─────────────────────────────
# Configuration
# ─────────────────────────────

LOCAL_ENV = os.getenv("ENV", "local") == "local"

DEFAULT_HOST = os.getenv("HOST", "http://127.0.0.1:8000")

class Mailer:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
    ):
        self.api_key = api_key or os.getenv("MAILJET_API_KEY")
        self.api_secret = api_secret or os.getenv("MAILJET_API_SECRET")
        self.sender_email = sender_email or os.getenv("MAILJET_SENDER_EMAIL")
        self.sender_name = sender_name or os.getenv("MAILJET_SENDER_NAME")

        if not self.api_key or not self.api_secret:
            # In dev you may skip, in prod this should be fatal
            self.client = None
        else:
            self.client = Client(auth=(self.api_key, self.api_secret), version="v3.1")

    # ─────────────────────────────
    # Templates
    # ─────────────────────────────
    
    # To add later: {os.getenv("EMAIL_BRANDING_URL", f"{DEFAULT_HOST}/static/email_branding.png")}

    def _otp_html(self, otp: str, reason: str | None) -> str:
        reason_html = ""
        if reason:
            reason_html = f"""
                <tr>
                    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
                        {reason}
                    </td>
                </tr>
            """
        return f"""
<!DOCTYPE html>
<html>

<head>
    <meta charset="UTF-8" />
    <title>Forkit Email Verification</title>
</head>

<body style="margin:0; padding:0; background-color:#0f0f0f; font-family:Arial, Helvetica, sans-serif;">

    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f; padding:24px 0;">
        <tr>
            <td align="center">

                <!-- Main container -->
                <table width="100%" cellpadding="0" cellspacing="0"
                    style="max-width:480px; background-color:#111111; border-radius:12px; padding:32px; color:#ffffff;">

                    <!-- Logo -->
                    <tr>
                        <td align="center" style="padding-bottom:16px;">
                            <img src="https://1l1qs.mjt.lu/img2/1l1qs/4dfa7a21-5210-4e60-8d54-dc575b2e7110/content" width="180" alt="Forkit"
                                style="max-width:100%; height:auto;" />
                        </td>
                    </tr>
                    
                    {reason_html}

                    <!-- Title -->
                    <tr>
                        <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
                            Verify your email
                        </td>
                    </tr>

                    <!-- Message -->
                    <tr>
                        <td align="center" style="font-size:14px; color:#cccccc; padding-bottom:20px; line-height:1.5;">
                            Use the verification code below to finish creating your Forkit account.
                        </td>
                    </tr>

                    <!-- OTP Box -->
                    <tr>
                        <td align="center">
                            <div style="
                display:inline-block;
                background:#1a1a1a;
                border:1px solid #ff7a18;
                border-radius:8px;
                padding:14px 24px;
                font-size:32px;
                font-weight:bold;
                letter-spacing:6px;
                color:#ff7a18;
                margin:8px 0;
              ">
                                {otp}
                            </div>
                        </td>
                    </tr>

                    <!-- Expiry -->
                    <tr>
                        <td align="center" style="font-size:13px; color:#aaaaaa; padding-top:16px;">
                            This code expires in <strong>5 minutes</strong>.
                        </td>
                    </tr>

                    <!-- Security Note -->
                    <tr>
                        <td align="center" style="font-size:12px; color:#777777; padding-top:24px; line-height:1.6;">
                            If you did not request this, you can safely ignore this email.<br />
                            Never share this code with anyone.
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td align="center" style="font-size:11px; color:#555555; padding-top:28px;">
                            © 2026 Forkit. All rights reserved.
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>

</body>

</html>
        """

    def _welcome_html(self, username: str, usrnm_system: bool) -> str:
        username_note = ""
        if usrnm_system:
            username_note = f"""
            <tr>
                <td align="center" style="font-size:13px; color:#aaaaaa; padding-bottom:18px; line-height:1.6;">
                    Your username <strong>{username}</strong> was automatically generated.
                    You can change it anytime from your profile settings, subject to availability.
                </td>
            </tr>
            """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>Welcome to Forkit</title>
</head>

<body style="margin:0; padding:0; background-color:#0f0f0f; font-family:Arial, Helvetica, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f; padding:24px 0;">
    <tr>
        <td align="center">

            <table width="100%" cellpadding="0" cellspacing="0"
                style="max-width:480px; background-color:#111111; border-radius:12px; padding:32px; color:#ffffff;">

                <tr>
                    <td align="center" style="padding-bottom:16px;">
                        <img src="https://1l1qs.mjt.lu/img2/1l1qs/4dfa7a21-5210-4e60-8d54-dc575b2e7110/content"
                            width="180" alt="Forkit" style="max-width:100%; height:auto;" />
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
                        Welcome aboard, {username} 👋
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:14px; color:#cccccc; padding-bottom:16px; line-height:1.6;">
                        Your Forkit account is now fully active. You can start discovering, creating,
                        and evolving recipes with the community.
                    </td>
                </tr>

                {username_note}

                <tr>
                    <td align="center" style="font-size:13px; color:#bbbbbb; padding-bottom:18px; line-height:1.6;">
                        By using Forkit, you agree to follow our platform guidelines and terms to help keep the
                        community respectful, safe, and enjoyable for everyone.
                    </td>
                </tr>

                <tr>
                    <td align="center" style="padding:12px 0;">
                        <a href="https://forkit.app" style="
                               display:inline-block;
                               background:#ff7a18;
                               color:#000000;
                               text-decoration:none;
                               padding:10px 18px;
                               border-radius:6px;
                               font-weight:bold;
                               font-size:14px;
                           ">
                            Open Forkit
                        </a>
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:12px; color:#777777; padding-top:24px;">
                        Happy cooking and forking recipes,<br />
                        - The Forkit Team
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:11px; color:#555555; padding-top:20px;">
                        © 2026 Forkit. All rights reserved.
                    </td>
                </tr>

            </table>
        </td>
    </tr>
</table>

</body>
</html>
"""

    def _activation_html(self, username: str, activation_url: str) -> str:
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>Activate your Forkit account</title>
</head>

<body style="margin:0; padding:0; background-color:#0f0f0f; font-family:Arial, Helvetica, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f; padding:24px 0;">
    <tr>
        <td align="center">

            <table width="100%" cellpadding="0" cellspacing="0"
                style="max-width:480px; background-color:#111111; border-radius:12px; padding:32px; color:#ffffff;">

                <tr>
                    <td align="center" style="padding-bottom:16px;">
                        <img src="https://1l1qs.mjt.lu/img2/1l1qs/4dfa7a21-5210-4e60-8d54-dc575b2e7110/content"
                            width="180" alt="Forkit" style="max-width:100%; height:auto;" />
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
                        One last step, {username} 🚀
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:14px; color:#cccccc; padding-bottom:18px; line-height:1.6;">
                        Click the button below to activate your Forkit account.
                        This link is personal and will expire for security reasons.
                    </td>
                </tr>

                <tr>
                    <td align="center" style="padding:14px 0;">
                        <a href="{activation_url}" style="
                               display:inline-block;
                               background:#ff7a18;
                               color:#000000;
                               text-decoration:none;
                               padding:12px 22px;
                               border-radius:6px;
                               font-weight:bold;
                               font-size:14px;
                           ">
                            Activate My Account
                        </a>
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:12px; color:#bbbbbb; padding-top:16px; line-height:1.6;">
                        By activating your account, you confirm that you will use Forkit in accordance with
                        our platform guidelines and terms of service.
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:12px; color:#777777; padding-top:24px;">
                        If you did not create this account, you can safely ignore this email.
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:12px; color:#777777; padding-top:12px;">
                        - The Forkit Team
                    </td>
                </tr>

                <tr>
                    <td align="center" style="font-size:11px; color:#555555; padding-top:20px;">
                        © 2026 Forkit. All rights reserved.
                    </td>
                </tr>

            </table>
        </td>
    </tr>
</table>

</body>
</html>
"""

    def _passwrd_change_otp_html(self, otp: str) -> str:
        return f"""
<!DOCTYPE html>
<html>

<head>
    <meta charset="UTF-8" />
    <title>Forkit Password Change</title>
</head>

<body style="margin:0; padding:0; background-color:#0f0f0f; font-family:Arial, Helvetica, sans-serif;">

    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f; padding:24px 0;">
        <tr>
            <td align="center">

                <!-- Main container -->
                <table width="100%" cellpadding="0" cellspacing="0"
                    style="max-width:480px; background-color:#111111; border-radius:12px; padding:32px; color:#ffffff;">

                    <!-- Logo -->
                    <tr>
                        <td align="center" style="padding-bottom:16px;">
                            <img src="https://1l1qs.mjt.lu/img2/1l1qs/4dfa7a21-5210-4e60-8d54-dc575b2e7110/content"
                                 width="180"
                                 alt="Forkit"
                                 style="max-width:100%; height:auto;" />
                        </td>
                    </tr>

                    <!-- Reason -->
                    <tr>
                        <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
                            Confirm password change
                        </td>
                    </tr>

                    <!-- Message -->
                    <tr>
                        <td align="center"
                            style="font-size:14px; color:#cccccc; padding-bottom:20px; line-height:1.6;">
                            We received a request to change the password for your Forkit account.
                            Use the verification code below to confirm this action.
                        </td>
                    </tr>

                    <!-- OTP Box -->
                    <tr>
                        <td align="center">
                            <div style="
                                display:inline-block;
                                background:#1a1a1a;
                                border:1px solid #ff3b30;
                                border-radius:8px;
                                padding:14px 24px;
                                font-size:32px;
                                font-weight:bold;
                                letter-spacing:6px;
                                color:#ff3b30;
                                margin:8px 0;
                            ">
                                {otp}
                            </div>
                        </td>
                    </tr>

                    <!-- Expiry -->
                    <tr>
                        <td align="center" style="font-size:13px; color:#aaaaaa; padding-top:16px;">
                            This code expires in <strong>5 minutes</strong>.
                        </td>
                    </tr>

                    <!-- Security warning -->
                    <tr>
                        <td align="center"
                            style="font-size:12px; color:#777777; padding-top:24px; line-height:1.6;">
                            If you did not request a password change, your account may be at risk.<br />
                            Do <strong>not</strong> share this code with anyone.
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td align="center" style="font-size:11px; color:#555555; padding-top:28px;">
                            © 2026 Forkit. All rights reserved.
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>

</body>
</html>
"""

    def _password_changed_html(self) -> str:
        return f"""
<!DOCTYPE html>
<html>

<head>
    <meta charset="UTF-8" />
    <title>Password changed</title>
</head>

<body style="margin:0; padding:0; background-color:#0f0f0f; font-family:Arial, Helvetica, sans-serif;">

    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f; padding:24px 0;">
        <tr>
            <td align="center">

                <!-- Main container -->
                <table width="100%" cellpadding="0" cellspacing="0"
                    style="max-width:480px; background-color:#111111; border-radius:12px; padding:32px; color:#ffffff;">

                    <!-- Logo -->
                    <tr>
                        <td align="center" style="padding-bottom:16px;">
                            <img src="https://1l1qs.mjt.lu/img2/1l1qs/4dfa7a21-5210-4e60-8d54-dc575b2e7110/content"
                                 width="180"
                                 alt="Forkit"
                                 style="max-width:100%; height:auto;" />
                        </td>
                    </tr>

                    <!-- Title -->
                    <tr>
                        <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
                            Your password was changed 🔐
                        </td>
                    </tr>

                    <!-- Message -->
                    <tr>
                        <td align="center"
                            style="font-size:14px; color:#cccccc; padding-bottom:18px; line-height:1.6;">
                            This is a confirmation that the password for your Forkit account
                            was successfully changed.
                        </td>
                    </tr>

                    <!-- Info box -->
                    <tr>
                        <td align="center">
                            <div style="
                                background:#1a1a1a;
                                border:1px solid #2ecc71;
                                border-radius:8px;
                                padding:14px 18px;
                                font-size:13px;
                                color:#b6f5c9;
                                line-height:1.6;
                                margin:8px 0;
                            ">
                                ✔ No further action is required if this was you.
                            </div>
                        </td>
                    </tr>

                    <!-- Security warning -->
                    <tr>
                        <td align="center"
                            style="font-size:12px; color:#777777; padding-top:22px; line-height:1.6;">
                            If you did <strong>not</strong> change your password,
                            please secure your account immediately by resetting your password
                            and reviewing your active devices.
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td align="center" style="font-size:11px; color:#555555; padding-top:28px;">
                            © 2026 Forkit. All rights reserved.
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>

</body>
</html>
"""


    # ─────────────────────────────
    # Senders
    # ─────────────────────────────


    async def send_otp_email(self, to_email: str, otp: str, reason: str | None = None):
        if LOCAL_ENV:
            debug_print(f"OTP: {otp}", color="green")
            return
        if not self.client:
            return

        data = {
            "Messages": [
                {
                    "From": {
                        "Email": self.sender_email,
                        "Name": self.sender_name,
                    },
                    "To": [
                        {"Email": to_email}
                    ],
                    "Subject": "Your Forkit verification code",
                    "HTMLPart": self._otp_html(otp, reason),
                }
            ]
        }

        result = self.client.send.create(data=data)
        if result.status_code >= 400:
            raise RuntimeError(f"Mailjet OTP send failed: {result.status_code} {result.json()}")

        return result.json()

    async def send_welcome_email(self, to_email: str, username: str, usrnm_system: bool):
        if LOCAL_ENV:
            debug_print(f"Username: {username}, sent welcome email", color="green")
            return
        if not self.client:
            return

        data = {
            "Messages": [
                {
                    "From": {
                        "Email": self.sender_email,
                        "Name": self.sender_name,
                    },
                    "To": [
                        {"Email": to_email}
                    ],
                    "Subject": "Welcome to Forkit - you're all set!",
                    "HTMLPart": self._welcome_html(username, usrnm_system),
                }
            ]
        }

        result = self.client.send.create(data=data)
        if result.status_code >= 400:
            raise RuntimeError(f"Mailjet welcome send failed: {result.status_code} {result.json()}")

        return result.json()

    async def send_activation_email(
        self,
        to_email: str,
        username: str,
        activation_url: str,
    ):
        if LOCAL_ENV:
            debug_print(f"Username: {username}, sent activation email, activation url: {activation_url}", color="green")
            return
        if not self.client:
            return

        subject = "Activate your Forkit account"

        html = self._activation_html(username, activation_url)

        data = {
            "Messages": [
                {
                    "From": {
                        "Email": self.sender_email,
                        "Name": self.sender_name,
                    },
                    "To": [
                        {"Email": to_email}
                    ],
                    "Subject": subject,
                    "HTMLPart": html,
                }
            ]
        }

        result = self.client.send.create(data=data)
        if result.status_code >= 400:
            raise RuntimeError(
                f"Mailjet activation send failed: {result.status_code} {result.json()}"
            )

        return result.json()

    async def send_password_change_otp_email(self, to_email: str, otp: str):
        if LOCAL_ENV:
            debug_print(f"OTP: {otp}", color="yellow")
            return
        if not self.client:
            return

        data = {
            "Messages": [
                {
                    "From": {
                        "Email": self.sender_email,
                        "Name": self.sender_name,
                    },
                    "To": [
                        {"Email": to_email}
                    ],
                    "Subject": "Your Forkit password change verification code",
                    "HTMLPart": self._passwrd_change_otp_html(otp),
                }
            ]
        }

        result = self.client.send.create(data=data)
        if result.status_code >= 400:
            raise RuntimeError(f"Mailjet password change OTP send failed: {result.status_code} {result.json()}")

        return result.json()

    async def send_password_changed_email(self, to_email: str):
        if LOCAL_ENV:
            debug_print("Sent password changed email", color="yellow")
            return
        if not self.client:
            return

        data = {
            "Messages": [
                {
                    "From": {
                        "Email": self.sender_email,
                        "Name": self.sender_name,
                    },
                    "To": [
                        {"Email": to_email}
                    ],
                    "Subject": "Your Forkit password was changed",
                    "HTMLPart": self._password_changed_html(),
                }
            ]
        }

        result = self.client.send.create(data=data)
        if result.status_code >= 400:
            raise RuntimeError(f"Mailjet password changed send failed: {result.status_code} {result.json()}")

        return result.json()