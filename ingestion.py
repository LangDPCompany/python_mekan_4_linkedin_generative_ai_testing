import logging
from typing import List, Dict, Any
from reddit_client import RedditClient
from linkedin_client import LinkedInClient

logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    def __init__(self):
        self.reddit_client = RedditClient()
        self.linkedin_client = LinkedInClient()

    def ingest_reddit(self) -> List[Dict[str, Any]]:
        logger.info("Starting Reddit ingestion...")
        try:
            items = self.reddit_client.fetch_posts()
            logger.info(f"Reddit ingestion complete: {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"Reddit ingestion failed: {e}")
            return []

    def ingest_linkedin(self) -> List[Dict[str, Any]]:
        logger.info("Starting LinkedIn ingestion...")
        try:
            items = self.linkedin_client.fetch_posts()
            logger.info(f"LinkedIn ingestion complete: {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"LinkedIn ingestion failed: {e}")
            return []

    def ingest_all(self) -> List[Dict[str, Any]]:
        all_items = []
        reddit_items = self.ingest_reddit()
        all_items.extend(reddit_items)
        linkedin_items = self.ingest_linkedin()
        all_items.extend(linkedin_items)
        logger.info(f"Total ingested: {len(all_items)} items (Reddit: {len(reddit_items)}, LinkedIn: {len(linkedin_items)})")
        return all_items