import praw
import logging
from datetime import datetime
from typing import List, Dict, Any
import config

logger = logging.getLogger(__name__)


class RedditClient:
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
        )
        self.subreddits = config.REDDIT_SUBREDDITS
        self.post_limit = config.REDDIT_POST_LIMIT

    def _normalize(self, text: str, author: str, url: str, timestamp: float, metadata: Dict) -> Dict[str, Any]:
        return {
            "text": text,
            "source": "reddit",
            "author": str(author) if author else "[deleted]",
            "url": url,
            "timestamp": datetime.utcfromtimestamp(timestamp).isoformat(),
            "platform_metadata": metadata,
        }

    def fetch_posts(self) -> List[Dict[str, Any]]:
        items = []
        for subreddit_name in self.subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name.strip())
                for post in subreddit.hot(limit=self.post_limit):
                    combined_text = f"{post.title} {post.selftext}".strip()
                    if not combined_text:
                        continue
                    item = self._normalize(
                        text=combined_text,
                        author=post.author,
                        url=f"https://reddit.com{post.permalink}",
                        timestamp=post.created_utc,
                        metadata={
                            "post_id": post.id,
                            "subreddit": subreddit_name,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "upvote_ratio": post.upvote_ratio,
                            "flair": post.link_flair_text,
                        },
                    )
                    items.append(item)

                    post.comments.replace_more(limit=0)
                    for comment in post.comments.list()[:10]:
                        if not comment.body or comment.body in ("[deleted]", "[removed]"):
                            continue
                        c_item = self._normalize(
                            text=comment.body,
                            author=comment.author,
                            url=f"https://reddit.com{post.permalink}",
                            timestamp=comment.created_utc,
                            metadata={
                                "comment_id": comment.id,
                                "post_id": post.id,
                                "subreddit": subreddit_name,
                                "score": comment.score,
                                "is_comment": True,
                            },
                        )
                        items.append(c_item)

            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit_name}: {e}")
                continue

        logger.info(f"Reddit: fetched {len(items)} items from {len(self.subreddits)} subreddits")
        return items