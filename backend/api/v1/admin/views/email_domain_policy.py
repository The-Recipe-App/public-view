from sqladmin import ModelView
from database.security.core.models import EmailDomainPolicy


class EmailDomainPolicyAdmin(ModelView, model=EmailDomainPolicy):
    name = "Email Domain"
    name_plural = "Email Domains"
    icon = "fa fa-envelope"

    # ---- List view ----
    column_list = [
        "domain",
        "is_blocked",
        "is_disposable",
        "is_allowed",
        "confidence",
        "source",
        "expires_at",
        "updated_at",
    ]

    # ---- Search (THIS WORKS) ----
    column_searchable_list = [
        "domain",
        "reason",
        "source",
    ]

    # ---- Sorting (THIS WORKS) ----
    column_sortable_list = [
        "domain",
        "confidence",
        "updated_at",
        "expires_at",
    ]

    # ---- Form ----
    form_columns = [
        "domain",
        "is_blocked",
        "is_disposable",
        "is_allowed",
        "confidence",
        "source",
        "reason",
        "expires_at",
    ]

    form_args = {
        "domain": {
            "label": "Email Domain",
            "description": "example: mailinator.com",
        },
        "confidence": {
            "label": "Confidence (0–100)",
        },
        "expires_at": {
            "label": "Temporary Block Expiry",
        },
    }

    page_size = 50
