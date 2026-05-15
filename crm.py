import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def _now() -> str:
    return datetime.utcnow().isoformat()


def _stable_id(*parts: str) -> str:
    raw = "::".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CRMDatabase:
    def __init__(self):
        self.db = self._init_firestore()
        self.leads = self.db.collection(config.FIREBASE_LEADS_COLLECTION)
        self.review_queue = self.db.collection(config.FIREBASE_REVIEW_QUEUE_COLLECTION)
        logger.info(
            "Firebase CRM initialized for project %s, database %s",
            config.FIREBASE_PROJECT_ID,
            config.FIREBASE_DATABASE_ID,
        )

    def _init_firestore(self):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as exc:
            raise RuntimeError(
                "firebase-admin is not installed. Run `pip install firebase-admin`."
            ) from exc

        if firebase_admin._apps:
            return firestore.client(database_id=config.FIREBASE_DATABASE_ID)

        private_key = config.FIREBASE_PRIVATE_KEY.replace("\\n", "\n")
        required = {
            "project_id": config.FIREBASE_PROJECT_ID,
            "client_email": config.FIREBASE_CLIENT_EMAIL,
            "private_key": private_key,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing Firebase config values: {', '.join(missing)}")

        service_account = {
            "type": config.FIREBASE_TYPE,
            "project_id": config.FIREBASE_PROJECT_ID,
            "private_key_id": config.FIREBASE_PRIVATE_KEY_ID,
            "private_key": private_key,
            "client_email": config.FIREBASE_CLIENT_EMAIL,
            "client_id": config.FIREBASE_CLIENT_ID,
            "auth_uri": config.FIREBASE_AUTH_URI,
            "token_uri": config.FIREBASE_TOKEN_URI,
            "auth_provider_x509_cert_url": config.FIREBASE_AUTH_PROVIDER_X509_CERT_URL,
            "client_x509_cert_url": config.FIREBASE_CLIENT_X509_CERT_URL,
            "universe_domain": config.FIREBASE_UNIVERSE_DOMAIN,
        }
        firebase_admin.initialize_app(credentials.Certificate(service_account))
        return firestore.client(database_id=config.FIREBASE_DATABASE_ID)

    def _lead_doc_id(self, item: Dict[str, Any]) -> str:
        source = item.get("source", "")
        url = item.get("url") or item.get("text", "")
        return _stable_id(source, url)

    def _lead_payload(self, item: Dict[str, Any], existing_created_at: Optional[str] = None) -> Dict[str, Any]:
        now = _now()
        return {
            "text": item.get("text", ""),
            "cleaned_text": item.get("cleaned_text", ""),
            "source": item.get("source", ""),
            "author": item.get("author", ""),
            "url": item.get("url", ""),
            "timestamp": item.get("timestamp", ""),
            "score": int(item.get("score", 0) or 0),
            "intent_level": item.get("intent_level", "low"),
            "is_lead": bool(item.get("is_lead")),
            "signals": item.get("signals", {}),
            "recommended_action": item.get("recommended_action", "no_action"),
            "ai_response": item.get("ai_response"),
            "status": item.get("status", STATUS_PENDING),
            "platform_metadata": item.get("platform_metadata", {}),
            "created_at": existing_created_at or now,
            "updated_at": now,
        }

    def upsert_lead(self, item: Dict[str, Any]) -> str:
        lead_id = self._lead_doc_id(item)
        doc_ref = self.leads.document(lead_id)
        existing = doc_ref.get()
        existing_created_at = None
        if existing.exists:
            existing_created_at = existing.to_dict().get("created_at")
        doc_ref.set(self._lead_payload(item, existing_created_at), merge=True)
        return lead_id

    def add_linkedin_post_record(
        self,
        content: str,
        status: str,
        share_urn: Optional[str] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        return self.add_social_post_record(
            platform="linkedin",
            endpoint="/api/linkedin/post",
            action="manual_linkedin_post",
            content=content,
            status=status,
            external_id=share_urn,
            error=error,
        )

    def add_social_post_record(
        self,
        platform: str,
        endpoint: str,
        action: str,
        content: str,
        status: str,
        external_id: Optional[str] = None,
        error: Optional[Dict[str, Any]] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        now = _now()
        lead_ref = self.leads.document()
        platform_metadata = {
            "endpoint": endpoint,
            "external_id": external_id,
            "error": error,
        }
        if extra_metadata:
            platform_metadata.update(extra_metadata)
        lead_ref.set({
            "text": content,
            "cleaned_text": content,
            "source": platform,
            "author": endpoint,
            "url": "",
            "timestamp": now,
            "score": 0,
            "intent_level": "manual_post",
            "is_lead": False,
            "signals": {},
            "recommended_action": action,
            "ai_response": None,
            "status": status,
            "platform_metadata": platform_metadata,
            "created_at": now,
            "updated_at": now,
        })
        queue_ref = self.review_queue.document()
        queue_ref.set({
            "lead_id": lead_ref.id,
            "action": action,
            "content": content,
            "status": status,
            "platform_metadata": platform_metadata,
            "created_at": now,
            "updated_at": now,
        })
        return {"lead_id": lead_ref.id, "post_id": queue_ref.id}

    def add_to_review_queue(self, lead_id: str, action: str, content: str) -> str:
        pending_items = (
            self.review_queue
            .where("lead_id", "==", str(lead_id))
            .where("action", "==", action)
            .where("status", "==", STATUS_PENDING)
            .limit(1)
            .stream()
        )
        existing = next(pending_items, None)
        now = _now()
        if existing:
            queue_id = existing.id
            self.review_queue.document(queue_id).set({
                "content": content,
                "updated_at": now,
            }, merge=True)
            return queue_id

        doc_ref = self.review_queue.document()
        doc_ref.set({
            "lead_id": str(lead_id),
            "action": action,
            "content": content,
            "status": STATUS_PENDING,
            "created_at": now,
            "updated_at": now,
        })
        return doc_ref.id

    def get_review_queue(self, status: Optional[str] = STATUS_PENDING) -> List[Dict[str, Any]]:
        self.ensure_manual_linkedin_posts_in_review_queue()
        rows = []
        stream = self.review_queue.stream() if status in (None, "", "all") else self.review_queue.where("status", "==", status).stream()
        for doc in stream:
            queue_item = {"id": doc.id, **doc.to_dict()}
            lead_doc = self.leads.document(str(queue_item.get("lead_id"))).get()
            if lead_doc.exists:
                lead = lead_doc.to_dict()
                queue_item.update({
                    "text": lead.get("text", ""),
                    "source": lead.get("source", ""),
                    "author": lead.get("author", ""),
                    "url": lead.get("url", ""),
                    "score": lead.get("score", 0),
                    "intent_level": lead.get("intent_level", "low"),
                })
            rows.append(queue_item)
        return sorted(rows, key=lambda row: (row.get("score", 0), row.get("created_at", "")), reverse=True)

    def ensure_manual_linkedin_posts_in_review_queue(self):
        for lead_doc in self.leads.where("recommended_action", "==", "manual_linkedin_post").stream():
            existing = (
                self.review_queue
                .where("lead_id", "==", lead_doc.id)
                .where("action", "==", "manual_linkedin_post")
                .limit(1)
                .stream()
            )
            if next(existing, None):
                continue

            lead = lead_doc.to_dict()
            created_at = lead.get("created_at") or _now()
            self.review_queue.document().set({
                "lead_id": lead_doc.id,
                "action": "manual_linkedin_post",
                "content": lead.get("text", ""),
                "status": lead.get("status", STATUS_PENDING),
                "platform_metadata": lead.get("platform_metadata", {}),
                "created_at": created_at,
                "updated_at": lead.get("updated_at") or created_at,
            })

    def get_review_queue_item(self, queue_id) -> Optional[Dict[str, Any]]:
        doc = self.review_queue.document(str(queue_id)).get()
        if not doc.exists:
            return None
        queue_item = {"id": doc.id, **doc.to_dict()}
        lead_doc = self.leads.document(str(queue_item.get("lead_id"))).get()
        if lead_doc.exists:
            lead = lead_doc.to_dict()
            queue_item.update({
                "text": lead.get("text", ""),
                "source": lead.get("source", ""),
                "author": lead.get("author", ""),
                "url": lead.get("url", ""),
                "score": lead.get("score", 0),
                "intent_level": lead.get("intent_level", "low"),
            })
        return queue_item

    def update_review_queue_item(self, queue_id, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"action", "content", "status"}
        clean_updates = {key: value for key, value in updates.items() if key in allowed}
        if not clean_updates:
            return self.get_review_queue_item(queue_id)
        doc_ref = self.review_queue.document(str(queue_id))
        if not doc_ref.get().exists:
            return None
        clean_updates["updated_at"] = _now()
        doc_ref.set(clean_updates, merge=True)
        return self.get_review_queue_item(queue_id)

    def delete_review_queue_item(self, queue_id) -> bool:
        doc_ref = self.review_queue.document(str(queue_id))
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        return True

    def approve_action(self, queue_id):
        self._update_queue_status(queue_id, STATUS_APPROVED)

    def reject_action(self, queue_id):
        self._update_queue_status(queue_id, STATUS_REJECTED)

    def _update_queue_status(self, queue_id, status: str):
        self.review_queue.document(str(queue_id)).set({
            "status": status,
            "updated_at": _now(),
        }, merge=True)

    def get_leads(self, min_score: int = 0, source: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = []
        for doc in self.leads.stream():
            item = {"id": doc.id, **doc.to_dict()}
            if item.get("score", 0) < min_score:
                continue
            if source and item.get("source") != source:
                continue
            rows.append(item)
        return sorted(rows, key=lambda row: row.get("score", 0), reverse=True)

    def get_lead(self, lead_id) -> Optional[Dict[str, Any]]:
        doc = self.leads.document(str(lead_id)).get()
        if not doc.exists:
            return None
        return {"id": doc.id, **doc.to_dict()}

    def update_lead(self, lead_id, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {
            "text", "cleaned_text", "source", "author", "url", "timestamp",
            "score", "intent_level", "is_lead", "signals", "recommended_action",
            "ai_response", "status", "platform_metadata",
        }
        clean_updates = {key: value for key, value in updates.items() if key in allowed}
        if not clean_updates:
            return self.get_lead(lead_id)
        doc_ref = self.leads.document(str(lead_id))
        if not doc_ref.get().exists:
            return None
        clean_updates["updated_at"] = _now()
        doc_ref.set(clean_updates, merge=True)
        return self.get_lead(lead_id)

    def delete_lead(self, lead_id) -> bool:
        doc_ref = self.leads.document(str(lead_id))
        if not doc_ref.get().exists:
            return False
        for doc in self.review_queue.where("lead_id", "==", str(lead_id)).stream():
            doc.reference.delete()
        doc_ref.delete()
        return True

    def get_stats(self) -> Dict[str, Any]:
        leads = [{"id": doc.id, **doc.to_dict()} for doc in self.leads.stream()]
        queue = [{"id": doc.id, **doc.to_dict()} for doc in self.review_queue.stream()]
        lead_items = [item for item in leads if item.get("is_lead")]
        by_source: Dict[str, int] = {}
        by_intent: Dict[str, int] = {}
        for item in leads:
            source = item.get("source", "unknown")
            by_source[source] = by_source.get(source, 0) + 1
        for item in lead_items:
            intent = item.get("intent_level", "low")
            by_intent[intent] = by_intent.get(intent, 0) + 1
        return {
            "backend": "firebase",
            "total_items": len(leads),
            "total_leads": len(lead_items),
            "pending_review": sum(1 for item in queue if item.get("status") == STATUS_PENDING),
            "approved_actions": sum(1 for item in queue if item.get("status") == STATUS_APPROVED),
            "rejected_actions": sum(1 for item in queue if item.get("status") == STATUS_REJECTED),
            "by_source": by_source,
            "by_intent": by_intent,
        }
