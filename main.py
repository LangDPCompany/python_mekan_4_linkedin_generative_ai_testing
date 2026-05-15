import logging
import json
import os
import sys
from typing import List, Dict, Any, Optional
from flask import Flask, request, jsonify
import config
from ingestion import IngestionOrchestrator
from ai_engine import GeminiEngine
from crm import CRMDatabase, STATUS_PENDING
from linkedin_client import LinkedInClient
from meta_client import FacebookClient, InstagramClient
from content_scheduler import ContentScheduler

# Initialize Flask app for API endpoints
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log"),
    ],
)
logger = logging.getLogger(__name__)


def json_error(message: str, status_code: int, **extra):
    payload = {"success": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status_code


def get_json_body():
    return request.get_json(silent=True) or {}


def print_separator(title: str = ""):
    line = "=" * 60
    if title:
        print(f"\n{line}\n  {title}\n{line}")
    else:
        print(line)


def run_pipeline(sources: Optional[List[str]] = None, dry_run: bool = False):
    print_separator("LEAD GENERATION PIPELINE STARTING")
    logger.info(f"Approval mode : {config.APPROVAL_MODE}")
    logger.info(f"Score threshold: {config.LEAD_SCORE_THRESHOLD}")
    logger.info(f"Dry run       : {dry_run}")

    # ── 1. INGESTION ──────────────────────────────────────────────────
    orchestrator = IngestionOrchestrator()
    if not sources or set(sources) == {"reddit", "linkedin"}:
        all_items = orchestrator.ingest_all()
    elif "reddit" in sources:
        all_items = orchestrator.ingest_reddit()
    elif "linkedin" in sources:
        all_items = orchestrator.ingest_linkedin()
    else:
        all_items = orchestrator.ingest_all()

    if not all_items:
        logger.warning("No items ingested. Check your credentials / fallback file.")
        return

    # Prepare LinkedIn client for auto-publish mode. Dry runs must never publish.
    linkedin_client = LinkedInClient() if config.APPROVAL_MODE == "AUTO_POST" and not dry_run else None

    # ── 2. PROCESSING & SCORING ───────────────────────────────────────
    print_separator("PROCESSING & SCORING")
    from processor import process_batch

    processed_items = process_batch(all_items)

    leads     = [i for i in processed_items if i.get("is_lead")]
    non_leads = [i for i in processed_items if not i.get("is_lead")]
    actionable = [i for i in leads if i.get("recommended_action") != "no_action"]

    logger.info(f"Total items : {len(processed_items)}")
    logger.info(f"Leads found : {len(leads)}  |  Actionable: {len(actionable)}")
    logger.info(f"Non-leads   : {len(non_leads)}")

    # Show score breakdown for every item so nothing is silently dropped
    print("\n--- SCORE BREAKDOWN ---")
    for item in processed_items:
        marker = "✓ LEAD" if item.get("is_lead") else "  skip"
        print(
            f"  [{marker}] score={item['score']:3d}  intent={item['intent_level']:6s}  "
            f"action={item.get('recommended_action','no_action'):28s}  "
            f"source={item['source']}  text={item.get('cleaned_text','')[:60]}..."
        )

    # ── 3. AI CONTENT GENERATION ─────────────────────────────────────
    print_separator("AI CONTENT GENERATION")

    if dry_run:
        logger.info("DRY RUN: skipping AI generation, using placeholder text.")
        for item in actionable:
            item["ai_response"] = (
                f"[DRY RUN PLACEHOLDER]\n"
                f"Action : {item['recommended_action']}\n"
                f"Source : {item['source']}\n"
                f"Score  : {item['score']}\n"
                f"Signals: {[k for k,v in item.get('signals',{}).items() if v]}"
            )
    else:
        ai_engine = GeminiEngine()
        if not ai_engine.is_available():
            logger.warning(
                "Gemini has no model available. "
                "Items will be queued WITHOUT AI content (you can edit them manually).\n"
                "To fix: `gemini pull llama3`  then re-run."
            )
        for item in actionable:
            try:
                response = ai_engine.generate_content(item) if ai_engine.is_available() else None
                # Queue item even if AI failed — human can write content manually
                item["ai_response"] = response or (
                    f"[AI UNAVAILABLE — write content manually]\n"
                    f"Action : {item['recommended_action']}\n"
                    f"Source : {item['source']}\n"
                    f"Score  : {item['score']}\n"
                    f"Signals: {[k for k,v in item.get('signals',{}).items() if v]}\n"
                    f"Text   : {item.get('cleaned_text','')[:300]}"
                )
            except Exception as e:
                logger.error(f"AI generation error: {e}")
                item["ai_response"] = "[AI ERROR — write content manually]"

    # ── 4. CRM STORAGE ────────────────────────────────────────────────
    print_separator("CRM STORAGE")
    crm = CRMDatabase()

    for item in processed_items:
        try:
            lead_id = crm.upsert_lead(item)
            # Add to review queue if actionable (even without AI content)
            if item.get("is_lead") and item.get("recommended_action") != "no_action":
                content = item.get("ai_response") or "[No AI content — write manually]"
                queue_id = crm.add_to_review_queue(
                    lead_id=lead_id,
                    action=item["recommended_action"],
                    content=content,
                )
                content_is_publishable = bool(item.get("ai_response")) and not str(item["ai_response"]).startswith("[")
                if config.APPROVAL_MODE == "AUTO_POST" and not dry_run and linkedin_client and linkedin_client.api_available:
                    if item["recommended_action"] == "generate_linkedin_post" and content_is_publishable:
                        if linkedin_client.post_share(item["ai_response"]):
                            crm.approve_action(queue_id)
                    elif item["recommended_action"] == "generate_insight_comment" and content_is_publishable:
                        ugc_post_id = item.get("platform_metadata", {}).get("ugc_post_id") or item.get("platform_metadata", {}).get("share_id")
                        if ugc_post_id and linkedin_client.post_comment(ugc_post_id, item["ai_response"]):
                            crm.approve_action(queue_id)
                    elif item["recommended_action"] == "generate_reply" and content_is_publishable:
                        # Reddit replies not auto-posted by this pipeline
                        pass
        except Exception as e:
            logger.error(f"CRM storage error: {e}")

    # ── 5. REVIEW QUEUE ───────────────────────────────────────────────
    print_separator("READY_FOR_REVIEW QUEUE")
    review_queue = crm.get_review_queue()
    logger.info(f"Items pending human review: {len(review_queue)}")

    if review_queue:
        for i, q in enumerate(review_queue, 1):
            print(f"\n{'─'*55}")
            print(f"  [{i}] Queue ID : {q['id']}")
            print(f"      Source   : {q['source'].upper()}")
            print(f"      Score    : {q['score']}  |  Intent: {q['intent_level'].upper()}")
            print(f"      Action   : {q['action']}")
            print(f"      Author   : {q['author']}")
            print(f"      URL      : {q['url']}")
            print(f"      Content  :")
            for line in str(q.get("content", "")).splitlines():
                print(f"        {line}")
    else:
        print("  (empty)")

    # ── 6. SUMMARY ────────────────────────────────────────────────────
    print_separator("PIPELINE SUMMARY")
    stats = crm.get_stats()
    ai_generated = sum(
        1 for i in actionable
        if i.get("ai_response") and not i["ai_response"].startswith("[")
    )
    print(f"  Items processed    : {len(processed_items)}")
    print(f"  Leads identified   : {len(leads)}")
    print(f"  Actionable leads   : {len(actionable)}")
    print(f"  AI responses       : {ai_generated}")
    print(f"  Pending review     : {stats['pending_review']}")
    print(f"  CRM total          : {stats['total_items']}")
    print(f"  By source          : {stats['by_source']}")
    print(f"  By intent          : {stats['by_intent']}")
    print()
    print("  APPROVAL MODE : ", config.APPROVAL_MODE)
    if dry_run:
        print("  Dry run enabled. Nothing was auto-posted.")
    elif config.APPROVAL_MODE == "AUTO_POST":
        print("  Auto-posting enabled. LinkedIn actions were attempted automatically.")
    else:
        print("  Nothing auto-posted. Human review required.")
    print_separator()

    return {
        "processed": len(processed_items),
        "leads": len(leads),
        "review_queue_size": len(review_queue),
        "stats": stats,
    }


def show_review_queue():
    crm = CRMDatabase()
    queue = crm.get_review_queue()
    print_separator("CURRENT REVIEW QUEUE")
    if not queue:
        print("  No items pending review.")
        return
    for q in queue:
        print(f"\nQueue ID : {q['id']}")
        print(f"  Source : {q['source']}  |  Score: {q['score']}")
        print(f"  Action : {q['action']}")
        print(f"  URL    : {q['url']}")
        print(f"  Content:")
        for line in str(q.get("content", "")).splitlines():
            print(f"    {line}")


def show_stats():
    crm = CRMDatabase()
    print_separator("CRM STATISTICS")
    print(json.dumps(crm.get_stats(), indent=2))


def approve_item(queue_id: int):
    CRMDatabase().approve_action(queue_id)
    print(f"Queue item {queue_id} → APPROVED. Ready for manual posting.")


def reject_item(queue_id: int):
    CRMDatabase().reject_action(queue_id)
    print(f"Queue item {queue_id} → REJECTED.")


# ═════════════════════════════════════════════════════════════════════════
#  API ENDPOINTS FOR LINKEDIN POSTING
# ═════════════════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
def api_index():
    return jsonify({
        "status": "ok",
        "message": "Lead Generation API is running",
        "endpoints": {
            "health": "GET /api/health",
            "linkedin_post": "POST /api/linkedin/post",
            "linkedin_comment": "POST /api/linkedin/comment",
            "linkedin_like": "POST /api/linkedin/like",
            "linkedin_comments_read": "GET /api/linkedin/comments/<post_id>",
            "linkedin_likes_read": "GET /api/linkedin/likes/<post_id>",
            "facebook_page": "GET /api/facebook/page",
            "facebook_posts": "GET /api/facebook/posts",
            "facebook_post": "POST /api/facebook/post",
            "facebook_photo": "POST /api/facebook/photo",
            "facebook_comment": "POST /api/facebook/comment",
            "facebook_react": "POST /api/facebook/react",
            "instagram_profile": "GET /api/instagram/profile",
            "instagram_media": "GET /api/instagram/media",
            "instagram_image": "POST /api/instagram/image",
            "instagram_reel": "POST /api/instagram/reel",
            "instagram_comment": "POST /api/instagram/comment",
            "firebase_leads": "GET /api/firebase/leads",
            "firebase_lead_detail": "GET|PATCH|DELETE /api/firebase/leads/<lead_id>",
            "firebase_posts": "GET /api/firebase/posts",
            "firebase_post_detail": "GET|PATCH|DELETE /api/firebase/posts/<post_id>",
            "generate_linkedin_post": "POST /api/llm/generate-linkedin-post",
        },
    }), 200


@app.route("/api/linkedin/post", methods=["POST"])
def api_linkedin_post_share():
    """
    API endpoint to post content on LinkedIn.
    
    Request body:
    {
        "content": "Your post content here"
    }
    
    Response:
    {
        "success": true,
        "share_urn": "urn:li:share:...",
        "message": "Post shared successfully"
    }
    """
    try:
        data = get_json_body()
        if not data or "content" not in data:
            return json_error("Missing 'content' field", 400)
        
        content = data.get("content")
        if not content or len(content.strip()) == 0:
            return json_error("Content cannot be empty", 400)
        
        linkedin_client = LinkedInClient()
        dry_run = bool(data.get("dry_run", False))
        if dry_run:
            prepared = linkedin_client.prepare_post_payload(content)
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Post payload prepared. Nothing was published.",
                "payload": prepared,
            }), 200
        if not linkedin_client.api_available:
            return json_error("LinkedIn API not available. Check credentials.", 503)
        
        share_urn = linkedin_client.post_share(content)
        if share_urn:
            firebase_record = CRMDatabase().add_linkedin_post_record(
                content=content,
                status="posted",
                share_urn=share_urn,
            )
            return jsonify({
                "success": True,
                "share_urn": share_urn,
                "firebase_record": firebase_record,
                "message": "Post shared successfully on LinkedIn"
            }), 201
        else:
            firebase_record = CRMDatabase().add_linkedin_post_record(
                content=content,
                status="post_failed",
                error=linkedin_client.last_error,
            )
            return json_error(
                "Failed to post on LinkedIn",
                502,
                linkedin_error=linkedin_client.last_error,
                firebase_record=firebase_record,
            )
    
    except Exception as e:
        logger.error(f"API error in /api/linkedin/post: {e}")
        return json_error(str(e), 500)


