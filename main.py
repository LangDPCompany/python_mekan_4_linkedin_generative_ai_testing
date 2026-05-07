import logging
import json
import os
import sys
from typing import List, Dict, Any, Optional
from flask import Flask, request, jsonify
import config
from ingestion import IngestionOrchestrator
from ai_engine import GeminiEngine
from crm import CRMDatabase
from linkedin_client import LinkedInClient
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
            return jsonify({
                "success": True,
                "share_urn": share_urn,
                "message": "Post shared successfully on LinkedIn"
            }), 201
        else:
            return json_error("Failed to post on LinkedIn", 502)
    
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


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check endpoint."""
    try:
        linkedin_client = LinkedInClient()
        return jsonify({
            "status": "healthy",
            "linkedin_api_available": linkedin_client.api_available,
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
                instructions="Check your Gemini setup."
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
