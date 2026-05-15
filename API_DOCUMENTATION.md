# LinkedIn REST API Documentation

LinkedIn post paylaşma işlemlerini HTTP API çağrıları ile yapabilirsiniz. API'yi çalıştırmak için aşağıdaki komutu kullanın:

```bash
python main.py api --port 8890
```

---

## Environment Variables

API-ni işə salmazdan əvvəl repo root-da `.env` faylı yaradın. `.env.example` sadəcə nümunədir; app lokalda `.env` faylını, Railway-də isə Railway Variables dəyərlərini oxuyur.

Minimal lokal setup üçün:

```env
APPROVAL_MODE=AUTO_ANALYZE_ONLY

LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token
LINKEDIN_ORGANIZATION_ID=your_linkedin_organization_id
LINKEDIN_USE_PERSONAL_PROFILE=true
LINKEDIN_PERSONAL_PROFILE_ID=your_personal_profile_id
LINKEDIN_PERSONAL_PROFILE_URN=urn:li:person:your_personal_profile_id

GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.0-flash

DB_BACKEND=firebase
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_DATABASE_ID=leads
FIREBASE_CLIENT_EMAIL=your_firebase_client_email
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

Optional Meta/Facebook/Instagram endpoint-ləri üçün:

```env
META_GRAPH_VERSION=v23.0
FACEBOOK_PAGE_ID=your_page_id
FACEBOOK_PAGE_ACCESS_TOKEN=your_page_access_token
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_instagram_business_account_id
INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token
```

Railway-də eyni dəyərləri **Variables** bölməsinə əlavə edin və deploy-u restart edin.

Secret-ləri `.env.example`, README və ya Git-ə commit etməyin. Real token/private key sızıbsa, onu revoke/rotate edin.

---

## API Canvas / Postman Setup

API canvas və ya Postman-da request hazırlayanda aşağıdakı ardıcıllıqdan istifadə edin.

**Query Params:**
- Əgər endpoint ayrıca query param tələb etmirsə, bu hissəni boş saxlayın.
- Məsələn `/api/firebase/posts` üçün `status=all`, `/api/firebase/leads` üçün `min_score=60` və `source=linkedin` əlavə edə bilərsiniz.

**Env Variables:**
Bu hissəyə real dəyərləri əlavə edin. Açar adları belə olmalıdır:

```env
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.0-flash

LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token
LINKEDIN_ORGANIZATION_ID=your_linkedin_organization_id
LINKEDIN_USE_PERSONAL_PROFILE=true
LINKEDIN_PERSONAL_PROFILE_ID=your_personal_profile_id
LINKEDIN_PERSONAL_PROFILE_URN=urn:li:person:your_personal_profile_id

DB_BACKEND=firebase
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_DATABASE_ID=leads
FIREBASE_CLIENT_EMAIL=your_firebase_client_email
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
```

**Qeyd:** Env variables request body və query params kimi göndərilmir. Onlar lokalda `.env` faylında, production-da isə Railway Variables bölməsində saxlanılır. API server restart edilmədən yeni env dəyərləri oxunmaya bilər.

---

## API Endpoints

### 1. **Health Check**

API'nin çalışıp çalışmadığını kontrol edin.

**Endpoint:**
```
GET /api/health
```

**cURL Örneği:**
```bash
curl http://127.0.0.1:8890/api/health
```

**Yanıt Örneği:**
```json
{
  "status": "healthy",
  "linkedin_api_available": true,
  "approval_mode": "AUTO_POST"
}
```

---

### 2. **LinkedIn Post Paylaş (Share)**

LinkedIn'de yeni bir post paylaşın.

**Endpoint:**
```
POST /api/linkedin/post
```

**Content-Type:**
```
application/json
```

**Request Body:**
```json
{
  "content": "Your post content here. Bu yeni ürünü çok merak ediyorum! 🚀"
}
```

**cURL Örneği:**
```bash
curl -X POST http://127.0.0.1:8890/api/linkedin/post \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Harika bir gün başlamak için hepinize selamlar! 👋 Yeni AI projemiz online! 🚀"
  }'
