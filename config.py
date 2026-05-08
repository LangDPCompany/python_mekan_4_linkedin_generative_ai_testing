import os
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
except ImportError:
    pass

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "YOUR_REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "YOUR_REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "LeadGenBot/1.0 by YourUsername")
REDDIT_SUBREDDITS = os.getenv("REDDIT_SUBREDDITS", "entrepreneur,smallbusiness,sales,CRM,automation").split(",")
REDDIT_POST_LIMIT = int(os.getenv("REDDIT_POST_LIMIT", "25"))

LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_ORGANIZATION_ID = os.getenv("LINKEDIN_ORGANIZATION_ID", "")
LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
LINKEDIN_FALLBACK_FILE = os.getenv("LINKEDIN_FALLBACK_FILE", "linkedin_data.json")
LINKEDIN_USE_PERSONAL_PROFILE = os.getenv("LINKEDIN_USE_PERSONAL_PROFILE", "false").lower() in ("1", "true", "yes")
LINKEDIN_PERSONAL_PROFILE_ID = os.getenv("LINKEDIN_PERSONAL_PROFILE_ID", "")
LINKEDIN_PERSONAL_PROFILE_URN = os.getenv("LINKEDIN_PERSONAL_PROFILE_URN", "")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "mistral")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

LEAD_SCORE_THRESHOLD = int(os.getenv("LEAD_SCORE_THRESHOLD", "60"))
HIGH_INTENT_THRESHOLD = int(os.getenv("HIGH_INTENT_THRESHOLD", "75"))
MEDIUM_INTENT_THRESHOLD = int(os.getenv("MEDIUM_INTENT_THRESHOLD", "50"))

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID", "")
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "")
FIREBASE_AUTH_PROVIDER_X509_CERT_URL = os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs")
FIREBASE_AUTH_URI = os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
FIREBASE_CLIENT_EMAIL = os.getenv("FIREBASE_CLIENT_EMAIL", "")
FIREBASE_CLIENT_ID = os.getenv("FIREBASE_CLIENT_ID", "")
FIREBASE_CLIENT_X509_CERT_URL = os.getenv("FIREBASE_CLIENT_X509_CERT_URL", "")
FIREBASE_MEASUREMENT_ID = os.getenv("FIREBASE_MEASUREMENT_ID", "")
FIREBASE_MESSAGING_SENDER_ID = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "")
FIREBASE_PRIVATE_KEY = os.getenv("FIREBASE_PRIVATE_KEY", "")
FIREBASE_PRIVATE_KEY_ID = os.getenv("FIREBASE_PRIVATE_KEY_ID", "")
FIREBASE_PROD = os.getenv("FIREBASE_PROD", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_DATABASE_ID = os.getenv("FIREBASE_DATABASE_ID", "leads")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "")
FIREBASE_TOKEN_URI = os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token")
FIREBASE_TYPE = os.getenv("FIREBASE_TYPE", "service_account")
FIREBASE_UNIVERSE_DOMAIN = os.getenv("FIREBASE_UNIVERSE_DOMAIN", "googleapis.com")
FIREBASE_LEADS_COLLECTION = os.getenv("FIREBASE_LEADS_COLLECTION", "leads")
FIREBASE_REVIEW_QUEUE_COLLECTION = os.getenv("FIREBASE_REVIEW_QUEUE_COLLECTION", "review_queue")

APPROVAL_MODE = os.getenv("APPROVAL_MODE", "AUTO_ANALYZE_ONLY")

BUSINESS_PAIN_KEYWORDS = [
    "struggling with", "can't figure out", "wasting time", "losing clients",
    "overwhelmed", "bottleneck", "inefficient", "manual process", "too slow",
    "falling behind", "burning out", "can't scale", "losing deals", "frustrated with",
]

AUTOMATION_KEYWORDS = [
    "automate", "automation", "workflow", "integrate", "integration",
    "zapier", "make.com", "n8n", "streamline", "eliminate manual",
    "save time", "reduce manual", "automatic", "hands-free",
]

SCALING_KEYWORDS = [
    "scale", "scaling", "growth", "grow", "expand", "hire", "team growing",
    "more clients", "can't keep up", "overwhelmed by demand", "too many leads",
    "rapid growth",
]

URGENCY_KEYWORDS = [
    "urgent", "asap", "immediately", "critical", "deadline", "need help now",
    "today", "right now", "desperate", "emergency", "must fix", "losing money",
]

CRM_KEYWORDS = [
    "crm", "salesforce", "hubspot", "pipedrive", "zoho", "customer relationship",
    "lead management", "sales pipeline", "contact management", "deal tracking",
]

AI_OPPORTUNITY_KEYWORDS = [
    "ai", "machine learning", "artificial intelligence", "chatbot", "gpt",
    "llm", "data analysis", "predictive", "smart automation", "intelligent",
]

WORKFLOW_KEYWORDS = [
    "workflow", "process", "pipeline", "system", "procedure", "task management",
    "project management", "coordination", "handoff", "approval process",
]

ENGAGEMENT_KEYWORDS = [
    "?", "help", "advice", "recommend", "suggestion", "anyone know",
    "how do you", "what do you use", "looking for", "need a solution",
]

SCORING_WEIGHTS = {
    "business_pain": 30,
    "automation_need": 20,
    "scaling_issue": 20,
    "urgency": 20,
    "engagement": 10,
}

# LinkedIn Content and Engagement Config
LINKEDIN_TAGS = os.getenv("LINKEDIN_TAGS", "automation,AI,CRM,sales,marketing").split(",")
LINKEDIN_DIRECTIONS = os.getenv("LINKEDIN_DIRECTIONS", "lead generation, business automation, AI solutions").split(",")
ARTICLE_SCHEDULE = os.getenv("ARTICLE_SCHEDULE", "weekly")  # daily, weekly, monthly
POST_SCHEDULE = os.getenv("POST_SCHEDULE", "daily")  # daily, weekly
ENGAGEMENT_INTERVAL = int(os.getenv("ENGAGEMENT_INTERVAL", "3600"))  # seconds
LEAD_CTA_TEXT = os.getenv("LEAD_CTA_TEXT", "Check out our website for more solutions: https://example.com/contact")
