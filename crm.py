import hashlib
import json
import logging
import sqlite3
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


class SQLiteCRMDatabase:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    cleaned_text TEXT,
                    source TEXT NOT NULL,
                    author TEXT,
                    url TEXT,
                    timestamp TEXT,
                    score INTEGER DEFAULT 0,
                    intent_level TEXT DEFAULT 'low',
                    is_lead INTEGER DEFAULT 0,
                    signals TEXT,
                    recommended_action TEXT,
                    ai_response TEXT,
                    status TEXT DEFAULT 'pending',
                    platform_metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    content TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lead_id) REFERENCES leads(id)
                )
            """)
            review_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(review_queue)").fetchall()
            }
            if "updated_at" not in review_columns:
                conn.execute("ALTER TABLE review_queue ADD COLUMN updated_at TEXT")
            conn.commit()
        logger.info(f"SQLite CRM initialized at {self.db_path}")

    def upsert_lead(self, item: Dict[str, Any]) -> int:
        url = item.get("url", "")
        source = item.get("source", "")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM leads WHERE url = ? AND source = ?", (url, source)
            ).fetchone()
            signals_json = json.dumps(item.get("signals", {}))
            metadata_json = json.dumps(item.get("platform_metadata", {}))
            now = _now()

            if existing:
                lead_id = existing["id"]
                conn.execute("""
                    UPDATE leads SET
                        score = ?, intent_level = ?, is_lead = ?,
                        signals = ?, recommended_action = ?, ai_response = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    item.get("score", 0),
                    item.get("intent_level", "low"),
                    1 if item.get("is_lead") else 0,
                    signals_json,
                    item.get("recommended_action", "no_action"),
                    item.get("ai_response"),
                    now,
                    lead_id,
                ))
            else:
                cursor = conn.execute("""
                    INSERT INTO leads (
                        text, cleaned_text, source, author, url, timestamp,
                        score, intent_level, is_lead, signals,
                        recommended_action, ai_response, status,
                        platform_metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("text", ""),
                    item.get("cleaned_text", ""),
                    source,
                    item.get("author", ""),
                    url,
                    item.get("timestamp", ""),
                    item.get("score", 0),
                    item.get("intent_level", "low"),
                    1 if item.get("is_lead") else 0,
                    signals_json,
                    item.get("recommended_action", "no_action"),
                    item.get("ai_response"),
                    STATUS_PENDING,
                    metadata_json,
                    now,
                    now,
                ))
                lead_id = cursor.lastrowid
            conn.commit()
        return lead_id

    def add_to_review_queue(self, lead_id: int, action: str, content: str):
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM review_queue WHERE lead_id = ? AND action = ? AND status = ?",
                (lead_id, action, STATUS_PENDING),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE review_queue SET content = ?, updated_at = ? WHERE id = ?",
                    (content, _now(), existing["id"]),
                )
                queue_id = existing["id"]
            else:
                now = _now()
                conn.execute("""
                    INSERT INTO review_queue (lead_id, action, content, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (lead_id, action, content, STATUS_PENDING, now, now))
                queue_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()
        return queue_id

    def get_review_queue(self, status: Optional[str] = STATUS_PENDING) -> List[Dict[str, Any]]:
        status = None if status in (None, "", "all") else status
        with self._connect() as conn:
            if status:
                rows = conn.execute("""
                    SELECT rq.*, l.text, l.source, l.author, l.url, l.score, l.intent_level
                    FROM review_queue rq
                    JOIN leads l ON rq.lead_id = l.id
                    WHERE rq.status = ?
                    ORDER BY l.score DESC, rq.created_at DESC
                """, (status,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT rq.*, l.text, l.source, l.author, l.url, l.score, l.intent_level
                    FROM review_queue rq
                    JOIN leads l ON rq.lead_id = l.id
                    ORDER BY l.score DESC, rq.created_at DESC
                """).fetchall()
        return [dict(r) for r in rows]

    def get_review_queue_item(self, queue_id) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT rq.*, l.text, l.source, l.author, l.url, l.score, l.intent_level
                FROM review_queue rq
                JOIN leads l ON rq.lead_id = l.id
                WHERE rq.id = ?
            """, (queue_id,)).fetchall()
        return dict(rows[0]) if rows else None

    def update_review_queue_item(self, queue_id, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"action", "content", "status"}
        clean_updates = {key: value for key, value in updates.items() if key in allowed}
        if not clean_updates:
            return self.get_review_queue_item(queue_id)
        clean_updates["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in clean_updates)
        params = list(clean_updates.values()) + [queue_id]
        with self._connect() as conn:
            cursor = conn.execute(f"UPDATE review_queue SET {assignments} WHERE id = ?", params)
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get_review_queue_item(queue_id)

    def delete_review_queue_item(self, queue_id) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM review_queue WHERE id = ?", (queue_id,))
            conn.commit()
        return cursor.rowcount > 0

    def approve_action(self, queue_id):
        self._update_queue_status(queue_id, STATUS_APPROVED)

    def reject_action(self, queue_id):
        self._update_queue_status(queue_id, STATUS_REJECTED)

    def _update_queue_status(self, queue_id, status: str):
        with self._connect() as conn:
            conn.execute("UPDATE review_queue SET status = ? WHERE id = ?", (status, queue_id))
            conn.commit()

    def get_leads(self, min_score: int = 0, source: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM leads WHERE score >= ?"
        params: list = [min_score]
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY score DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["signals"] = json.loads(item["signals"] or "{}")
            item["platform_metadata"] = json.loads(item["platform_metadata"] or "{}")
            results.append(item)
        return results

    def get_lead(self, lead_id) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["signals"] = json.loads(item["signals"] or "{}")
        item["platform_metadata"] = json.loads(item["platform_metadata"] or "{}")
        return item

    def update_lead(self, lead_id, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {
            "text", "cleaned_text", "source", "author", "url", "timestamp",
            "score", "intent_level", "is_lead", "signals", "recommended_action",
            "ai_response", "status", "platform_metadata",
        }
        clean_updates = {key: value for key, value in updates.items() if key in allowed}
        if not clean_updates:
            return self.get_lead(lead_id)
        if "signals" in clean_updates and not isinstance(clean_updates["signals"], str):
            clean_updates["signals"] = json.dumps(clean_updates["signals"])
        if "platform_metadata" in clean_updates and not isinstance(clean_updates["platform_metadata"], str):
            clean_updates["platform_metadata"] = json.dumps(clean_updates["platform_metadata"])
        if "is_lead" in clean_updates:
            clean_updates["is_lead"] = 1 if clean_updates["is_lead"] else 0
        clean_updates["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in clean_updates)
        params = list(clean_updates.values()) + [lead_id]
        with self._connect() as conn:
            cursor = conn.execute(f"UPDATE leads SET {assignments} WHERE id = ?", params)
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get_lead(lead_id)

    def delete_lead(self, lead_id) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM review_queue WHERE lead_id = ?", (lead_id,))
            cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            conn.commit()
        return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            total_leads = conn.execute("SELECT COUNT(*) FROM leads WHERE is_lead = 1").fetchone()[0]
            pending_review = conn.execute("SELECT COUNT(*) FROM review_queue WHERE status = 'pending'").fetchone()[0]
            approved = conn.execute("SELECT COUNT(*) FROM review_queue WHERE status = 'approved'").fetchone()[0]
            rejected = conn.execute("SELECT COUNT(*) FROM review_queue WHERE status = 'rejected'").fetchone()[0]
            by_source = conn.execute("SELECT source, COUNT(*) as cnt FROM leads GROUP BY source").fetchall()
            by_intent = conn.execute(
                "SELECT intent_level, COUNT(*) as cnt FROM leads WHERE is_lead = 1 GROUP BY intent_level"
            ).fetchall()
        return {
            "backend": "sqlite",
            "total_items": total,
            "total_leads": total_leads,
            "pending_review": pending_review,
            "approved_actions": approved,
            "rejected_actions": rejected,
            "by_source": {row[0]: row[1] for row in by_source},
            "by_intent": {row[0]: row[1] for row in by_intent},
        }


class FirebaseCRMDatabase:
    def __init__(self):
        self.db = self._init_firestore()
        self.leads = self.db.collection(config.FIREBASE_LEADS_COLLECTION)
        self.review_queue = self.db.collection(config.FIREBASE_REVIEW_QUEUE_COLLECTION)
        logger.info(
            "Firebase CRM initialized for project %s",
            config.FIREBASE_PROJECT_ID,
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
            return firestore.client()

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
        return firestore.client()

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


class CRMDatabase:
    def __init__(self, db_path: str = None):
        backend = config.DB_BACKEND.lower()
        if backend in ("firebase", "firestore"):
            self.backend = FirebaseCRMDatabase()
        elif backend == "sqlite":
            self.backend = SQLiteCRMDatabase(db_path=db_path)
        else:
            raise ValueError("DB_BACKEND must be either 'firebase' or 'sqlite'")

    def upsert_lead(self, item: Dict[str, Any]):
        return self.backend.upsert_lead(item)

    def add_to_review_queue(self, lead_id, action: str, content: str):
        return self.backend.add_to_review_queue(lead_id, action, content)

    def get_review_queue(self, status: Optional[str] = STATUS_PENDING) -> List[Dict[str, Any]]:
        return self.backend.get_review_queue(status=status)

    def get_review_queue_item(self, queue_id) -> Optional[Dict[str, Any]]:
        return self.backend.get_review_queue_item(queue_id)

    def update_review_queue_item(self, queue_id, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.backend.update_review_queue_item(queue_id, updates)

    def delete_review_queue_item(self, queue_id) -> bool:
        return self.backend.delete_review_queue_item(queue_id)

    def approve_action(self, queue_id):
        return self.backend.approve_action(queue_id)

    def reject_action(self, queue_id):
        return self.backend.reject_action(queue_id)

    def get_leads(self, min_score: int = 0, source: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.backend.get_leads(min_score=min_score, source=source)

    def get_lead(self, lead_id) -> Optional[Dict[str, Any]]:
        return self.backend.get_lead(lead_id)

    def update_lead(self, lead_id, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.backend.update_lead(lead_id, updates)

    def delete_lead(self, lead_id) -> bool:
        return self.backend.delete_lead(lead_id)

    def get_stats(self) -> Dict[str, Any]:
        return self.backend.get_stats()