@app.route("/api/linkedin/comment", methods=["POST"])
def api_linkedin_post_comment():
    """
    API endpoint to post a comment on a LinkedIn post.
    
    Request body:
    {
        "post_id": "7457679327678189568",
        "content": "Your comment here"
    }
    
    Response:
    {
        "success": true,
        "comment_urn": "urn:li:comment:...",
        "message": "Comment posted successfully"
    }
    """
    try:
        data = get_json_body()
        if not data or "post_id" not in data or "content" not in data:
            return json_error("Missing 'post_id' or 'content' field", 400)
        
        post_id = data.get("post_id")
        content = data.get("content")
        
        if not content or len(content.strip()) == 0:
            return json_error("Content cannot be empty", 400)
        
        linkedin_client = LinkedInClient()
        dry_run = bool(data.get("dry_run", False))
        if dry_run:
            prepared = linkedin_client.prepare_comment_payload(post_id, content)
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Comment payload prepared. Nothing was published.",
                "payload": prepared,
            }), 200
        if not linkedin_client.api_available:
            return json_error("LinkedIn API not available. Check credentials.", 503)
        
        comment_urn = linkedin_client.post_comment(post_id, content)
        if comment_urn:
            return jsonify({
                "success": True,
                "comment_urn": comment_urn,
                "message": "Comment posted successfully on LinkedIn"
            }), 201
        else:
            return json_error("Failed to post comment on LinkedIn", 502)
    
    except Exception as e:
        logger.error(f"API error in /api/linkedin/comment: {e}")
        return json_error(str(e), 500)


