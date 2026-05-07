# Firebase Firestore Setup

This project can store CRM data in Firestore using Firebase Admin SDK.

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` includes `firebase-admin`.

## 2. Enable Firebase Backend

Set:

```env
DB_BACKEND=firebase
```

If you want local SQLite instead:

```env
DB_BACKEND=sqlite
DB_PATH=leads.db
```

## 3. Required Firebase Admin Variables

Add these to `.env` locally or Railway Variables in production:

```env
FIREBASE_TYPE=service_account
FIREBASE_PROJECT_ID=langdp-test
FIREBASE_PRIVATE_KEY_ID=your-private-key-id
FIREBASE_PRIVATE_KEY="<escaped-service-account-private-key>"
FIREBASE_CLIENT_EMAIL=firebase-adminsdk-fbsvc@langdp-test.iam.gserviceaccount.com
FIREBASE_CLIENT_ID=your-client-id
FIREBASE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FIREBASE_TOKEN_URI=https://oauth2.googleapis.com/token
FIREBASE_AUTH_PROVIDER_X509_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
FIREBASE_CLIENT_X509_CERT_URL=https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40langdp-test.iam.gserviceaccount.com
FIREBASE_UNIVERSE_DOMAIN=googleapis.com
```

Client/web app values can also be stored if you need them elsewhere:

```env
FIREBASE_API_KEY=your-web-api-key
FIREBASE_APP_ID=your-app-id
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
FIREBASE_MEASUREMENT_ID=your-measurement-id
FIREBASE_MESSAGING_SENDER_ID=your-sender-id
FIREBASE_STORAGE_BUCKET=your-bucket
FIREBASE_PROD=
```

Do not commit real Firebase private keys to GitHub.

## 4. Private Key Formatting

For Railway, store the private key as one env value with escaped newlines:

```env
FIREBASE_PRIVATE_KEY="<escaped-service-account-private-key>"
```

The app converts `\n` into real newlines before initializing Firebase Admin SDK.

## 5. Firestore Collections

Default collections:

- `leads`
- `review_queue`

Override names if needed:

```env
FIREBASE_LEADS_COLLECTION=leads
FIREBASE_REVIEW_QUEUE_COLLECTION=review_queue
```

## 6. Run Locally

```bash
python main.py run --sources linkedin --dry-run
python main.py queue
python main.py stats
```

Start API:

```bash
python main.py api --port 8890
```

Test:

```bash
curl http://127.0.0.1:8890/api/health
```

## 7. Railway

1. Push code to GitHub.
2. Create a Railway project from the GitHub repo.
3. Add all Firebase variables in Railway `Variables`.
4. Set `DB_BACKEND=firebase`.
5. Deploy. The included `Procfile` starts the API with Gunicorn.

## 8. Security

If a Firebase service account private key was shared in chat, logs, screenshots, or GitHub, revoke it and create a new key in Google Cloud Console.