```

**Başarılı Yanıt (201):**
```json
{
  "success": true,
  "share_urn": "urn:li:share:7457679327678189568",
  "firebase_record": {
    "lead_id": "lead_doc_id",
    "post_id": "review_queue_doc_id"
  },
  "message": "Post shared successfully on LinkedIn"
}
```

Bu endpoint LinkedIn post cəhdini Firebase Firestore-da da saxlayır:

- `leads` collection: post content-i və metadata saxlanılır
- `review_queue` collection: `/api/firebase/posts` endpoint-i üçün post record-u saxlanılır
- Uğurlu post üçün `status = posted`
- LinkedIn uğursuz cavab versə, yenə Firebase-ə yazılır və `status = post_failed` olur

**LinkedIn uğursuz, Firebase record uğurlu Yanıt (502):**
```json
{
  "success": false,
  "error": "Failed to post on LinkedIn",
  "linkedin_error": {
    "status_code": 403,
    "response": "LinkedIn error response..."
  },
  "firebase_record": {
    "lead_id": "lead_doc_id",
    "post_id": "review_queue_doc_id"
  }
}
```

**Hata Yanıtları:**
- `400` - Content field boş veya eksik
- `503` - LinkedIn API kullanılamıyor
- `502` - LinkedIn post uğursuz oldu, amma cəhd Firebase-də `post_failed` kimi saxlanılır
- `500` - Sunucu hatası

---

### 3. **LinkedIn Post'a Yorum Yap**

Bir LinkedIn post'una yorum yazın.

**Endpoint:**
```
POST /api/linkedin/comment
```

**Content-Type:**
```
application/json
```

**Request Body:**
```json
{
  "post_id": "7457679327678189568",
  "content": "Your comment here"
}
```

**cURL Örneği:**
```bash
curl -X POST http://127.0.0.1:8890/api/linkedin/comment \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "7457679327678189568",
    "content": "Bu çok önemli bir konu! Sizin deneyimlerinizi merak ediyorum."
  }'
```

**Başarılı Yanıt (201):**
```json
{
  "success": true,
  "comment_urn": "urn:li:comment:...",
  "message": "Comment posted successfully on LinkedIn"
}
```

**Hata Yanıtları:**
- `400` - post_id veya content field eksik
- `503` - LinkedIn API kullanılamıyor
- `500` - Yorum paylaşımında hata

---

### 4. **LinkedIn Post'u Beğen (Like)**

Bir LinkedIn post'unu beğenin.

**Endpoint:**
```
POST /api/linkedin/like
```

**Content-Type:**
```
application/json
```

**Request Body:**
```json
{
  "post_id": "7457679327678189568"
}
```

**cURL Örneği:**
```bash
curl -X POST http://127.0.0.1:8890/api/linkedin/like \
  -H "Content-Type: application/json" \
  -d '{"post_id": "7457679327678189568"}'
```

**Başarılı Yanıt (200):**
```json
{
  "success": true,
  "message": "Post liked successfully on LinkedIn"
}
```

**Hata Yanıtları:**
- `400` - post_id field eksik
- `503` - LinkedIn API kullanılamıyor
- `500` - Like işleminde hata

---

### 5. **LLM ilə LinkedIn Post Yarat**

Verilən mövzuya görə AI/LLM vasitəsilə LinkedIn post mətni yaradın. Bu endpoint LinkedIn-də paylaşım etmir, sadəcə post content generasiya edir.

**Endpoint:**
```
POST /api/llm/generate-linkedin-post
```

**Content-Type:**
```
application/json
```

**Request Body:**
```json
{
  "topic": "AI in business transformation"
}
```

**Field-lər:**
- `topic` - Məcburidir. LinkedIn postunun hansı mövzu haqqında yazılacağını bildirir. Boş string göndərmək olmaz.

**cURL Örneği:**
```bash
curl -X POST http://127.0.0.1:8890/api/llm/generate-linkedin-post \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Generative AI testing startup-lar üçün niyə vacibdir?"
  }'
