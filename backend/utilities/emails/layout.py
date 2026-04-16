# api/v1/auth/emails/layout.py

LOGO_URL = "https://1l1qs.mjt.lu/img2/1l1qs/4dfa7a21-5210-4e60-8d54-dc575b2e7110/content"

def header_html(title: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>{title}</title>
</head>
<body style="margin:0; padding:0; background-color:#0f0f0f; font-family:Arial, Helvetica, sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0"
style="max-width:480px; background:#111; border-radius:12px; padding:32px; color:#fff;">
<tr>
<td align="center" style="padding-bottom:16px;">
<img src="{LOGO_URL}" width="180" alt="Forkit" />
</td>
</tr>
"""

def footer_html() -> str:
    return """
<tr>
<td align="center" style="font-size:11px; color:#555; padding-top:28px;">
© 2026 Forkit. All rights reserved.
</td>
</tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