@app.route("/api/linkedin/like", methods=["POST"])
def api_linkedin_like_post():
    """
    API endpoint to like a LinkedIn post.
    
    Request body:
    {
        "post_id": "7457679327678189568"
    }
    
    Response:
    {
        "success": true,
        "message": "Post liked successfully"
    }
    """
    try:
        data = get_json_body()
        if not data or "post_id" not in data:
            return json_error("Missing 'post_id' field", 400)
        
        post_id = data.get("post_id")
        
        linkedin_client = LinkedInClient()
        if bool(data.get("dry_run", False)):
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Like request accepted in dry-run mode. Nothing was published.",
                "post_id": post_id,
            }), 200
        if not linkedin_client.api_available:
            return json_error("LinkedIn API not available. Check credentials.", 503)
        
        success = linkedin_client.like_post(post_id)
        if success:
            return jsonify({
                "success": True,
                "message": "Post liked successfully on LinkedIn"
            }), 200
        else:
            return json_error("Failed to like post on LinkedIn", 502)
    
    except Exception as e:
        logger.error(f"API error in /api/linkedin/like: {e}")
        return json_error(str(e), 500)


@app.route("/api/linkedin/comments/<path:post_id>", methods=["GET"])
def api_linkedin_read_comments(post_id: str):
    """Read comments from a LinkedIn post."""
    try:
        linkedin_client = LinkedInClient()
        if not linkedin_client.api_available:
            return json_error("LinkedIn API not available. Check credentials.", 503)

        comments = linkedin_client.fetch_comments(post_id)
        return jsonify({
            "success": True,
            "post_id": post_id,
            "count": len(comments),
            "comments": comments,
        }), 200
    except Exception as e:
        logger.error(f"API error in /api/linkedin/comments/{post_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/linkedin/likes/<path:post_id>", methods=["GET"])