```

**Başarılı Yanıt (201):**
```json
{
  "success": true,
  "post": "Generated LinkedIn post content...",
  "message": "LinkedIn post generated successfully",
  "topic": "Generative AI testing startup-lar üçün niyə vacibdir?"
}
```

**Hata Yanıtları:**
- `400` - `topic` field eksikdir və ya boşdur
- `503` - Gemini istifadə edilə bilmir. `GEMINI_API_KEY` və `GEMINI_BASE_URL` ayarlarını yoxlayın
- `502` - LLM post generasiya edə bilmədi
- `500` - Sunucu hatası

---

### Facebook Page API-ləri

Bu endpoint-lər Meta Graph API ilə Facebook Page üzərində işləyir. Lazım olan env-lər:

```env
META_GRAPH_VERSION=v23.0
FACEBOOK_PAGE_ID=your_page_id
FACEBOOK_PAGE_ACCESS_TOKEN=your_page_access_token
```

Page access token adətən Page üzərində content yaratmaq və engagement oxumaq üçün uyğun Meta permissions tələb edir, məsələn `pages_manage_posts`, `pages_read_engagement`, `pages_manage_engagement`.

#### Facebook Page Info

```bash
curl http://127.0.0.1:8890/api/facebook/page
```

#### Facebook Page Posts Oxu

```bash
curl "http://127.0.0.1:8890/api/facebook/posts?limit=10"
```

#### Facebook Text/Link Post

Dry-run, təhlükəsiz test:

```bash
curl -X POST http://127.0.0.1:8890/api/facebook/post \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Testing Facebook Page API",
    "link": "https://example.com",
    "dry_run": true
  }'
```

Real publish:

```bash
curl -X POST http://127.0.0.1:8890/api/facebook/post \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Testing Facebook Page API",
    "link": "https://example.com"
  }'
```

#### Facebook Photo Post

`image_url` public reachable URL olmalıdır.

```bash
curl -X POST http://127.0.0.1:8890/api/facebook/photo \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/image.jpg",
    "caption": "Photo caption",
    "dry_run": true
  }'
```

#### Facebook Comment

```bash
curl -X POST http://127.0.0.1:8890/api/facebook/comment \
  -H "Content-Type: application/json" \
  -d '{
    "object_id": "facebook_post_or_photo_id",
    "content": "Great point",
    "dry_run": true
  }'
```

#### Facebook Reaction

```bash
curl -X POST http://127.0.0.1:8890/api/facebook/react \
  -H "Content-Type: application/json" \
  -d '{
    "object_id": "facebook_post_or_photo_id",
    "type": "LIKE",
    "dry_run": true
  }'
```

#### Facebook Comments/Reactions Oxu

```bash
curl "http://127.0.0.1:8890/api/facebook/comments/facebook_object_id?limit=25"
curl "http://127.0.0.1:8890/api/facebook/reactions/facebook_object_id?limit=25"
```

---

### Instagram Graph API-ləri

Bu endpoint-lər Instagram Business/Creator account üçün Meta Graph API istifadə edir. Lazım olan env-lər:

```env
META_GRAPH_VERSION=v23.0
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_ig_user_id
INSTAGRAM_ACCESS_TOKEN=your_access_token
```

`INSTAGRAM_ACCESS_TOKEN` boş saxlanılsa app `FACEBOOK_PAGE_ACCESS_TOKEN` dəyərindən fallback kimi istifadə edir. Content publishing üçün adətən Instagram account Facebook Page-ə bağlı olmalı və token `instagram_content_publish` kimi uyğun permission-lara sahib olmalıdır.

#### Instagram Profile

```bash
curl http://127.0.0.1:8890/api/instagram/profile
```

#### Instagram Media Oxu

```bash
curl "http://127.0.0.1:8890/api/instagram/media?limit=10"
```

#### Instagram Image Publish

Instagram publish iki addımlıdır: media container yaradılır, sonra `media_publish` çağırılır. Bu endpoint ikisini də edir.

`image_url` public reachable URL olmalıdır.

Dry-run:

```bash
curl -X POST http://127.0.0.1:8890/api/instagram/image \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/image.jpg",
    "caption": "Instagram caption",
    "dry_run": true
  }'
