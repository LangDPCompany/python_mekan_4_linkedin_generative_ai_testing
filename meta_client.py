import logging
from typing import Any, Dict, List, Optional

import requests

import config

logger = logging.getLogger(__name__)


class MetaGraphClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.api_base = config.META_GRAPH_API_BASE.rstrip("/")
        self.version = config.META_GRAPH_VERSION.strip("/")
        self.timeout = 30
        self.last_error = None

    def _url(self, path: str) -> str:
        return f"{self.api_base}/{self.version}/{path.lstrip('/')}"

    def _params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = {"access_token": self.access_token}
        if extra:
            params.update(extra)
        return params

    def _request(self, method: str, path: str, **kwargs) -> Optional[Dict[str, Any]]:
        self.last_error = None
        try:
            resp = requests.request(method, self._url(path), timeout=self.timeout, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except requests.HTTPError as e:
            response = e.response
            self.last_error = {
                "status_code": response.status_code if response is not None else None,
                "response": response.text if response is not None else str(e),
            }
            logger.error("Meta Graph API request failed: %s", self.last_error)
            return None
        except Exception as e:
            self.last_error = {"message": str(e)}
            logger.error("Meta Graph API request failed: %s", e)
            return None

    @property
    def api_available(self) -> bool:
        return bool(self.access_token)


class FacebookClient(MetaGraphClient):
    def __init__(self):
        super().__init__(config.FACEBOOK_PAGE_ACCESS_TOKEN)
        self.page_id = config.FACEBOOK_PAGE_ID

    @property
    def api_available(self) -> bool:
        return bool(self.access_token and self.page_id)

    def prepare_post_payload(self, message: str, link: Optional[str] = None) -> Dict[str, Any]:
        payload = {"message": message}
        if link:
            payload["link"] = link
        page_id = self.page_id or "<FACEBOOK_PAGE_ID>"
        return {"endpoint": f"/{page_id}/feed", "payload": payload}

    def prepare_photo_payload(self, image_url: str, caption: str = "") -> Dict[str, Any]:
        page_id = self.page_id or "<FACEBOOK_PAGE_ID>"
        return {"endpoint": f"/{page_id}/photos", "payload": {"url": image_url, "caption": caption}}

    def get_page(self) -> Optional[Dict[str, Any]]:
        if not self.api_available:
            self.last_error = {"message": "FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN is missing"}
            return None
        return self._request("GET", self.page_id, params=self._params({"fields": "id,name,link,followers_count"}))

    def fetch_posts(self, limit: int = 25) -> List[Dict[str, Any]]:
        if not self.api_available:
            self.last_error = {"message": "FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN is missing"}
            return []
        data = self._request(
            "GET",
            f"{self.page_id}/posts",
            params=self._params({"limit": limit, "fields": "id,message,created_time,permalink_url"}),
        )
        return data.get("data", []) if data else []

    def post_feed(self, message: str, link: Optional[str] = None) -> Optional[str]:
        payload = self.prepare_post_payload(message, link)["payload"]
        data = self._request("POST", f"{self.page_id}/feed", data=self._params(payload))
        return data.get("id") if data else None

    def post_photo(self, image_url: str, caption: str = "") -> Optional[str]:
        payload = self.prepare_photo_payload(image_url, caption)["payload"]
        data = self._request("POST", f"{self.page_id}/photos", data=self._params(payload))
        return data.get("id") or data.get("post_id") if data else None

    def post_comment(self, object_id: str, message: str) -> Optional[str]:
        data = self._request("POST", f"{object_id}/comments", data=self._params({"message": message}))
        return data.get("id") if data else None

    def react(self, object_id: str, reaction_type: str = "LIKE") -> bool:
        data = self._request("POST", f"{object_id}/reactions", data=self._params({"type": reaction_type}))
        return bool(data and data.get("success", True))

    def fetch_comments(self, object_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            f"{object_id}/comments",
            params=self._params({"limit": limit, "fields": "id,message,created_time,from"}),
        )
        return data.get("data", []) if data else []

    def fetch_reactions(self, object_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            f"{object_id}/reactions",
            params=self._params({"limit": limit, "fields": "id,name,type"}),
        )
        return data.get("data", []) if data else []


class InstagramClient(MetaGraphClient):
    def __init__(self):
        super().__init__(config.INSTAGRAM_ACCESS_TOKEN)
        self.ig_user_id = config.INSTAGRAM_BUSINESS_ACCOUNT_ID

    @property
    def api_available(self) -> bool:
        return bool(self.access_token and self.ig_user_id)

    def prepare_media_payload(
        self,
        caption: str = "",
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {"caption": caption}
        if image_url:
            payload["image_url"] = image_url
        if video_url:
            payload["video_url"] = video_url
        if media_type:
            payload["media_type"] = media_type
        ig_user_id = self.ig_user_id or "<INSTAGRAM_BUSINESS_ACCOUNT_ID>"
        return {"endpoint": f"/{ig_user_id}/media", "payload": payload}

    def get_profile(self) -> Optional[Dict[str, Any]]:
        if not self.api_available:
            self.last_error = {"message": "INSTAGRAM_BUSINESS_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN is missing"}
            return None
        return self._request(
            "GET",
            self.ig_user_id,
            params=self._params({"fields": "id,username,name,profile_picture_url,followers_count,media_count"}),
        )

    def fetch_media(self, limit: int = 25) -> List[Dict[str, Any]]:
        if not self.api_available:
            self.last_error = {"message": "INSTAGRAM_BUSINESS_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN is missing"}
            return []
        data = self._request(
            "GET",
            f"{self.ig_user_id}/media",
            params=self._params({"limit": limit, "fields": "id,caption,media_type,media_url,permalink,timestamp"}),
        )
        return data.get("data", []) if data else []

    def create_media_container(
        self,
        caption: str = "",
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Optional[str]:
        payload = self.prepare_media_payload(caption, image_url, video_url, media_type)["payload"]
        data = self._request("POST", f"{self.ig_user_id}/media", data=self._params(payload))
        return data.get("id") if data else None

    def publish_media(self, creation_id: str) -> Optional[str]:
        data = self._request("POST", f"{self.ig_user_id}/media_publish", data=self._params({"creation_id": creation_id}))
        return data.get("id") if data else None

    def publish_image(self, image_url: str, caption: str = "") -> Optional[Dict[str, str]]:
        creation_id = self.create_media_container(caption=caption, image_url=image_url)
        if not creation_id:
            return None
        media_id = self.publish_media(creation_id)
        if not media_id:
            return None
        return {"creation_id": creation_id, "media_id": media_id}

    def publish_reel(self, video_url: str, caption: str = "") -> Optional[Dict[str, str]]:
        creation_id = self.create_media_container(caption=caption, video_url=video_url, media_type="REELS")
        if not creation_id:
            return None
        media_id = self.publish_media(creation_id)
        if not media_id:
            return None
        return {"creation_id": creation_id, "media_id": media_id}

    def post_comment(self, media_id: str, message: str) -> Optional[str]:
        data = self._request("POST", f"{media_id}/comments", data=self._params({"message": message}))
        return data.get("id") if data else None

    def fetch_comments(self, media_id: str, limit: int = 25) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            f"{media_id}/comments",
            params=self._params({"limit": limit, "fields": "id,text,timestamp,username"}),
        )
        return data.get("data", []) if data else []
