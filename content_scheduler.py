import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from ai_engine import GeminiEngine
from linkedin_client import LinkedInClient
import config

logger = logging.getLogger(__name__)

class ContentScheduler:
    def __init__(self):
        self.ai_engine = GeminiEngine()
        self.linkedin_client = LinkedInClient()
        self.scheduler = BlockingScheduler()

    def generate_article(self):
        if not self.ai_engine.is_available():
            logger.warning("Gemini engine not available. Skipping article generation.")
            return
        prompt = f"Write a professional LinkedIn article about {config.LINKEDIN_DIRECTIONS[0]}. Include lead generation call to action: {config.LEAD_CTA_TEXT}"
        article = self.ai_engine._call(prompt)
        if article:
            # For articles, LinkedIn API might require different endpoint, but for simplicity, post as share
            success = self.linkedin_client.post_share(article)
            if success:
                logger.info("Article posted successfully.")
            else:
                logger.error("Failed to post article.")

    def generate_post(self):
        if not self.ai_engine.is_available():
            logger.warning("AI engine not available. Skipping post generation.")
            return
        prompt = f"Write a short LinkedIn post about {config.LINKEDIN_DIRECTIONS[0]}. End with a question to engage and {config.LEAD_CTA_TEXT}"
        post = self.ai_engine._call(prompt)
        if post:
            success = self.linkedin_client.post_share(post)
            if success:
                logger.info("Post published successfully.")
            else:
                logger.error("Failed to publish post.")

    def engage_with_posts(self):
        posts = self.linkedin_client.search_posts(config.LINKEDIN_TAGS)
        for post in posts:
            if not self.ai_engine.is_available():
                continue
            prompt = f"Write a helpful comment on this LinkedIn post to attract leads: '{post['text']}'. Include {config.LEAD_CTA_TEXT}"
            comment = self.ai_engine._call(prompt)
            if comment:
                ugc_post_id = post['platform_metadata'].get('ugc_post_id')
                if ugc_post_id:
                    success = self.linkedin_client.post_comment(ugc_post_id, comment)
                    if success:
                        logger.info(f"Commented on post {ugc_post_id}")
                    # Optionally like
                    self.linkedin_client.like_post(ugc_post_id)

                    # Optionally like
                    self.linkedin_client.like_post(ugc_post_id)

    def handle_feedback(self):
        own_posts = self.linkedin_client.fetch_posts()  # Fetch own posts
        for post in own_posts:
            ugc_post_id = post['platform_metadata'].get('ugc_post_id') or post['platform_metadata'].get('share_id')
            if not ugc_post_id:
                continue
            comments = self.linkedin_client.fetch_comments(ugc_post_id)
            for comment in comments:
                # Check if already replied (simple check, assume not)
                if not self.ai_engine.is_available():
                    continue
                prompt = f"Reply to this comment on your LinkedIn post: '{comment['text']}'. Be helpful and include {config.LEAD_CTA_TEXT} if appropriate."
                reply = self.ai_engine._call(prompt)
                if reply:
                    success = self.linkedin_client.post_comment(ugc_post_id, reply)
                    if success:
                        logger.info(f"Replied to comment on {ugc_post_id}")

    def setup_schedules(self):
        # Article schedule
        if config.ARTICLE_SCHEDULE == "daily":
            self.scheduler.add_job(self.generate_article, CronTrigger(hour=9))  # 9 AM daily
        elif config.ARTICLE_SCHEDULE == "weekly":
            self.scheduler.add_job(self.generate_article, CronTrigger(day_of_week='mon', hour=9))
        # Post schedule
        if config.POST_SCHEDULE == "daily":
            self.scheduler.add_job(self.generate_post, CronTrigger(hour=12))  # Noon daily
        # Engagement
        self.scheduler.add_job(self.engage_with_posts, 'interval', seconds=config.ENGAGEMENT_INTERVAL)
        # Feedback
        self.scheduler.add_job(self.handle_feedback, 'interval', seconds=config.ENGAGEMENT_INTERVAL * 2)  # Less frequent

    def start(self):
        self.setup_schedules()
        logger.info("Content scheduler started.")
        self.scheduler.start()