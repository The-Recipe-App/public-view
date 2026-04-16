from sqladmin import Admin
from fastapi import FastAPI

from database.security.core.session import engine as security_engine
from api.v1.admin.views.email_domain_policy import EmailDomainPolicyAdmin

def setup_admin(app: FastAPI, path: str = "/admin"):
    admin = Admin(
        app=app,
        engine=security_engine,
        title="Forkit Security Admin",
        base_url=path,
        logo_url="/static/site_logo_text.svg",
        favicon_url="/static/web-logo-transp.svg",
    )

    admin.add_view(EmailDomainPolicyAdmin)