def api_linkedin_read_likes(post_id: str):
    """Read like count from a LinkedIn post."""
    try:
        linkedin_client = LinkedInClient()
        if not linkedin_client.api_available:
            return json_error("LinkedIn API not available. Check credentials.", 503)

        likes = linkedin_client.fetch_likes(post_id)
        return jsonify({
            "success": True,
            "post_id": post_id,
            "likes": likes,
        }), 200
    except Exception as e:
        logger.error(f"API error in /api/linkedin/likes/{post_id}: {e}")
        return json_error(str(e), 500)


# ═════════════════════════════════════════════════════════════════════════
#  API ENDPOINTS FOR FACEBOOK PAGES
# ═════════════════════════════════════════════════════════════════════════

@app.route("/api/facebook/page", methods=["GET"])
def api_facebook_page():
    try:
        client = FacebookClient()
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)
        page = client.get_page()
        if page:
            return jsonify({"success": True, "page": page}), 200
        return json_error("Failed to fetch Facebook Page", 502, facebook_error=client.last_error)
    except Exception as e:
        logger.error(f"API error in /api/facebook/page: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/posts", methods=["GET"])
def api_facebook_posts():
    try:
        limit = request.args.get("limit", default=25, type=int)
        client = FacebookClient()
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)
        posts = client.fetch_posts(limit=limit)
        return jsonify({"success": True, "count": len(posts), "posts": posts}), 200
    except Exception as e:
        logger.error(f"API error in /api/facebook/posts: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/post", methods=["POST"])
def api_facebook_post():
    try:
        data = get_json_body()
        message = data.get("content") or data.get("message")
        link = data.get("link")
        if not message or not str(message).strip():
            return json_error("Missing 'content' or 'message' field", 400)

        client = FacebookClient()
        if bool(data.get("dry_run", False)):
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Facebook post payload prepared. Nothing was published.",
                "payload": client.prepare_post_payload(message, link),
            }), 200
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)

        post_id = client.post_feed(message, link=link)
        if post_id:
            record = CRMDatabase().add_social_post_record(
                platform="facebook",
                endpoint="/api/facebook/post",
                action="manual_facebook_post",
                content=message,
                status="posted",
                external_id=post_id,
                extra_metadata={"link": link},
            )
            return jsonify({
                "success": True,
                "post_id": post_id,
                "firebase_record": record,
                "message": "Post shared successfully on Facebook",
            }), 201
        record = CRMDatabase().add_social_post_record(
            platform="facebook",
            endpoint="/api/facebook/post",
            action="manual_facebook_post",
            content=message,
            status="post_failed",
            error=client.last_error,
            extra_metadata={"link": link},
        )
        return json_error("Failed to post on Facebook", 502, facebook_error=client.last_error, firebase_record=record)
    except Exception as e:
        logger.error(f"API error in /api/facebook/post: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/photo", methods=["POST"])
