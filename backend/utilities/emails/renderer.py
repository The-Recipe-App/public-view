
from .layout import header_html, footer_html
from .templates import *
from .enums import EmailKind

def render_email(kind: EmailKind, **data) -> tuple[str, str]:
    """
    Returns: (subject, html)
    """

    if kind == EmailKind.OTP:
        subject = "Your Forkit verification code"
        body = otp_body(
            otp=data["otp"],
            reason=data.get("reason"),
        )
    
    elif kind == EmailKind.NEW_DEVICE_LOGIN_OTP:
        subject = "New device login attempt - your Forkit verification code"
        body = otp_body(
            otp=data["otp"],
            reason=data.get("reason"),
        )

    elif kind == EmailKind.WELCOME:
        subject = "Welcome to Forkit - you're all set!"
        body = welcome_body(
            username=data["username"],
            usrnm_system=data["usrnm_system"],
            auth_method=data["auth_method"],
        )

    elif kind == EmailKind.ACTIVATION:
        subject = "Activate your Forkit account"
        body = activation_body(
            username=data["username"],
            activation_url=data["activation_url"],
        )

    elif kind == EmailKind.PASSWORD_CHANGE_OTP:
        subject = "Your Forkit password change verification code"
        body = password_change_otp_body(otp=data["otp"])

    elif kind == EmailKind.PASSWORD_CHANGED:
        subject = "Your Forkit password was changed"
        body = password_changed_body()

    else:
        raise ValueError(f"Unsupported EmailKind: {kind}")

    html = (
        header_html(subject)
        + body
        + footer_html()
    )

    return subject, html
