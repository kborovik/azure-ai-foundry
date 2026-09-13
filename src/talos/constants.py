SEARCH_API_VERSION = "2026-08-01-preview"
ARM_API_VERSION = "2025-10-01-preview"
FOUNDRY_API_VERSION = "v1"

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
APPLICATION_TYPE_ID_TOKEN = {
    "accepted": "ACCEPTED",
    "rejected": "REJECTED",
    "missing-data": "MISSING-DATA",
}
APPLICATION_ID_RE = r"^CA-(ACCEPTED|REJECTED|MISSING-DATA)-\d{4}-\d{2}$"
CUSTOMER_ID_RE = r"^SYN-\d{6}$"
EMAIL_DOMAIN = "example.invalid"
APPLICATION_LLM_ATTEMPTS = 2

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
    "Synthetic Contoso Demo Bank client applications for demo evaluation only: "
    "accepted, rejected, and missing-data slots. Identify an application by "
    "application_id or customer_name. Not a production origination system."
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
