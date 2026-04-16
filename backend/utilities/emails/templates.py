# api/v1/auth/emails/templates.py

# ─────────────────────────────
# OTP (Email verification / generic)
# ─────────────────────────────

def otp_body(otp: str, reason: str | None) -> str:
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

{reason_html}

<tr>
    <td align="center"
        style="font-size:14px; color:#cccccc; padding-bottom:20px; line-height:1.5;">
        Use the verification code below to finish creating your Forkit account.
    </td>
</tr>

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

<tr>
    <td align="center" style="font-size:13px; color:#aaaaaa; padding-top:16px;">
        This code expires in <strong>5 minutes</strong>.
    </td>
</tr>

<tr>
    <td align="center" style="font-size:12px; color:#777777; padding-top:24px; line-height:1.6;">
        If you did not request this, you can safely ignore this email.<br />
        Never share this code with anyone.
    </td>
</tr>
"""


# ─────────────────────────────
# Welcome email
# ─────────────────────────────

def welcome_body(username: str, usrnm_system: bool, auth_method: str) -> str:
    auth_note = ""

    if auth_method == "oauth_google":
        auth_note= """
        <tr>
            <td align="center"
                style="font-size:13px; color:#aaaaaa; padding-bottom:18px; line-height:1.6;">
                Your account was created using <strong>Google</strong>.
                You can continue signing in with Google anytime.
            </td>
        </tr>

        """

    elif auth_method == "password":
        auth_note = """
        <tr>
            <td align="center"
                style="font-size:13px; color:#aaaaaa; padding-bottom:18px; line-height:1.6;">
                You registered using your email and password.
                Keep your password secure and never share it.
            </td>
        </tr>
        """
    username_note = ""
    if usrnm_system:
        username_note = f"""
        <tr>
            <td align="center"
                style="font-size:13px; color:#aaaaaa; padding-bottom:18px; line-height:1.6;">
                Your username <strong>{username}</strong> was automatically generated.
                You can change it anytime from your profile settings, subject to availability.
            </td>
        </tr>
        """

    return f"""
<tr>
    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
        Welcome aboard, {username} 👋
    </td>
</tr>

{auth_note}

<tr>
    <td align="center"
        style="font-size:14px; color:#cccccc; padding-bottom:16px; line-height:1.6;">
        Your Forkit account is now fully active. You can start discovering, creating,
        and evolving recipes with the community.
    </td>
</tr>

{username_note}

<tr>
    <td align="center"
        style="font-size:13px; color:#bbbbbb; padding-bottom:18px; line-height:1.6;">
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
"""


# ─────────────────────────────
# Activation email
# ─────────────────────────────

def activation_body(username: str, activation_url: str) -> str:
    return f"""
<tr>
    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
        One last step, {username} 🚀
    </td>
</tr>

<tr>
    <td align="center"
        style="font-size:14px; color:#cccccc; padding-bottom:18px; line-height:1.6;">
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
    <td align="center"
        style="font-size:12px; color:#bbbbbb; padding-top:16px; line-height:1.6;">
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
"""


# ─────────────────────────────
# Password change OTP
# ─────────────────────────────

def password_change_otp_body(otp: str) -> str:
    return f"""
<tr>
    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
        Confirm password change
    </td>
</tr>

<tr>
    <td align="center"
        style="font-size:14px; color:#cccccc; padding-bottom:20px; line-height:1.6;">
        We received a request to change the password for your Forkit account.
        Use the verification code below to confirm this action.
    </td>
</tr>

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

<tr>
    <td align="center" style="font-size:13px; color:#aaaaaa; padding-top:16px;">
        This code expires in <strong>5 minutes</strong>.
    </td>
</tr>

<tr>
    <td align="center"
        style="font-size:12px; color:#777777; padding-top:24px; line-height:1.6;">
        If you did not request a password change, your account may be at risk.<br />
        Do <strong>not</strong> share this code with anyone.
    </td>
</tr>
"""


# ─────────────────────────────
# Password changed confirmation
# ─────────────────────────────

def password_changed_body() -> str:
    return f"""
<tr>
    <td align="center" style="font-size:20px; font-weight:bold; padding-bottom:12px;">
        Your password was changed 🔐
    </td>
</tr>

<tr>
    <td align="center"
        style="font-size:14px; color:#cccccc; padding-bottom:18px; line-height:1.6;">
        This is a confirmation that the password for your Forkit account
        was successfully changed.
    </td>
</tr>

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

<tr>
    <td align="center"
        style="font-size:12px; color:#777777; padding-top:22px; line-height:1.6;">
        If you did <strong>not</strong> change your password,
        please secure your account immediately by resetting your password
        and reviewing your active devices.
    </td>
</tr>
"""