def api_facebook_photo():
    try:
        data = get_json_body()
        image_url = data.get("image_url")
        caption = data.get("caption", "")
        if not image_url:
            return json_error("Missing 'image_url' field", 400)

        client = FacebookClient()
        if bool(data.get("dry_run", False)):
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Facebook photo payload prepared. Nothing was published.",
                "payload": client.prepare_photo_payload(image_url, caption),
            }), 200
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)

        photo_id = client.post_photo(image_url, caption)
        if photo_id:
            record = CRMDatabase().add_social_post_record(
                platform="facebook",
                endpoint="/api/facebook/photo",
                action="manual_facebook_photo",
                content=caption,
                status="posted",
                external_id=photo_id,
                extra_metadata={"image_url": image_url},
            )
            return jsonify({"success": True, "photo_id": photo_id, "firebase_record": record}), 201
        record = CRMDatabase().add_social_post_record(
            platform="facebook",
            endpoint="/api/facebook/photo",
            action="manual_facebook_photo",
            content=caption,
            status="post_failed",
            error=client.last_error,
            extra_metadata={"image_url": image_url},
        )
        return json_error("Failed to post Facebook photo", 502, facebook_error=client.last_error, firebase_record=record)
    except Exception as e:
        logger.error(f"API error in /api/facebook/photo: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/comment", methods=["POST"])
def api_facebook_comment():
    try:
        data = get_json_body()
        object_id = data.get("object_id") or data.get("post_id")
        message = data.get("content") or data.get("message")
        if not object_id or not message:
            return json_error("Missing 'object_id'/'post_id' or 'content'/'message'", 400)
        client = FacebookClient()
        if bool(data.get("dry_run", False)):
            return jsonify({"success": True, "dry_run": True, "object_id": object_id, "message": message}), 200
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)
        comment_id = client.post_comment(object_id, message)
        if comment_id:
            return jsonify({"success": True, "comment_id": comment_id}), 201
        return json_error("Failed to post Facebook comment", 502, facebook_error=client.last_error)
    except Exception as e:
        logger.error(f"API error in /api/facebook/comment: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/react", methods=["POST"])
def api_facebook_react():
    try:
        data = get_json_body()
        object_id = data.get("object_id") or data.get("post_id")
        reaction_type = data.get("type", "LIKE")
        if not object_id:
            return json_error("Missing 'object_id' or 'post_id'", 400)
        client = FacebookClient()
        if bool(data.get("dry_run", False)):
            return jsonify({"success": True, "dry_run": True, "object_id": object_id, "type": reaction_type}), 200
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)
        if client.react(object_id, reaction_type):
            return jsonify({"success": True, "message": "Reaction sent successfully"}), 200
        return json_error("Failed to react on Facebook", 502, facebook_error=client.last_error)
    except Exception as e:
        logger.error(f"API error in /api/facebook/react: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/comments/<path:object_id>", methods=["GET"])
def api_facebook_comments(object_id: str):
    try:
        limit = request.args.get("limit", default=25, type=int)
        client = FacebookClient()
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)
        comments = client.fetch_comments(object_id, limit=limit)
        return jsonify({"success": True, "count": len(comments), "comments": comments}), 200
    except Exception as e:
        logger.error(f"API error in /api/facebook/comments/{object_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/facebook/reactions/<path:object_id>", methods=["GET"])
def api_facebook_reactions(object_id: str):
    try:
        limit = request.args.get("limit", default=25, type=int)
        client = FacebookClient()
        if not client.api_available:
            return json_error("Facebook API not available. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.", 503)
        reactions = client.fetch_reactions(object_id, limit=limit)
        return jsonify({"success": True, "count": len(reactions), "reactions": reactions}), 200
    except Exception as e:
        logger.error(f"API error in /api/facebook/reactions/{object_id}: {e}")
        return json_error(str(e), 500)


# ═════════════════════════════════════════════════════════════════════════
#  API ENDPOINTS FOR INSTAGRAM BUSINESS / CREATOR ACCOUNTS
# ═════════════════════════════════════════════════════════════════════════

@app.route("/api/instagram/profile", methods=["GET"])
def api_instagram_profile():
    try:
        client = InstagramClient()
        if not client.api_available:
            return json_error("Instagram API not available. Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN.", 503)
        profile = client.get_profile()
        if profile:
            return jsonify({"success": True, "profile": profile}), 200
        return json_error("Failed to fetch Instagram profile", 502, instagram_error=client.last_error)
    except Exception as e:
        logger.error(f"API error in /api/instagram/profile: {e}")
        return json_error(str(e), 500)


