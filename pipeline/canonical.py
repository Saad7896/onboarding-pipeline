"""Canonical schema: what a clean customer record looks like in OUR system."""

SCHEMA_VERSION = "v1"

CUSTOMER_FIELDS = {
    "customer_id": {
        "type": "id",
        "required": True,
        "description": "Unique customer identifier in the source system",
        "synonyms": ["account id", "acct id", "customer id", "cust id", "client id", "customer number"],
        "default_transforms": ["trim"],
    },
    "legal_name": {
        "type": "text",
        "required": True,
        "description": "Registered company name",
        "synonyms": ["account name", "acct name", "company", "company name", "customer name", "organization"],
        "default_transforms": ["trim"],
    },
    "email": {
        "type": "email",
        "required": True,
        "description": "Primary contact email",
        "synonyms": ["email", "email address", "email addr", "contact email", "e-mail"],
        "default_transforms": ["trim", "lowercase"],
    },
    "created_at": {
        "type": "date",
        "required": True,
        "description": "Date the customer account was created",
        "synonyms": ["created date", "created", "created on", "date created", "signup date", "open date"],
        "default_transforms": ["parse_date"],
    },
    "country": {
        "type": "country",
        "required": False,
        "description": "Customer country as ISO 3166 alpha-2 code",
        "synonyms": ["country", "country code", "nation", "billing country"],
        "default_transforms": ["normalize_country_iso2"],
    },
}