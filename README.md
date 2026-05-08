# python_mekan_4_linkedin_AI_agent

AI-powered LinkedIn automation system for lead generation.

## Features

- Ingest leads from LinkedIn and Reddit
- Score and process leads
- Generate AI responses
- Automated LinkedIn content posting (articles, posts)
- Engagement with posts (comments, likes)
- Feedback handling on own content
- Time-based scheduling

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Set environment variables (see config.py)
	- For personal profile posting, set `LINKEDIN_USE_PERSONAL_PROFILE=true`
	- Optionally set `LINKEDIN_PERSONAL_PROFILE_ID` or `LINKEDIN_PERSONAL_PROFILE_URN`
	- For Firestore storage, set the Firebase Admin SDK variables listed in `FIREBASE_SETUP.md`
3. Run the pipeline safely: `python main.py run --sources linkedin --dry-run`
4. To auto-publish generated LinkedIn content, set `APPROVAL_MODE=AUTO_POST`.
5. Start the API server locally: `python main.py api --port 8890`
6. Start the scheduler: `python main.py schedule` (runs in background)

## Commands

- `python main.py run` : Run lead generation pipeline
- `python main.py run --sources linkedin --dry-run` : Test the pipeline without AI calls or auto-posting
- `python main.py api --port 8890` : Start the Flask API server
- `python main.py schedule` : Start automated content scheduler
- `python main.py queue` : Show review queue
- `python main.py approve --id <id>` : Approve queued action
- `python main.py reject --id <id>` : Reject queued action

## Database

The app stores CRM data only in Firebase Firestore using Firebase Admin SDK.

Default Firestore target:

- Project: `langdp-test`
- Database ID: `leads`
- `leads` collection: processed leads and manual LinkedIn post records
- `review_queue` collection: generated drafts and manual LinkedIn post records returned by `/api/firebase/posts`

`POST /api/linkedin/post` writes a Firebase record even when LinkedIn posting fails:

- `status=posted` when LinkedIn accepts the post
- `status=post_failed` when LinkedIn rejects the post

See `FIREBASE_SETUP.md` for the required Firebase variables.
