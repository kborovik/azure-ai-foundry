SEARCH_API_VERSION = "2026-08-01-preview"
ARM_API_VERSION = "2025-10-01-preview"
FOUNDRY_API_VERSION = "v1"
BOT_API_VERSION = "2022-09-15"
BOT_CHANNEL_API_VERSION = "2021-03-01"
ACTIVITY_PROTOCOL_API_VERSION = "2025-05-15-preview"

SEARCH_SCOPE = "https://search.azure.com/.default"
ARM_SCOPE = "https://management.azure.com/.default"
FOUNDRY_SCOPE = "https://ai.azure.com/.default"

DEFAULT_CONTAINER = "credit-policies"
DEFAULT_APPLICATION_CONTAINER = "client-applications"
DEFAULT_KNOWLEDGE_SOURCE = "ks-credit-policies"
DEFAULT_APPLICATION_KNOWLEDGE_SOURCE = "ks-client-applications"
DEFAULT_KNOWLEDGE_BASE = "kb-credit-policies"
DEFAULT_AGENT_NAME = "credit-policy-agent"
DEFAULT_CONNECTION_NAME = "conn-kb-credit-policies"
DEFAULT_BOT_NAME = "bot-credit-policy-agent"
DEFAULT_PUBLISH_DISPLAY_NAME = "Credit Policy Agent"
DEFAULT_APP_VERSION = "1.0.0"
DEFAULT_DEVELOPER_NAME = "Contoso Demo Bank"
DEFAULT_DEVELOPER_WEBSITE_URL = "https://azure.microsoft.com"
DEFAULT_PRIVACY_URL = "https://privacy.microsoft.com"
DEFAULT_TERMS_OF_USE_URL = "https://www.microsoft.com/legal/terms-of-use"
DEFAULT_PUBLISH_SHORT_DESCRIPTION = (
    "Cited credit-policy answers and synthetic application evaluation."
)
DEFAULT_PUBLISH_FULL_DESCRIPTION = (
    "Demo Foundry prompt agent that answers credit-policy questions from synthetic "
    "Markdown in Foundry IQ and evaluates synthetic client applications by "
    "application_id or customer_name. Not a production credit system."
)
PUBLISH_SCOPE_JUST_YOU = "Shared"
DEFAULT_CHAT_DEPLOYMENT = "gpt-5-mini"
DEFAULT_EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
DEFAULT_INSTRUCTIONS_RELATIVE = "agents/credit-policy-agent.instructions.md"
DEFAULT_FACTS_RELATIVE = "corpus/facts.yaml"
DEFAULT_TEMPLATES_RELATIVE = "corpus/templates"
DEFAULT_OUTPUT_RELATIVE = "data/credit-policies"
DEFAULT_APPLICATION_OUTPUT_RELATIVE = "data/client-applications"
DEFAULT_APPLICATION_SCHEMA_RELATIVE = "corpus/application/schema.json"
DEFAULT_APPLICATION_SYSTEM_PROMPT_RELATIVE = "corpus/application/system.md"
DEFAULT_APPLICATION_USER_PROMPT_RELATIVE = "corpus/application/user.md.j2"
DEFAULT_APPLICATION_TEMPLATE_RELATIVE = "corpus/application/document.md.j2"

APPLICATION_TYPES = ("accepted", "rejected", "missing-data")
APPLICATION_ID_RE = r"^CA-\d{8}-\d+$"
APPLICATION_FILENAME_TEMPLATE = "credit-application-{application_id}.md"
FORBIDDEN_OUTCOME_TOKENS = (
    "ACCEPTED",
    "REJECTED",
    "MISSING",
    "APPROVED",
    "DECLINED",
    "DENIED",
    "PASS",
    "FAIL",
)
CUSTOMER_ID_RE = r"^SYN-\d{6}$"
EMAIL_DOMAIN = "example.invalid"
APPLICATION_LLM_ATTEMPTS = 2

PRODUCT_FAMILIES = (
    "residential_mortgage",
    "commercial_real_estate",
    "unsecured_consumer",
    "sme_lending",
    "construction_development",
)
SLOT_PRODUCT_FAMILY = {
    "accepted": "residential_mortgage",
    "rejected": "commercial_real_estate",
    "missing-data": "sme_lending",
}
PRODUCT_FAMILY_LABEL = {
    "residential_mortgage": "owner-occupied residential mortgage",
    "commercial_real_estate": "stabilized commercial real estate",
    "unsecured_consumer": "unsecured personal loan",
    "sme_lending": "SME working-capital facility",
    "construction_development": "construction and development facility",
}
# Titles that appear verbatim in published policy Markdown (CP-DOC, CP-COL, CP-SME, CP-CND).
PRODUCT_REQUIRED_DOCUMENTS = {
    "residential_mortgage": (
        "last 2 pay stubs",
        "W-2",
        "residential appraisal",
    ),
    "commercial_real_estate": (
        "2 years tax returns",
        "YTD P&L",
        "CRE valuation",
    ),
    "unsecured_consumer": (
        "last 2 pay stubs",
        "W-2",
    ),
    "sme_lending": (
        "personal guarantee",
        "last 2 pay stubs",
        "W-2",
    ),
    "construction_development": (
        "completion guarantee",
        "2 years tax returns",
        "YTD P&L",
    ),
}
# field, op, limit — facts.yaml literals (80%, 43%, 680, 65%, 1.25x, USD 2,500,000, …).
PRODUCT_FACILITY_LIMITS: dict[str, tuple[tuple[str, str, float], ...]] = {
    "residential_mortgage": (
        ("ltv", "<=", 80.0),
        ("dti", "<=", 43.0),
        ("credit_score", ">=", 680.0),
    ),
    "commercial_real_estate": (
        ("ltv", "<=", 65.0),
        ("dscr", ">=", 1.25),
    ),
    "unsecured_consumer": (
        ("loan_amount", "<=", 50_000.0),
        ("credit_score", ">=", 700.0),
        ("dti", "<=", 36.0),
        ("tenor_months", "<=", 60.0),
    ),
    "sme_lending": (
        ("loan_amount", "<=", 2_500_000.0),
        ("years_in_operation", ">=", 3.0),
        ("tenor_months", "<=", 12.0),
    ),
    "construction_development": (
        ("ltv", "<=", 55.0),
        ("tenor_months", "<=", 18.0),
    ),
}
FACILITY_PROMPT_HINTS = {
    "residential_mortgage": (
        "Owner-occupied residential: max LTV 80%, max DTI 43%, min credit score 680."
    ),
    "commercial_real_estate": "Stabilized CRE: max LTV 65%, min DSCR 1.25x.",
    "unsecured_consumer": (
        "Unsecured personal loan: max USD 50,000, max term 60 months, min FICO 700, "
        "max DTI 36%."
    ),
    "sme_lending": (
        "SME working capital: max USD 2,500,000, personal guarantee above USD 250,000, "
        "max tenor 12 months, min 3 years in operation. Amount must be above USD 250,000."
    ),
    "construction_development": (
        "Construction: construction max LTV 55%, max interest-only 18 months, "
        "completion guarantee required."
    ),
}

