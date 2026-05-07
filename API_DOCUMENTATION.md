# LinkedIn REST API Documentation

LinkedIn post paylaşma işlemlerini HTTP API çağrıları ile yapabilirsiniz. API'yi çalıştırmak için aşağıdaki komutu kullanın:

```bash
python main.py api --port 8888
```

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
curl http://127.0.0.1:8888/api/health
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
curl -X POST http://127.0.0.1:8888/api/linkedin/post \
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
  "message": "Post shared successfully on LinkedIn"
}
```

**Hata Yanıtları:**
- `400` - Content field boş veya eksik
- `503` - LinkedIn API kullanılamıyor
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
curl -X POST http://127.0.0.1:8888/api/linkedin/comment \
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
curl -X POST http://127.0.0.1:8888/api/linkedin/like \
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
curl -X POST http://127.0.0.1:8888/api/llm/generate-linkedin-post \
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

## Kullanım Örnekleri

### Python ile

```python
import requests
import json

API_URL = "http://127.0.0.1:8888"

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
const API_URL = "http://127.0.0.1:8888";

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

### Database Backend

The API and pipeline use the same CRM storage layer.

For local SQLite:

```env
DB_BACKEND=sqlite
DB_PATH=leads.db
```

For Firebase Firestore:

```env
DB_BACKEND=firebase
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CLIENT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
FIREBASE_PRIVATE_KEY="<escaped-service-account-private-key>"
FIREBASE_PRIVATE_KEY_ID=your-private-key-id
FIREBASE_CLIENT_ID=your-client-id
```

Firestore collections:

- `leads`: processed lead records
- `review_queue`: pending, approved, and rejected actions

Optional collection names:

```env
FIREBASE_LEADS_COLLECTION=leads
FIREBASE_REVIEW_QUEUE_COLLECTION=review_queue
```

API sunucusunu başlarken port ve host belirtebilirsiniz:

```bash
# Özel port ve host ile başlat
python main.py api --host 0.0.0.0 --port 8080

# Varsayılan (127.0.0.1:8888)
python main.py api
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
curl http://127.0.0.1:8888/api/health
```

---

## İletişim ve Destek

Sorunlar veya sorularınız varsa lütfen GitHub issues açınız.