@app.route("/api/instagram/media", methods=["GET"])
def api_instagram_media():
    try:
        limit = request.args.get("limit", default=25, type=int)
        client = InstagramClient()
        if not client.api_available:
            return json_error("Instagram API not available. Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN.", 503)
        media = client.fetch_media(limit=limit)
        return jsonify({"success": True, "count": len(media), "media": media}), 200
    except Exception as e:
        logger.error(f"API error in /api/instagram/media: {e}")
        return json_error(str(e), 500)


@app.route("/api/instagram/image", methods=["POST"])
@app.route("/api/instagram/media", methods=["POST"])
def api_instagram_image():
    try:
        data = get_json_body()
        image_url = data.get("image_url")
        caption = data.get("caption", "")
        if not image_url:
            return json_error("Missing 'image_url' field", 400)
        client = InstagramClient()
        if bool(data.get("dry_run", False)):
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Instagram image payload prepared. Nothing was published.",
                "payload": client.prepare_media_payload(caption=caption, image_url=image_url),
            }), 200
        if not client.api_available:
            return json_error("Instagram API not available. Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN.", 503)
        result = client.publish_image(image_url=image_url, caption=caption)
        if result:
            record = CRMDatabase().add_social_post_record(
                platform="instagram",
                endpoint="/api/instagram/image",
                action="manual_instagram_image",
                content=caption,
                status="posted",
                external_id=result.get("media_id"),
                extra_metadata={"image_url": image_url, "creation_id": result.get("creation_id")},
            )
            return jsonify({"success": True, **result, "firebase_record": record}), 201
        record = CRMDatabase().add_social_post_record(
            platform="instagram",
            endpoint="/api/instagram/image",
            action="manual_instagram_image",
            content=caption,
            status="post_failed",
            error=client.last_error,
            extra_metadata={"image_url": image_url},
        )
        return json_error("Failed to publish Instagram image", 502, instagram_error=client.last_error, firebase_record=record)
    except Exception as e:
        logger.error(f"API error in /api/instagram/image: {e}")
        return json_error(str(e), 500)


@app.route("/api/instagram/reel", methods=["POST"])
def api_instagram_reel():
    try:
        data = get_json_body()
        video_url = data.get("video_url")
        caption = data.get("caption", "")
        if not video_url:
            return json_error("Missing 'video_url' field", 400)
        client = InstagramClient()
        if bool(data.get("dry_run", False)):
            return jsonify({
                "success": True,
                "dry_run": True,
                "message": "Instagram Reel payload prepared. Nothing was published.",
                "payload": client.prepare_media_payload(caption=caption, video_url=video_url, media_type="REELS"),
            }), 200
        if not client.api_available:
            return json_error("Instagram API not available. Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN.", 503)
        result = client.publish_reel(video_url=video_url, caption=caption)
        if result:
            record = CRMDatabase().add_social_post_record(
                platform="instagram",
                endpoint="/api/instagram/reel",
                action="manual_instagram_reel",
                content=caption,
                status="posted",
                external_id=result.get("media_id"),
                extra_metadata={"video_url": video_url, "creation_id": result.get("creation_id")},
            )
            return jsonify({"success": True, **result, "firebase_record": record}), 201
        record = CRMDatabase().add_social_post_record(
            platform="instagram",
            endpoint="/api/instagram/reel",
            action="manual_instagram_reel",
            content=caption,
            status="post_failed",
            error=client.last_error,
            extra_metadata={"video_url": video_url},
        )
        return json_error("Failed to publish Instagram Reel", 502, instagram_error=client.last_error, firebase_record=record)
    except Exception as e:
        logger.error(f"API error in /api/instagram/reel: {e}")
        return json_error(str(e), 500)


@app.route("/api/instagram/comment", methods=["POST"])
def api_instagram_comment():
    try:
        data = get_json_body()
        media_id = data.get("media_id")
        message = data.get("content") or data.get("message")
        if not media_id or not message:
            return json_error("Missing 'media_id' or 'content'/'message'", 400)
        client = InstagramClient()
        if bool(data.get("dry_run", False)):
            return jsonify({"success": True, "dry_run": True, "media_id": media_id, "message": message}), 200
        if not client.api_available:
            return json_error("Instagram API not available. Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN.", 503)
        comment_id = client.post_comment(media_id, message)
        if comment_id:
            return jsonify({"success": True, "comment_id": comment_id}), 201
        return json_error("Failed to post Instagram comment", 502, instagram_error=client.last_error)
    except Exception as e:
        logger.error(f"API error in /api/instagram/comment: {e}")
        return json_error(str(e), 500)


