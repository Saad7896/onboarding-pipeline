"""Test schemas of increasing difficulty, with the ground-truth mapping for each.

We know the correct answer because we created the mess ourselves.
"""

GROUND_TRUTH = {
    "S1_clean_crm": {
        "csv": """customer_id,legal_name,email,created_at,country,risk_tier
C-001,Acme Ltd,ops@acme.com,2025-01-15,GB,high
C-002,Globex Corp,ops@globex.com,2025-02-20,US,low
C-003,Initech,billing@initech.io,2025-03-05,DE,medium
""",
        "mapping": {
            "customer_id": "customer_id", "legal_name": "legal_name", "email": "email",
            "created_at": "created_at", "country": "country", "risk_tier": "risk_tier",
        },
        "expected_valid": 3,
        "expected_exceptions": 0,
    },
    "S2_salesforce_style": {
        "csv": """Account_ID__c,AcctName,Email_Addr,Created Date,Country,Risk_Level__c
00123,Acme Ltd,ops@acme.com,01/15/2025,UK,high
00124,Globex Corp,,02/20/2025,United Kingdom,medium
00125,Initech,billing@initech.io,03/05/2025,uk,low
""",
        "mapping": {
            "customer_id": "Account_ID__c", "legal_name": "AcctName", "email": "Email_Addr",
            "created_at": "Created Date", "country": "Country", "risk_tier": "Risk_Level__c",
        },
        "expected_valid": 2,
        "expected_exceptions": 1,  # missing email
    },
    "S3_legacy_erp": {
        "csv": """CUST_NO,CO_NM,EML,DT_OPN,CTRY_CD,RSK_BND
A-9001,Stark Industries,tony@stark.com,2024-11-03,US,1
A-9002,Wayne Enterprises,bruce@wayne.com,2024-12-19,US,3
A-9003,Cyberdyne Systems,miles@cyberdyne.com,06/01/2025,US,2
""",
        "mapping": {
            "customer_id": "CUST_NO", "legal_name": "CO_NM", "email": "EML",
            "created_at": "DT_OPN", "country": "CTRY_CD", "risk_tier": "RSK_BND",
        },
        "expected_valid": 2,
        "expected_exceptions": 1,  # ambiguous date
    },
    "S4_adversarial": {
        "csv": """id,name,contact,modified_on,opened,region,tier,notes
X1,Umbrella PLC,admin@umbrella.co.uk,2025-06-01,2025-01-10,United Kingdom,critical,vip
X2,Hooli Inc,team@hooli.com,2025-06-02,2025-02-14,US,minimal,
X1,Umbrella PLC,admin@umbrella.co.uk,2025-06-03,2025-01-10,uk,critical,dupe
""",
        # 'opened' is the creation date; 'modified_on' is a decoy.
        # 'name' and 'contact' are vague; 'region' is country; 'tier' is risk.
        "mapping": {
            "customer_id": "id", "legal_name": "name", "email": "contact",
            "created_at": "opened", "country": "region", "risk_tier": "tier",
        },
        "expected_valid": 2,
        "expected_exceptions": 1,  # duplicate X1
    },
}