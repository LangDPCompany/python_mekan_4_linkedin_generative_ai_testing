import logging
import os
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class GeminiEngine:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.timeout = int(os.getenv("GEMINI_TIMEOUT", "10"))
        self._active_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def _call(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set.")
            return None
        url = f"{self.base_url}/models/{self._active_model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {"maxOutputTokens": 300},
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            text = "".join(part.get("text", "") for part in parts)
            return text.strip()
        except requests.exceptions.ConnectionError:
            logger.error("Gemini API not reachable.")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"Gemini API HTTP {e.response.status_code}: {e.response.text[:300]}")
            return None
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return None

    def generate_content(self, item: Dict[str, Any]) -> Optional[str]:
        action = item.get("recommended_action", "no_action")
        if action == "no_action":
            return None

        prompt_map = {
            "generate_reply": self._build_reddit_reply_prompt,
            "generate_linkedin_post": self._build_linkedin_post_prompt,
            "generate_insight_comment": self._build_insight_comment_prompt,
        }
        builder = prompt_map.get(action)
        if not builder:
            return None

        prompt = builder(item)
        result = self._call(prompt)
        if result:
            logger.info(f"Generated content | action={action}")
        else:
            logger.warning(f"AI generation returned nothing | action={action}")
        return result

    def generate_linkedin_post_from_topic(self, topic: str) -> Optional[str]:
        prompt = (
            "Write a professional LinkedIn post.\n\n"
            f"Topic:\n---\n{topic}\n---\n\n"
            "Rules:\n"
            "- Genuine insight, not a sales pitch\n"
            "- Professional expert tone\n"
            "- Under 200 words\n"
            "- End with a thoughtful question\n\n"
            "LinkedIn Post:"
        )
        return self._call(prompt)

    def _build_reddit_reply_prompt(self, item: Dict[str, Any]) -> str:
        signals = item.get("signals", {})
        detected = [k for k, v in signals.items() if v]
        return (
            "You are a helpful, expert business advisor replying on Reddit.\n\n"
            f"Post:\n---\n{item.get('cleaned_text') or item.get('text', '')}\n---\n\n"
            f"Detected themes: {', '.join(detected) or 'general business'}\n\n"
            "Rules:\n"
            "- Genuinely helpful, expert tone\n"
            "- NO selling, NO product mentions\n"
            "- Actionable advice only\n"
            "- Under 150 words\n"
            "- Sound human\n\n"
            "Reply:"
        )

    def _build_linkedin_post_prompt(self, item: Dict[str, Any]) -> str:
        signals = item.get("signals", {})
        detected = [k for k, v in signals.items() if v]
        return (
            "You are a thought leader writing a LinkedIn Company Page post.\n\n"
            f"Inspiration:\n---\n{item.get('cleaned_text') or item.get('text', '')}\n---\n\n"
            f"Themes: {', '.join(detected) or 'business efficiency'}\n\n"
            "Rules:\n"
            "- Genuine insight, NOT a sales pitch\n"
            "- Professional expert tone\n"
            "- End with a thought-provoking question\n"
            "- Under 200 words\n"
            "- Do NOT reference the source text directly\n\n"
            "LinkedIn Post:"
        )

    def _build_insight_comment_prompt(self, item: Dict[str, Any]) -> str:
        return (
            "You are a knowledgeable business advisor leaving a LinkedIn comment.\n\n"
            f"Post context:\n---\n{item.get('cleaned_text') or item.get('text', '')}\n---\n\n"
            "Rules:\n"
            "- Adds real value\n"
            "- No promotion or product mention\n"
            "- Under 80 words\n"
            "- Natural, human tone\n\n"
            "Comment:"
        )

    def is_available(self) -> bool:
        """
        Check if the GeminiEngine is available by verifying the API key and connectivity.
        Returns:
            True if the engine is available, False otherwise.
        """
        if not self.api_key:
            logger.warning("Gemini unavailable: GEMINI_API_KEY is not set.")
            return False
        try:
            url = f"{self.base_url}/models/{self._active_model}"
            headers = {"x-goog-api-key": self.api_key}
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to check GeminiEngine availability: {e}")
            return False