```

Real publish:

```bash
curl -X POST http://127.0.0.1:8890/api/instagram/image \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/image.jpg",
    "caption": "Instagram caption"
  }'
```

#### Instagram Reel Publish

`video_url` public reachable MP4 URL olmalıdır.

```bash
curl -X POST http://127.0.0.1:8890/api/instagram/reel \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://example.com/video.mp4",
    "caption": "Reel caption",
    "dry_run": true
  }'
```

#### Instagram Comment

```bash
curl -X POST http://127.0.0.1:8890/api/instagram/comment \
  -H "Content-Type: application/json" \
  -d '{
    "media_id": "instagram_media_id",
    "content": "Nice post",
    "dry_run": true
  }'
```

#### Instagram Comments Oxu

```bash
curl "http://127.0.0.1:8890/api/instagram/comments/instagram_media_id?limit=25"
```

---

### 6. **Firebase Leads Oxu**

Firebase Firestore-da (`leads` collection) saxlanılan lead datalarını oxuyun.

**Endpoint:**
```
GET /api/firebase/leads
```

**Query Parametrlər:**
- `min_score` - Optional. Minimum score filteri. Default: `0`
- `source` - Optional. Məsələn: `linkedin` və ya `reddit`

**cURL Örneği:**
```bash
curl "http://127.0.0.1:8890/api/firebase/leads?min_score=60&source=linkedin"
```

**Başarılı Yanıt (200):**
```json
{
  "success": true,
  "backend": "firebase",
  "count": 1,
  "leads": [
    {
      "id": "lead_doc_id",
      "text": "Original post text",
      "source": "linkedin",
      "score": 80,
      "intent_level": "high",
      "is_lead": true,
      "recommended_action": "generate_linkedin_post"
    }
  ]
}
```

---

### 7. **Firebase Lead Detail, Update, Delete**

Tək lead-i ID ilə oxuyun, update edin və ya silin.

**Endpoint-lər:**
```
GET    /api/firebase/leads/{lead_id}
PATCH  /api/firebase/leads/{lead_id}
PUT    /api/firebase/leads/{lead_id}
DELETE /api/firebase/leads/{lead_id}
```

**Update edilə bilən field-lər:**
`text`, `cleaned_text`, `source`, `author`, `url`, `timestamp`, `score`, `intent_level`, `is_lead`, `signals`, `recommended_action`, `ai_response`, `status`, `platform_metadata`

**Read cURL:**
```bash
curl http://127.0.0.1:8890/api/firebase/leads/lead_doc_id
```

**Update cURL:**
```bash
curl -X PATCH http://127.0.0.1:8890/api/firebase/leads/lead_doc_id \
  -H "Content-Type: application/json" \
  -d '{
    "score": 90,
    "status": "reviewed",
    "ai_response": "Updated generated content"
  }'
