import re
import logging
from typing import Dict, Any, List, Tuple
import config

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    EMBEDDINGS_AVAILABLE = True
except Exception as e:
    logger.warning(f"sentence-transformers not available: {e}. Embeddings disabled.")
    _embedding_model = None
    EMBEDDINGS_AVAILABLE = False


def clean_text(text: str) -> str:
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"[^\w\s\?\!\.\,\-\']", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def generate_embedding(text: str) -> List[float]:
    if not EMBEDDINGS_AVAILABLE or _embedding_model is None:
        return []
    try:
        embedding = _embedding_model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return []


def _keyword_hit(text_lower: str, keywords: List[str]) -> bool:
    return any(kw.lower() in text_lower for kw in keywords)


def detect_intent_signals(text: str) -> Dict[str, bool]:
    t = text.lower()
    return {
        "business_pain": _keyword_hit(t, config.BUSINESS_PAIN_KEYWORDS),
        "automation_need": _keyword_hit(t, config.AUTOMATION_KEYWORDS),
        "scaling_issue": _keyword_hit(t, config.SCALING_KEYWORDS),
        "urgency": _keyword_hit(t, config.URGENCY_KEYWORDS),
        "engagement": _keyword_hit(t, config.ENGAGEMENT_KEYWORDS),
        "crm_related": _keyword_hit(t, config.CRM_KEYWORDS),
        "ai_opportunity": _keyword_hit(t, config.AI_OPPORTUNITY_KEYWORDS),
        "workflow_issue": _keyword_hit(t, config.WORKFLOW_KEYWORDS),
    }


def calculate_lead_score(signals: Dict[str, bool]) -> int:
    score = 0
    weights = config.SCORING_WEIGHTS
    if signals.get("business_pain"):
        score += weights["business_pain"]
    if signals.get("automation_need"):
        score += weights["automation_need"]
    if signals.get("scaling_issue"):
        score += weights["scaling_issue"]
    if signals.get("urgency"):
        score += weights["urgency"]
    if signals.get("engagement"):
        score += weights["engagement"]
    return min(score, 100)


def classify_intent(score: int) -> str:
    if score >= config.HIGH_INTENT_THRESHOLD:
        return "high"
    elif score >= config.MEDIUM_INTENT_THRESHOLD:
        return "medium"
    return "low"


def decide_action(score: int, source: str, signals: Dict[str, bool]) -> str:
    if score < config.LEAD_SCORE_THRESHOLD:
        return "no_action"
    if source == "linkedin":
        if signals.get("business_pain") or signals.get("automation_need"):
            return "generate_linkedin_post"
        return "generate_insight_comment"
    if source == "reddit":
        if signals.get("engagement") or signals.get("business_pain"):
            return "generate_reply"
        return "generate_insight_comment"
    return "no_action"


def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
    raw_text = item.get("text", "")
    cleaned = clean_text(raw_text)
    embedding = generate_embedding(cleaned)
    signals = detect_intent_signals(cleaned)
    score = calculate_lead_score(signals)
    intent = classify_intent(score)
    action = decide_action(score, item.get("source", ""), signals)
    is_lead = score >= config.LEAD_SCORE_THRESHOLD

    return {
        **item,
        "cleaned_text": cleaned,
        "embedding": embedding,
        "signals": signals,
        "score": score,
        "intent_level": intent,
        "is_lead": is_lead,
        "recommended_action": action,
    }


def process_batch(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    processed = []
    for item in items:
        try:
            result = process_item(item)
            processed.append(result)
        except Exception as e:
            logger.error(f"Error processing item: {e}")
            continue
    leads = [p for p in processed if p["is_lead"]]
    logger.info(f"Processed {len(processed)} items. Leads found: {len(leads)}")
    return processed