import requests
import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote
import config

logger = logging.getLogger(__name__)


class LinkedInClient:
    def __init__(self):
        self.access_token = config.LINKEDIN_ACCESS_TOKEN
        self.org_id = config.LINKEDIN_ORGANIZATION_ID
        self.use_personal_profile = config.LINKEDIN_USE_PERSONAL_PROFILE
        self.profile_id = config.LINKEDIN_PERSONAL_PROFILE_ID
        self.profile_urn = config.LINKEDIN_PERSONAL_PROFILE_URN
        self.api_base = config.LINKEDIN_API_BASE
        self.fallback_file = config.LINKEDIN_FALLBACK_FILE
        self.author_urn = None
        self.last_error = None
        self.api_available = self._check_api_availability()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _check_api_availability(self) -> bool:
        if not self.access_token or not self.org_id:
            if self.use_personal_profile and self.access_token:
                return self._check_personal_profile_availability()
            logger.warning("LinkedIn API credentials not set. Falling back to JSON import.")
            return False
        if self.use_personal_profile:
            return self._check_personal_profile_availability()
        try:
            url = f"{self.api_base}/organizationalEntityAcls?q=roleAssignee&role=ADMINISTRATOR"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                self.author_urn = f"urn:li:organization:{self.org_id}"
                logger.info("LinkedIn API is available.")
                return True
            else:
                logger.warning(f"LinkedIn API check failed: {resp.status_code}. Using fallback.")
                return False
        except Exception as e:
            logger.warning(f"LinkedIn API not reachable: {e}. Using fallback.")
            return False

    def _normalize(self, text: str, author: str, url: str, timestamp: str, metadata: Dict) -> Dict[str, Any]:
        return {
            "text": text,
            "source": "linkedin",
            "author": author,
            "url": url,
            "timestamp": timestamp,
            "platform_metadata": metadata,
        }

    def _get_author_urn(self) -> Optional[str]:
        if self.author_urn:
            return self.author_urn
        if self.use_personal_profile:
            if self.profile_urn:
                return self.profile_urn
            if self.profile_id:
                return f"urn:li:person:{self.profile_id}"
        if self.org_id:
            return f"urn:li:organization:{self.org_id}"
        return None

    def _check_personal_profile_availability(self) -> bool:
        if not self.access_token:
            logger.warning("LinkedIn access token missing for personal profile.")
            return False
        # If profile URN or ID is provided via config, use it directly without validation
        if self.profile_urn:
            self.author_urn = self.profile_urn
            logger.info("LinkedIn personal profile URN configured directly.")
            return True
        if self.profile_id:
            self.author_urn = f"urn:li:person:{self.profile_id}"
            logger.info("LinkedIn personal profile ID configured directly.")
            return True
        # Try to fetch profile from /me endpoint as fallback
        try:
            url = f"{self.api_base}/me"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.profile_id = data.get("id", "")
                if self.profile_id:
                    self.author_urn = f"urn:li:person:{self.profile_id}"
                    logger.info("LinkedIn API is available for personal profile (fetched from /me).")
                    return True
            logger.warning(f"LinkedIn /me endpoint failed: {resp.status_code}. But using provided credentials if available.")
            return bool(self.profile_id or self.profile_urn)
        except Exception as e:
            logger.warning(f"LinkedIn profile availability check error: {e}. Will attempt posting if credentials are set.")
            return bool(self.profile_id or self.profile_urn)

    def _fetch_org_posts_api(self) -> List[Dict[str, Any]]:
        items = []
        try:
            owner = self._get_author_urn() or f"urn:li:organization:{self.org_id}"
            url = f"{self.api_base}/shares?q=owners&owners={owner}&count=20"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            for el in elements:
                activity = el.get("activity", "")
                text_val = el.get("text", {}).get("text", "") or el.get("specificContent", {}).get(
                    "com.linkedin.ugc.ShareContent", {}
                ).get("shareCommentary", {}).get("text", "")
                if not text_val:
                    continue
                created = el.get("created", {}).get("time", 0)
                ts = datetime.utcfromtimestamp(created / 1000).isoformat() if created else datetime.utcnow().isoformat()
                item = self._normalize(
                    text=text_val,
                    author=owner,
                    url=f"https://www.linkedin.com/feed/update/{activity}",
                    timestamp=ts,
                    metadata={"share_id": el.get("id"), "activity": activity, "author_urn": owner},
                )
                items.append(item)
        except Exception as e:
            logger.error(f"Error fetching LinkedIn org posts: {e}")
        return items

    def _fetch_ugc_posts_api(self) -> List[Dict[str, Any]]:
        items = []
        try:
            author_urn = self._get_author_urn() or f"urn:li:organization:{self.org_id}"
            encoded_author = quote(author_urn, safe="")
            url = f"{self.api_base}/ugcPosts?q=authors&authors=List({encoded_author})&count=20"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            for el in elements:
                text_val = (
                    el.get("specificContent", {})
                    .get("com.linkedin.ugc.ShareContent", {})
                    .get("shareCommentary", {})
                    .get("text", "")
                )
                if not text_val:
                    continue
                created = el.get("created", {}).get("time", 0)
                ts = datetime.utcfromtimestamp(created / 1000).isoformat() if created else datetime.utcnow().isoformat()
                post_id = el.get("id", "")
                item = self._normalize(
                    text=text_val,
                    author=author_urn,
                    url=f"https://www.linkedin.com/feed/update/{post_id}",
                    timestamp=ts,
                    metadata={"ugc_post_id": post_id, "author_urn": author_urn},
                )
                items.append(item)
        except Exception as e:
            logger.error(f"Error fetching LinkedIn UGC posts: {e}")
        return items

    def _load_fallback(self) -> List[Dict[str, Any]]:
        items = []
        if not os.path.exists(self.fallback_file):
            logger.warning(f"LinkedIn fallback file not found: {self.fallback_file}")
            return items
        try:
            with open(self.fallback_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                entries = raw
            elif isinstance(raw, dict):
                entries = raw.get("posts", raw.get("data", raw.get("elements", [])))
            else:
                entries = []
            for entry in entries:
                text = entry.get("text", entry.get("content", entry.get("body", "")))
                if not text:
                    continue
                item = self._normalize(
                    text=text,
                    author=entry.get("author", entry.get("author_name", "unknown")),
                    url=entry.get("url", entry.get("link", "")),
                    timestamp=entry.get("timestamp", entry.get("date", datetime.utcnow().isoformat())),
                    metadata={"source_file": self.fallback_file, "raw": entry},
                )
                items.append(item)
            logger.info(f"LinkedIn fallback: loaded {len(items)} items from {self.fallback_file}")
        except Exception as e:
            logger.error(f"Error loading LinkedIn fallback file: {e}")
        return items

    def fetch_posts(self) -> List[Dict[str, Any]]:
        if self.api_available:
            items = self._fetch_ugc_posts_api()
            if not items:
                items = self._fetch_org_posts_api()
            if items:
                logger.info(f"LinkedIn API: fetched {len(items)} items")
                return items
        # Always try fallback if API failed or not available
        fallback_items = self._load_fallback()
        if fallback_items:
            return fallback_items
        return []

    def prepare_post_payload(self, text: str) -> Optional[Dict[str, Any]]:
        author_urn = self._get_author_urn()
        if not author_urn:
            logger.warning("No author URN configured. Post payload cannot be prepared.")
            return None
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        return {"status": "ready_for_human_approval", "payload": payload}

    def prepare_comment_payload(self, ugc_post_id: str, text: str) -> Optional[Dict[str, Any]]:
        actor = self._get_author_urn()
        if not self.api_available or not actor:
            return {
                "status": "draft_only",
                "text": text,
                "note": "API unavailable. Comment manually on LinkedIn.",
            }
        payload = {
            "actor": actor,
            "message": {"text": text},
            "object": ugc_post_id,
        }
        return {"status": "ready_for_human_approval", "payload": payload}

    def post_share(self, text: str) -> Optional[str]:
        self.last_error = None
        author_urn = self._get_author_urn()
        if not author_urn:
            logger.warning("No author URN. Cannot post.")
            self.last_error = {"message": "No author URN configured"}
            return None
        url = f"{self.api_base}/ugcPosts"
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            try:
                body = resp.json() if resp.content else {}
            except ValueError:
                body = {}
            share_id = body.get("id") or resp.headers.get("x-restli-id")
            logger.info(f"Posted share successfully: {share_id}")
            return share_id or "posted"
        except requests.HTTPError as e:
            response = e.response
            self.last_error = {
                "status_code": response.status_code if response is not None else None,
                "response": response.text if response is not None else str(e),
            }
            logger.error(f"Failed to post share: {self.last_error}")
            return None
        except Exception as e:
            self.last_error = {"message": str(e)}
            logger.error(f"Failed to post share: {e}")
            return None

    def post_comment(self, ugc_post_id: str, text: str) -> Optional[str]:
        actor = self._get_author_urn()
        if not actor:
            logger.warning("No author URN. Cannot comment.")
            return None
        url = f"{self.api_base}/socialActions/{ugc_post_id}/comments"
        payload = {
            "actor": actor,
            "message": {"text": text},
        }
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            comment_id = resp.json().get("id") or resp.headers.get("x-restli-id")
            logger.info(f"Posted comment successfully on {ugc_post_id}: {comment_id}")
            return comment_id or "posted"
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")
            return None

    def like_post(self, ugc_post_id: str) -> bool:
        actor = self._get_author_urn()
        if not actor:
            logger.warning("No author URN. Cannot like.")
            return False
        url = f"{self.api_base}/socialActions/{ugc_post_id}/likes"
        payload = {
            "actor": actor,
        }
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            logger.info(f"Liked post {ugc_post_id} successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to like post: {e}")
            return False

    def search_posts(self, keywords: List[str], count: int = 20) -> List[Dict[str, Any]]:
        author_urn = self._get_author_urn()
        if not author_urn:
            logger.warning("No author URN configured. Cannot search.")
            return []
        query = " ".join(keywords)
        url = f"{self.api_base}/search?q=keywords&keywords={query}&count={count}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            items = []
            for el in elements:
                # Assuming structure similar to posts
                text_val = el.get("text", {}).get("text", "") or el.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {}).get("shareCommentary", {}).get("text", "")
                if not text_val:
                    continue
                author = el.get("author", "unknown")
                post_id = el.get("id", "")
                url_link = f"https://www.linkedin.com/feed/update/{post_id}"
                ts = datetime.utcnow().isoformat()  # Approximate
                item = self._normalize(
                    text=text_val,
                    author=author,
                    url=url_link,
                    timestamp=ts,
                    metadata={"ugc_post_id": post_id},
                )
                items.append(item)
            logger.info(f"Searched posts: found {len(items)} items for keywords {keywords}")
            return items
        except Exception as e:
            logger.error(f"Failed to search posts: {e}")
            return []

    def fetch_comments(self, ugc_post_id: str) -> List[Dict[str, Any]]:
        if not self.api_available:
            return []
        url = f"{self.api_base}/socialActions/{ugc_post_id}/comments"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            comments = []
            for el in elements:
                comment_text = el.get("message", {}).get("text", "")
                author = el.get("actor", "unknown")
                ts = el.get("created", {}).get("time", 0)
                timestamp = datetime.utcfromtimestamp(ts / 1000).isoformat() if ts else datetime.utcnow().isoformat()
                comments.append({
                    "text": comment_text,
                    "author": author,
                    "timestamp": timestamp,
                    "comment_id": el.get("id"),
                })
            return comments
        except Exception as e:
            logger.error(f"Failed to fetch comments for {ugc_post_id}: {e}")
            return []
        if not self.api_available:
            return []
        url = f"{self.api_base}/socialActions/{ugc_post_id}/comments"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            comments = []
            for el in elements:
                comment_text = el.get("message", {}).get("text", "")
                author = el.get("actor", "unknown")
                ts = el.get("created", {}).get("time", 0)
                timestamp = datetime.utcfromtimestamp(ts / 1000).isoformat() if ts else datetime.utcnow().isoformat()
                comments.append({
                    "text": comment_text,
                    "author": author,
                    "timestamp": timestamp,
                    "comment_id": el.get("id"),
                })
            return comments
        except Exception as e:
            logger.error(f"Failed to fetch comments for {ugc_post_id}: {e}")
            return []

    def fetch_likes(self, ugc_post_id: str) -> int:
        if not self.api_available:
            return 0
        url = f"{self.api_base}/socialActions/{ugc_post_id}/likes?count=1"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("paging", {}).get("total", 0)
        except Exception as e:
            logger.error(f"Failed to fetch likes for {ugc_post_id}: {e}")
            return 0