```

**Delete cURL:**
```bash
curl -X DELETE http://127.0.0.1:8890/api/firebase/leads/lead_doc_id
```

**Qeyd:** Lead silinəndə həmin lead-ə bağlı `review_queue` item-ləri də silinir.

---

### 8. **Firebase Generated/Manual Post-ları Oxu**

Pipeline-in yaratdığı LinkedIn post/comment content-ləri və `/api/linkedin/post` ilə edilən manual post cəhdləri `review_queue` collection içində saxlanılır. Bu endpoint-lər həmin generated/manual post datalarını oxumaq üçündür.

**Endpoint-lər:**
```
GET /api/firebase/posts
GET /api/firebase/review-queue
```

Hər iki endpoint eyni datanı qaytarır. `posts` daha rahat alias-dır.

**Query Parametrlər:**
- `status` - Optional. `pending`, `approved`, `rejected`, `posted`, `post_failed`, `firebase_connection_test`, yaxud `all`. Default: `pending`

**Qeyd:** Köhnə manual LinkedIn post record-ları yalnız `leads` collection-da qalıbsa, API onları avtomatik `review_queue` collection-a əlavə edir. Buna görə `/api/firebase/posts?status=all` bütün post datalarını qaytarır.

**cURL Örneği:**
```bash
curl "http://127.0.0.1:8890/api/firebase/posts?status=all"
```

**Başarılı Yanıt (200):**
```json
{
  "success": true,
  "backend": "firebase",
  "status": "all",
  "count": 1,
  "posts": [
    {
      "id": "queue_doc_id",
      "lead_id": "lead_doc_id",
      "action": "manual_linkedin_post",
      "content": "LinkedIn post content...",
      "status": "posted",
      "score": 0,
      "source": "linkedin",
      "author": "api/linkedin/post",
      "platform_metadata": {
        "endpoint": "/api/linkedin/post",
        "share_urn": "urn:li:share:7458448549433839616",
        "error": null
      }
    }
  ]
}
```

---

### 9. **Firebase Generated Post Detail, Update, Delete**

Yaradılmış post/comment draft-larını review queue ID ilə oxuyun, update edin və ya silin.

**Endpoint-lər:**
```
GET    /api/firebase/posts/{post_id}
PATCH  /api/firebase/posts/{post_id}
PUT    /api/firebase/posts/{post_id}
DELETE /api/firebase/posts/{post_id}
```

Alternative path:
```
GET    /api/firebase/review-queue/{post_id}
PATCH  /api/firebase/review-queue/{post_id}
PUT    /api/firebase/review-queue/{post_id}
DELETE /api/firebase/review-queue/{post_id}
```

**Update edilə bilən field-lər:**
`content`, `action`, `status`

**Read cURL:**
```bash
curl http://127.0.0.1:8890/api/firebase/posts/queue_doc_id
```

**Update cURL:**
```bash
curl -X PATCH http://127.0.0.1:8890/api/firebase/posts/queue_doc_id \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Updated LinkedIn post draft",
    "status": "pending"
  }'
```

**Delete cURL:**
```bash
curl -X DELETE http://127.0.0.1:8890/api/firebase/posts/queue_doc_id
```

---

### 10. **LinkedIn Comment-ləri Oxu**

LinkedIn post-un comment-lərini oxuyun.

**Endpoint:**
```
GET /api/linkedin/comments/{post_id}
```

**cURL Örneği:**
```bash
curl "http://127.0.0.1:8890/api/linkedin/comments/urn:li:ugcPost:7457679327678189568"
```

**Başarılı Yanıt (200):**
```json
{
  "success": true,
  "post_id": "urn:li:ugcPost:7457679327678189568",
  "count": 1,
  "comments": [
    {
      "text": "Great point!",
      "author": "urn:li:person:...",
      "timestamp": "2026-05-08T10:00:00",
      "comment_id": "..."
    }
  ]
}
```

---

### 11. **LinkedIn Like Sayını Oxu**

LinkedIn post-un like sayını oxuyun.

**Endpoint:**
```
GET /api/linkedin/likes/{post_id}
```

**cURL Örneği:**
```bash
curl "http://127.0.0.1:8890/api/linkedin/likes/urn:li:ugcPost:7457679327678189568"
```

**Başarılı Yanıt (200):**
```json
{
  "success": true,
  "post_id": "urn:li:ugcPost:7457679327678189568",
  "likes": 12
}
```

**Hata Yanıtları:**
- `503` - LinkedIn API istifadə edilə bilmir
- `500` - Sunucu hatası

---

## Kullanım Örnekleri

### Python ile

```python
import requests
import json

API_URL = "http://127.0.0.1:8890"

# Post Paylaş
def post_on_linkedin(content):
    response = requests.post(
        f"{API_URL}/api/linkedin/post",
        json={"content": content},
        headers={"Content-Type": "application/json"}
    )
    return response.json()