WATERMARK = "SYNTHETIC — DEMO ONLY"

CORPUS_IDS = (
    "CP-RML-2026-01",
    "CP-CRE-2026-01",
    "CP-UCL-2026-01",
    "CP-SME-2026-01",
    "CP-EXC-2026-01",
    "CP-PRO-2026-01",
    "CP-COL-2026-01",
    "CP-DOC-2026-01",
    "CP-RPL-2026-01",
    "CP-ESG-2026-01",
    "CP-CND-2026-01",
    "CP-AUTH-2026-01",
)

GOLDEN_QUERY_IDS = (
    "Q-RML-LTV-OO",
    "Q-RML-DTI",
    "Q-CRE-DSCR",
    "Q-UCL-MAX",
    "Q-SME-PG",
    "Q-COL-AVM",
    "Q-AUTH-RM",
    "Q-CMP-LTV-CRE-ESG",
    "Q-CMP-CONSTRUCTION",
    "Q-NEG-AUTO",
    "Q-NEG-SOVEREIGN",
    "Q-AMB-LTV",
    "Q-CIT-PROHIBITED",
    "Q-MT-EXCEPTION",
    "Q-MT-ESG-FOLLOWUP",
    "Q-ADV-JAILBREAK",
    "Q-ADV-INVENT",
    "Q-DOC-SE",
)

DEFAULT_GOLDEN_LAYERS = ("retrieval", "agent")
REFUSAL_SENTENCE = "not in the published policies"
TEAMS_CHECKLIST_QUERY_IDS = (
    "Q-RML-LTV-OO",
    "Q-NEG-AUTO",
    "Q-ADV-JAILBREAK",
)

MIN_INDEXED_ITEMS = 12
MIN_APPLICATION_INDEXED_ITEMS = 3
WAIT_TIMEOUT_SECONDS = 15 * 60
POLL_INTERVAL_SECONDS = 10.0
CONNECTION_RETRIES = 5
CONNECTION_RETRY_DELAY_SECONDS = 20.0
INDEXER_NAME_RETRIES = 10
INDEXER_NAME_RETRY_DELAY_SECONDS = 2.0

REQUIRED_ENV = (
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_AI_PROJECT_ENDPOINT",
    "AZURE_AI_PROJECT_RESOURCE_ID",
    "AZURE_STORAGE_RESOURCE_ID",
    "AZURE_AI_SERVICES_ENDPOINT",
)

CANONICAL_ENV = (
    "AZURE_LOCATION",
    "AZURE_RESOURCE_GROUP",
    "AZURE_STORAGE_ACCOUNT_URL",
    "AZURE_STORAGE_RESOURCE_ID",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_AI_PROJECT_ENDPOINT",
    "AZURE_AI_PROJECT_RESOURCE_ID",
    "AZURE_AI_SERVICES_ENDPOINT",
    "AZURE_AI_PROJECT_PRINCIPAL_ID",
)

KS_DESCRIPTION = (
    "Synthetic Contoso Demo Bank credit policies: residential mortgage LTV/DTI, "
    "commercial real estate, unsecured consumer, SME lending, exceptions and override "
    "authority, prohibited sectors, collateral valuation, documentation, related-party "
    "lending, climate/ESG overlay, construction lending, and delegated credit authority. "
    "Use for credit-officer policy questions."
)

KS_APPLICATION_DESCRIPTION = (
    "Synthetic Contoso Demo Bank client applications for demo evaluation only. "
    "Identify an application by application_id or customer_name. Not a production "
    "origination system."
)

KB_DESCRIPTION = (
    "Contoso Demo Bank credit policy knowledge base. Grounds answers in synthetic "
    "published policies and evaluates synthetic client applications."
)

KB_RETRIEVAL_INSTRUCTIONS = (
    "Use ks-credit-policies for all credit policy, LTV, DTI, DSCR, collateral, "
    "exception authority, prohibited sector, related-party, documentation, construction, "
    "and ESG overlay questions. Use ks-client-applications when evaluating a client "
    "application identified by application_id or customer_name. Do not use web or "
    "other sources."
)