@app.route("/api/instagram/comments/<path:media_id>", methods=["GET"])
def api_instagram_comments(media_id: str):
    try:
        limit = request.args.get("limit", default=25, type=int)
        client = InstagramClient()
        if not client.api_available:
            return json_error("Instagram API not available. Set INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN.", 503)
        comments = client.fetch_comments(media_id, limit=limit)
        return jsonify({"success": True, "count": len(comments), "comments": comments}), 200
    except Exception as e:
        logger.error(f"API error in /api/instagram/comments/{media_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/leads", methods=["GET"])
def api_firebase_list_leads():
    """Read leads from Firebase Firestore."""
    try:
        min_score = request.args.get("min_score", default=0, type=int)
        source = request.args.get("source")
        crm = CRMDatabase()
        leads = crm.get_leads(min_score=min_score, source=source)
        return jsonify({
            "success": True,
            "backend": "firebase",
            "count": len(leads),
            "leads": leads,
        }), 200
    except Exception as e:
        logger.error(f"API error in /api/firebase/leads: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/leads/<path:lead_id>", methods=["GET"])
def api_firebase_get_lead(lead_id: str):
    """Read a single lead by ID."""
    try:
        lead = CRMDatabase().get_lead(lead_id)
        if not lead:
            return json_error("Lead not found", 404)
        return jsonify({"success": True, "lead": lead}), 200
    except Exception as e:
        logger.error(f"API error in /api/firebase/leads/{lead_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/leads/<path:lead_id>", methods=["PATCH", "PUT"])
def api_firebase_update_lead(lead_id: str):
    """Update a lead by ID."""
    try:
        data = get_json_body()
        if not data:
            return json_error("Request body cannot be empty", 400)

        lead = CRMDatabase().update_lead(lead_id, data)
        if not lead:
            return json_error("Lead not found", 404)
        return jsonify({
            "success": True,
            "lead": lead,
            "message": "Lead updated successfully",
        }), 200
    except Exception as e:
        logger.error(f"API error updating lead {lead_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/leads/<path:lead_id>", methods=["DELETE"])
def api_firebase_delete_lead(lead_id: str):
    """Delete a lead by ID. Related review queue items are also removed."""
    try:
        deleted = CRMDatabase().delete_lead(lead_id)
        if not deleted:
            return json_error("Lead not found", 404)
        return jsonify({
            "success": True,
            "message": "Lead deleted successfully",
            "lead_id": lead_id,
        }), 200
    except Exception as e:
        logger.error(f"API error deleting lead {lead_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/review-queue", methods=["GET"])
@app.route("/api/firebase/posts", methods=["GET"])
def api_firebase_list_posts():
    """Read generated/stored post actions from the review queue."""
    try:
        status = request.args.get("status", STATUS_PENDING)
        crm = CRMDatabase()
        posts = crm.get_review_queue(status=status)
        return jsonify({
            "success": True,
            "backend": "firebase",
            "status": status,
            "count": len(posts),
            "posts": posts,
        }), 200
    except Exception as e:
        logger.error(f"API error in /api/firebase/posts: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/review-queue/<path:post_id>", methods=["GET"])
@app.route("/api/firebase/posts/<path:post_id>", methods=["GET"])
def api_firebase_get_post(post_id: str):
    """Read a generated/stored post action by review queue ID."""
    try:
        post = CRMDatabase().get_review_queue_item(post_id)
        if not post:
            return json_error("Post not found", 404)
        return jsonify({"success": True, "post": post}), 200
    except Exception as e:
        logger.error(f"API error in /api/firebase/posts/{post_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/review-queue/<path:post_id>", methods=["PATCH", "PUT"])
@app.route("/api/firebase/posts/<path:post_id>", methods=["PATCH", "PUT"])
def api_firebase_update_post(post_id: str):
    """Update generated/stored post content, action, or status."""
    try:
        data = get_json_body()
        if not data:
            return json_error("Request body cannot be empty", 400)

        post = CRMDatabase().update_review_queue_item(post_id, data)
        if not post:
            return json_error("Post not found", 404)
        return jsonify({
            "success": True,
            "post": post,
            "message": "Post updated successfully",
        }), 200
    except Exception as e:
        logger.error(f"API error updating post {post_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/firebase/review-queue/<path:post_id>", methods=["DELETE"])