# Yorum Yap
def comment_on_post(post_id, comment_text):
    response = requests.post(
        f"{API_URL}/api/linkedin/comment",
        json={"post_id": post_id, "content": comment_text},
        headers={"Content-Type": "application/json"}
    )
    return response.json()

# Post Beğen
def like_post(post_id):
    response = requests.post(
        f"{API_URL}/api/linkedin/like",
        json={"post_id": post_id},
        headers={"Content-Type": "application/json"}
    )
    return response.json()

# Kullanım
result = post_on_linkedin("API üzerinden test post! 🎉")
print(result)
```

### JavaScript/Node.js ile

```javascript
const API_URL = "http://127.0.0.1:8890";

// Post Paylaş
async function postOnLinkedIn(content) {
  const response = await fetch(`${API_URL}/api/linkedin/post`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content })
  });
  return response.json();
}

// Yorum Yap
async function commentOnPost(postId, comment) {
  const response = await fetch(`${API_URL}/api/linkedin/comment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_id: postId, content: comment })
  });
  return response.json();
}

// Post Beğen
async function likePost(postId) {
  const response = await fetch(`${API_URL}/api/linkedin/like`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_id: postId })
  });
  return response.json();
}

// Kullanım
postOnLinkedIn("API'den javascript test! 🚀")
  .then(result => console.log(result));
```

---

## Ayarlar

### Database

The API and pipeline store CRM data in Firebase Firestore.

```env
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_DATABASE_ID=leads
FIREBASE_CLIENT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
FIREBASE_PRIVATE_KEY="<escaped-service-account-private-key>"
FIREBASE_PRIVATE_KEY_ID=your-private-key-id
FIREBASE_CLIENT_ID=your-client-id
```

Firestore database:

- `leads`: default Firestore database ID used by this app

Firestore collections inside that database:

- `leads`: processed lead records and manual LinkedIn post records
- `review_queue`: pending/approved/rejected generated actions and manual LinkedIn post records returned by `/api/firebase/posts`

Manual LinkedIn post flow:

- `POST /api/linkedin/post` writes to both `leads` and `review_queue`
- Successful LinkedIn post: `status=posted`
- Failed LinkedIn post: `status=post_failed`, with LinkedIn error details in `platform_metadata.error`
- `GET /api/firebase/posts?status=all` returns all `review_queue` post records
- Older manual post records that exist only in `leads` are auto-added to `review_queue` when posts are read

Optional collection names:

```env
FIREBASE_LEADS_COLLECTION=leads
FIREBASE_REVIEW_QUEUE_COLLECTION=review_queue
```

API sunucusunu başlarken port ve host belirtebilirsiniz:

```bash
# Özel port ve host ile başlat
python main.py api --host 0.0.0.0 --port 8080

# Kod default-u: env PORT və ya 5000
python main.py api

# Bu dokümandakı nümunələr üçün istifadə etdiyimiz port
python main.py api --port 8890
```

---

## Ortam Değişkenleri (`.env`)

API'nin düzgün çalışması için `.env` dosyasında gerekli LinkedIn credentials olması gerekir:

```env
LINKEDIN_ACCESS_TOKEN=your_access_token_here
LINKEDIN_USE_PERSONAL_PROFILE=True
LINKEDIN_PERSONAL_PROFILE_URN=urn:li:person:L5yErU8yLK
APPROVAL_MODE=AUTO_POST
```

---

## Hata Çözmesi

### `503 Service Unavailable`
LinkedIn API credentials'ları kontrol edin. `.env` dosyasını kontrol ettiğinizden emin olun.

### `400 Bad Request`
Request body'sini kontrol edin. Gerekli alanları eksik bırakmış olabilirsiniz.

### Connection Refused
API sunucusunun çalıştığından emin olun:
```bash
curl http://127.0.0.1:8890/api/health
```

---

## İletişim ve Destek

Sorunlar veya sorularınız varsa lütfen GitHub issues açınız.