@app.route("/api/firebase/posts/<path:post_id>", methods=["DELETE"])
def api_firebase_delete_post(post_id: str):
    """Delete a generated/stored post action by review queue ID."""
    try:
        deleted = CRMDatabase().delete_review_queue_item(post_id)
        if not deleted:
            return json_error("Post not found", 404)
        return jsonify({
            "success": True,
            "message": "Post deleted successfully",
            "post_id": post_id,
        }), 200
    except Exception as e:
        logger.error(f"API error deleting post {post_id}: {e}")
        return json_error(str(e), 500)


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check endpoint."""
    try:
        linkedin_client = LinkedInClient()
        facebook_client = FacebookClient()
        instagram_client = InstagramClient()
        return jsonify({
            "status": "healthy",
            "linkedin_api_available": linkedin_client.api_available,
            "facebook_api_available": facebook_client.api_available,
            "instagram_api_available": instagram_client.api_available,
            "approval_mode": config.APPROVAL_MODE
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@app.route("/api/llm/generate-linkedin-post", methods=["POST"])
def api_llm_generate_linkedin_post():
    """
    Generate a LinkedIn post from a given topic using LLM (Ollama).
    
    Request body:
    {
        "topic": "Your topic here, e.g., 'AI in business transformation'"
    }
    
    Response:
    {
        "success": true,
        "post": "Generated LinkedIn post content",
        "model": "llama3:latest",
        "message": "Post generated successfully"
    }
    """
    try:
        data = get_json_body()
        if not data or "topic" not in data:
            return json_error("Missing 'topic' field", 400)
        
        topic = data.get("topic", "").strip()
        if not topic or len(topic) == 0:
            return json_error("Topic cannot be empty", 400)
        
        ai_engine = GeminiEngine()
        if not ai_engine.is_available():
            return json_error(
                "Gemini not available. Set GEMINI_API_KEY and check GEMINI_BASE_URL.",
                503,
                instructions="Check your Gemini setup.",
                model=ai_engine._active_model,
                gemini_error=ai_engine.last_error,
            )

        post_content = ai_engine.generate_linkedin_post_from_topic(topic)
        if post_content:
            return jsonify({
                "success": True,
                "post": post_content,
                "message": "LinkedIn post generated successfully",
                "topic": topic
            }), 201
        else:
            return json_error(
                "Failed to generate post from topic",
                502,
                model=ai_engine._active_model,
                gemini_error=ai_engine.last_error,
            )
    
    except Exception as e:
        logger.error(f"API error in /api/llm/generate-linkedin-post: {e}")
        return json_error(str(e), 500)


def run_api_server(host: str = "127.0.0.1", port: int = 5000):
    """Start the Flask API server."""
    print_separator("API SERVER STARTING")
    logger.info(f"Starting API server on http://{host}:{port}")
    logger.info("Available endpoints:")
    logger.info("  POST /api/linkedin/post               - Post content on LinkedIn")
    logger.info("  POST /api/linkedin/comment            - Post comment on LinkedIn")
    logger.info("  POST /api/linkedin/like               - Like a post on LinkedIn")
    logger.info("  GET  /api/linkedin/comments/<post_id> - Read LinkedIn comments")
    logger.info("  GET  /api/linkedin/likes/<post_id>    - Read LinkedIn like count")
    logger.info("  POST /api/facebook/post              - Post text/link on Facebook Page")
    logger.info("  POST /api/facebook/photo             - Post photo on Facebook Page")
    logger.info("  POST /api/facebook/comment           - Comment on Facebook object")
    logger.info("  POST /api/facebook/react             - React to Facebook object")
    logger.info("  POST /api/instagram/image            - Publish Instagram image")
    logger.info("  POST /api/instagram/reel             - Publish Instagram Reel")
    logger.info("  POST /api/instagram/comment          - Comment on Instagram media")
    logger.info("  GET  /api/firebase/leads              - Read stored leads")
    logger.info("  GET  /api/firebase/posts              - Read stored/generated posts")
    logger.info("  POST /api/llm/generate-linkedin-post  - Generate post from topic (LLM)")
    logger.info("  GET  /api/health                      - Health check")
    print_separator()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Lead Generation Pipeline")
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["run", "queue", "stats", "approve", "reject", "schedule", "api"],
    )
    parser.add_argument("--sources", nargs="+", choices=["reddit", "linkedin"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Queue items with placeholder text instead of calling Ollama")
    parser.add_argument("--id", type=str, help="Queue ID for approve/reject")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "5000")), help="API server port (default: env PORT or 5000)")

    args = parser.parse_args()

    if args.command == "run":
        run_pipeline(sources=args.sources, dry_run=args.dry_run)
    elif args.command == "queue":
        show_review_queue()
    elif args.command == "stats":
        show_stats()
    elif args.command == "approve":
        if not args.id:
            print("Error: --id required"); sys.exit(1)
        approve_item(args.id)
    elif args.command == "reject":
        if not args.id:
            print("Error: --id required"); sys.exit(1)
        reject_item(args.id)
    elif args.command == "schedule":
        scheduler = ContentScheduler()
        scheduler.start()
    elif args.command == "api":
        run_api_server(host=args.host, port=args.port)
